# -*- coding: utf-8 -*-
"""
SQLite-based storage for scheduled tasks and execution logs.
Migrates from JSON files to database for better performance.
"""

import sqlite3
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager
from dataclasses import asdict

from web_app.models.scheduler import ScheduledTask

logger = logging.getLogger(__name__)


class SchedulerStorage:
    """SQLite storage for scheduled tasks and logs."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".autoglm" / "chat.db"  # Use same DB as chat
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.config_dir = Path.home() / ".autoglm"
        self._init_db()
        self._migrate_from_json()

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

            # Scheduled tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    task_content TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    schedule_type TEXT DEFAULT 'daily',
                    run_at TEXT DEFAULT '',
                    interval_minutes INTEGER DEFAULT 60,
                    daily_time TEXT DEFAULT '09:00',
                    weekly_days TEXT DEFAULT '[0]',
                    weekly_time TEXT DEFAULT '09:00',
                    monthly_day INTEGER DEFAULT 1,
                    monthly_time TEXT DEFAULT '09:00',
                    last_run TEXT DEFAULT '',
                    next_run TEXT DEFAULT '',
                    run_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    devices TEXT DEFAULT '[]'
                )
            """)

            # Scheduler logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduler_logs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    message TEXT DEFAULT '',
                    details TEXT DEFAULT '',
                    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_logs_task ON scheduler_logs(task_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_logs_timestamp ON scheduler_logs(timestamp DESC)")

            logger.info("Scheduler database tables initialized")

    def _migrate_from_json(self):
        """Migrate existing JSON data to database (one-time)."""
        tasks_file = self.config_dir / "scheduled_tasks.json"
        logs_file = self.config_dir / "scheduler_logs.json"
        migrated_marker = self.config_dir / ".scheduler_migrated"

        # Skip if already migrated
        if migrated_marker.exists():
            return

        migrated_count = 0

        # Migrate tasks
        if tasks_file.exists():
            try:
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)
                
                with self._get_conn() as conn:
                    cursor = conn.cursor()
                    for task_id, task_dict in tasks_data.items():
                        # Check if already exists
                        cursor.execute("SELECT id FROM scheduled_tasks WHERE id = ?", (task_id,))
                        if cursor.fetchone():
                            continue
                        
                        # Insert task
                        cursor.execute("""
                            INSERT INTO scheduled_tasks (
                                id, name, task_content, enabled, schedule_type,
                                run_at, interval_minutes, daily_time, weekly_days,
                                weekly_time, monthly_day, monthly_time, last_run,
                                next_run, run_count, created_at, devices
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            task_dict.get('id', task_id),
                            task_dict.get('name', ''),
                            task_dict.get('task_content', ''),
                            1 if task_dict.get('enabled', True) else 0,
                            task_dict.get('schedule_type', 'daily'),
                            task_dict.get('run_at', ''),
                            task_dict.get('interval_minutes', 60),
                            task_dict.get('daily_time', '09:00'),
                            json.dumps(task_dict.get('weekly_days', [0])),
                            task_dict.get('weekly_time', '09:00'),
                            task_dict.get('monthly_day', 1),
                            task_dict.get('monthly_time', '09:00'),
                            task_dict.get('last_run', ''),
                            task_dict.get('next_run', ''),
                            task_dict.get('run_count', 0),
                            task_dict.get('created_at', datetime.now().isoformat()),
                            json.dumps(task_dict.get('devices', []))
                        ))
                        migrated_count += 1
                
                logger.info(f"Migrated {migrated_count} scheduled tasks from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate tasks: {e}")

        # Migrate logs
        if logs_file.exists():
            try:
                with open(logs_file, 'r', encoding='utf-8') as f:
                    logs_data = json.load(f)
                
                log_count = 0
                with self._get_conn() as conn:
                    cursor = conn.cursor()
                    for task_id, task_logs in logs_data.items():
                        for log_entry in task_logs:
                            log_id = str(uuid.uuid4())[:8]
                            cursor.execute("""
                                INSERT INTO scheduler_logs (id, task_id, timestamp, success, message, details)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (
                                log_id,
                                task_id,
                                log_entry.get('timestamp', ''),
                                1 if log_entry.get('success', False) else 0,
                                log_entry.get('message', ''),
                                log_entry.get('details', '')
                            ))
                            log_count += 1
                
                logger.info(f"Migrated {log_count} scheduler logs from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate logs: {e}")

        # Mark as migrated
        if migrated_count > 0:
            migrated_marker.write_text(datetime.now().isoformat())
            logger.info("Scheduler migration completed")

    # ========== Task Operations ==========

    def get_all_tasks(self) -> Dict[str, ScheduledTask]:
        """Get all scheduled tasks."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_tasks")
            
            tasks = {}
            for row in cursor.fetchall():
                task = self._row_to_task(row)
                tasks[task.id] = task
            return tasks

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_task(row)
            return None

    def save_task(self, task: ScheduledTask):
        """Save or update a task."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO scheduled_tasks (
                    id, name, task_content, enabled, schedule_type,
                    run_at, interval_minutes, daily_time, weekly_days,
                    weekly_time, monthly_day, monthly_time, last_run,
                    next_run, run_count, created_at, devices
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.name,
                task.task_content,
                1 if task.enabled else 0,
                task.schedule_type,
                task.run_at,
                task.interval_minutes,
                task.daily_time,
                json.dumps(task.weekly_days),
                task.weekly_time,
                task.monthly_day,
                task.monthly_time,
                task.last_run,
                task.next_run,
                task.run_count,
                task.created_at,
                json.dumps(task.devices)
            ))

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its logs."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scheduler_logs WHERE task_id = ?", (task_id,))
            cursor.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    def save_all_tasks(self, tasks: Dict[str, ScheduledTask]):
        """Save all tasks (bulk update)."""
        for task in tasks.values():
            self.save_task(task)

    def _row_to_task(self, row: sqlite3.Row) -> ScheduledTask:
        """Convert database row to ScheduledTask."""
        return ScheduledTask(
            id=row['id'],
            name=row['name'],
            task_content=row['task_content'],
            enabled=bool(row['enabled']),
            schedule_type=row['schedule_type'],
            run_at=row['run_at'] or '',
            interval_minutes=row['interval_minutes'],
            daily_time=row['daily_time'],
            weekly_days=json.loads(row['weekly_days']) if row['weekly_days'] else [0],
            weekly_time=row['weekly_time'],
            monthly_day=row['monthly_day'],
            monthly_time=row['monthly_time'],
            last_run=row['last_run'] or '',
            next_run=row['next_run'] or '',
            run_count=row['run_count'],
            created_at=row['created_at'],
            devices=json.loads(row['devices']) if row['devices'] else []
        )

    # ========== Log Operations ==========

    def add_log(self, task_id: str, success: bool, message: str, details: str = "") -> str:
        """Add a log entry for a task execution."""
        log_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scheduler_logs (id, task_id, timestamp, success, message, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (log_id, task_id, timestamp, 1 if success else 0, message, details))
        
        return log_id

    def get_task_logs(self, task_id: str, limit: int = 20) -> List[Dict]:
        """Get logs for a specific task."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM scheduler_logs
                WHERE task_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (task_id, limit))
            
            return [self._row_to_log(row) for row in cursor.fetchall()]

    def get_all_logs(self, limit: int = 50) -> List[Dict]:
        """Get all logs across all tasks, sorted by time."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.*, t.name as task_name
                FROM scheduler_logs l
                LEFT JOIN scheduled_tasks t ON l.task_id = t.id
                ORDER BY l.timestamp DESC
                LIMIT ?
            """, (limit,))
            
            logs = []
            for row in cursor.fetchall():
                log = self._row_to_log(row)
                log['task_name'] = row['task_name'] or 'Unknown Task'
                logs.append(log)
            return logs

    def clear_task_logs(self, task_id: str):
        """Clear logs for a specific task."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scheduler_logs WHERE task_id = ?", (task_id,))

    def clear_all_logs(self):
        """Clear all logs."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scheduler_logs")

    def _row_to_log(self, row: sqlite3.Row) -> Dict:
        """Convert database row to log dict."""
        return {
            'id': row['id'],
            'task_id': row['task_id'],
            'timestamp': row['timestamp'],
            'success': bool(row['success']),
            'message': row['message'],
            'details': row['details']
        }


# Global instance
scheduler_storage = SchedulerStorage()
