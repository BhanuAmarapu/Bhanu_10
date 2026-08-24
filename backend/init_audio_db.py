import pymysql
import os
import sys

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
from config import Config

def init_audio_db():
    print("Initializing Audio Database Table...")
    connection = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    table_sql = """
    CREATE TABLE IF NOT EXISTS audio_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        original_filename VARCHAR(500) NOT NULL,
        uuid_filename VARCHAR(255) UNIQUE NOT NULL,
        transcript LONGTEXT,
        embedding LONGTEXT,
        language VARCHAR(50),
        duration FLOAT,
        s3_object_key VARCHAR(1000) NOT NULL,
        similarity_score FLOAT DEFAULT NULL,
        status VARCHAR(50) DEFAULT 'completed',
        matched_file VARCHAR(500) DEFAULT NULL,
        matched_transcript LONGTEXT DEFAULT NULL,
        file_hash VARCHAR(64) DEFAULT NULL,
        upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """
    index_sql_1 = "CREATE INDEX idx_audio_user ON audio_records(user_id);"
    index_sql_2 = "CREATE INDEX idx_audio_timestamp ON audio_records(upload_timestamp);"
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(table_sql)
            print("Table 'audio_records' verified/created.")
            
            try:
                cursor.execute(index_sql_1)
                print("Index idx_audio_user created.")
            except Exception as e:
                print(f"Index idx_audio_user note: {e}")
                
            try:
                cursor.execute(index_sql_2)
                print("Index idx_audio_timestamp created.")
            except Exception as e:
                print(f"Index idx_audio_timestamp note: {e}")
                
        connection.commit()
        print("Database migrations for audio pipeline completed.")
    finally:
        connection.close()

if __name__ == "__main__":
    init_audio_db()
