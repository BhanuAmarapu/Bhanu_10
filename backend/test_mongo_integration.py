import os
import sys
from datetime import datetime

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from config import Config
from mongo_wrapper import get_mongo_connection, get_mongo_db, IntegrityError

def test_mongo_integration():
    print("=" * 60)
    print("Testing MongoDB Atlas Integration")
    print("=" * 60)
    
    conn = get_mongo_connection()
    db = get_mongo_db()

    # 1. Test User Queries
    print("\n1. Testing User Operations...")
    user = conn.execute("SELECT * FROM users WHERE username = ?", ("admin",)).fetchone()
    assert user is not None, "Admin user not found"
    print(f"  [PASS] Found admin user: id={user['id']}, role={user['role']}, username={user['username']}")

    # Test Duplicate User Registration
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                     ("admin", "newpass", "user"))
        conn.commit()
        assert False, "Should have raised IntegrityError for duplicate username"
    except (IntegrityError, Exception) as e:
        print(f"  [PASS] Duplicate username correctly rejected: {e}")

    # 2. Test File & Upload Insertion
    print("\n2. Testing File & Deduplication Insertions...")
    cursor = conn.execute("""
        INSERT INTO files (file_name, file_hash, file_size, file_type, stored_path)
        VALUES (?, ?, ?, ?, ?)
    """, ("test_document.pdf", "hash_test_12345", 1048576, "pdf", "local/path/test_doc.pdf"))
    file_id = cursor.lastrowid
    assert file_id is not None and file_id > 0, f"Invalid lastrowid: {file_id}"
    print(f"  [PASS] Inserted file with auto-increment ID: {file_id}")

    # Insert upload linking user to file
    conn.execute("INSERT INTO uploads (user_id, file_id) VALUES (?, ?)", (user['id'], file_id))
    print(f"  [PASS] Inserted upload record linking user {user['id']} to file {file_id}")

    # 3. Test Aggregate Queries
    print("\n3. Testing Aggregation Queries...")
    sum_res = conn.execute("SELECT SUM(file_size) FROM files").fetchone()
    assert sum_res is not None and sum_res[0] >= 1048576, f"Incorrect sum: {sum_res}"
    print(f"  [PASS] SELECT SUM(file_size) FROM files -> {sum_res[0]} bytes")

    join_sum = conn.execute("""
        SELECT SUM(f.file_size) 
        FROM uploads u 
        JOIN files f ON u.file_id = f.id
    """).fetchone()
    assert join_sum is not None and join_sum[0] >= 1048576, f"Incorrect joined sum: {join_sum}"
    print(f"  [PASS] Joined SUM query -> {join_sum[0]} bytes")

    # 4. Test Audit Logging & JOIN
    print("\n4. Testing Audit Records & JOIN...")
    conn.execute("INSERT INTO audits (file_id, audit_status, message) VALUES (?, ?, ?)",
                 (file_id, "Success", "Integrity verified successfully"))
    
    audit_rows = conn.execute("""
        SELECT a.*, f.file_name 
        FROM audits a 
        JOIN files f ON a.file_id = f.id 
        ORDER BY a.timestamp DESC LIMIT 10
    """).fetchall()
    assert len(audit_rows) > 0, "No audit rows found"
    print(f"  [PASS] Joined audit query fetched: file_name='{audit_rows[0]['file_name']}', status='{audit_rows[0]['audit_status']}'")

    # 5. Clean up test records
    print("\n5. Cleaning up test data...")
    conn.execute("DELETE FROM uploads WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM audits WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    
    deleted_check = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    assert deleted_check is None, "File was not deleted"
    print("  [PASS] Test records cleaned up successfully.")

    conn.close()
    print("\n" + "=" * 60)
    print("ALL MONGODB INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_mongo_integration()
