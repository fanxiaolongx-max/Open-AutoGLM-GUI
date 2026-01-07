# -*- coding: utf-8 -*-
"""Scheduled tasks manager for automated task execution."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable

from PySide6 import QtCore


class ScheduleType(Enum):
    """Task schedule frequency types."""
    ONCE = "once"           # Run once at specified time
    INTERVAL = "interval"   # Run every N minutes/hours
    DAILY = "daily"         # Run daily at specified time
    WEEKLY = "weekly"       # Run weekly on specified days
    MONTHLY = "monthly"     # Run monthly on specified day


class WeekDay(Enum):
    """Days of the week."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


@dataclass
class GeminiConfig:
    """Configuration for Gemini API."""
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8045/v1"
    api_key: str = "sk-985786ae787d43e6b8d42688f39ed83a"
    model_name: str = "gemini-3-pro-high"
    system_prompt: str = "你是一个智能手机自动化助手。根据用户提供的任务执行结果，分析并生成下一步的任务指令。如果任务已完成，请回复'任务完成'。\n\n重要：你必须严格按照以下格式返回动作指令，不要添加任何解释或说明：\n\n动作格式（必须完全匹配）：\n- 点击：do(action=\"Tap\", element=[x, y])\n- 输入：do(action=\"Type\", text=\"具体内容\")\n- 等待：do(action=\"Wait\", duration=\"3秒\")\n- 滑动：do(action=\"Swipe\", start=[x1, y1], end=[x2, y2])\n- 返回：do(action=\"Back\")\n- 主页：do(action=\"Home\")\n- 完成：finish(message=\"任务完成\")\n\n示例：\n用户：点击微信图标\n你：do(action=\"Tap\", element=[844, 915])\n\n用户：输入密码123\n你：do(action=\"Type\", text=\"123\")\n\n用户：等待3秒\n你：do(action=\"Wait\", duration=\"3秒\")\n\n不要包含任何其他文字、解释或HTML标签！"
    max_rounds: int = 10  # 最大交互轮数，防止无限循环
    temperature: float = 0.7
    max_tokens: int = 4000

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GeminiConfig":
        # 过滤掉不存在的字段
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    task_content: str = ""  # The actual task instruction
    enabled: bool = True
    schedule_type: str = "daily"  # ScheduleType value

    # For ONCE: specific datetime
    run_at: str = ""  # ISO format datetime string

    # For INTERVAL: interval in minutes
    interval_minutes: int = 60

    # For DAILY: time of day (HH:MM)
    daily_time: str = "09:00"

    # For WEEKLY: days of week (0=Monday, 6=Sunday) and time
    weekly_days: list = field(default_factory=lambda: [0])  # Monday by default
    weekly_time: str = "09:00"

    # For MONTHLY: day of month and time
    monthly_day: int = 1
    monthly_time: str = "09:00"

    # Tracking
    last_run: str = ""  # ISO format datetime
    next_run: str = ""  # ISO format datetime
    run_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Gemini feedback loop settings
    use_gemini_feedback: bool = False  # 是否启用 Gemini 反馈循环
    gemini_max_rounds: int = 5  # 单次任务最大交互轮数

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        # 过滤掉不存在的字段，确保向后兼容
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    def calculate_next_run(self) -> datetime | None:
        """Calculate the next run time based on schedule type."""
        now = datetime.now()

        if self.schedule_type == ScheduleType.ONCE.value:
            if self.run_at:
                run_time = datetime.fromisoformat(self.run_at)
                return run_time if run_time > now else None
            return None

        elif self.schedule_type == ScheduleType.INTERVAL.value:
            if self.last_run:
                last = datetime.fromisoformat(self.last_run)
                return last + timedelta(minutes=self.interval_minutes)
            return now + timedelta(minutes=self.interval_minutes)

        elif self.schedule_type == ScheduleType.DAILY.value:
            hour, minute = map(int, self.daily_time.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif self.schedule_type == ScheduleType.WEEKLY.value:
            if not self.weekly_days:
                return None
            hour, minute = map(int, self.weekly_time.split(":"))

            # Find the next matching weekday
            for days_ahead in range(8):  # Check up to 7 days ahead
                check_date = now + timedelta(days=days_ahead)
                if check_date.weekday() in self.weekly_days:
                    next_run = check_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if next_run > now:
                        return next_run
            return None

        elif self.schedule_type == ScheduleType.MONTHLY.value:
            hour, minute = map(int, self.monthly_time.split(":"))

            # Try this month
            try:
                next_run = now.replace(day=self.monthly_day, hour=hour, minute=minute, second=0, microsecond=0)
                if next_run > now:
                    return next_run
            except ValueError:
                pass  # Day doesn't exist in this month

            # Try next month
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)

            try:
                return next_month.replace(day=self.monthly_day, hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                return None

        return None

    def update_next_run(self):
        """Update the next_run field."""
        next_time = self.calculate_next_run()
        self.next_run = next_time.isoformat() if next_time else ""

    def should_run_now(self) -> bool:
        """Check if the task should run now."""
        if not self.enabled:
            return False
        if not self.next_run:
            return False

        next_time = datetime.fromisoformat(self.next_run)
        return datetime.now() >= next_time


class ScheduledTasksManager(QtCore.QObject):
    """Manager for scheduled tasks with persistent storage."""

    task_triggered = QtCore.Signal(str, str)  # task_id, task_content
    task_triggered_with_gemini = QtCore.Signal(str, str, bool, int)  # task_id, task_content, use_gemini, max_rounds
    tasks_changed = QtCore.Signal()
    gemini_config_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks: dict[str, ScheduledTask] = {}
        self.config_file = Path.home() / ".autoglm" / "scheduled_tasks.json"
        self.gemini_config_file = Path.home() / ".autoglm" / "gemini_config.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Gemini configuration
        self.gemini_config = GeminiConfig()
        self._load_gemini_config()

        # Timer for checking scheduled tasks
        self.check_timer = QtCore.QTimer(self)
        self.check_timer.timeout.connect(self._check_tasks)
        self.check_timer.setInterval(30000)  # Check every 30 seconds

        self._load_tasks()

    def start(self):
        """Start the scheduler."""
        self._update_all_next_runs()
        self.check_timer.start()

    def stop(self):
        """Stop the scheduler."""
        self.check_timer.stop()

    def _load_gemini_config(self):
        """Load Gemini configuration from file."""
        if self.gemini_config_file.exists():
            try:
                data = json.loads(self.gemini_config_file.read_text(encoding="utf-8"))
                self.gemini_config = GeminiConfig.from_dict(data)
            except Exception:
                self.gemini_config = GeminiConfig()

    def _save_gemini_config(self):
        """Save Gemini configuration to file."""
        self.gemini_config_file.write_text(
            json.dumps(self.gemini_config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_gemini_config(self) -> GeminiConfig:
        """Get current Gemini configuration."""
        return self.gemini_config

    def update_gemini_config(self, config: GeminiConfig):
        """Update Gemini configuration."""
        self.gemini_config = config
        self._save_gemini_config()
        self.gemini_config_changed.emit()

    def call_gemini_api(self, messages: list[dict]) -> str | None:
        """Call Gemini API and return the response content.

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            Response content string, or None if failed
        """
        if not self.gemini_config.enabled or not self.gemini_config.api_key:
            return None

        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.gemini_config.base_url,
                api_key=self.gemini_config.api_key
            )

            # Add system prompt if configured
            full_messages = []
            if self.gemini_config.system_prompt:
                full_messages.append({
                    "role": "system",
                    "content": self.gemini_config.system_prompt
                })
            full_messages.extend(messages)

            response = client.chat.completions.create(
                model=self.gemini_config.model_name,
                messages=full_messages,
                temperature=getattr(self.gemini_config, 'temperature', 0.7),
                max_tokens=getattr(self.gemini_config, 'max_tokens', 4000)
            )

            return response.choices[0].message.content
        except Exception as e:
            print(f"Gemini API error: {e}")
            return None

    def _load_tasks(self):
        """Load tasks from config file."""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.tasks = {
                    task_id: ScheduledTask.from_dict(task_data)
                    for task_id, task_data in data.items()
                }
            except Exception:
                self.tasks = {}

    def _save_tasks(self):
        """Save tasks to config file."""
        data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
        self.config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_all_next_runs(self):
        """Update next_run for all tasks."""
        for task in self.tasks.values():
            task.update_next_run()
        self._save_tasks()

    def _check_tasks(self):
        """Check and trigger tasks that should run."""
        for task in self.tasks.values():
            if task.should_run_now():
                # Mark as run
                task.last_run = datetime.now().isoformat()
                task.run_count += 1
                task.update_next_run()

                # For one-time tasks, disable after run
                if task.schedule_type == ScheduleType.ONCE.value:
                    task.enabled = False

                self._save_tasks()

                # Emit appropriate signal based on Gemini feedback setting
                if task.use_gemini_feedback and self.gemini_config.enabled:
                    self.task_triggered_with_gemini.emit(
                        task.id, task.task_content, True, task.gemini_max_rounds
                    )
                else:
                    self.task_triggered.emit(task.id, task.task_content)

    def add_task(self, task: ScheduledTask) -> str:
        """Add a new scheduled task."""
        task.update_next_run()
        self.tasks[task.id] = task
        self._save_tasks()
        self.tasks_changed.emit()
        return task.id

    def update_task(self, task: ScheduledTask):
        """Update an existing task."""
        task.update_next_run()
        self.tasks[task.id] = task
        self._save_tasks()
        self.tasks_changed.emit()

    def delete_task(self, task_id: str):
        """Delete a task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            self.tasks_changed.emit()

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[ScheduledTask]:
        """Get all tasks sorted by next run time."""
        return sorted(
            self.tasks.values(),
            key=lambda t: t.next_run if t.next_run else "9999"
        )

    def set_task_enabled(self, task_id: str, enabled: bool):
        """Enable or disable a task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = enabled
            if enabled:
                self.tasks[task_id].update_next_run()
            self._save_tasks()
            self.tasks_changed.emit()

    def run_task_now(self, task_id: str):
        """Manually trigger a task to run immediately."""
        task = self.tasks.get(task_id)
        if task:
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            task.update_next_run()
            self._save_tasks()

            # Emit appropriate signal based on Gemini feedback setting
            if task.use_gemini_feedback and self.gemini_config.enabled:
                self.task_triggered_with_gemini.emit(
                    task.id, task.task_content, True, task.gemini_max_rounds
                )
            else:
                self.task_triggered.emit(task.id, task.task_content)
