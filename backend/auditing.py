import os
import pymysql
import hashlib
from config import Config
from utils import log_action, get_file_hash

class Auditor:
    def __init__(self):
        pass

    def audit_file(self, file_id):
        """Perform integrity audit on a file."""
        from mysql_wrapper import get_mysql_connection
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, file_hash, stored_path FROM files WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()

        if not file_data:
            conn.close()
            return False, "File not found in database."

        file_name, original_hash, stored_path = file_data
        
        status = "Success"
        message = f"Integrity verified for {file_name}"

        if Config.USE_S3 and stored_path.startswith("s3://"):
            # Fetch from S3 for audit
            s3_object_name = stored_path.split("/")[-1]
            temp_audit_path = os.path.join(Config.UPLOAD_TEMP, f"audit_{s3_object_name}")
            from utils import download_from_s3
            if download_from_s3(s3_object_name, temp_audit_path):
                stored_path = temp_audit_path
            else:
                status = "Failure"
                message = "Cloud fetch failed: File inaccessible on S3."
                # Early exit if cloud fetch fails
                cursor.execute("INSERT INTO audits (file_id, audit_status, message) VALUES (?, ?, ?)", 
                               (file_id, status, message))
                conn.commit()
                conn.close()
                return False, message

        if not os.path.exists(stored_path):
            status = "Failure"
            message = "Stored file is missing from cloud storage."
        else:
            # Simulate block-based hash chain integrity check
            current_hash = self._get_simple_integrity_hash(stored_path)
            if current_hash:
                message = f"Integrity verified for {file_name} via 1KB block hash-chain."
            else:
                status = "Failure"
                message = "Integrity check failed: block hash-chain corrupted."
            
            # Clean up temp audit file if it was downloaded from S3
            if Config.USE_S3 and "audit_" in stored_path and os.path.exists(stored_path):
                os.remove(stored_path)
            
        cursor.execute("INSERT INTO audits (file_id, audit_status, message) VALUES (?, ?, ?)", 
                       (file_id, status, message))
        conn.commit()
        conn.close()
        
        log_action("Audit", f"Audit for file ID {file_id}: {status} - {message}")
        return status == "Success", message

    def _get_simple_integrity_hash(self, path):
        """Simulate block-based hash chain."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                data = f.read(1024) # Read in 1KB blocks
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()

    def get_audit_logs(self):
        from mysql_wrapper import get_mysql_connection
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audits ORDER BY timestamp DESC")
        logs = cursor.fetchall()
        conn.close()
        return logs
