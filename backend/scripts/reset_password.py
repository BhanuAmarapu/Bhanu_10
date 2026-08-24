"""
Reset password for an existing user (MySQL version)
"""
from mysql_wrapper import get_mysql_connection
import os
import sys

def reset_password():
    """Reset password for an existing user"""
    print("=" * 60)
    print("MySQL Password Reset Tool")
    print("=" * 60)
    
    # Connect to database
    try:
        conn = get_mysql_connection()
    except Exception as e:
        print(f"\n[ERROR] Could not connect to database: {e}")
        return
    
    # Show existing users
    print("\nExisting users:")
    try:
        cursor = conn.execute("SELECT id, username, role FROM users")
        users = cursor.fetchall()
        for user in users:
            print(f"  [{user['id']}] {user['username']} ({user['role']})")
    except Exception as e:
        print(f"  (Error fetching users: {e})")
    
    print("\n" + "=" * 60)
    
    # Get user input
    username = input("Enter username to reset password: ").strip()
    
    # Check if user exists
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    
    if not user:
        print(f"\n[ERROR] User '{username}' not found!")
        conn.close()
        return
    
    # Get new password
    new_password = input(f"Enter new password for '{username}': ").strip()
    
    if not new_password:
        print("\n[ERROR] Password cannot be empty!")
        conn.close()
        return
    
    # Update password
    conn.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, username))
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print(f"[SUCCESS] Password updated successfully in MySQL!")
    print(f"   Username: {username}")
    print(f"   New Password: {new_password}")
    print("=" * 60)
    print("\nYou can now log in with these credentials.")

if __name__ == "__main__":
    try:
        reset_password()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
