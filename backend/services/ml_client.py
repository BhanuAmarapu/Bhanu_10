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

    def process_video(self, video_path):
        """Call FastAPI unified video processing endpoint (transcription + SBERT + DINOv2 in parallel)."""
        try:
            filename = os.path.basename(video_path)
            with open(video_path, 'rb') as f:
                files = {'file': (filename, f)}
                resp = requests.post(f"{self.url}/process_video", files=files, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"ML service video processing failed: {e}")

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
            clean_records = []
            for r in stored_records:
                if r is None:
                    continue
                try:
                    clean_records.append({
                        "id": r["id"],
                        "original_filename": r["original_filename"],
                        "transcript": r["transcript"] if "transcript" in r else None,
                        "embedding": r["embedding"] if "embedding" in r else None,
                        "dino_embedding": r["dino_embedding"] if "dino_embedding" in r else None,
                        "language": r["language"] if "language" in r else "en",
                        "duration": float(r["duration"]) if "duration" in r and r["duration"] is not None else 0.0,
                        "s3_object_key": r["s3_object_key"] if "s3_object_key" in r else ""
                    })
                except Exception:
                    clean_records.append(dict(r))

            payload = {
                "new_embedding": list(new_embedding) if new_embedding is not None else [],
                "stored_records": clean_records,
                "exclude_id": exclude_id,
                "table_name": table_name,
                "new_transcript": str(new_transcript) if new_transcript else None,
                "new_dino_embedding": list(new_dino_embedding) if new_dino_embedding is not None else None
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

    def read_file_content(self, file_path, filename=None):
        """Call FastAPI text/image description extractor."""
        try:
            if not filename:
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

    def compare_two_texts(self, text1, text2):
        """Call FastAPI text comparison endpoint."""
        try:
            resp = requests.post(f"{self.url}/compare_two_texts", json={"text1": text1, "text2": text2}, timeout=30)
            resp.raise_for_status()
            return resp.json()["similarity"]
        except Exception as e:
            print(f"[MLClient] Compare texts error: {e}")
            return 0.0

    def is_text_file(self, filename):
        """True for non-image, non-audio, non-video files that can be processed as content."""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        media_exts = {'mp3', 'wav', 'aac', 'flac', 'm4a', 'mpeg', 'mpg', 'ogg', 'opus', 'amr', 'wma', 'mpga', 'mp2',
                      'mp4', 'avi', 'mov', 'mkv', 'webm', 'wmv', 'flv'}
        image_exts = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tiff', 'svg', 'ico', 'avif', 'heic'}
        if ext in media_exts or ext in image_exts:
            return False
        return True

    def is_image_file(self, filename):
        """Check if file is an image file based on extension."""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in {'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tiff', 'svg', 'ico', 'avif', 'heic'}

ml_client = MLClient()

