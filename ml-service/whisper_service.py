import os
import shutil
import tempfile
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
    """Gets audio play duration in seconds with wave header parsing before ffprobe fallback."""
    try:
        import wave
        with wave.open(audio_path, 'r') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate > 0:
                return float(frames / float(rate))
    except Exception:
        pass

    try:
        ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
        cmd = [
            ffprobe_bin, 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            audio_path
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return float(output.decode().strip())
    except Exception:
        return 0.0

def convert_to_16k_wav(input_audio_path):
    """Converts any audio file to 16kHz mono 16-bit PCM WAV for Whisper."""
    try:
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        fd, temp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = [
            ffmpeg_bin, "-y",
            "-i", input_audio_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            temp_wav
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 100:
            return temp_wav
        if os.path.exists(temp_wav):
            try: os.remove(temp_wav)
            except: pass
        return None
    except Exception as e:
        print(f"[WhisperService] WAV conversion error: {e}")
        return None

class WhisperService:
    def __init__(self):
        self.pipe = None

    def load_model(self):
        """Loads Hugging Face Whisper model only once and caches it."""
        if self.pipe is None:
            if not torch.cuda.is_available() and torch.get_num_threads() > 4:
                torch.set_num_threads(4)
                print("[WhisperService] Limited PyTorch CPU threads to 4 to eliminate core contention.")
                
            device = 0 if torch.cuda.is_available() else -1
            device_str = f"cuda:{device}" if device >= 0 else "cpu"
            model_name = os.getenv("WHISPER_MODEL", "openai/whisper-tiny")
            print(f"[WhisperService] Loading Hugging Face Whisper model '{model_name}' on {device_str}...")
            
            try:
                print(f"[WhisperService] Attempting local-first load for model '{model_name}'...")
                os.environ["HF_HUB_OFFLINE"] = "1"
                self.pipe = pipeline(
                    "automatic-speech-recognition",
                    model=model_name,
                    device=device,
                    chunk_length_s=30,
                    stride_length_s=5,
                    return_timestamps=True
                )
            except Exception as local_err:
                print(f"[WhisperService] Local Whisper model load failed: {local_err}. Trying online loading...")
                os.environ["HF_HUB_OFFLINE"] = "0"
                try:
                    self.pipe = pipeline(
                        "automatic-speech-recognition",
                        model=model_name,
                        device=device,
                        chunk_length_s=30,
                        stride_length_s=5,
                        return_timestamps=True
                    )
                except Exception as e:
                    print(f"[WhisperService] Online Whisper loading failed: {e}")
                    raise e
            finally:
                os.environ.pop("HF_HUB_OFFLINE", None)
            print(f"[WhisperService] Whisper model '{model_name}' pipeline loaded successfully.")
        return self.pipe
 
    def transcribe(self, audio_path, duration=None):
        """
        Transcribes the speech in an audio file using Hugging Face pipeline.
        Returns a dict: {"transcript": str, "language": str, "duration": float}
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found at: {audio_path}")
            
        log_action("Whisper Processing Started", f"Transcribing file: {os.path.basename(audio_path)}")
        
        # Ensure model pipeline is loaded
        self.load_model()
        
        # Convert to 16kHz mono WAV for guaranteed Whisper compatibility
        clean_wav = convert_to_16k_wav(audio_path)
        eval_path = clean_wav if clean_wav else audio_path

        # Get duration if not provided
        if duration is None or duration <= 0:
            duration = get_audio_duration(eval_path)
        
        transcript = ""
        language = "en"
        try:
            with torch.inference_mode():
                result = self.pipe(
                    eval_path, 
                    return_timestamps=True,
                    generate_kwargs={
                        "task": "transcribe"
                    }
                )
                if isinstance(result, dict):
                    transcript = result.get("text", "").strip()
                elif isinstance(result, str):
                    transcript = result.strip()
        except Exception as e:
            print(f"[WhisperService] Transcription warning: {e}")
            transcript = "No clear speech detected in audio."
        finally:
            if clean_wav and os.path.exists(clean_wav):
                try: os.remove(clean_wav)
                except: pass
            
        if not transcript:
            transcript = "No clear speech detected in audio."
            
        log_action("Transcript Generated", f"File: {os.path.basename(audio_path)} | Lang: {language} | Dur: {duration:.2f}s")
        
        return {
            "transcript": transcript,
            "language": language,
            "duration": float(duration)
        }

whisper_service = WhisperService()


