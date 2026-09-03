import os
import sys
import pymongo

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
from config import Config
from mongo_wrapper import get_mongo_db

def init_audio_db():
    print("Initializing Audio & Video Database Collections in MongoDB Atlas...")
    db = get_mongo_db()
    
    existing = db.list_collection_names()
    if 'audio_records' not in existing:
        db.create_collection('audio_records')
        print("Created collection: audio_records")
        
    if 'video_records' not in existing:
        db.create_collection('video_records')
        print("Created collection: video_records")
        
    db.audio_records.create_index([("uuid_filename", pymongo.ASCENDING)], unique=True)
    db.audio_records.create_index([("user_id", pymongo.ASCENDING)])
    db.audio_records.create_index([("upload_timestamp", pymongo.DESCENDING)])
    
    db.video_records.create_index([("uuid_filename", pymongo.ASCENDING)], unique=True)
    db.video_records.create_index([("user_id", pymongo.ASCENDING)])
    db.video_records.create_index([("upload_timestamp", pymongo.DESCENDING)])
    
    print("MongoDB Atlas setup for audio and video records complete.")

if __name__ == "__main__":
    init_audio_db()
