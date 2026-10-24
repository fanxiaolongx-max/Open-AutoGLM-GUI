# -*- coding: utf-8 -*-
"""
Task execution service for running automation tasks.
"""

import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logger = logging.getLogger(__name__)


class ChatSessionContext:
    """Context for managing chat session during task execution."""

    def __init__(self):
        self.session_id: Optional[str] = None
        self.message_id: Optional[str] = None
        self.device_id: Optional[str] = None

    def clear(self):
        self.session_id = None
        self.message_id = None
        self.device_id = None


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    WAITING_FOR_USER = "waiting_for_user"
    INTERRUPTED = "interrupted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class TaskType(Enum):
    """Task type with priority (higher value = higher priority)."""
    MANUAL = "manual"      # 手动任务，优先级最低
    SCHEDULED = "scheduled"  # 定时任务，优先级中等
    CHAT = "chat"          # Chat任务，优先级最高

    @property
    def priority(self) -> int:
        """Get priority value (higher = more important)."""
        priorities = {
            "manual": 1,
            "scheduled": 2,
            "chat": 3,
        }
        return priorities.get(self.value, 0)


@dataclass
class TaskResult:
    """Result of a task execution."""
    id: str
    device_id: str
    status: str
    start_time: str
    end_time: str = ""
    success: bool = False
    message: str = ""
    logs: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskExecution:
    """Represents a running or completed task."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_content: str = ""
    device_ids: list = field(default_factory=list)
    status: str = TaskStatus.PENDING.value
    start_time: str = ""
    end_time: str = ""
    results: list = field(default_factory=list)  # List of TaskResult dicts
    logs: list = field(default_factory=list)
    progress: int = 0  # 0-100
    is_scheduled: bool = False  # Whether this is a scheduled task
    send_email: bool = True  # Whether to send email after completion
    task_type: str = TaskType.MANUAL.value  # 任务类型
    initial_lock_state: Optional[bool] = None  # Initial lock state detected (for subtask chains)
    chat_session_id: Optional[str] = None  # Chat session ID for this task
    chat_message_id: Optional[str] = None  # Chat message ID for this task

    def to_dict(self) -> dict:
        return asdict(self)

    def get_type_display(self) -> str:
        """获取任务类型的中文显示名称."""
        type_names = {
            TaskType.MANUAL.value: "手动任务",
            TaskType.SCHEDULED.value: "定时任务",
            TaskType.CHAT.value: "Chat任务",
        }
        return type_names.get(self.task_type, "未知任务")


class TaskService:
    """Service for executing automation tasks."""

    def __init__(self):
        self._current_task: Optional[TaskExecution] = None  # For backward compatibility
        self._running_tasks: dict[str, TaskExecution] = {}  # task_id -> TaskExecution for parallel support
        self._task_history: list[TaskExecution] = []
        self._stop_requested = False
        self._log_callbacks: list[Callable[[str, str], None]] = []
        self._progress_callbacks: list[Callable[[str, int], None]] = []
        self._finished_callbacks: list[Callable[[str, bool, str, Optional[str]], None]] = []
        self._token_callbacks: list[Callable[[str, int, int, int], None]] = []  # task_id, input, output, total
        self._running_agents: dict[str, asyncio.Task] = {}
        self._agent_instances: dict[str, any] = {}  # Store agent instances for cleanup
        self._chat_context = ChatSessionContext()  # Chat session context for SQLite storage

    def add_log_callback(self, callback: Callable[[str, str, Optional[str]], None]):
        """Add a callback for log messages. Callback receives (task_id, message, task_type)."""
        self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: Callable[[str, str, Optional[str]], None]):
        """Remove a log callback."""
        if callback in self._log_callbacks:
            self._log_callbacks.remove(callback)

    def add_progress_callback(self, callback: Callable[[str, int], None]):
        """Add a callback for progress updates. Callback receives (task_id, progress)."""
        self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: Callable[[str, int], None]):
        """Remove a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    def add_token_callback(self, callback: Callable[[str, int, int, int], None]):
        """Add a callback for token usage. Callback receives (task_id, input_tokens, output_tokens, total_tokens)."""
        self._token_callbacks.append(callback)

    def remove_token_callback(self, callback: Callable[[str, int, int, int], None]):
        """Remove a token callback."""
        if callback in self._token_callbacks:
            self._token_callbacks.remove(callback)

    def add_finished_callback(self, callback: Callable[[str, bool, str, Optional[str], Optional[str], Optional[str]], None]):
        """Add a callback for task completion. Callback receives (task_id, success, message, screenshot, screenshot_id, task_type)."""
        self._finished_callbacks.append(callback)

    def remove_finished_callback(self, callback: Callable[[str, bool, str, Optional[str], Optional[str], Optional[str]], None]):
        """Remove a finished callback."""
        if callback in self._finished_callbacks:
            self._finished_callbacks.remove(callback)

    def _emit_finished(self, task_id: str, success: bool, message: str, screenshot: Optional[str] = None, screenshot_id: Optional[str] = None, task_type: Optional[str] = None):
        """Emit task finished event to all callbacks."""
        # screenshot 参数保留以保持兼容性，但不再使用 base64，只使用 screenshot_id
        for callback in self._finished_callbacks:
            try:
                callback(task_id, success, message, None, screenshot_id, task_type)  # 不传递 base64 截图
            except Exception:
                pass

    def _emit_log(self, task_id: str, message: str):
        """Emit a log message to all callbacks and store in current task."""
        # Store log in current task for email report
        # Use _running_tasks dict to support parallel execution
        task = self._running_tasks.get(task_id) or (self._current_task if self._current_task and self._current_task.id == task_id else None)
        task_type = None

        if task:
            timestamp = datetime.now().strftime("%H:%M:%S")
            task.logs.append(f"[{timestamp}] {message}")
            task_type = task.task_type

            # For chat tasks, also save to SQLite
            # Use task's own session/message IDs (not shared _chat_context) to avoid parallel mode issues
            if task_type == TaskType.CHAT.value and task.chat_session_id and task.chat_message_id:
                try:
                    from web_app.services.chat_service import chat_service
                    # Determine log type based on content
                    log_type = "info"
                    if "❌" in message or "Error" in message or "error" in message:
                        log_type = "error"
                    elif "🧠" in message or "思考" in message or "think" in message.lower():
                        log_type = "thinking"
                    elif "🎯" in message or "✅" in message or "点击" in message or "输入" in message:
                        log_type = "action"
                    chat_service.add_log(
                        task.chat_session_id,
                        task.chat_message_id,
                        message,
                        log_type
                    )
                except Exception as e:
                    logger.error(f"Failed to save chat log to SQLite: {e}")

        if task is None:
            from web_app.services.automation_runtime import get_runtime
            record = get_runtime().store.get('task', task_id)
            if record:
                task_type = record['options'].get('task_type','manual')

        for callback in self._log_callbacks:
            try:
                callback(task_id, message, task_type)
            except Exception:
                pass

    def _emit_progress(self, task_id: str, progress: int):
        """Emit progress update to all callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(task_id, progress)
            except Exception:
                pass

    def _emit_tokens(self, task_id: str, input_tokens: int, output_tokens: int, total_tokens: int):
        """Emit token usage update to all callbacks."""
        for callback in self._token_callbacks:
            try:
                callback(task_id, input_tokens, output_tokens, total_tokens)
            except Exception:
                pass

    async def _check_device_connected(self, device_id: str) -> tuple[bool, str]:
        """
        检查设备是否连接。

        Returns:
            (connected, error_message) 元组
        """
        try:
            from phone_agent.device_factory import get_device_factory

            loop = asyncio.get_event_loop()

            def check_sync():
                factory = get_device_factory()
                devices = factory.list_devices()
                for d in devices:
                    if d.device_id == device_id:
                        if d.status == "device":
                            return True, None
                        elif d.status == "offline":
                            return False, f"设备 {device_id} 处于离线状态(offline)"
                        elif d.status == "unauthorized":
                            return False, f"设备 {device_id} 未授权调试(unauthorized)，请在设备上确认USB调试授权"
                        else:
                            return False, f"设备 {device_id} 状态异常: {d.status}"
                return False, f"设备 {device_id} 未连接或已断开"

            return await loop.run_in_executor(None, check_sync)
        except Exception as e:
            return False, f"检查设备连接状态失败: {str(e)}"

    @staticmethod
    def from_runtime(record, include_media=False):
        def iso(value):
            return datetime.fromtimestamp(value).isoformat() if isinstance(value, (int, float)) else (value or "")
        result = TaskExecution(
            id=record['id'], task_content=record['task_content'], device_ids=record['device_ids'],
            status=record['status'], start_time=iso(record['start_time']), end_time=iso(record.get('end_time')),
            results=record.get('results', []), logs=record.get('logs', []), progress=record['progress'],
            task_type=record['options'].get('task_type', 'manual'),
            is_scheduled=record['options'].get('is_scheduled', False),
            send_email=record['options'].get('send_email', True),
            chat_session_id=record['options'].get('session_id'), chat_message_id=record['options'].get('message_id'))
        if include_media:
            from web_app.services.automation_runtime import get_runtime
            store = get_runtime().store
            screenshots, cursor = {}, 0
            while True:
                events = store.events(record['id'],cursor,500)
                for event in events:
                    if event['kind']=='screen' and event['data'].get('final') and event['data'].get('image_id'):
                        data = store.get_image(event['data']['image_id'])
                        if data:
                            screenshots[event['device_id']] = data
                if len(events)<500:
                    break
                cursor=events[-1]['seq']
            if screenshots:
                result._device_screenshots = screenshots
                result._screenshot_data = next(iter(screenshots.values()))
        return result

    async def run_task(self, task_content, device_ids, model_config=None, is_scheduled=False,
                       send_email=True, no_auto_lock=False, restore_lock_to_state=None,
                       task_type='manual', session_id=None, message_id=None, debug_mode=False):
        from web_app.services.automation_runtime import get_runtime
        runtime = get_runtime()
        record = runtime.submit(task_content, device_ids, queue=True, model_config=model_config,
                                is_scheduled=is_scheduled, send_email=send_email,
                                no_auto_lock=no_auto_lock, restore_lock_to_state=restore_lock_to_state,
                                task_type=task_type, session_id=session_id, message_id=message_id,
                                debug_mode=debug_mode)
        return self.from_runtime(await runtime.wait(record['id']), include_media=True)

    async def _send_email_report(self, task: TaskExecution):
        """Send email report after task completion."""
        # Debug log to trace email decision
        logger.info(f"[EMAIL] Task {task.id[:8]} - send_email={task.send_email}, task_type={task.task_type}")

        # Check if email should be sent for this task
        if not task.send_email:
            # Always log when email is skipped for debugging
            self._emit_log(task.id, f"📧 Email skipped (disabled for this task)")
            return

        try:
            from web_app.services.email_service import email_service

            # Calculate success/failed counts
            success_count = sum(1 for r in task.results if r.get("success", False))
            failed_count = len(task.results) - success_count
            total_count = len(task.results)

            # Build details from logs
            details = "\n".join(task.logs) if task.logs else "No logs available"

            # Use screenshot captured before locking
            # Priority: 1) _screenshot_data (Web path), 2) _device_screenshots (Telegram/Bot path)
            screenshot_data = getattr(task, '_screenshot_data', None)
            if not screenshot_data:
                # Try to get screenshot from _device_screenshots (used by Telegram/Bot tasks)
                device_screenshots = getattr(task, '_device_screenshots', None)
                if device_screenshots and isinstance(device_screenshots, dict):
                    # Get the first available screenshot from any device
                    for device_id, ss_data in device_screenshots.items():
                        if ss_data:
                            screenshot_data = ss_data
                            logger.info(f"Using screenshot from device {device_id} for email report")
                            break
            
            # Ensure screenshot_data is bytes (may be base64 string from Telegram path)
            if screenshot_data and isinstance(screenshot_data, str):
                import base64
                try:
                    screenshot_data = base64.b64decode(screenshot_data)
                    logger.info(f"Converted base64 screenshot to bytes for email")
                except Exception as decode_error:
                    logger.warning(f"Failed to decode base64 screenshot: {decode_error}")
                    screenshot_data = None

            # Generate task summary using AI (if agent is available)
            task_summary = None
            try:
                # First, collect any finish messages from task results
                finish_messages = []
                for result in task.results:
                    if result.get("success") and result.get("message"):
                        finish_messages.append(result.get("message"))
                
                # Get agent instance from the first device (for single device tasks)
                # or use any available agent for summary
                agent = None
                if self._agent_instances:
                    # Get first available agent
                    agent = next(iter(self._agent_instances.values()), None)
                
                if agent:
                    self._emit_log(task.id, f"🤖 Generating AI task summary...")
                    ai_summary = agent.generate_task_summary(task.task_content)
                    self._emit_log(task.id, f"✅ Task summary generated")
                    
                    # Combine AI summary with finish messages
                    if finish_messages:
                        # Add finish messages to provide complete context
                        task_summary = f"{ai_summary}\n\n✅ 任务完成详情:\n" + "\n".join(f"• {msg}" for msg in finish_messages)
                    else:
                        task_summary = ai_summary
                elif finish_messages:
                    # No AI agent, but we have finish messages - use them as summary
                    status_text = "成功完成" if success_count == total_count else ("部分完成" if success_count > 0 else "执行失败")
                    task_summary = f"任务「{task.task_content[:30]}」{status_text}。\n\n✅ 任务完成详情:\n" + "\n".join(f"• {msg}" for msg in finish_messages)
                else:
                    # Agent not available and no finish messages, create simple summary
                    status_text = "成功完成" if success_count == total_count else ("部分完成" if success_count > 0 else "执行失败")
                    task_summary = f"任务「{task.task_content[:30]}」{status_text}，共涉及{total_count}个设备。"
            except Exception as e:
                logger.warning(f"Failed to generate task summary: {e}")
                # Fallback summary
                status_text = "完成" if success_count > 0 else "失败"
                task_summary = f"任务{status_text}，详细信息请查看执行日志。"

            # Send report with correct is_scheduled flag and summary
            # Pass device screenshots dict for multi-device tasks
            device_screenshots = getattr(task, '_device_screenshots', None)
            success, message = await asyncio.to_thread(email_service.send_task_report,
                task_name=task.task_content[:50],
                success_count=success_count,
                failed_count=failed_count,
                total_count=total_count,
                details=details,
                screenshot_data=screenshot_data,
                is_scheduled=task.is_scheduled,
                task_summary=task_summary,
                screenshots=device_screenshots,  # Multi-device screenshots dict
            )

            if success:
                self._emit_log(task.id, f"📧 Email report sent successfully")
            else:
                self._emit_log(task.id, f"📧 Email not sent: {message}")
            return success, message
        except Exception as e:
            logger.error(f"Failed to send email report: {e}")
            return False, str(e)

    async def _run_agent(self, agent, task_content, task_id, device_id):
        # Compatibility for integrations; structured outcome is authoritative.
        result = await asyncio.to_thread(agent.run_result, task_content)
        return result.success

    async def stop_all_tasks(self) -> bool:
        from web_app.services.automation_runtime import get_runtime, TERMINAL
        runtime = get_runtime()
        for task in runtime.store.list('task'):
            if task['status'] not in TERMINAL:
                runtime.control(task['id'], 'stop')
        return True

    def get_current_task(self):
        from web_app.services.automation_runtime import get_runtime, TERMINAL
        tasks = [t for t in get_runtime().store.list('task') if t['status'] not in TERMINAL]
        return self.from_runtime(tasks[0]) if tasks else None

    def get_task_status(self):
        current = self.get_current_task()
        return {'running': current is not None, 'task': current.to_dict() if current else None}

    def get_task_history(self, limit=10):
        from web_app.services.automation_runtime import get_runtime
        return [self.from_runtime(t).to_dict() for t in get_runtime().store.list('task')[-limit:]]

    def can_interrupt_current_task(self, new_task_type):
        current = self.get_current_task()
        return bool(current), current.to_dict() if current else None

    async def run_task_parallel(self, task_content, device_ids, model_config=None,
                                is_scheduled=False, send_email=True, no_auto_lock=False,
                                restore_lock_to_state=None, task_type='manual', session_id=None,
                                debug_mode=False):
        from web_app.services.automation_runtime import get_runtime
        runtime = get_runtime()
        task = runtime.submit(task_content, device_ids, parallel=True, queue=True,
                              model_config=model_config, is_scheduled=is_scheduled, send_email=send_email,
                              no_auto_lock=no_auto_lock, restore_lock_to_state=restore_lock_to_state,
                              task_type=task_type, session_id=session_id, debug_mode=debug_mode)
        return self.from_runtime(await runtime.wait(task['id']), include_media=True)


# Global service instance
task_service = TaskService()
