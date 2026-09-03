import os
import sys

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from config import Config
from mongo_wrapper import get_mongo_db, get_mongo_connection

try:
    print(f"Connecting to MongoDB Atlas at database: {Config.MONGO_DB}...")
    db = get_mongo_db()
    collections = db.list_collection_names()
    print("Collections in MongoDB:", collections)

    conn = get_mongo_connection()
    try:
        users_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        print(f"Users in MongoDB: {users_count}")

        if users_count == 0:
            print("\nNo users found. Creating default admin user...")
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                         ('admin', 'admin123', 'admin'))
            conn.commit()
            print("Default admin user created!")
            print("  Username: admin")
            print("  Password: admin123")
            print("  Role: admin")
    except Exception as e:
        print(f"Error checking users collection: {e}")
        print("Tip: Run 'python init_db.py' to initialize collections.")

    # Show document counts across collections
    print("\nCollection Statistics:")
    for col in collections:
        if col != 'counters':
            print(f"  - {col}: {db[col].count_documents({})} documents")

    conn.close()
    print("\nMongoDB Atlas connection verified successfully!")
except Exception as e:
    print(f"Connection failed: {e}")
