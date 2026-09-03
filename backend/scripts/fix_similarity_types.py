import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mongo_wrapper import get_mongo_connection

def fix_types():
    conn = get_mongo_connection()
    db = conn.db
    for coll_name in ['files', 'audio_records', 'video_records']:
        coll = db[coll_name]
        for doc in coll.find():
            val = doc.get('similarity_score')
            if isinstance(val, str):
                try:
                    f_val = float(val)
                except Exception:
                    f_val = None
                coll.update_one({'_id': doc['_id']}, {'$set': {'similarity_score': f_val}})
                print(f"Fixed {coll_name} doc {doc.get('id')}: {val} -> {f_val}")
    print("Type fix complete.")

if __name__ == '__main__':
    fix_types()
