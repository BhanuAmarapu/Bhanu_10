"""
Backward compatibility module.
All database access is routed to mongo_wrapper.py
"""
from mongo_wrapper import (
    MongoRow as SQLiteRow,
    MongoCursor as SQLiteMimicCursor,
    MongoConnectionWrapper as SQLiteConnectionMimic,
    get_mongo_connection as get_mysql_connection,
    IntegrityError
)

__all__ = [
    'SQLiteRow',
    'SQLiteMimicCursor',
    'SQLiteConnectionMimic',
    'get_mysql_connection',
    'IntegrityError'
]
