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
        self._current_task: Optional[TaskExecution] = None
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

    def add_finished_callback(self, callback: Callable[[str, bool, str, Optional[str], Optional[str]], None]):
        """Add a callback for task completion. Callback receives (task_id, success, message, screenshot, screenshot_id)."""
        self._finished_callbacks.append(callback)

    def remove_finished_callback(self, callback: Callable[[str, bool, str, Optional[str], Optional[str]], None]):
        """Remove a finished callback."""
        if callback in self._finished_callbacks:
            self._finished_callbacks.remove(callback)

    def _emit_finished(self, task_id: str, success: bool, message: str, screenshot: Optional[str] = None, screenshot_id: Optional[str] = None):
        """Emit task finished event to all callbacks."""
        # screenshot 参数保留以保持兼容性，但不再使用 base64，只使用 screenshot_id
        for callback in self._finished_callbacks:
            try:
                callback(task_id, success, message, None, screenshot_id)  # 不传递 base64 截图
            except Exception:
                pass

    def _emit_log(self, task_id: str, message: str):
        """Emit a log message to all callbacks and store in current task."""
        # Store log in current task for email report
        task_type = None
        if self._current_task and self._current_task.id == task_id:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._current_task.logs.append(f"[{timestamp}] {message}")
            task_type = self._current_task.task_type

            # For chat tasks, also save to SQLite
            if task_type == TaskType.CHAT.value and self._chat_context.session_id and self._chat_context.message_id:
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
                        self._chat_context.session_id,
                        self._chat_context.message_id,
                        message,
                        log_type
                    )
                except Exception as e:
                    logger.error(f"Failed to save chat log to SQLite: {e}")

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

    async def run_task(
        self,
        task_content: str,
        device_ids: list[str],
        model_config: Optional[dict] = None,
        is_scheduled: bool = False,
        send_email: bool = True,
        no_auto_lock: bool = False,
        task_type: str = TaskType.MANUAL.value,
        session_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> TaskExecution:
        """
        Run a task on specified devices.

        Args:
            task_content: The task instruction to execute
            device_ids: List of device IDs to run the task on
            model_config: Optional model configuration override
            is_scheduled: Whether this is a scheduled task
            send_email: Whether to send email after completion
            no_auto_lock: Whether to skip auto-lock after task (for complex task mode)
            task_type: Task type for priority handling (chat/scheduled/manual)
            session_id: Optional existing session ID to use (for chat tasks)
            message_id: Optional existing message ID to bind logs/screenshots to

        Returns:
            TaskExecution object with results
        """
        self._stop_requested = False

        # For chat tasks, use existing session or create new one
        chat_session_id = session_id
        chat_message_id = message_id
        if task_type == TaskType.CHAT.value:
            try:
                from web_app.services.chat_service import chat_service
                device_id = device_ids[0] if device_ids else "unknown"
                
                # 如果提供了 session_id，使用现有会话
                if session_id:
                    # 验证会话存在
                    session = chat_service.get_session(session_id)
                    if session:
                        chat_session_id = session_id
                        # 如果提供了 message_id，使用现有消息
                        if message_id:
                            chat_message_id = message_id
                            logger.info(f"Using existing chat session {chat_session_id} with message {chat_message_id}")
                        else:
                            # 只添加 assistant 消息（user 消息由前端管理）
                            assistant_message = chat_service.add_message(chat_session_id, "assistant", "执行中...")
                            chat_message_id = assistant_message["id"]
                            logger.info(f"Using existing chat session {chat_session_id}, created assistant message {chat_message_id}")
                    else:
                        # 会话不存在，创建新会话
                        logger.warning(f"Session {session_id} not found, creating new session")
                        session = chat_service.create_session(device_id, task_content[:50])
                        chat_session_id = session["id"]
                        user_message = chat_service.add_message(chat_session_id, "user", task_content)
                        assistant_message = chat_service.add_message(chat_session_id, "assistant", "执行中...")
                        chat_message_id = assistant_message["id"]
                        logger.info(f"Created new chat session {chat_session_id}")
                else:
                    # 没有提供 session_id，创建新会话
                    session = chat_service.create_session(device_id, task_content[:50])
                    chat_session_id = session["id"]
                    user_message = chat_service.add_message(chat_session_id, "user", task_content)
                    assistant_message = chat_service.add_message(chat_session_id, "assistant", "执行中...")
                    chat_message_id = assistant_message["id"]
                    logger.info(f"Created chat session {chat_session_id} with assistant message {chat_message_id}")
                
                # Set context for logging
                self._chat_context.session_id = chat_session_id
                self._chat_context.message_id = chat_message_id
                self._chat_context.device_id = device_id
            except Exception as e:
                logger.error(f"Failed to handle chat session: {e}")

        # Create task execution
        task = TaskExecution(
            task_content=task_content,
            device_ids=device_ids,
            status=TaskStatus.RUNNING.value,
            start_time=datetime.now().isoformat(),
            is_scheduled=is_scheduled,
            send_email=send_email,
            task_type=task_type,
        )
        self._current_task = task

        self._emit_log(task.id, f"Starting task: {task_content}")
        self._emit_log(task.id, f"Devices: {', '.join(device_ids)}")

        total_devices = len(device_ids)
        completed = 0

        for device_id in device_ids:
            if self._stop_requested:
                self._emit_log(task.id, "Task stopped by user")
                break

            self._emit_log(task.id, f"Running on device: {device_id}")

            # Check device connection status first
            from web_app.services.device_service import device_service
            self._emit_log(task.id, f"📱 检查设备 {device_id} 连接状态...")

            device_connected, disconnect_reason = await self._check_device_connected(device_id)
            if not device_connected:
                self._emit_log(task.id, f"❌ 设备断联: {disconnect_reason}")
                result = TaskResult(
                    id=str(uuid.uuid4())[:8],
                    device_id=device_id,
                    status=TaskStatus.FAILED.value,
                    start_time=datetime.now().isoformat(),
                    end_time=datetime.now().isoformat(),
                    success=False,
                    message=f"设备断联: {disconnect_reason}",
                )
                task.results.append(result.to_dict())
                completed += 1
                task.progress = int((completed / total_devices) * 100)
                self._emit_progress(task.id, task.progress)
                continue

            self._emit_log(task.id, f"✓ 设备 {device_id} 已连接")

            # Check and record initial lock state, then unlock if needed
            was_locked = False
            unlock_failed = False
            try:
                was_locked = await device_service.is_screen_locked(device_id)
                if was_locked:
                    self._emit_log(task.id, f"🔒 Device is locked, attempting to unlock...")
                    pin = device_service.get_device_pin(device_id)
                    unlock_success = await device_service.unlock_device(device_id, pin)
                    if unlock_success:
                        self._emit_log(task.id, f"🔓 Device unlocked successfully")
                    else:
                        self._emit_log(task.id, f"❌ Failed to unlock device - stopping task")
                        unlock_failed = True
                else:
                    self._emit_log(task.id, f"📱 Device is already unlocked")
            except Exception as e:
                self._emit_log(task.id, f"❌ Lock check failed: {e} - stopping task")
                unlock_failed = True

            # If unlock failed, skip this device
            if unlock_failed:
                result = TaskResult(
                    id=str(uuid.uuid4())[:8],
                    device_id=device_id,
                    status=TaskStatus.FAILED.value,
                    start_time=datetime.now().isoformat(),
                    end_time=datetime.now().isoformat(),
                    success=False,
                    message="设备解锁失败，无法执行任务",
                )
                task.results.append(result.to_dict())
                completed += 1
                task.progress = int((completed / total_devices) * 100)
                self._emit_progress(task.id, task.progress)
                continue

            result = TaskResult(
                id=str(uuid.uuid4())[:8],
                device_id=device_id,
                status=TaskStatus.RUNNING.value,
                start_time=datetime.now().isoformat(),
            )

            try:
                # Import phone_agent
                from phone_agent import PhoneAgent
                from phone_agent.agent import AgentConfig
                from phone_agent.model import ModelConfig
                from web_app.services.model_service import model_service

                # Get model config
                if not model_config:
                    active_model = model_service.get_active_service()
                    if active_model:
                        model_config = {
                            "base_url": active_model.base_url,
                            "api_key": active_model.api_key,
                            "model_name": active_model.model_name,
                            "max_tokens": active_model.max_tokens,
                            "temperature": active_model.temperature,
                            "protocol": active_model.protocol,
                        }

                if not model_config:
                    raise ValueError("No model service configured")

                # Create proper config objects
                model_cfg = ModelConfig(
                    base_url=model_config.get("base_url", ""),
                    api_key=model_config.get("api_key", ""),
                    model_name=model_config.get("model_name", ""),
                    max_tokens=model_config.get("max_tokens", 3000),
                    temperature=model_config.get("temperature", 0.0),
                    protocol=model_config.get("protocol", "openai"),
                )

                agent_cfg = AgentConfig(
                    device_id=device_id,
                    max_steps=50,
                    verbose=True,
                )

                # Create agent with proper config objects
                agent = PhoneAgent(
                    model_config=model_cfg,
                    agent_config=agent_cfg,
                )

                # Run the agent
                self._emit_log(task.id, f"Agent created for {device_id}")

                # Store agent instance for cleanup on stop
                self._agent_instances[device_id] = agent

                # Execute task
                agent_task = asyncio.create_task(
                    self._run_agent(agent, task_content, task.id, device_id)
                )
                self._running_agents[device_id] = agent_task

                try:
                    success = await agent_task
                    result.success = success
                    result.status = TaskStatus.COMPLETED.value if success else TaskStatus.FAILED.value
                    result.message = "Task completed successfully" if success else "Task failed"
                except asyncio.CancelledError:
                    result.status = TaskStatus.STOPPED.value
                    result.message = "Task was stopped"
                    self._emit_log(task.id, f"Task stopped on device {device_id}")
                    # Cleanup agent on cancellation
                    try:
                        agent.cleanup()
                    except Exception as cleanup_error:
                        logger.error(f"Error cleaning up agent: {cleanup_error}")
                finally:
                    self._running_agents.pop(device_id, None)
                    self._agent_instances.pop(device_id, None)

            except ImportError as e:
                result.status = TaskStatus.FAILED.value
                result.message = f"Import error: {e}"
                self._emit_log(task.id, f"Error: {e}")
            except Exception as e:
                result.status = TaskStatus.FAILED.value
                result.message = str(e)
                self._emit_log(task.id, f"Error on {device_id}: {e}")

            result.end_time = datetime.now().isoformat()
            task.results.append(result.to_dict())

            # Capture screenshot BEFORE locking (for email report)
            if result.success and not hasattr(task, '_screenshot_data'):
                try:
                    screenshot_data = await device_service.get_screenshot(device_id)
                    if screenshot_data:
                        task._screenshot_data = screenshot_data
                        self._emit_log(task.id, f"📸 Screenshot captured from {device_id}")

                        # For chat tasks, also save screenshot to SQLite
                        if task.task_type == TaskType.CHAT.value and self._chat_context.session_id and self._chat_context.message_id:
                            try:
                                from web_app.services.chat_service import chat_service
                                screenshot_result = chat_service.add_screenshot(
                                    self._chat_context.session_id,
                                    self._chat_context.message_id,
                                    screenshot_data,
                                    "Task completion screenshot"
                                )
                                # Save screenshot_id for WebSocket broadcast
                                task._screenshot_id = screenshot_result.get("id")
                                logger.info(f"Saved screenshot {task._screenshot_id} to chat session {self._chat_context.session_id}")
                            except Exception as e:
                                logger.error(f"Failed to save screenshot to SQLite: {e}")
                except Exception as e:
                    self._emit_log(task.id, f"⚠️ Failed to capture screenshot: {e}")

            # Restore lock state if device was locked before (skip if no_auto_lock is True)
            if was_locked and not no_auto_lock:
                try:
                    self._emit_log(task.id, f"🔒 Restoring lock state...")
                    lock_success = await device_service.lock_device(device_id)
                    if lock_success:
                        self._emit_log(task.id, f"🔒 Device locked")
                    else:
                        self._emit_log(task.id, f"⚠️ Failed to lock device")
                except Exception as e:
                    self._emit_log(task.id, f"⚠️ Lock restore failed: {e}")
            elif was_locked and no_auto_lock:
                self._emit_log(task.id, f"🔓 Keeping device unlocked (complex task mode)")

            completed += 1
            task.progress = int((completed / total_devices) * 100)
            self._emit_progress(task.id, task.progress)

        # Finalize task
        task.end_time = datetime.now().isoformat()
        if self._stop_requested:
            task.status = TaskStatus.STOPPED.value
        else:
            # Check if all succeeded
            all_success = all(r.get("success", False) for r in task.results)
            task.status = TaskStatus.COMPLETED.value if all_success else TaskStatus.FAILED.value

        self._emit_log(task.id, f"Task finished with status: {task.status}")
        self._task_history.append(task)

        # For chat tasks, update session status and add assistant response
        if task.task_type == TaskType.CHAT.value and self._chat_context.session_id:
            try:
                from web_app.services.chat_service import chat_service
                # Update session status
                status = "completed" if all_success else "failed"
                chat_service.update_session_status(self._chat_context.session_id, status)
                # Update assistant message content (don't create new one, update existing)
                from web_app.services.chat_storage import chat_storage
                response_content = f"任务{'完成' if all_success else '失败'}: {task.task_content[:50]}"
                # Update the existing assistant message
                with chat_storage._get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE chat_messages SET content = ? WHERE id = ?",
                        (response_content, self._chat_context.message_id)
                    )
                logger.info(f"Updated chat session {self._chat_context.session_id} status to {status}")
            except Exception as e:
                logger.error(f"Failed to update chat session: {e}")
            finally:
                # Clear chat context
                self._chat_context.clear()

        # Emit task finished event before clearing current task
        all_success = all(r.get("success", False) for r in task.results)
        screenshot_id = getattr(task, '_screenshot_id', None)
        # 不再发送 base64 截图，只发送 screenshot_id，前端从数据库加载
        self._emit_finished(
            task.id,
            all_success,
            f"Task {task.status}: {len([r for r in task.results if r.get('success')])} succeeded, {len([r for r in task.results if not r.get('success')])} failed",
            None,  # 不再发送 base64 截图
            screenshot_id  # 只发送 screenshot_id
        )

        self._current_task = None

        # Send email report after task completion
        await self._send_email_report(task)

        return task

    async def _send_email_report(self, task: TaskExecution):
        """Send email report after task completion."""
        # Check if email should be sent for this task
        if not task.send_email:
            # Don't log "skipped" for chat tasks to avoid noise (handled separately or not needed)
            if task.task_type != "chat":
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
            screenshot_data = getattr(task, '_screenshot_data', None)

            # Send report with correct is_scheduled flag
            success, message = email_service.send_task_report(
                task_name=task.task_content[:50],
                success_count=success_count,
                failed_count=failed_count,
                total_count=total_count,
                details=details,
                screenshot_data=screenshot_data,
                is_scheduled=task.is_scheduled,
            )

            if success:
                self._emit_log(task.id, f"📧 Email report sent successfully")
            else:
                self._emit_log(task.id, f"📧 Email not sent: {message}")
        except Exception as e:
            logger.error(f"Failed to send email report: {e}")

    async def _run_agent(
        self,
        agent,
        task_content: str,
        task_id: str,
        device_id: str
    ) -> bool:
        """Run the phone agent asynchronously with real-time log capture."""
        import io
        import sys
        import threading
        import queue

        try:
            loop = asyncio.get_event_loop()

            # Queue for real-time log messages
            log_queue = queue.Queue()

            class RealTimeStdout:
                """Custom stdout that captures and queues output in real-time."""
                def __init__(self, original_stdout, log_queue):
                    self.original_stdout = original_stdout
                    self.log_queue = log_queue
                    self.buffer = ""

                def write(self, text):
                    # Also write to original stdout for debugging
                    if self.original_stdout:
                        self.original_stdout.write(text)

                    # Buffer and process lines
                    self.buffer += text
                    while '\n' in self.buffer:
                        line, self.buffer = self.buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            self.log_queue.put(line)

                def flush(self):
                    if self.original_stdout:
                        self.original_stdout.flush()
                    # Flush any remaining buffer
                    if self.buffer.strip():
                        self.log_queue.put(self.buffer.strip())
                        self.buffer = ""

            # Background task to process log queue
            async def process_logs():
                while True:
                    try:
                        # Non-blocking check for new logs
                        while not log_queue.empty():
                            line = log_queue.get_nowait()
                            if line:
                                # Check for token usage marker
                                if line.startswith('[TOKENS]') and '[/TOKENS]' in line:
                                    # Parse token info: [TOKENS]input,output,total[/TOKENS]
                                    try:
                                        token_str = line.replace('[TOKENS]', '').replace('[/TOKENS]', '')
                                        parts = token_str.split(',')
                                        if len(parts) == 3:
                                            input_tokens = int(parts[0])
                                            output_tokens = int(parts[1])
                                            total_tokens = int(parts[2])
                                            self._emit_tokens(task_id, input_tokens, output_tokens, total_tokens)
                                    except Exception:
                                        pass
                                    continue  # Don't emit as log
                                # Format and emit log
                                if '💭' in line or '🎯' in line or '✅' in line or '🎉' in line:
                                    self._emit_log(task_id, line)
                                elif line.startswith('{') and '"' in line:
                                    self._emit_log(task_id, f"  {line}")
                                elif '==' in line:
                                    self._emit_log(task_id, line)
                                elif '思考' in line or 'think' in line.lower():
                                    self._emit_log(task_id, f"🧠 {line}")
                                elif line.strip() and not line.startswith('-'):
                                    self._emit_log(task_id, line)
                        await asyncio.sleep(0.1)  # Check every 100ms
                    except asyncio.CancelledError:
                        break
                    except Exception:
                        break

            # Start log processor
            log_task = asyncio.create_task(process_logs())

            def run_sync_with_capture():
                old_stdout = sys.stdout
                sys.stdout = RealTimeStdout(old_stdout, log_queue)
                try:
                    result = agent.run(task_content)
                    return result
                finally:
                    sys.stdout.flush()
                    sys.stdout = old_stdout

            try:
                result = await loop.run_in_executor(None, run_sync_with_capture)
                # Give time for remaining logs to be processed
                await asyncio.sleep(0.5)
                return result is not None
            finally:
                log_task.cancel()
                try:
                    await log_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            self._emit_log(task_id, f"Agent error on {device_id}: {e}")
            return False

    async def stop_all_tasks(self) -> bool:
        """Stop all running tasks."""
        self._stop_requested = True
        logger.info("Stop signal received, attempting to stop all tasks")

        # First, request stop on all agent instances (this is checked between steps)
        for device_id, agent in list(self._agent_instances.items()):
            try:
                logger.info(f"Requesting stop for agent on device {device_id}")
                agent.request_stop()
            except Exception as e:
                logger.error(f"Error requesting stop for {device_id}: {e}")

        # Then, try to cleanup all agent instances
        for device_id, agent in list(self._agent_instances.items()):
            try:
                logger.info(f"Cleaning up agent for device {device_id}")
                agent.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up agent for {device_id}: {e}")

        # Then cancel all running agent tasks
        for device_id, agent_task in list(self._running_agents.items()):
            if not agent_task.done():
                logger.info(f"Cancelling task for device {device_id}")
                agent_task.cancel()

        # Wait a bit for tasks to cancel
        await asyncio.sleep(0.5)

        # Update task status if there's a current task
        if self._current_task and self._current_task.status == TaskStatus.RUNNING.value:
            self._current_task.status = TaskStatus.STOPPED.value
            self._emit_log(self._current_task.id, "All tasks have been stopped")

        logger.info("Stop all tasks completed")
        return True

    def get_current_task(self) -> Optional[TaskExecution]:
        """Get the currently running task."""
        return self._current_task

    def get_task_status(self) -> dict:
        """Get current task status."""
        if self._current_task:
            return {
                "running": True,
                "task": self._current_task.to_dict()
            }
        return {
            "running": False,
            "task": None
        }

    def get_task_history(self, limit: int = 10) -> list[dict]:
        """Get recent task history."""
        return [t.to_dict() for t in self._task_history[-limit:]]

    def can_interrupt_current_task(self, new_task_type: str) -> tuple[bool, Optional[dict]]:
        """
        检查新任务是否可以打断当前任务。

        Args:
            new_task_type: 新任务的类型 (chat/scheduled/manual)

        Returns:
            (can_interrupt, current_task_info) 元组
            - can_interrupt: 是否可以打断
            - current_task_info: 当前任务的信息（如果有）
        """
        if not self._current_task:
            return True, None

        current_type = self._current_task.task_type
        new_priority = TaskType(new_task_type).priority
        current_priority = TaskType(current_type).priority

        current_info = {
            "id": self._current_task.id,
            "task_content": self._current_task.task_content,
            "task_type": current_type,
            "task_type_display": self._current_task.get_type_display(),
            "start_time": self._current_task.start_time,
            "progress": self._current_task.progress,
        }

        # 高优先级任务可以打断低优先级任务
        can_interrupt = new_priority > current_priority
        return can_interrupt, current_info


# Global service instance
task_service = TaskService()
