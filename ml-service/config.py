import os

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # ML Data paths
    ML_DATASET = os.path.join(BASE_DIR, 'ml_data', 'metadata_dataset.csv')
    ML_MODEL_PATH = os.path.join(BASE_DIR, 'ml_data', 'model.pkl')
    
    # Persistent caches
    EMBEDDING_CACHE_FILE = os.path.join(BASE_DIR, 'ml_data', 'embedding_cache.pkl')
    DINO_CACHE_FILE = os.path.join(BASE_DIR, 'ml_data', 'dino_cache.pkl')
    
    # OpenAI key
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    
    # Media processing config
    AUDIO_SNIPPET_DURATION = int(os.getenv('AUDIO_SNIPPET_DURATION', 30))

# Ensure ml_data directory exists
os.makedirs(os.path.join(Config.BASE_DIR, 'ml_data'), exist_ok=True)
