import os
import torch
import subprocess
from transformers import pipeline
from utils import log_action

# Dynamically add static FFmpeg to the runtime PATH for Windows compatibility
try:
    from static_ffmpeg import add_paths
    add_paths()
    print("[WhisperService] Added FFmpeg to system PATH using static-ffmpeg.")
except Exception as e:
    print(f"[WhisperService] Warning: Could not configure static-ffmpeg paths: {e}")

def get_audio_duration(audio_path):
    """Probes the audio file using ffprobe to get play duration in seconds."""
    try:
        # Run ffprobe
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            audio_path
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return float(output.decode().strip())
    except Exception as e:
        print(f"[WhisperService] Error getting duration with ffprobe: {e}")
        # Fallback duration estimation based on wave header
        try:
            import wave
            with wave.open(audio_path, 'r') as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                return frames / float(rate)
        except Exception:
            return 0.0

class WhisperService:
    def __init__(self):
        self.pipe = None

    def load_model(self):
        """Loads Hugging Face Whisper model only once and caches it."""
        if self.pipe is None:
            # CPU threading optimization to prevent core scheduling contention
            if not torch.cuda.is_available() and torch.get_num_threads() > 4:
                torch.set_num_threads(4)
                print("[WhisperService] Limited PyTorch CPU threads to 4 to eliminate core contention.")
                
            device = 0 if torch.cuda.is_available() else -1
            device_str = f"cuda:{device}" if device >= 0 else "cpu"
            model_name = os.getenv("WHISPER_MODEL", "openai/whisper-tiny")
            print(f"[WhisperService] Loading Hugging Face Whisper model '{model_name}' on {device_str}...")
            
            try:
                # Try loading locally first for speed and offline robustness by setting HF_HUB_OFFLINE=1
                print(f"[WhisperService] Attempting local-first load for model '{model_name}'...")
                os.environ["HF_HUB_OFFLINE"] = "1"
                self.pipe = pipeline(
                    "automatic-speech-recognition",
                    model=model_name,
                    chunk_length_s=30,
                    device=device
                )
            except Exception as local_err:
                print(f"[WhisperService] Local Whisper model load failed: {local_err}. Trying online loading...")
                os.environ["HF_HUB_OFFLINE"] = "0"
                try:
                    self.pipe = pipeline(
                        "automatic-speech-recognition",
                        model=model_name,
                        chunk_length_s=30,
                        device=device
                    )
                except Exception as e:
                    print(f"[WhisperService] Online Whisper loading failed: {e}")
                    raise e
            finally:
                # Clean up/reset HF_HUB_OFFLINE
                os.environ.pop("HF_HUB_OFFLINE", None)
            print(f"[WhisperService] Whisper model '{model_name}' pipeline loaded successfully.")
        return self.pipe
 
    def transcribe(self, audio_path):
        """
        Transcribes the speech in an audio file using Hugging Face pipeline.
        Returns a dict: {"transcript": str, "language": str, "duration": float}
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found at: {audio_path}")
            
        log_action("Whisper Processing Started", f"Transcribing file: {os.path.basename(audio_path)}")
        
        # Ensure model pipeline is loaded
        self.load_model()
        
        # Get duration using ffprobe
        duration = get_audio_duration(audio_path)
        
        # Run ASR pipeline optimized for CPU speed (greedy decoding + caching + batching)
        try:
            result = self.pipe(
                audio_path, 
                batch_size=8,
                generate_kwargs={
                    "task": "transcribe",
                    "num_beams": 1,
                    "use_cache": True
                }
            )
        except Exception as e:
            raise RuntimeError(f"Whisper transcription error: {e}")
            
        transcript = result.get("text", "").strip()
        # Default to English (en) or extract from model output
        language = "en"
        
        log_action("Transcript Generated", f"File: {os.path.basename(audio_path)} | Lang: {language} | Dur: {duration:.2f}s")
        
        return {
            "transcript": transcript,
            "language": language,
            "duration": duration
        }

whisper_service = WhisperService()
