import os
import requests
import json
try:
    from config import Config
except ImportError:
    from backend.config import Config

class ModerationResult:
    def __init__(self, is_safe, violation_type=None, violation_details=None, confidence_score=0.0, flagged_keywords=None):
        self.is_safe = is_safe
        self.violation_type = violation_type
        self.violation_details = violation_details
        self.confidence_score = confidence_score
        self.flagged_keywords = flagged_keywords or []

class DinoEmbeddingWrapper:
    def __init__(self, emb_list):
        self.emb_list = emb_list
    def tolist(self):
        return self.emb_list

class MLClient:
    def __init__(self):
        self.url = Config.ML_SERVICE_URL.rstrip('/')

    def predict_duplicate(self, file_metadata):
        """Call FastAPI ML service Decision Tree prediction."""
        try:
            resp = requests.post(f"{self.url}/predict_duplicate", json=file_metadata, timeout=10)
            resp.raise_for_status()
            return resp.json()["prediction"]
        except Exception as e:
            print(f"[MLClient] Predict error: {e}. Falling back to 'Unique'")
            return "Unique"

    def moderate_file(self, file_path, filename):
        """Call FastAPI ML service safety content moderation."""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                data = {'filename': filename}
                resp = requests.post(f"{self.url}/moderate_file", files=files, data=data, timeout=60)
            resp.raise_for_status()
            res_json = resp.json()
            return ModerationResult(
                is_safe=res_json["is_safe"],
                violation_type=res_json["violation_type"],
                violation_details=res_json["violation_details"],
                confidence_score=res_json["confidence_score"],
                flagged_keywords=res_json["flagged_keywords"]
            )
        except Exception as e:
            print(f"[MLClient] Moderation error: {e}")
            # If using strict guardrails, we fail closed on API/communication errors
            return ModerationResult(
                is_safe=False,
                violation_type="COMMUNICATION_ERROR",
                violation_details=f"Moderation request to ML service failed: {str(e)}",
                confidence_score=1.0
            )

    def detect_similar_content(self, file_path, filename, file_hash, existing_files, threshold=0.60):
        """Call FastAPI SBERT/DINOv2 similarity detector."""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                data = {
                    'filename': filename,
                    'file_hash': file_hash,
                    'threshold': threshold,
                    'existing_files': json.dumps(existing_files)
                }
                resp = requests.post(f"{self.url}/detect_similar_content", files=files, data=data, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[MLClient] Content similarity error: {e}")
            return []

    def transcribe(self, audio_path):
        """Call FastAPI speech transcription service (Whisper)."""
        try:
            filename = os.path.basename(audio_path)
            with open(audio_path, 'rb') as f:
                files = {'file': (filename, f)}
                resp = requests.post(f"{self.url}/transcribe", files=files, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"ML service audio transcription failed: {e}")

    def generate_embedding(self, text):
        """Call FastAPI SBERT embedding generation."""
        try:
            resp = requests.post(f"{self.url}/generate_embedding", json={"text": text}, timeout=30)
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as e:
            raise RuntimeError(f"ML service embedding generation failed: {e}")

    def find_highest_similarity(self, new_embedding, stored_records, exclude_id=None, table_name="audio_records", new_transcript=None, new_dino_embedding=None):
        """Call FastAPI similarity calculator."""
        try:
            payload = {
                "new_embedding": new_embedding,
                "stored_records": stored_records,
                "exclude_id": exclude_id,
                "table_name": table_name,
                "new_transcript": new_transcript,
                "new_dino_embedding": new_dino_embedding
            }
            resp = requests.post(f"{self.url}/find_highest_similarity", json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[MLClient] Similarity calculation error: {e}")
            return {"similarity": 0.0, "matched_record": None, "match_type": "transcript"}

    def compute_dinov2_embedding(self, file_path):
        """Call FastAPI DINOv2 visual embedding computation."""
        try:
            filename = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                resp = requests.post(f"{self.url}/compute_dinov2_embedding", files=files, timeout=60)
            resp.raise_for_status()
            emb_list = resp.json()["embedding"]
            if emb_list:
                return DinoEmbeddingWrapper(emb_list)
            return None
        except Exception as e:
            print(f"[MLClient] DINOv2 embedding error: {e}")
            return None

    def add_dino_cache(self, file_id, file_path):
        """Call FastAPI add DINO cache endpoint."""
        try:
            filename = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                data = {'file_id': file_id}
                resp = requests.post(f"{self.url}/add_dino_cache", files=files, data=data, timeout=30)
            resp.raise_for_status()
            return resp.json()["success"]
        except Exception as e:
            print(f"[MLClient] Add DINO cache error: {e}")
            return False

    def read_file_content(self, file_path):
        """Call FastAPI text/image description extractor."""
        try:
            filename = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                data = {'filename': filename}
                resp = requests.post(f"{self.url}/extract_text", files=files, data=data, timeout=60)
            resp.raise_for_status()
            return resp.json()["text"]
        except Exception as e:
            print(f"[MLClient] Extract text error: {e}")
            return None

    def is_text_file(self, filename):
        """Check if file is a text file based on extension (matches content_similarity.py)."""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in {
            'txt', 'md', 'py', 'js', 'java', 'cpp', 'c', 'h', 
            'html', 'css', 'json', 'xml', 'csv', 'log', 'sql', 'pdf'
        }

    def is_image_file(self, filename):
        """Check if file is an image file based on extension (matches content_similarity.py)."""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in {'png', 'jpg', 'jpeg', 'webp', 'gif'}

ml_client = MLClient()
