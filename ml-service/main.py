import os
import tempfile
import json
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
    print("[ML-SERVICE] static_ffmpeg paths initialized.")
except Exception as e:
    print(f"[ML-SERVICE] Warning initializing static_ffmpeg: {e}")

from config import Config
from ml_model import MLModel
from whisper_service import whisper_service
from sentencebert_service import sentencebert_service
from similarity_service import similarity_service
from content_moderator import ContentModerator
from content_similarity import ContentSimilarityDetector, detect_similar_content

app = FastAPI(title="CloudDedup Pro ML Service")

# Initialize models
ml_model = MLModel()
moderator = None
similarity_detector = None

@app.on_event("startup")
def startup_event():
    global moderator, similarity_detector
    print("[STARTUP] Pre-warming ML models and caches...")
    
    # 1. Train Decision Tree model if not already trained
    if not os.path.exists(Config.ML_MODEL_PATH):
        print("[STARTUP] Training new Decision Tree ML model...")
        try:
            ml_model.train(Config.ML_DATASET)
            print("[STARTUP] ML Model trained successfully.")
        except Exception as e:
            print(f"[STARTUP] ML Model training failed: {e}")
    else:
        print("[STARTUP] ML Model found, skipping training.")
        
    # 2. Pre-warm SBERT, DINOv2, Whisper
    moderator = ContentModerator()
    similarity_detector = ContentSimilarityDetector()
    whisper_service.load_model()
    sentencebert_service.load_model()
    print("[STARTUP] All models loaded successfully.")

# Helper to save uploaded file to temp file
def save_temp_file(uploaded_file: UploadFile) -> str:
    fname = uploaded_file.filename or "temp_file"
    suffix = os.path.splitext(fname)[1] or ".tmp"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "wb") as f:
        f.write(uploaded_file.file.read())
    return path

class PredictRequest(BaseModel):
    file_size: int
    extension_code: int
    frequency: int

@app.post("/predict_duplicate")
def predict_duplicate(req: PredictRequest):
    try:
        prediction = ml_model.predict({
            'file_size': req.file_size,
            'extension_code': req.extension_code,
            'frequency': req.frequency
        })
        return {"prediction": prediction}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/moderate_file")
def moderate_file_endpoint(file: UploadFile = File(...), filename: str = Form(...)):
    temp_path = save_temp_file(file)
    try:
        res = moderator.moderate_file(temp_path, filename)
        return {
            "is_safe": res.is_safe,
            "violation_type": res.violation_type,
            "violation_details": res.violation_details,
            "confidence_score": res.confidence_score,
            "flagged_keywords": res.flagged_keywords
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/detect_similar_content")
def detect_similar_content_endpoint(
    file: UploadFile = File(...),
    filename: str = Form(...),
    file_hash: str = Form(...),
    existing_files: str = Form(...),
    threshold: float = Form(0.60)
):
    temp_path = save_temp_file(file)
    try:
        files_list = json.loads(existing_files)
        res = detect_similar_content(temp_path, filename, file_hash, files_list, threshold)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

from concurrent.futures import ThreadPoolExecutor

def extract_audio_snippet_fast(media_path: str, duration_sec: int = 15) -> Optional[str]:
    """Extracts a short 16kHz mono audio snippet fast for Whisper."""
    try:
        import subprocess
        import uuid
        ml_data_dir = os.path.join(Config.BASE_DIR, 'ml_data')
        os.makedirs(ml_data_dir, exist_ok=True)
        snippet_filename = f"snippet_{uuid.uuid4().hex}.wav"
        temp_audio_snippet = os.path.join(ml_data_dir, snippet_filename)
        
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        # Fast input-seeking and downsampling to 16kHz 16-bit mono
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", "0",
            "-t", str(duration_sec),
            "-i", media_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            "-threads", "4",
            temp_audio_snippet
        ]
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode == 0 and os.path.exists(temp_audio_snippet) and os.path.getsize(temp_audio_snippet) > 100:
            return temp_audio_snippet
        return None
    except Exception as e:
        print(f"[ML-SERVICE] Audio snippet extraction error: {e}")
        return None

def extract_video_frame(video_path: str) -> Optional[str]:
    """Extracts a representative video frame using fast direct seek."""
    try:
        import subprocess
        fd, temp_img_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        # Fast input seek at 1.5s
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", "1.5",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            "-threads", "4",
            temp_img_path
        ]
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 0 or not os.path.exists(temp_img_path) or os.path.getsize(temp_img_path) == 0:
            # Fallback to start of video if short
            cmd = [
                ffmpeg_bin, "-y",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                "-threads", "4",
                temp_img_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
        if os.path.exists(temp_img_path) and os.path.getsize(temp_img_path) > 0:
            return temp_img_path
        return None
    except Exception as e:
        print(f"[VideoFrameExtraction] Error: {e}")
        return None


@app.post("/transcribe")
def transcribe_endpoint(file: UploadFile = File(...)):
    temp_path = save_temp_file(file)
    temp_snippet = None
    try:
        from whisper_service import get_audio_duration
        full_duration = get_audio_duration(temp_path)
        temp_snippet = extract_audio_snippet_fast(temp_path, duration_sec=min(Config.AUDIO_SNIPPET_DURATION, 20))
        transcribe_path = temp_snippet if temp_snippet else temp_path
        res = whisper_service.transcribe(transcribe_path, duration=full_duration)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_snippet and os.path.exists(temp_snippet):
            try: os.remove(temp_snippet)
            except: pass
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass


@app.post("/process_video")
def process_video_endpoint(file: UploadFile = File(...)):
    """
    Unified high-performance video processing endpoint.
    Accepts video once, extracts audio and frame in parallel,
    runs Whisper, SBERT, and DINOv2, and returns all embeddings in one call.
    """
    temp_path = save_temp_file(file)
    try:
        # Extract audio snippet and video frame concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_audio = executor.submit(extract_audio_snippet_fast, temp_path, min(Config.AUDIO_SNIPPET_DURATION, 15))
            future_frame = executor.submit(extract_video_frame, temp_path)
            
            audio_snippet_path = future_audio.result()
            frame_img_path = future_frame.result()

        transcript = ""
        language = "en"
        duration = 0.0
        embedding = []
        dino_embedding = []

        # 1. Transcribe audio and generate SBERT embedding
        if audio_snippet_path:
            try:
                res = whisper_service.transcribe(audio_snippet_path)
                transcript = res.get("transcript", "").strip()
                language = res.get("language", "en")
                duration = res.get("duration", 0.0)
                if transcript:
                    embedding = sentencebert_service.generate_embedding(transcript)
            except Exception as w_err:
                print(f"[ML-SERVICE] Video audio transcription warning: {w_err}")
            finally:
                if os.path.exists(audio_snippet_path):
                    try: os.remove(audio_snippet_path)
                    except: pass

        # 2. Compute DINOv2 visual embedding for frame
        if frame_img_path:
            try:
                tensor = similarity_detector.compute_dinov2_embedding(frame_img_path)
                if tensor is not None:
                    emb = tensor.tolist()
                    if emb and isinstance(emb[0], list):
                        emb = emb[0]
                    dino_embedding = emb
            except Exception as d_err:
                print(f"[ML-SERVICE] Video frame DINOv2 warning: {d_err}")
            finally:
                if os.path.exists(frame_img_path):
                    try: os.remove(frame_img_path)
                    except: pass

        return {
            "transcript": transcript or "No speech detected in video track.",
            "language": language,
            "duration": duration,
            "embedding": embedding,
            "dino_embedding": dino_embedding
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass

class EmbeddingRequest(BaseModel):
    text: str

@app.post("/generate_embedding")
def generate_embedding_endpoint(req: EmbeddingRequest):
    try:
        emb = sentencebert_service.generate_embedding(req.text)
        return {"embedding": emb}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SimilarityRequest(BaseModel):
    new_embedding: List[float]
    stored_records: List[dict]
    exclude_id: Optional[int] = None
    table_name: str = "audio_records"
    new_transcript: Optional[str] = None
    new_dino_embedding: Optional[List[float]] = None

@app.post("/find_highest_similarity")
def find_highest_similarity_endpoint(req: SimilarityRequest):
    try:
        res = similarity_service.find_highest_similarity(
            new_embedding=req.new_embedding,
            stored_records=req.stored_records,
            exclude_id=req.exclude_id,
            table_name=req.table_name,
            new_transcript=req.new_transcript,
            new_dino_embedding=req.new_dino_embedding
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compute_dinov2_embedding")
def compute_dinov2_embedding_endpoint(file: UploadFile = File(...)):
    temp_path = save_temp_file(file)
    try:
        tensor = similarity_detector.compute_dinov2_embedding(temp_path)
        if tensor is not None:
            emb = tensor.tolist()
            if emb and isinstance(emb[0], list):
                emb = emb[0]
            return {"embedding": emb}
        return {"embedding": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/add_dino_cache")
def add_dino_cache_endpoint(file: UploadFile = File(...), file_id: int = Form(...)):
    temp_path = save_temp_file(file)
    try:
        similarity_detector.add_dino_cache(file_id, temp_path)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/extract_text")
def extract_text_endpoint(file: UploadFile = File(...), filename: str = Form(...)):
    temp_path = save_temp_file(file)
    try:
        text = similarity_detector.read_file_content(temp_path, filename=filename)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/process_video_visual")
def process_video_visual_endpoint(file: UploadFile = File(...)):
    temp_path = save_temp_file(file)
    try:
        temp_frame_path = extract_video_frame(temp_path)
        if temp_frame_path:
            try:
                tensor = similarity_detector.compute_dinov2_embedding(temp_frame_path)
                if tensor is not None:
                    emb = tensor.tolist()
                    if emb and isinstance(emb[0], list):
                        emb = emb[0]
                    return {"dino_embedding": emb}
            finally:
                if os.path.exists(temp_frame_path):
                    try: os.remove(temp_frame_path)
                    except: pass
        return {"dino_embedding": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

class CompareTextsRequest(BaseModel):
    text1: str
    text2: str

@app.post("/compare_two_texts")
def compare_two_texts_endpoint(req: CompareTextsRequest):
    try:
        score = similarity_detector.compute_text_similarity(req.text1, req.text2)
        return {"similarity": score}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

