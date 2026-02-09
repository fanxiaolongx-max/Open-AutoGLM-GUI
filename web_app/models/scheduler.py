# -*- coding: utf-8 -*-
"""
Scheduled task data models.
Pure data classes without Qt dependencies.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum


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

    # 执行设备列表
    devices: list = field(default_factory=list)  # 设备 ID 列表，支持多选

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
