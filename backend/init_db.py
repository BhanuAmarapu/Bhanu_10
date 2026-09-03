import os
import sys
import pymongo

# Ensure backend directory is in the path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from config import Config
from mongo_wrapper import get_mongo_db, get_next_sequence_value

def init_db():
    print(f"Connecting to MongoDB Atlas ({Config.MONGO_DB})...")
    db = get_mongo_db()
    
    # Collections to initialize
    collections = [
        'users',
        'files',
        'uploads',
        'audits',
        'logs',
        'suspicious_activities',
        'user_activity_stats',
        'moderation_logs',
        'audio_records',
        'video_records',
        'counters'
    ]
    
    existing_cols = db.list_collection_names()
    for col in collections:
        if col not in existing_cols:
            db.create_collection(col)
            print(f"Created collection: {col}")
        else:
            print(f"Collection already exists: {col}")

    # Set up indexes
    print("Setting up indexes...")
    db.users.create_index([("username", pymongo.ASCENDING)], unique=True)
    db.users.create_index([("id", pymongo.ASCENDING)], unique=True)
    
    db.files.create_index([("file_hash", pymongo.ASCENDING)], unique=True)
    db.files.create_index([("id", pymongo.ASCENDING)], unique=True)
    
    db.uploads.create_index([("user_id", pymongo.ASCENDING)])
    db.uploads.create_index([("file_id", pymongo.ASCENDING)])
    db.uploads.create_index([("timestamp", pymongo.DESCENDING)])
    
    db.audits.create_index([("file_id", pymongo.ASCENDING)])
    db.audits.create_index([("timestamp", pymongo.DESCENDING)])
    
    db.logs.create_index([("timestamp", pymongo.DESCENDING)])
    
    db.suspicious_activities.create_index([("user_id", pymongo.ASCENDING)])
    db.suspicious_activities.create_index([("timestamp", pymongo.DESCENDING)])
    db.suspicious_activities.create_index([("is_dismissed", pymongo.ASCENDING)])
    
    db.moderation_logs.create_index([("user_id", pymongo.ASCENDING)])
    db.moderation_logs.create_index([("timestamp", pymongo.DESCENDING)])
    db.moderation_logs.create_index([("reviewed", pymongo.ASCENDING)])
    
    db.audio_records.create_index([("uuid_filename", pymongo.ASCENDING)], unique=True)
    db.audio_records.create_index([("user_id", pymongo.ASCENDING)])
    db.audio_records.create_index([("upload_timestamp", pymongo.DESCENDING)])
    
    db.video_records.create_index([("uuid_filename", pymongo.ASCENDING)], unique=True)
    db.video_records.create_index([("user_id", pymongo.ASCENDING)])
    db.video_records.create_index([("upload_timestamp", pymongo.DESCENDING)])

    # Initialize default admin user if no users exist
    if db.users.count_documents({}) == 0:
        admin_id = get_next_sequence_value(db, 'users')
        db.users.insert_one({
            "id": admin_id,
            "username": "admin",
            "email": "admin@example.com",
            "password": "adminpassword",
            "role": "admin"
        })
        print(f"Default admin user created (admin / adminpassword) with ID {admin_id}")

    print(f"Database initialization complete on MongoDB Atlas: {Config.MONGO_DB}")

if __name__ == "__main__":
    init_db()
