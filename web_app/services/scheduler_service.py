# -*- coding: utf-8 -*-
"""
Scheduler service for managing scheduled tasks.
Wraps the existing scheduler functionality for web use.
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gui_app.scheduler import ScheduledTask, ScheduleType

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled tasks without Qt dependencies."""

    def __init__(self):
        self.tasks: dict[str, ScheduledTask] = {}
        self.running_tasks: set[str] = set()
        self.config_file = Path.home() / ".autoglm" / "scheduled_tasks.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        self._check_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable[[str, str], None]] = []
        self._running = False

        self._load_tasks()

    def _load_tasks(self):
        """Load tasks from config file."""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.tasks = {
                    task_id: ScheduledTask.from_dict(task_data)
                    for task_id, task_data in data.items()
                }
            except Exception as e:
                logger.error(f"Error loading scheduled tasks: {e}")
                self.tasks = {}

    def _save_tasks(self):
        """Save tasks to config file."""
        data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
        self.config_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_task_callback(self, callback: Callable[[str, str], None]):
        """Add a callback for when tasks are triggered. Receives (task_id, task_content)."""
        self._callbacks.append(callback)

    def remove_task_callback(self, callback: Callable[[str, str], None]):
        """Remove a task callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self):
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._update_all_next_runs()
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None
        logger.info("Scheduler stopped")

    async def _check_loop(self):
        """Main loop for checking scheduled tasks."""
        while self._running:
            try:
                await self._check_tasks()
            except Exception as e:
                logger.error(f"Error in scheduler check loop: {e}")
            await asyncio.sleep(30)  # Check every 30 seconds

    async def _check_tasks(self):
        """Check and trigger tasks that should run."""
        for task in self.tasks.values():
            if task.should_run_now() and task.id not in self.running_tasks:
                # Mark as running
                self.running_tasks.add(task.id)

                # Mark as run
                task.last_run = datetime.now().isoformat()
                task.run_count += 1
                task.update_next_run()

                # For one-time tasks, disable after run
                if task.schedule_type == ScheduleType.ONCE.value:
                    task.enabled = False

                self._save_tasks()

                # Trigger callbacks
                for callback in self._callbacks:
                    try:
                        callback(task.id, task.task_content)
                    except Exception as e:
                        logger.error(f"Error in task callback: {e}")

    def _update_all_next_runs(self):
        """Update next_run for all tasks."""
        for task in self.tasks.values():
            task.update_next_run()
        self._save_tasks()

    def add_task(self, task: ScheduledTask) -> str:
        """Add a new scheduled task."""
        task.update_next_run()
        self.tasks[task.id] = task
        self._save_tasks()
        return task.id

    def update_task(self, task: ScheduledTask) -> bool:
        """Update an existing task."""
        if task.id not in self.tasks:
            return False
        task.update_next_run()
        self.tasks[task.id] = task
        self._save_tasks()
        return True

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            return True
        return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[ScheduledTask]:
        """Get all tasks sorted by next run time."""
        return sorted(
            self.tasks.values(),
            key=lambda t: t.next_run if t.next_run else "9999"
        )

    def get_all_tasks_dict(self) -> list[dict]:
        """Get all tasks as dictionaries."""
        return [t.to_dict() for t in self.get_all_tasks()]

    def set_task_enabled(self, task_id: str, enabled: bool) -> bool:
        """Enable or disable a task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = enabled
            if enabled:
                self.tasks[task_id].update_next_run()
            self._save_tasks()
            return True
        return False

    def mark_task_finished(self, task_id: str):
        """Mark a task as finished running."""
        self.running_tasks.discard(task_id)

    def run_task_now(self, task_id: str) -> bool:
        """Manually trigger a task to run immediately."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        # Mark as running
        self.running_tasks.add(task.id)

        task.last_run = datetime.now().isoformat()
        task.run_count += 1
        task.update_next_run()
        self._save_tasks()

        # Trigger callbacks
        for callback in self._callbacks:
            try:
                callback(task.id, task.task_content)
            except Exception as e:
                logger.error(f"Error in task callback: {e}")

        return True


# Global service instance
scheduler_service = SchedulerService()
