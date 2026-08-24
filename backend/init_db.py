import pymysql
import os
import sys

# Ensure backend directory is in the path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from config import Config

SCHEMA_PATH = os.path.join(backend_dir, '..', 'db', 'schema.sql')

def init_db():
    connection = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    with open(SCHEMA_PATH, 'r') as f:
        schema_sql = f.read()
        
    statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
    
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                try:
                    cursor.execute(statement)
                except pymysql.err.OperationalError as e:
                    if e.args[0] == 1061: # Duplicate key name
                        pass
                    else:
                        raise e
        connection.commit()
        print(f"Database initialized in MySQL at {Config.MYSQL_HOST}")
    finally:
        connection.close()

if __name__ == "__main__":
    init_db()
