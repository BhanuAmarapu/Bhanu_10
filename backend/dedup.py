import os
from config import Config
from utils import get_file_hash, encrypt_file, log_action, upload_to_s3
from mongo_wrapper import get_mongo_connection

class Deduplicator:
    def __init__(self):
        pass
        self.stored_dir = Config.UPLOAD_STORED

    def process_file(self, temp_path, file_name, user_id, content_text=None, similarity_score=None, similarity_match=None, dino_embedding=None):
        """
        Process an uploaded file: Hash -> Check Dedup -> Encrypt -> Store
        Returns (is_duplicate, file_id)
        """
        file_hash = get_file_hash(temp_path)
        file_size = os.path.getsize(temp_path)
        file_type = file_name.split('.')[-1] if '.' in file_name else 'unknown'

        # Check for deduplication
        conn = get_mongo_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, stored_path FROM files WHERE file_hash = ?", (file_hash,))
        existing_file = cursor.fetchone()

        if existing_file:
            # Duplicate found
            file_id = existing_file['id'] if isinstance(existing_file, dict) or hasattr(existing_file, '__getitem__') else existing_file[0]
            log_action("Deduplication", f"Duplicate detected for {file_name} (Hash: {file_hash}). Referencing existing file ID: {file_id}")
            
            # Record the upload for this user with content_text
            cursor.execute("INSERT INTO uploads (user_id, file_id, content_text) VALUES (?, ?, ?)", (user_id, file_id, content_text))
            conn.commit()
            conn.close()
            log_action("Deduplication Success", f"Duplicate detected for {file_name} (Hash: {file_hash}). Referencing existing file ID: {file_id}")
            return True, file_id
        else:
            # Unique file
            # Limit filename length to prevent Windows path issues (max 260 chars)
            file_extension = os.path.splitext(file_name)[1]  # e.g., '.pdf'
            base_name = os.path.splitext(file_name)[0]  # filename without extension
            
            # Limit base name to 50 characters to keep total path under Windows limit
            max_base_length = 50
            if len(base_name) > max_base_length:
                base_name = base_name[:max_base_length]
            
            stored_file_name = f"{file_hash}_{base_name}{file_extension}"
            stored_path = os.path.join(self.stored_dir, stored_file_name)
            
            # Ensure stored directory exists
            if not os.path.exists(self.stored_dir):
                os.makedirs(self.stored_dir, exist_ok=True)
            
            # Encrypt and move to stored_files (local temp before S3)
            encrypt_file(temp_path, stored_path)
            
            db_stored_path = stored_path
            
            # Cloud Sync (Synchronous Upload)
            if Config.USE_S3:
                try:
                    if upload_to_s3(stored_path, stored_file_name):
                        log_action("Cloud Sync", f"File {file_name} stored directly in S3 bucket.")
                        db_stored_path = f"s3://{Config.S3_BUCKET_NAME}/{stored_file_name}"
                        # Remove local encrypted file to save space immediately
                        if os.path.exists(stored_path):
                            os.remove(stored_path)
                    else:
                        log_action("Cloud Warning", f"S3 sync failed for {file_name}, using local storage fallback.")
                except Exception as e:
                    log_action("Cloud Error", f"S3 Error during upload of {file_name}: {str(e)}")
            else:
                log_action("Local Storage", f"S3 disabled, storing {file_name} locally.")

            # Insert into database with final path and content metadata
            cursor.execute("""
                INSERT INTO files (file_name, file_hash, file_size, file_type, stored_path, content_text, similarity_score, similarity_match, dino_embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (file_name, file_hash, file_size, file_type, db_stored_path, content_text, similarity_score, similarity_match, dino_embedding))
            
            file_id = cursor.lastrowid
            
            cursor.execute("INSERT INTO uploads (user_id, file_id, content_text) VALUES (?, ?, ?)", (user_id, file_id, content_text))
            
            conn.commit()
            conn.close()
            
            log_action("Upload", f"New file stored: {file_name} (ID: {file_id})")
            return False, file_id


    def proof_of_ownership(self, user_id, file_hash):
        """Simulate Proof of Ownership (PoW)."""
        log_action("PoW Verified", f"User {user_id} verified ownership for file hash: {file_hash}")
        return True
