# -*- coding: utf-8 -*-
"""
Scheduler service for managing scheduled tasks.
Uses SQLite database for storage instead of JSON files.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from web_app.models.scheduler import ScheduledTask, ScheduleType
from web_app.services.scheduler_storage import scheduler_storage

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled tasks with database storage."""

    def __init__(self):
        self.tasks: dict[str, ScheduledTask] = {}
        self.running_tasks: set[str] = set()
        self._storage = scheduler_storage

        self._check_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable[[str, str], None]] = []
        self._running = False
        self._telegram_bot = None  # Will be set by main.py

        self._load_tasks()

    def _load_tasks(self):
        """Load tasks from database."""
        try:
            self.tasks = self._storage.get_all_tasks()
            logger.info(f"Loaded {len(self.tasks)} scheduled tasks from database")
        except Exception as e:
            logger.error(f"Error loading scheduled tasks: {e}")
            self.tasks = {}

    def _save_tasks(self):
        """Save all tasks to database."""
        self._storage.save_all_tasks(self.tasks)

    def add_task_log(self, task_id: str, success: bool, message: str, details: str = ""):
        """Add a log entry for a task execution."""
        # Smart truncation: if details are too long, keep both beginning and end
        max_length = 50000
        if details and len(details) > max_length:
            truncated_details = (
                details[:40000] + 
                "\n\n... [中间部分已省略] ...\n\n" + 
                details[-9000:]
            )
        else:
            truncated_details = details if details else ""

        # Save to database
        self._storage.add_log(task_id, success, message, truncated_details)
        
        # Send notification to Telegram bot (async, non-blocking)
        if self._telegram_bot:
            asyncio.create_task(self._send_task_notification(task_id, success, message, details))

    def get_task_logs(self, task_id: str, limit: int = 20) -> list[dict]:
        """Get execution logs for a task."""
        return self._storage.get_task_logs(task_id, limit)

    def get_all_logs(self, limit: int = 50) -> list[dict]:
        """Get all execution logs across all tasks, sorted by time."""
        return self._storage.get_all_logs(limit)

    def clear_task_logs(self, task_id: str):
        """Clear logs for a specific task."""
        self._storage.clear_task_logs(task_id)

    def clear_all_logs(self):
        """Clear all execution logs."""
        self._storage.clear_all_logs()

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

    def _is_manual_task_running(self) -> tuple[bool, str]:
        """
        检查是否有手动任务或 Chat 任务正在运行。

        Returns:
            (is_running, task_info) 元组
        """
        try:
            from web_app.services.task_service import task_service

            current_task = task_service.get_current_task()
            if current_task and current_task.status == "running":
                # 只有手动任务和 Chat 任务才阻止定时任务
                if current_task.task_type in ("manual", "chat"):
                    return True, f"{current_task.get_type_display()}: {current_task.task_content[:30]}..."
            return False, ""
        except Exception as e:
            logger.error(f"Error checking manual task status: {e}")
            return False, ""

    async def _check_tasks(self):
        """Check and trigger tasks that should run."""
        for task in self.tasks.values():
            if task.should_run_now() and task.id not in self.running_tasks:
                # 检查是否有手动任务或 Chat 任务正在运行
                manual_running, task_info = self._is_manual_task_running()
                if manual_running:
                    logger.info(f"跳过定时任务 [{task.name}]: 当前有 {task_info} 正在运行")
                    # 记录跳过日志
                    self.add_task_log(
                        task.id,
                        success=False,
                        message=f"跳过执行: 当前有 {task_info} 正在运行",
                        details="定时任务被跳过，等待当前任务完成后在下次调度时间执行"
                    )
                    continue

                # Mark as running
                self.running_tasks.add(task.id)

                # Mark as run
                task.last_run = datetime.now().isoformat()
                task.run_count += 1
                task.update_next_run()

                # For one-time tasks, disable after run
                if task.schedule_type == ScheduleType.ONCE.value:
                    task.enabled = False

                # Save task state to database
                self._storage.save_task(task)

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
        self._storage.save_task(task)
        return task.id

    def update_task(self, task: ScheduledTask) -> bool:
        """Update an existing task."""
        if task.id not in self.tasks:
            return False
        task.update_next_run()
        self.tasks[task.id] = task
        self._storage.save_task(task)
        return True

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._storage.delete_task(task_id)
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
            self._storage.save_task(self.tasks[task_id])
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
        self._storage.save_task(task)

        # Trigger callbacks
        for callback in self._callbacks:
            try:
                callback(task.id, task.task_content)
            except Exception as e:
                logger.error(f"Error in task callback: {e}")

        return True
    
    def set_telegram_bot(self, telegram_bot):
        """Set telegram bot reference for task notifications."""
        self._telegram_bot = telegram_bot
        logger.info("Telegram bot reference set for scheduler notifications")
    
    async def _send_task_notification(self, task_id: str, success: bool, message: str, details: str):
        """Send task result notification to Telegram bot."""
        try:
            task = self.tasks.get(task_id)
            if not task:
                return
            
            # Format notification message
            status_icon = "✅" if success else "❌"
            notification = f"{status_icon} **定时任务执行结果**\\n\\n"
            notification += f"任务名称: `{task.name}`\\n"
            notification += f"任务内容: {task.task_content[:50]}...\\n" if len(task.task_content) > 50 else f"任务内容: {task.task_content}\\n"
            notification += f"执行状态: {message}\\n"
            
            if details:
                # Truncate details for notification (keep it short)
                summary = details[:300] + "..." if len(details) > 300 else details
                # Escape markdown special characters in details
                summary = summary.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                notification += f"\\n详情摘要:\\n```\\n{summary}\\n```"
            
            # Send to all authorized users
            await self._telegram_bot.send_system_notification(notification)
            logger.info(f"Task notification sent for task {task_id}")
            
        except Exception as e:
            logger.error(f"Error sending task notification for {task_id}: {e}")


# Global service instance
scheduler_service = SchedulerService()
