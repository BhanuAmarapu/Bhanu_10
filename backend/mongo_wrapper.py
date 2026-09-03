import os
import re
from datetime import datetime, timezone
import pymongo
from pymongo.errors import DuplicateKeyError

# Custom IntegrityError for compatibility with existing exception handlers
class IntegrityError(Exception):
    pass

class MongoRow:
    """A row object that allows access by column name or numeric index."""
    def __init__(self, data_dict, columns=None):
        self._data = dict(data_dict) if data_dict is not None else {}
        # Remove internal MongoDB _id from standard column access unless requested
        if '_id' in self._data and 'id' in self._data:
            self._mongo_id = self._data['_id']
        else:
            self._mongo_id = self._data.get('_id')
            
        if columns:
            self._columns = list(columns)
        else:
            # Maintain stable order with 'id' first if present
            keys = list(self._data.keys())
            if '_id' in keys:
                keys.remove('_id')
            if 'id' in keys:
                keys.remove('id')
                self._columns = ['id'] + keys
            else:
                self._columns = keys
                
        self._row_tuple = tuple(self._data.get(col) for col in self._columns)

    def __getitem__(self, key):
        if isinstance(key, int):
            if 0 <= key < len(self._row_tuple):
                val = self._row_tuple[key]
                return 0 if val is None and len(self._columns) == 1 and any(k in str(self._columns[0]).upper() for k in ('SUM', 'COUNT')) else val
            return 0
        if key in self._data:
            return self._data[key]
        if key == '_id':
            return self._mongo_id
        return None

    def __setitem__(self, key, value):
        self._data[key] = value

    def keys(self):
        return self._columns

    def values(self):
        return [self._data.get(k) for k in self._columns]

    def items(self):
        return [(k, self._data.get(k)) for k in self._columns]

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def __contains__(self, key):
        return key in self._data or key in self._columns

    def __repr__(self):
        return f"<MongoRow {self._data}>"

class MongoCursor:
    def __init__(self, rows=None, lastrowid=None):
        self._rows = rows or []
        self._index = 0
        self._lastrowid = lastrowid

    def fetchone(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    def fetchall(self):
        remaining = self._rows[self._index:]
        self._index = len(self._rows)
        return remaining

    @property
    def lastrowid(self):
        return self._lastrowid

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

# Global MongoClient singleton
_mongo_client_instance = None

def get_mongo_client():
    global _mongo_client_instance
    if _mongo_client_instance is None:
        from config import Config
        _mongo_client_instance = pymongo.MongoClient(Config.MONGO_URI)
    return _mongo_client_instance

def get_mongo_db():
    from config import Config
    client = get_mongo_client()
    db_name = getattr(Config, 'MONGO_DB', 'cloud_dedup') or 'cloud_dedup'
    return client[db_name]

def get_next_sequence_value(db, sequence_name):
    """Generate an auto-incrementing numeric integer ID for collection records."""
    counter = db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER
    )
    return counter["seq"]

class MongoConnectionWrapper:
    """Wrapper that translates SQL queries to MongoDB operations transparently."""
    def __init__(self, db=None):
        self.db = db if db is not None else get_mongo_db()
        self.IntegrityError = IntegrityError
        self._last_cursor = None

    def cursor(self):
        return self

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    @property
    def lastrowid(self):
        return self._last_cursor.lastrowid if self._last_cursor else None

    def fetchone(self):
        return self._last_cursor.fetchone() if self._last_cursor else None

    def fetchall(self):
        return self._last_cursor.fetchall() if self._last_cursor else []

    def execute(self, query, params=None):
        params = list(params) if params is not None else []
        cursor = self._execute_internal(query.strip(), params)
        self._last_cursor = cursor
        return cursor

    def _execute_internal(self, query, params):
        q_upper = query.upper()

        # DDL: CREATE TABLE
        if q_upper.startswith("CREATE TABLE"):
            return self._handle_create_table(query)

        # DDL: CREATE INDEX
        if q_upper.startswith("CREATE INDEX"):
            return self._handle_create_index(query)

        # DDL: ALTER TABLE
        if q_upper.startswith("ALTER TABLE"):
            return MongoCursor([])

        # DDL: SHOW TABLES
        if q_upper.startswith("SHOW TABLES"):
            cols = self.db.list_collection_names()
            rows = [MongoRow({"Tables_in_db": c}, ["Tables_in_db"]) for c in cols]
            return MongoCursor(rows)

        # DDL: SHOW COLUMNS FROM <table>
        if q_upper.startswith("SHOW COLUMNS"):
            # Return dummy column info indicating column exists
            return MongoCursor([MongoRow({"Field": "status", "Type": "varchar(50)"}, ["Field", "Type"])])

        # DML: INSERT
        if q_upper.startswith("INSERT INTO"):
            return self._handle_insert(query, params)

        # DML: UPDATE
        if q_upper.startswith("UPDATE"):
            return self._handle_update(query, params)

        # DML: DELETE
        if q_upper.startswith("DELETE FROM"):
            return self._handle_delete(query, params)

        # DQL: SELECT
        if q_upper.startswith("SELECT"):
            return self._handle_select(query, params)

        print(f"[MongoWrapper Warning] Unhandled query: {query}")
        return MongoCursor([])

    def _handle_create_table(self, query):
        match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)", query, re.IGNORECASE)
        if match:
            table_name = match.group(1)
            # Ensure collection exists
            if table_name not in self.db.list_collection_names():
                self.db.create_collection(table_name)
        return MongoCursor([])

    def _handle_create_index(self, query):
        match = re.search(r"CREATE\s+INDEX\s+([a-zA-Z0-9_]+)\s+ON\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)", query, re.IGNORECASE)
        if match:
            col_name = match.group(2)
            fields = [f.strip() for f in match.group(3).split(',')]
            keys = [(f, pymongo.ASCENDING) for f in fields]
            try:
                self.db[col_name].create_index(keys)
            except Exception as e:
                print(f"[MongoWrapper] Create index note: {e}")
        return MongoCursor([])

    def _handle_insert(self, query, params):
        match = re.search(r"INSERT\s+INTO\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", query, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse INSERT statement: {query}")

        table_name = match.group(1)
        col_names = [c.strip() for c in match.group(2).split(',')]
        
        doc = {}
        for idx, col in enumerate(col_names):
            if idx < len(params):
                doc[col] = params[idx]

        # Generate auto-increment integer ID
        if 'id' not in doc:
            doc['id'] = get_next_sequence_value(self.db, table_name)

        # Handle default timestamps
        now = datetime.now()
        if 'upload_timestamp' not in doc and table_name in ('files', 'audio_records', 'video_records'):
            doc['upload_timestamp'] = now
        if 'timestamp' not in doc and table_name in ('uploads', 'audits', 'logs', 'suspicious_activities', 'moderation_logs'):
            doc['timestamp'] = now

        try:
            self.db[table_name].insert_one(doc)
            return MongoCursor([], lastrowid=doc['id'])
        except DuplicateKeyError as e:
            raise IntegrityError(f"Duplicate key error in {table_name}: {e}")

    def _handle_update(self, query, params):
        # Example: UPDATE users SET password = ? WHERE username = ?
        # Example: UPDATE moderation_logs SET reviewed = 1, reviewer_notes = ? WHERE id = ?
        match = re.search(r"UPDATE\s+([a-zA-Z0-9_]+)\s+SET\s+(.+?)\s+WHERE\s+(.+)", query, re.IGNORECASE | re.DOTALL)
        if not match:
            # Fallback simple update
            return MongoCursor([])

        table_name = match.group(1)
        set_clause = match.group(2)
        where_clause = match.group(3)

        # Parse SET items
        set_items = [s.strip() for s in set_clause.split(',')]
        param_idx = 0
        update_doc = {}
        for item in set_items:
            parts = [p.strip() for p in item.split('=', 1)]
            if len(parts) == 2:
                field = parts[0]
                val = parts[1]
                if val == '?':
                    update_doc[field] = params[param_idx]
                    param_idx += 1
                else:
                    # Literal value e.g. 1 or 'completed'
                    v = val.strip("'\"")
                    if v.isdigit():
                        v = int(v)
                    update_doc[field] = v

        where_params = params[param_idx:]
        filter_doc = self._build_filter_from_where(where_clause, where_params)

        self.db[table_name].update_many(filter_doc, {"$set": update_doc})
        return MongoCursor([])

    def _handle_delete(self, query, params):
        # Example: DELETE FROM files WHERE id = ?
        match = re.search(r"DELETE\s+FROM\s+([a-zA-Z0-9_]+)(?:\s+WHERE\s+(.+))?", query, re.IGNORECASE | re.DOTALL)
        if not match:
            return MongoCursor([])

        table_name = match.group(1)
        where_clause = match.group(2)
        filter_doc = {}
        if where_clause:
            filter_doc = self._build_filter_from_where(where_clause, params)

        self.db[table_name].delete_many(filter_doc)
        return MongoCursor([])


    def _build_filter_from_where(self, where_clause, params):
        if not where_clause:
            return {}

        filter_doc = {}
        param_idx = 0

        # Tokenize by AND
        conditions = re.split(r"\s+AND\s+", where_clause, flags=re.IGNORECASE)
        for cond in conditions:
            cond = cond.strip()
            # Check for IN subquery e.g. f.file_hash IN (SELECT ...)
            in_sub_match = re.search(r"([a-zA-Z0-9_.]+)\s+IN\s*\((.+)\)", cond, re.IGNORECASE)
            if in_sub_match:
                field = in_sub_match.group(1).split('.')[-1]
                subquery = in_sub_match.group(2)
                sub_res = self.execute(subquery)
                values = [r[0] for r in sub_res.fetchall()]
                filter_doc[field] = {"$in": values}
                continue

            # Field != ?
            m_ne = re.match(r"([a-zA-Z0-9_.]+)\s*!=\s*(\?|'[^']*'|\d+)", cond)
            if m_ne:
                field = m_ne.group(1).split('.')[-1]
                val = m_ne.group(2)
                if val == '?':
                    filter_doc[field] = {"$ne": params[param_idx]}
                    param_idx += 1
                else:
                    v = val.strip("'\"")
                    if v.isdigit(): v = int(v)
                    filter_doc[field] = {"$ne": v}
                continue

            # Field IS NULL
            m_isnull = re.match(r"([a-zA-Z0-9_.]+)\s+IS\s+NULL", cond, re.IGNORECASE)
            if m_isnull:
                field = m_isnull.group(1).split('.')[-1]
                filter_doc[field] = None
                continue

            # Field IS NOT NULL
            m_isnotnull = re.match(r"([a-zA-Z0-9_.]+)\s+IS\s+NOT\s+NULL", cond, re.IGNORECASE)
            if m_isnotnull:
                field = m_isnotnull.group(1).split('.')[-1]
                filter_doc[field] = {"$ne": None}
                continue

            # Field >= ?
            m_gte = re.match(r"([a-zA-Z0-9_.]+)\s*>=\s*(\?|'[^']*'|\d+)", cond)

            if m_gte:
                field = m_gte.group(1).split('.')[-1]
                val = m_gte.group(2)
                if val == '?':
                    filter_doc[field] = {"$gte": params[param_idx]}
                    param_idx += 1
                else:
                    v = val.strip("'\"")
                    filter_doc[field] = {"$gte": int(v) if v.isdigit() else v}
                continue

            # Field <= ?
            m_lte = re.match(r"([a-zA-Z0-9_.]+)\s*<=\s*(\?|'[^']*'|\d+)", cond)
            if m_lte:
                field = m_lte.group(1).split('.')[-1]
                val = m_lte.group(2)
                if val == '?':
                    filter_doc[field] = {"$lte": params[param_idx]}
                    param_idx += 1
                else:
                    v = val.strip("'\"")
                    filter_doc[field] = {"$lte": int(v) if v.isdigit() else v}
                continue

            # Field LIKE ?
            m_like = re.match(r"([a-zA-Z0-9_.]+)\s+LIKE\s+(\?|'[^']*')", cond, re.IGNORECASE)
            if m_like:
                field = m_like.group(1).split('.')[-1]
                val = m_like.group(2)
                raw_pattern = params[param_idx] if val == '?' else val.strip("'\"")
                if val == '?': param_idx += 1
                regex_pattern = re.escape(raw_pattern).replace(r'\%', '.*').replace(r'\_', '.')
                filter_doc[field] = {"$regex": regex_pattern, "$options": "i"}
                continue

            # Field = ? or Field = 'val' or Field = 0
            m_eq = re.match(r"([a-zA-Z0-9_.]+)\s*=\s*(\?|'[^']*'|\d+)", cond)
            if m_eq:
                field = m_eq.group(1).split('.')[-1]
                val = m_eq.group(2)
                if val == '?':
                    target_val = params[param_idx]
                    param_idx += 1
                    # Handle integer id lookups passed as string or int
                    if field in ('id', 'user_id', 'file_id') and isinstance(target_val, str) and target_val.isdigit():
                        target_val = int(target_val)
                    filter_doc[field] = target_val
                else:
                    v = val.strip("'\"")
                    if v.isdigit(): v = int(v)
                    filter_doc[field] = v
                continue

        return filter_doc

    def _handle_select(self, query, params):
        q_clean = query.strip()
        
        # 1. Handle SUM / Aggregations
        # e.g. SELECT SUM(unique_size) FROM (SELECT MAX(file_size) as unique_size FROM <audio_records|video_records> ...)
        if "SUM(UNIQUE_SIZE)" in q_clean.upper():
            tbl_match = re.search(r"FROM\s+([a-zA-Z0-9_]+records)", q_clean, re.IGNORECASE)
            tbl = tbl_match.group(1) if tbl_match else ("video_records" if "video_records" in q_clean.lower() else "audio_records")
            pipeline = [
                {"$group": {
                    "_id": {"$ifNull": ["$file_hash", {"$concat": ["no_hash_", {"$toString": "$id"}]}]},
                    "unique_size": {"$max": "$file_size"}
                }},
                {"$group": {"_id": None, "total": {"$sum": "$unique_size"}}}
            ]
            res = list(self.db[tbl].aggregate(pipeline))
            total = res[0]["total"] if res and "total" in res[0] and res[0]["total"] is not None else 0
            return MongoCursor([MongoRow({"SUM(unique_size)": total, "total": total, 0: total}, ["SUM(unique_size)"])])

        # e.g. SELECT SUM(file_size) FROM files / audio_records / video_records
        m_sum_file = re.search(r"SELECT\s+SUM\(\s*file_size\s*\)\s+FROM\s+([a-zA-Z0-9_]+)", q_clean, re.IGNORECASE)
        if m_sum_file:
            tbl = m_sum_file.group(1)
            pipeline = [{"$group": {"_id": None, "total": {"$sum": "$file_size"}}}]
            res = list(self.db[tbl].aggregate(pipeline))
            total = res[0]["total"] if res and "total" in res[0] and res[0]["total"] is not None else 0
            return MongoCursor([MongoRow({"SUM(file_size)": total, "total": total, 0: total}, ["SUM(file_size)"])])

        # e.g. SELECT SUM(f.file_size) FROM uploads u JOIN files f ON u.file_id = f.id
        if "SUM(F.FILE_SIZE)" in q_clean.upper() or ("SUM(" in q_clean.upper() and "JOIN FILES" in q_clean.upper()):
            pipeline = [
                {"$lookup": {"from": "files", "localField": "file_id", "foreignField": "id", "as": "file"}},
                {"$unwind": "$file"},
                {"$group": {"_id": None, "total": {"$sum": "$file.file_size"}}}
            ]
            res = list(self.db.uploads.aggregate(pipeline))
            total = res[0]["total"] if res and "total" in res[0] and res[0]["total"] is not None else 0
            return MongoCursor([MongoRow({"SUM(f.file_size)": total, "total": total, 0: total}, ["SUM(f.file_size)"])])

        # 2. Handle subquery: SELECT file_hash FROM files GROUP BY file_hash HAVING COUNT(*) > 1
        if "GROUP BY FILE_HASH HAVING COUNT(*) > 1" in q_clean.upper():
            pipeline = [
                {"$group": {"_id": "$file_hash", "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}, "_id": {"$ne": None}}}
            ]
            res = list(self.db.files.aggregate(pipeline))
            rows = [MongoRow({"file_hash": r["_id"]}, ["file_hash"]) for r in res]
            return MongoCursor(rows)

        # 3. Handle JOIN queries
        # e.g. SELECT sa.*, u.username, u.email FROM suspicious_activities sa JOIN users u ON sa.user_id = u.id
        if "FROM SUSPICIOUS_ACTIVITIES" in q_clean.upper() and "JOIN USERS" in q_clean.upper():
            where_match = re.search(r"WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s*$)", q_clean, re.IGNORECASE)
            filter_doc = self._build_filter_from_where(where_match.group(1), params) if where_match else {}
            pipeline = [
                {"$match": filter_doc},
                {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "id", "as": "user"}},
                {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
                {"$sort": {"timestamp": -1}}
            ]
            res = list(self.db.suspicious_activities.aggregate(pipeline))
            rows = []
            for doc in res:
                u = doc.get("user") or {}
                doc["username"] = u.get("username", "Unknown")
                doc["email"] = u.get("email", "Unknown")
                if "user" in doc: del doc["user"]
                rows.append(MongoRow(doc))
            return MongoCursor(rows)

        # e.g. SELECT m.*, u.username, u.email FROM moderation_logs m JOIN users u ON m.user_id = u.id
        if "FROM MODERATION_LOGS" in q_clean.upper() and "JOIN USERS" in q_clean.upper():
            where_match = re.search(r"WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s*$)", q_clean, re.IGNORECASE)
            filter_doc = self._build_filter_from_where(where_match.group(1), params) if where_match else {}
            pipeline = [
                {"$match": filter_doc},
                {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "id", "as": "user"}},
                {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
                {"$sort": {"timestamp": -1}}
            ]
            res = list(self.db.moderation_logs.aggregate(pipeline))
            rows = []
            for doc in res:
                u = doc.get("user") or {}
                doc["username"] = u.get("username", "Unknown")
                doc["email"] = u.get("email", "Unknown")
                if "user" in doc: del doc["user"]
                rows.append(MongoRow(doc))
            return MongoCursor(rows)

        # e.g. SELECT f.id, f.file_name, ... (SELECT content_text FROM uploads WHERE file_id = f.id) as content_text FROM files f WHERE f.file_hash != ?
        if "FROM FILES" in q_clean.upper() and "CONTENT_TEXT" in q_clean.upper():
            target_hash = params[0] if params else ""
            pipeline = [
                {"$match": {"file_hash": {"$ne": target_hash}}},
                {"$lookup": {
                    "from": "uploads",
                    "let": {"fid": "$id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$file_id", "$$fid"]}}},
                        {"$sort": {"timestamp": -1}},
                        {"$limit": 1}
                    ],
                    "as": "upload"
                }},
                {"$unwind": {"path": "$upload", "preserveNullAndEmptyArrays": True}},
                {"$sort": {"upload_timestamp": -1}}
            ]
            res = list(self.db.files.aggregate(pipeline))
            rows = []
            for doc in res:
                u = doc.get("upload") or {}
                # Prioritize content_text in upload doc, fallback to files doc
                doc["content_text"] = u.get("content_text") or doc.get("content_text")
                if "upload" in doc: del doc["upload"]
                rows.append(MongoRow(doc))
            return MongoCursor(rows)

        # e.g. SELECT a.*, f.file_name FROM audits a JOIN files f ON a.file_id = f.id ORDER BY a.timestamp DESC LIMIT 10
        if "FROM AUDITS" in q_clean.upper() and "JOIN FILES" in q_clean.upper():
            limit_match = re.search(r"LIMIT\s+(\d+)", q_clean, re.IGNORECASE)
            limit_val = int(limit_match.group(1)) if limit_match else 100
            pipeline = [
                {"$lookup": {"from": "files", "localField": "file_id", "foreignField": "id", "as": "file"}},
                {"$unwind": {"path": "$file", "preserveNullAndEmptyArrays": True}},
                {"$sort": {"timestamp": -1}},
                {"$limit": limit_val}
            ]
            res = list(self.db.audits.aggregate(pipeline))
            rows = []
            for doc in res:
                f = doc.get("file") or {}
                doc["file_name"] = f.get("file_name", "Unknown")
                if "file" in doc: del doc["file"]
                rows.append(MongoRow(doc))
            return MongoCursor(rows)

        # e.g. SELECT COUNT(*) as count FROM uploads u JOIN files f ON u.file_id = f.id WHERE ...
        if "FROM UPLOADS" in q_clean.upper() and "JOIN FILES" in q_clean.upper() and "COUNT(*)" in q_clean.upper():
            where_match = re.search(r"WHERE\s+(.+)", q_clean, re.IGNORECASE)
            filter_doc = self._build_filter_from_where(where_match.group(1), params) if where_match else {}
            
            # If subquery f.file_hash IN (...) was extracted
            pipeline = [
                {"$lookup": {"from": "files", "localField": "file_id", "foreignField": "id", "as": "file"}},
                {"$unwind": "$file"}
            ]
            match_stage = {}
            if "user_id" in filter_doc: match_stage["user_id"] = filter_doc["user_id"]
            if "timestamp" in filter_doc: match_stage["timestamp"] = filter_doc["timestamp"]
            if "file_hash" in filter_doc: match_stage["file.file_hash"] = filter_doc["file_hash"]
            
            if match_stage:
                pipeline.append({"$match": match_stage})
            pipeline.append({"$count": "count"})
            res = list(self.db.uploads.aggregate(pipeline))
            count_val = res[0]["count"] if res else 0
            return MongoCursor([MongoRow({"count": count_val, "COUNT(*)": count_val}, ["count"])])

        # 4. Standard Single Collection SELECT Queries
        # Parse table name
        m_from = re.search(r"FROM\s+([a-zA-Z0-9_]+)", q_clean, re.IGNORECASE)
        if not m_from:
            return MongoCursor([])
        table_name = m_from.group(1)

        # Parse selected fields
        m_select = re.search(r"SELECT\s+(.+?)\s+FROM", q_clean, re.IGNORECASE)
        select_fields_raw = m_select.group(1).strip() if m_select else "*"

        # Check for COUNT(*) query
        if "COUNT(*)" in select_fields_raw.upper():
            where_match = re.search(r"WHERE\s+(.+)", q_clean, re.IGNORECASE)
            filter_doc = self._build_filter_from_where(where_match.group(1), params) if where_match else {}
            count = self.db[table_name].count_documents(filter_doc)
            return MongoCursor([MongoRow({"count": count, "COUNT(*)": count}, ["count"])])

        # Parse WHERE
        where_match = re.search(r"WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+LIMIT|\s*$)", q_clean, re.IGNORECASE)
        filter_doc = self._build_filter_from_where(where_match.group(1), params) if where_match else {}

        # Parse ORDER BY
        order_match = re.search(r"ORDER\s+BY\s+([a-zA-Z0-9_]+)(?:\s+(ASC|DESC))?", q_clean, re.IGNORECASE)
        sort_config = None
        if order_match:
            sort_field = order_match.group(1)
            sort_dir = pymongo.DESCENDING if (order_match.group(2) or '').upper() == 'DESC' else pymongo.ASCENDING
            sort_config = [(sort_field, sort_dir)]

        # Parse LIMIT
        limit_match = re.search(r"LIMIT\s+(\d+)", q_clean, re.IGNORECASE)
        limit_val = int(limit_match.group(1)) if limit_match else None

        # Execute MongoDB find
        find_cursor = self.db[table_name].find(filter_doc)
        if sort_config:
            find_cursor = find_cursor.sort(sort_config)
        if limit_val:
            find_cursor = find_cursor.limit(limit_val)

        # Build columns list if explicit fields requested
        columns = None
        if select_fields_raw != "*":
            # Extract explicit fields e.g. "id, original_filename, transcript"
            columns = [re.sub(r"\s+as\s+[a-zA-Z0-9_]+", "", f, flags=re.IGNORECASE).strip().split('.')[-1] for f in select_fields_raw.split(',')]
            # Clean expressions like "NULL as dino_embedding"
            columns = [f.split()[-1] if ' as ' in f.lower() else f for f in columns]

        rows = []
        for doc in find_cursor:
            # If specific columns requested, ensure all keys exist
            if columns:
                for c in columns:
                    if c not in doc:
                        doc[c] = None
            rows.append(MongoRow(doc, columns))

        return MongoCursor(rows)

def get_mongo_connection():
    return MongoConnectionWrapper()

# Backward compatibility alias
def get_mysql_connection():
    return get_mongo_connection()
