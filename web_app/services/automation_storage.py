"""Versioned, thread-safe storage for automation. Existing chat databases are untouched."""
import base64
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class AutomationStorage:
    VERSION = 1

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > self.VERSION:
                raise RuntimeError('Automation database is newer than this application')
            if version < self.VERSION:
                if self.path.stat().st_size:
                    backup = sqlite3.connect(str(self.path) + f'.v{version}.{time.time_ns()}.bak')
                    try:
                        conn.backup(backup)
                    finally:
                        backup.close()
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS objects (
                      kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                      PRIMARY KEY(kind,id));
                    CREATE TABLE IF NOT EXISTS events (
                      seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                      device_id TEXT NOT NULL, kind TEXT NOT NULL, created REAL NOT NULL,
                      data TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS events_task ON events(task_id,seq);
                    CREATE TABLE IF NOT EXISTS images (
                      id TEXT PRIMARY KEY, created REAL NOT NULL, pinned INTEGER DEFAULT 0,
                      data BLOB, size INTEGER NOT NULL);
                ''')
                conn.execute(f'PRAGMA user_version={self.VERSION}')

    @contextmanager
    def connection(self):
        with self.lock:
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def put(self, kind, value):
        with self.connection() as conn:
            conn.execute('INSERT INTO objects VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',
                         (kind, value['id'], json.dumps(value, ensure_ascii=False)))
        return value

    def get(self, kind, key):
        with self.connection() as conn:
            row = conn.execute('SELECT data FROM objects WHERE kind=? AND id=?', (kind, key)).fetchone()
            return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.connection() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                'SELECT data FROM objects WHERE kind=? ORDER BY rowid', (kind,))]

    def event(self, task_id, device_id, kind, data):
        created = time.time()
        with self.connection() as conn:
            seq = conn.execute('INSERT INTO events(task_id,device_id,kind,created,data) VALUES (?,?,?,?,?)',
                               (task_id, device_id, kind, created, json.dumps(data, ensure_ascii=False))).lastrowid
        return dict(seq=seq, task_id=task_id, device_id=device_id, kind=kind, created=created, data=data)

    def events(self, task_id, after=0, limit=100):
        with self.connection() as conn:
            rows = conn.execute('SELECT * FROM events WHERE task_id=? AND seq>? ORDER BY seq LIMIT ?',
                                (task_id, after, min(max(limit, 1), 500)))
            return [{**dict(row), 'data': json.loads(row['data'])} for row in rows]

    def image(self, encoded):
        key = uuid.uuid4().hex
        data = base64.b64decode(encoded, validate=True)
        with self.connection() as conn:
            conn.execute('INSERT INTO images VALUES (?,?,0,?,?)', (key, time.time(), data, len(data)))
        return key

    def get_image(self, key):
        with self.connection() as conn:
            row = conn.execute('SELECT data FROM images WHERE id=?', (key,)).fetchone()
            return bytes(row[0]) if row and row[0] else None

    def cleanup(self, days=30, max_bytes=2*1024**3):
        with self.connection() as conn:
            conn.execute('UPDATE images SET data=NULL,size=0 WHERE pinned=0 AND created<?',
                         (time.time()-days*86400,))
            total = conn.execute('SELECT COALESCE(SUM(size),0) FROM images').fetchone()[0]
            for row in conn.execute('SELECT id,size FROM images WHERE pinned=0 AND size>0 ORDER BY created').fetchall():
                if total <= max_bytes:
                    break
                conn.execute('UPDATE images SET data=NULL,size=0 WHERE id=?', (row['id'],))
                total -= row['size']
