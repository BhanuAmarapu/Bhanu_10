import os
import tempfile
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional

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
    suffix = os.path.splitext(uploaded_file.filename)[1]
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

@app.post("/transcribe")
def transcribe_endpoint(file: UploadFile = File(...)):
    temp_path = save_temp_file(file)
    try:
        # Extract audio snippet using FFmpeg for speed
        import subprocess
        import uuid
        snippet_filename = f"snippet_{uuid.uuid4().hex}.wav"
        temp_audio_snippet = os.path.join(Config.BASE_DIR, 'ml_data', snippet_filename)
        
        snippet_duration = str(Config.AUDIO_SNIPPET_DURATION)
        cmd = [
            "ffmpeg", "-y", 
            "-ss", "0", "-t", snippet_duration, 
            "-i", temp_path, 
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", 
            temp_audio_snippet
        ]
        
        print(f"[ML-SERVICE] Extracting {snippet_duration}s snippet: {' '.join(cmd)}")
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        transcribe_path = temp_audio_snippet if (process.returncode == 0 and os.path.exists(temp_audio_snippet) and os.path.getsize(temp_audio_snippet) > 1000) else temp_path
        
        res = whisper_service.transcribe(transcribe_path)
        
        # Clean up snippet file
        if os.path.exists(temp_audio_snippet):
            try: os.remove(temp_audio_snippet)
            except: pass
            
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

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
        text = similarity_detector.read_file_content(temp_path)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def extract_video_frame(video_path):
    """Extracts the middle frame of a video using FFmpeg/ffprobe and saves it as a temp JPEG."""
    try:
        import subprocess
        # 1. Get video duration using ffprobe
        duration = 0.0
        try:
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_path
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            duration = float(output.decode().strip())
        except Exception as e:
            print(f"[VideoFrameExtraction] ffprobe duration check failed: {e}")
            
        # 2. Determine seek time (middle of the video, fallback to 2 seconds or 0 if very short)
        seek_time = duration / 2.0 if duration > 0 else 2.0
        
        fd, temp_img_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        
        # 3. FFmpeg command to extract 1 frame at seek_time
        if duration > 0 and seek_time > duration:
            seek_time = duration / 2.0
            
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seek_time),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            temp_img_path
        ]
        
        print(f"[VideoFrameExtraction] Extracting frame at {seek_time}s using FFmpeg...")
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 0:
            print(f"[VideoFrameExtraction] FFmpeg ss-seek failed (code {process.returncode}). Retrying from start...")
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                temp_img_path
            ]
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
        if process.returncode == 0 and os.path.exists(temp_img_path) and os.path.getsize(temp_img_path) > 0:
            return temp_img_path
        return None
    except Exception as e:
        print(f"[VideoFrameExtraction] General error: {e}")
        return None

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
