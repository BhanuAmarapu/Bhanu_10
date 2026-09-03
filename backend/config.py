import os
from pathlib import Path

# Try to load environment variables from .env file (optional)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    print("Note: python-dotenv not installed. Using environment variables or defaults.")
    print("      Install with: pip install python-dotenv")

class Config:
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'secure-data-dedup-key')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', 5000))
    
    # ML Service Address
    ML_SERVICE_URL = os.getenv('ML_SERVICE_URL', 'http://localhost:8000')
    
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Database - MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://bhanu89190654_db_user:P6s4X0ODr5bhcwlr@cluster0.clqmce7.mongodb.net/?appName=Cluster0')
    MONGO_DB = os.getenv('MONGO_DB', 'cloud_dedup')
    
    # Upload folders
    UPLOAD_TEMP = os.path.join(BASE_DIR, 'uploads', 'temp_files')
    UPLOAD_STORED = os.path.join(BASE_DIR, 'uploads', 'stored_files')
    
    # ML Data
    ML_DATASET = os.path.join(BASE_DIR, 'ml_data', 'metadata_dataset.csv')
    ML_MODEL_PATH = os.path.join(BASE_DIR, 'ml_data', 'model.pkl')
    
    # Encryption
    AES_KEY = os.getenv('AES_KEY', 'Sixteen byte key').encode()
    
    # Audit Logs
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    
    # OpenAI API Key for GPT-4 Vision
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    
    # Cloud Storage (AWS S3)
    USE_S3 = os.getenv('USE_S3', 'True').lower() == 'true'
    AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY', '')
    AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY', '')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', '')
    
    # Auto-disable S3 if credentials are missing but it was enabled
    if USE_S3 and (not AWS_ACCESS_KEY or not AWS_SECRET_KEY):
        print("WARNING: USE_S3 is True but AWS credentials are missing. S3 will be disabled.")
        USE_S3 = False
    
    # Suspicious Upload Detector Configuration
    ENABLE_SUSPICIOUS_DETECTOR = os.getenv('ENABLE_SUSPICIOUS_DETECTOR', 'True').lower() == 'true'  # Enabled for security monitoring

    # Audio Analysis Snippet Duration (seconds)
    AUDIO_SNIPPET_DURATION = int(os.getenv('AUDIO_SNIPPET_DURATION', 30))

    
    # Rapid upload detection
    RAPID_UPLOAD_THRESHOLD = int(os.getenv('RAPID_UPLOAD_THRESHOLD', 10))  # uploads
    RAPID_UPLOAD_WINDOW_MINUTES = int(os.getenv('RAPID_UPLOAD_WINDOW_MINUTES', 1))  # minutes
    
    # Duplicate attempt detection
    DUPLICATE_ATTEMPT_THRESHOLD = int(os.getenv('DUPLICATE_ATTEMPT_THRESHOLD', 5))  # attempts
    DUPLICATE_ATTEMPT_WINDOW_HOURS = int(os.getenv('DUPLICATE_ATTEMPT_WINDOW_HOURS', 1))  # hours
    
    # PoW failure detection
    POW_FAILURE_THRESHOLD = int(os.getenv('POW_FAILURE_THRESHOLD', 3))  # failures
    POW_FAILURE_WINDOW_HOURS = int(os.getenv('POW_FAILURE_WINDOW_HOURS', 1))  # hours

# Ensure directories exist
for folder in [Config.UPLOAD_TEMP, Config.UPLOAD_STORED, Config.LOGS_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)
