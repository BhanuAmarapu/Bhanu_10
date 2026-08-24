import pymysql

class SQLiteRow:
    def __init__(self, row_tuple, description):
        self.row_tuple = row_tuple
        self.description = description
        
    def __getitem__(self, key):
        if isinstance(key, int):
            return self.row_tuple[key]
        for idx, desc in enumerate(self.description):
            if desc[0] == key:
                return self.row_tuple[idx]
        raise KeyError(key)

    def keys(self):
        return [desc[0] for desc in self.description]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

class SQLiteMimicCursor(pymysql.cursors.Cursor):
    def fetchone(self):
        row = super().fetchone()
        if not row:
            return None
        return SQLiteRow(row, self.description)

    def fetchall(self):
        rows = super().fetchall()
        return [SQLiteRow(row, self.description) for row in rows]

class CursorWrapper:
    def __init__(self, db_conn):
        self.cursor = db_conn.conn.cursor(SQLiteMimicCursor)
    
    def execute(self, query, params=None):
        query = query.replace('?', '%s')
        self.cursor.execute(query, params)
        return self.cursor
        
    def fetchone(self): return self.cursor.fetchone()
    def fetchall(self): return self.cursor.fetchall()
    
    @property
    def lastrowid(self): return self.cursor.lastrowid

class SQLiteConnectionMimic:
    def __init__(self, host, user, password, database):
        self.conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        self.IntegrityError = pymysql.err.IntegrityError

    def execute(self, query, params=None):
        cursor = self.conn.cursor(SQLiteMimicCursor)
        query = query.replace('?', '%s')
        cursor.execute(query, params)
        return cursor
        
    def cursor(self):
        return CursorWrapper(self)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()

def get_mysql_connection():
    from config import Config
    return SQLiteConnectionMimic(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
