# -*- coding: utf-8 -*-
"""
SQLite-based storage for chat sessions, logs, and screenshots.
Provides persistent storage that survives server restarts.
"""

import sqlite3
import json
import logging
import uuid
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ChatSession:
    """Represents a chat session."""
    id: str
    device_id: str
    created_at: str
    updated_at: str
    status: str  # active, completed, failed
    title: str  # Auto-generated from first message
    total_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChatMessage:
    """Represents a chat message."""
    id: str
    session_id: str
    role: str  # user, assistant, system
    content: str
    created_at: str
    image_id: Optional[str] = None  # Reference to screenshot
    status: Optional[str] = None  # running, success, error (for assistant messages)
    todo_list: Optional[str] = None  # JSON string of todoList for complex tasks
    tokens: int = 0
    model_name: Optional[str] = None
    source: Optional[str] = None  # 'web' or 'telegram' - message source

    def to_dict(self) -> dict:
        result = asdict(self)
        # Parse todo_list if it's a JSON string
        if self.todo_list:
            try:
                result['todo_list'] = json.loads(self.todo_list)
            except (json.JSONDecodeError, TypeError):
                result['todo_list'] = None
        return result


@dataclass
class ChatLog:
    """Represents a log entry during chat execution."""
    id: str
    session_id: str
    message_id: str  # Which message triggered this log
    content: str
    created_at: str
    log_type: str = "info"  # info, error, action, thinking

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChatScreenshot:
    """Represents a screenshot taken during chat."""
    id: str
    session_id: str
    message_id: str  # Which message this screenshot belongs to
    image_data: bytes  # PNG image data
    created_at: str
    description: str = ""

    def to_dict(self, include_data: bool = False) -> dict:
        d = asdict(self)
        if not include_data:
            # Return base64 encoded for API responses
            d['image_data'] = None
            d['image_url'] = f"/api/chat/screenshots/{self.id}"
        else:
            d['image_data'] = base64.b64encode(self.image_data).decode('utf-8')
        return d


class ChatStorage:
    """SQLite-based storage for chat data."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".autoglm" / "chat.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()
        self._init_context_storage()

    def _init_context_storage(self):
        """Versioned additive migration; back up existing conversations before upgrading."""
        with self._get_conn() as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='chat_context_schema'").fetchone()
            version = conn.execute('SELECT version FROM chat_context_schema').fetchone()[0] if exists else 0
            if version > 1:
                raise RuntimeError('Chat context schema is newer than this application')
            if version == 1:
                return
            if conn.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0]:
                backup_path = str(self.db_path)+'.context-v0.'+datetime.now().strftime('%Y%m%d%H%M%S%f')+'.bak'
                with sqlite3.connect(backup_path) as backup:
                    conn.backup(backup)
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE chat_context_schema (version INTEGER NOT NULL)')
            conn.execute('INSERT INTO chat_context_schema VALUES (1)')
            conn.execute('CREATE TABLE chat_context_events (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, data TEXT NOT NULL)')
            conn.execute('CREATE INDEX chat_context_event_session ON chat_context_events(session_id)')
            conn.execute('CREATE TABLE chat_context_status (session_id TEXT PRIMARY KEY, data TEXT NOT NULL)')

    def context_rows(self, session_id, through_id=None, after_seq=0):
        with self._get_conn() as conn:
            rows = conn.execute('''SELECT rowid AS seq, * FROM chat_messages
                WHERE session_id=? AND rowid>? AND rowid <= COALESCE(
                    (SELECT rowid FROM chat_messages WHERE id=? AND session_id=?),
                    CASE WHEN ? IS NULL THEN 9223372036854775807 ELSE -1 END)
                AND role IN ('user','assistant') ORDER BY rowid''',
                (session_id, after_seq, through_id, session_id, through_id)).fetchall()
            return [dict(r) for r in rows]

    def context_events(self, session_id):
        with self._get_conn() as conn:
            return [json.loads(r[0]) for r in conn.execute(
                'SELECT data FROM chat_context_events WHERE session_id=? ORDER BY rowid', (session_id,))]

    def save_context_event(self, event):
        with self._get_conn() as conn:
            conn.execute('INSERT INTO chat_context_events VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                         (event['id'],event['session_id'],json.dumps(event, ensure_ascii=False)))

    def context_status(self, session_id, value=None):
        with self._get_conn() as conn:
            if value is not None:
                conn.execute('INSERT INTO chat_context_status VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data',
                             (session_id, json.dumps(value, ensure_ascii=False)))
            row = conn.execute('SELECT data FROM chat_context_status WHERE session_id=?', (session_id,)).fetchone()
            return json.loads(row[0]) if row else {}

    @contextmanager
    def _get_conn(self):
        """Get a database connection with context management."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    title TEXT DEFAULT '',
                    total_tokens INTEGER DEFAULT 0
                )
            """)

            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    image_id TEXT,
                    status TEXT,
                    todo_list TEXT,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
                )
            """)
            
            # Migration: add new columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE chat_messages ADD COLUMN status TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE chat_messages ADD COLUMN todo_list TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE chat_messages ADD COLUMN tokens INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE chat_messages ADD COLUMN model_name TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE chat_messages ADD COLUMN source TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_logs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    log_type TEXT DEFAULT 'info',
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
                    FOREIGN KEY (message_id) REFERENCES chat_messages(id)
                )
            """)

            # Screenshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_screenshots (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    image_data BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
                    FOREIGN KEY (message_id) REFERENCES chat_messages(id)
                )
            """)

            # Create indexes for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_session ON chat_logs(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_message ON chat_logs(message_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_session ON chat_screenshots(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_message ON chat_screenshots(message_id)")

            logger.info(f"Chat database initialized at {self.db_path}")

    # ========== Session Operations ==========

    def create_session(self, device_id: str, title: str = "") -> ChatSession:
        """Create a new chat session."""
        session = ChatSession(
            id=str(uuid.uuid4())[:8],
            device_id=device_id,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            status="active",
            title=title,
            total_tokens=0,
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_sessions (id, device_id, created_at, updated_at, status, title, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session.id, session.device_id, session.created_at, session.updated_at,
                  session.status, session.title, session.total_tokens))

        logger.info(f"Created chat session: {session.id}")
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return ChatSession(**dict(row))
            return None

    def get_sessions(self, limit: int = 50, device_id: Optional[str] = None) -> List[ChatSession]:
        """Get recent sessions, optionally filtered by device."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if device_id:
                cursor.execute("""
                    SELECT * FROM chat_sessions
                    WHERE device_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                """, (device_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM chat_sessions
                    ORDER BY updated_at DESC LIMIT ?
                """, (limit,))
            return [ChatSession(**dict(row)) for row in cursor.fetchall()]

    def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session fields."""
        allowed_fields = {'status', 'title', 'total_tokens', 'updated_at'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        updates['updated_at'] = datetime.now().isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [session_id]

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE chat_sessions SET {set_clause} WHERE id = ?", values)
            return cursor.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all related data."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Delete in order: screenshots, logs, messages, session
            cursor.execute("DELETE FROM chat_screenshots WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM chat_logs WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            cursor.execute('DELETE FROM chat_context_events WHERE session_id=?', (session_id,))
            cursor.execute('DELETE FROM chat_context_status WHERE session_id=?', (session_id,))
            cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    # ========== Message Operations ==========

    def add_message(self, session_id: str, role: str, content: str, image_id: Optional[str] = None,
                     status: Optional[str] = None, todo_list: Optional[list] = None,
                     tokens: int = 0, model_name: Optional[str] = None,
                     source: Optional[str] = None) -> ChatMessage:
        """Add a message to a session.
        
        Args:
            source: Message source - 'web' or 'telegram' (None for legacy messages)
        """
        # Convert todo_list to JSON string for storage
        todo_list_json = json.dumps(todo_list) if todo_list else None
        
        message = ChatMessage(
            id=str(uuid.uuid4())[:8],
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now().isoformat(),
            image_id=image_id,
            status=status,
            todo_list=todo_list_json,
            tokens=tokens,
            model_name=model_name,
            source=source,
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_messages (id, session_id, role, content, created_at, image_id, status, todo_list, tokens, model_name, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (message.id, message.session_id, message.role, message.content,
                  message.created_at, message.image_id, message.status, message.todo_list,
                  message.tokens, message.model_name, message.source))

            # Update session title if this is the first user message
            if role == "user":
                cursor.execute("""
                    UPDATE chat_sessions
                    SET title = CASE WHEN title = '' THEN ? ELSE title END,
                        updated_at = ?
                    WHERE id = ?
                """, (content[:50], datetime.now().isoformat(), session_id))

        return message

    def update_message(self, message_id: str, content: Optional[str] = None,
                       status: Optional[str] = None, todo_list: Optional[list] = None,
                       tokens: Optional[int] = None, model_name: Optional[str] = None) -> bool:
        """Update message fields (content, status, todo_list, tokens, model_name)."""
        updates = []
        values = []
        
        if content is not None:
            updates.append("content = ?")
            values.append(content)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if todo_list is not None:
            updates.append("todo_list = ?")
            values.append(json.dumps(todo_list))
        if tokens is not None:
            updates.append("tokens = ?")
            values.append(tokens)
        if model_name is not None:
            updates.append("model_name = ?")
            values.append(model_name)
        
        if not updates:
            return False
        
        values.append(message_id)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE chat_messages SET {', '.join(updates)} WHERE id = ?", values)
            return cursor.rowcount > 0

    def get_messages(self, session_id: str, limit: int = 100) -> List[ChatMessage]:
        """Get messages for a session."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM (SELECT rowid AS sequence,* FROM chat_messages
                WHERE session_id = ? ORDER BY rowid DESC LIMIT ?) ORDER BY sequence ASC
            """, (session_id, limit))
            return [ChatMessage(**{k: row[k] for k in row.keys() if k != 'sequence'}) for row in cursor.fetchall()]

    def get_context_messages(self, session_id: str, through_id: str, limit: int = 40) -> List[ChatMessage]:
        """Latest messages through a stable boundary, including equal-time inserts."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM (
                    SELECT rowid AS sequence, * FROM chat_messages
                    WHERE session_id = ? AND rowid <= (
                        SELECT rowid FROM chat_messages WHERE id = ? AND session_id = ?
                    ) ORDER BY rowid DESC LIMIT ?
                ) ORDER BY sequence ASC
            """, (session_id, through_id, session_id, limit)).fetchall()
            return [ChatMessage(**{k: row[k] for k in row.keys() if k != 'sequence'}) for row in rows]

    def get_message(self, message_id: str) -> Optional[ChatMessage]:
        """Get a specific message."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,))
            row = cursor.fetchone()
            if row:
                return ChatMessage(**dict(row))
            return None

    # ========== Log Operations ==========

    def add_log(self, session_id: str, message_id: str, content: str, log_type: str = "info") -> ChatLog:
        """Add a log entry."""
        log = ChatLog(
            id=str(uuid.uuid4())[:8],
            session_id=session_id,
            message_id=message_id,
            content=content,
            created_at=datetime.now().isoformat(),
            log_type=log_type,
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_logs (id, session_id, message_id, content, created_at, log_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (log.id, log.session_id, log.message_id, log.content, log.created_at, log.log_type))

        return log

    def get_logs(self, session_id: str, message_id: Optional[str] = None, limit: int = 500) -> List[ChatLog]:
        """Get logs for a session or specific message."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if message_id:
                cursor.execute("""
                    SELECT * FROM chat_logs
                    WHERE session_id = ? AND message_id = ?
                    ORDER BY created_at ASC LIMIT ?
                """, (session_id, message_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM chat_logs
                    WHERE session_id = ?
                    ORDER BY created_at ASC LIMIT ?
                """, (session_id, limit))
            return [ChatLog(**dict(row)) for row in cursor.fetchall()]

    # ========== Screenshot Operations ==========

    def add_screenshot(self, session_id: str, message_id: str, image_data: bytes, description: str = "") -> ChatScreenshot:
        """Add a screenshot."""
        screenshot = ChatScreenshot(
            id=str(uuid.uuid4())[:8],
            session_id=session_id,
            message_id=message_id,
            image_data=image_data,
            created_at=datetime.now().isoformat(),
            description=description,
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_screenshots (id, session_id, message_id, image_data, created_at, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (screenshot.id, screenshot.session_id, screenshot.message_id,
                  screenshot.image_data, screenshot.created_at, screenshot.description))

        logger.info(f"Saved screenshot {screenshot.id} for session {session_id}")
        return screenshot

    def get_screenshot(self, screenshot_id: str) -> Optional[ChatScreenshot]:
        """Get a screenshot by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chat_screenshots WHERE id = ?", (screenshot_id,))
            row = cursor.fetchone()
            if row:
                return ChatScreenshot(**dict(row))
            return None

    def get_screenshots(self, session_id: str, message_id: Optional[str] = None) -> List[Dict]:
        """Get screenshot metadata for a session (without image data)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if message_id:
                cursor.execute("""
                    SELECT id, session_id, message_id, created_at, description
                    FROM chat_screenshots
                    WHERE session_id = ? AND message_id = ?
                    ORDER BY created_at ASC
                """, (session_id, message_id))
            else:
                cursor.execute("""
                    SELECT id, session_id, message_id, created_at, description
                    FROM chat_screenshots
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                """, (session_id,))

            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d['image_url'] = f"/api/chat/screenshots/{d['id']}"
                results.append(d)
            return results

    # ========== Session Detail ==========

    def get_session_detail(self, session_id: str) -> Optional[Dict]:
        """Get full session detail including messages, logs, and screenshots."""
        session = self.get_session(session_id)
        if not session:
            return None

        messages = self.get_messages(session_id, limit=-1)
        logs = self.get_logs(session_id, limit=5000)  # Increased limit to ensure all logs are returned
        screenshots = self.get_screenshots(session_id)

        # Group logs and screenshots by message_id
        logs_by_message = {}
        for log in logs:
            if log.message_id not in logs_by_message:
                logs_by_message[log.message_id] = []
            logs_by_message[log.message_id].append(log.to_dict())

        screenshots_by_message = {}
        for screenshot in screenshots:
            if screenshot['message_id'] not in screenshots_by_message:
                screenshots_by_message[screenshot['message_id']] = []
            screenshots_by_message[screenshot['message_id']].append(screenshot)

        # Build detailed messages
        detailed_messages = []
        context_events = {e['message_id']: e for e in self.context_events(session_id)}
        for msg in messages:
            msg_dict = msg.to_dict()
            if msg.id in context_events:
                msg_dict['context_event'] = context_events[msg.id]
            msg_dict['logs'] = logs_by_message.get(msg.id, [])
            msg_dict['screenshots'] = screenshots_by_message.get(msg.id, [])
            detailed_messages.append(msg_dict)

        return {
            "session": session.to_dict(),
            "messages": detailed_messages,
            "total_logs": len(logs),
            "total_screenshots": len(screenshots),
        }

    # ========== Cleanup ==========

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Delete sessions older than specified days."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Get old session IDs
            cursor.execute("SELECT id FROM chat_sessions WHERE updated_at < ?", (cutoff,))
            old_ids = [row['id'] for row in cursor.fetchall()]

            if not old_ids:
                return 0

            placeholders = ",".join("?" * len(old_ids))

            # Delete related data
            cursor.execute(f"DELETE FROM chat_screenshots WHERE session_id IN ({placeholders})", old_ids)
            cursor.execute(f"DELETE FROM chat_logs WHERE session_id IN ({placeholders})", old_ids)
            cursor.execute(f"DELETE FROM chat_messages WHERE session_id IN ({placeholders})", old_ids)
            cursor.execute(f"DELETE FROM chat_context_events WHERE session_id IN ({placeholders})", old_ids)
            cursor.execute(f"DELETE FROM chat_context_status WHERE session_id IN ({placeholders})", old_ids)
            cursor.execute(f"DELETE FROM chat_sessions WHERE id IN ({placeholders})", old_ids)

            logger.info(f"Cleaned up {len(old_ids)} old chat sessions")
            return len(old_ids)


# Global instance
chat_storage = ChatStorage()
