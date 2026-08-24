import hashlib
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from config import Config

def get_file_hash(file_path):
    """Generate SHA-256 hash for a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_string_hash(data):
    """Generate SHA-256 hash for a string."""
    return hashlib.sha256(data.encode()).hexdigest()

def encrypt_file(file_path, output_path, key=None):
    """Encrypt file using Fernet (AES)."""
    if key is None:
        # Generate a key from Config.AES_KEY for Fernet compatibility
        salt = b'salt_' # In production use random salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(Config.AES_KEY))
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    fernet = Fernet(key)
    with open(file_path, 'rb') as f:
        data = f.read()
    
    encrypted_data = fernet.encrypt(data)
    with open(output_path, 'wb') as f:
        f.write(encrypted_data)
    return key

def decrypt_file(file_path, output_path, key=None):
    """Decrypt file using Fernet (AES)."""
    if key is None:
        # Generate the same key used for encryption
        salt = b'salt_'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(Config.AES_KEY))
        
    fernet = Fernet(key)
    with open(file_path, 'rb') as f:
        encrypted_data = f.read()
    
    decrypted_data = fernet.decrypt(encrypted_data)
    with open(output_path, 'wb') as f:
        f.write(decrypted_data)

def log_action(action, details):
    """Append log entry to logs directory."""
    from mysql_wrapper import get_mysql_connection
    from datetime import datetime
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs (action, details) VALUES (?, ?)", (action, details))
    conn.commit()
    conn.close()
    
    log_file = os.path.join(Config.LOGS_DIR, 'system.log')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.now()}] {action}: {details}\n")

# S3 Client Lazy-Loader
_s3_client_instance = None

def get_s3_client():
    """Lazy-load and return the S3 client."""
    global _s3_client_instance
    if not Config.USE_S3:
        return None
        
    if _s3_client_instance is None:
        try:
            import boto3
            _s3_client_instance = boto3.client(
                's3',
                aws_access_key_id=Config.AWS_ACCESS_KEY,
                aws_secret_access_key=Config.AWS_SECRET_KEY,
                region_name=Config.AWS_REGION
            )
        except Exception as e:
            print(f"Failed to initialize S3 client: {e}")
            return None
    return _s3_client_instance

def upload_to_s3(file_path, object_name):
    """Upload a file to an S3 bucket."""
    s3 = get_s3_client()
    if not s3:
        return False
    try:
        s3.upload_file(file_path, Config.S3_BUCKET_NAME, object_name)
        return True
    except Exception as e:
        from botocore.exceptions import NoCredentialsError
        if isinstance(e, NoCredentialsError):
            print("AWS credentials not found.")
        else:
            print(f"S3 Upload Error: {e}")
        return False

def download_from_s3(object_name, local_path):
    """Download a file from an S3 bucket."""
    s3 = get_s3_client()
    if not s3:
        return False
    try:
        s3.download_file(Config.S3_BUCKET_NAME, object_name, local_path)
        return True
    except Exception as e:
        print(f"S3 Download Error: {e}")
        return False
