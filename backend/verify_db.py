import os
import sys

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from mysql_wrapper import get_mysql_connection
import pymysql

try:
    conn = get_mysql_connection()

    # Check tables
    cursor = conn.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print("Tables in MySQL:", [t[0] for t in tables])

    # Check users count
    try:
        users_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        print(f"Users in database: {users_count}")

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
        print(f"Error checking users table: {e}")
        print("Tip: Run 'python init_db.py' to create the tables.")

    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")
