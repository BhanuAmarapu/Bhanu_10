"""
Suspicious Upload Detector Module
Monitors user upload behavior and detects anomalies such as:
- Rapid file uploads
- Excessive duplicate upload attempts
- Repeated Proof of Ownership (PoW) failures
"""

import pymysql
from datetime import datetime, timedelta
from config import Config
from utils import log_action


class SuspiciousUploadDetector:
    """Detects and tracks suspicious upload activities"""
    
    # Severity levels
    SEVERITY_LOW = "LOW"
    SEVERITY_MEDIUM = "MEDIUM"
    SEVERITY_HIGH = "HIGH"
    SEVERITY_CRITICAL = "CRITICAL"
    
    # Activity types
    ACTIVITY_RAPID_UPLOAD = "RAPID_UPLOAD"
    ACTIVITY_EXCESSIVE_DUPLICATES = "EXCESSIVE_DUPLICATES"
    ACTIVITY_POW_FAILURE = "POW_FAILURE"
    
    def __init__(self):
        pass
        
    def get_db_connection(self):
        """Get database connection"""
        from mysql_wrapper import get_mysql_connection
        conn = get_mysql_connection()
        return conn
    
    def track_upload(self, user_id):
        """
        Track a file upload and check for rapid upload pattern
        Returns: (is_suspicious, alert_message)
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get or create activity stats for this user
        now = datetime.now()
        window_start = now - timedelta(minutes=Config.RAPID_UPLOAD_WINDOW_MINUTES)
        
        # Count uploads in the current time window
        cursor.execute("""
            SELECT COUNT(*) as count FROM uploads 
            WHERE user_id = ? AND timestamp >= ?
        """, (user_id, window_start))
        
        upload_count = cursor.fetchone()['count']
        
        # Check threshold
        if upload_count >= Config.RAPID_UPLOAD_THRESHOLD:
            # Generate alert
            self._create_alert(
                user_id=user_id,
                activity_type=self.ACTIVITY_RAPID_UPLOAD,
                severity=self.SEVERITY_MEDIUM,
                description=f"Rapid upload detected: {upload_count} uploads in {Config.RAPID_UPLOAD_WINDOW_MINUTES} minute(s)",
                details=f"Threshold: {Config.RAPID_UPLOAD_THRESHOLD}, Actual: {upload_count}"
            )
            conn.close()
            log_action("Security Alert", f"Rapid upload detected for user {user_id}")
            return True, f"Warning: Rapid upload pattern detected ({upload_count} uploads)"
        
        conn.close()
        return False, None
    
    def track_duplicate_attempt(self, user_id, file_hash):
        """
        Track duplicate upload attempts
        Returns: (is_suspicious, alert_message)
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Count duplicate attempts in the last hour
        window_start = datetime.now() - timedelta(hours=Config.DUPLICATE_ATTEMPT_WINDOW_HOURS)
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM uploads u
            JOIN files f ON u.file_id = f.id
            WHERE u.user_id = ? AND f.file_hash = ? AND u.timestamp >= ?
        """, (user_id, file_hash, window_start))
        
        duplicate_count = cursor.fetchone()['count']
        
        # Check threshold
        if duplicate_count >= Config.DUPLICATE_ATTEMPT_THRESHOLD:
            # Generate alert
            self._create_alert(
                user_id=user_id,
                activity_type=self.ACTIVITY_EXCESSIVE_DUPLICATES,
                severity=self.SEVERITY_HIGH,
                description=f"Excessive duplicate attempts: {duplicate_count} attempts in {Config.DUPLICATE_ATTEMPT_WINDOW_HOURS} hour(s)",
                details=f"File hash: {file_hash[:16]}..., Threshold: {Config.DUPLICATE_ATTEMPT_THRESHOLD}, Actual: {duplicate_count}"
            )
            conn.close()
            log_action("Security Alert", f"Excessive duplicate attempts detected for user {user_id}")
            return True, f"Warning: Excessive duplicate upload attempts detected ({duplicate_count} attempts)"
        
        conn.close()
        return False, None
    
    def track_pow_failure(self, user_id, file_hash):
        """
        Track Proof of Ownership failures
        Returns: (is_suspicious, alert_message)
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Count PoW failures in the last hour
        window_start = datetime.now() - timedelta(hours=Config.POW_FAILURE_WINDOW_HOURS)
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM logs
            WHERE action = 'PoW Failed' AND details LIKE ? AND timestamp >= ?
        """, (f"%user {user_id}%", window_start))
        
        failure_count = cursor.fetchone()['count']
        
        # Check threshold
        if failure_count >= Config.POW_FAILURE_THRESHOLD:
            # Generate alert
            self._create_alert(
                user_id=user_id,
                activity_type=self.ACTIVITY_POW_FAILURE,
                severity=self.SEVERITY_CRITICAL,
                description=f"Multiple PoW failures: {failure_count} failures in {Config.POW_FAILURE_WINDOW_HOURS} hour(s)",
                details=f"File hash: {file_hash[:16]}..., Threshold: {Config.POW_FAILURE_THRESHOLD}, Actual: {failure_count}"
            )
            conn.close()
            log_action("Security Alert", f"Multiple PoW failures detected for user {user_id}")
            return True, f"Critical: Multiple Proof of Ownership failures detected ({failure_count} failures)"
        
        conn.close()
        return False, None
    
    def _create_alert(self, user_id, activity_type, severity, description, details):
        """Create a suspicious activity alert"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if similar alert exists in the last 5 minutes (avoid spam)
        recent_check = datetime.now() - timedelta(minutes=5)
        cursor.execute("""
            SELECT id FROM suspicious_activities
            WHERE user_id = ? AND activity_type = ? AND timestamp >= ?
        """, (user_id, activity_type, recent_check))
        
        if cursor.fetchone():
            # Similar alert already exists recently, skip
            conn.close()
            return
        
        # Create new alert
        cursor.execute("""
            INSERT INTO suspicious_activities 
            (user_id, activity_type, severity, description, details)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, activity_type, severity, description, details))
        
        conn.commit()
        conn.close()
    
    def get_all_alerts(self, include_dismissed=False):
        """Get all suspicious activity alerts"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT sa.*, u.username, u.email 
            FROM suspicious_activities sa
            JOIN users u ON sa.user_id = u.id
        """
        
        if not include_dismissed:
            query += " WHERE sa.is_dismissed = 0"
        
        query += " ORDER BY sa.timestamp DESC"
        
        cursor.execute(query)
        alerts = cursor.fetchall()
        conn.close()
        
        return alerts
    
    def get_alert_count(self, user_id=None, dismissed=False):
        """Get count of alerts"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) as count FROM suspicious_activities WHERE is_dismissed = ?"
        params = [1 if dismissed else 0]
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        cursor.execute(query, params)
        count = cursor.fetchone()['count']
        conn.close()
        
        return count
    
    def dismiss_alert(self, alert_id):
        """Dismiss/acknowledge an alert"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE suspicious_activities 
            SET is_dismissed = 1 
            WHERE id = ?
        """, (alert_id,))
        
        conn.commit()
        conn.close()
        
        log_action("Alert Dismissed", f"Alert ID {alert_id} dismissed by admin")
    
    def get_user_stats(self, user_id, hours=24):
        """Get user activity statistics"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        window_start = datetime.now() - timedelta(hours=hours)
        
        # Upload count
        cursor.execute("""
            SELECT COUNT(*) as count FROM uploads
            WHERE user_id = ? AND timestamp >= ?
        """, (user_id, window_start))
        upload_count = cursor.fetchone()['count']
        
        # Duplicate count
        cursor.execute("""
            SELECT COUNT(*) as count FROM uploads u
            JOIN files f ON u.file_id = f.id
            WHERE u.user_id = ? AND u.timestamp >= ?
            AND f.file_hash IN (
                SELECT file_hash FROM files 
                GROUP BY file_hash HAVING COUNT(*) > 1
            )
        """, (user_id, window_start))
        duplicate_count = cursor.fetchone()['count']
        
        # Alert count
        cursor.execute("""
            SELECT COUNT(*) as count FROM suspicious_activities
            WHERE user_id = ? AND timestamp >= ?
        """, (user_id, window_start))
        alert_count = cursor.fetchone()['count']
        
        conn.close()
        
        return {
            'upload_count': upload_count,
            'duplicate_count': duplicate_count,
            'alert_count': alert_count,
            'hours': hours
        }
