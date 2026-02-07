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
    initial_lock_state: Optional[bool] = None  # Initial lock state detected (for subtask chains)

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
        restore_lock_to_state: Optional[bool] = None,
        task_type: str = TaskType.MANUAL.value,
        session_id: Optional[str] = None,
        message_id: Optional[str] = None,
        debug_mode: bool = False,
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
            restore_lock_to_state: Explicitly specify lock state to restore to (for subtask chains)
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
                        # For Telegram bot: message_id will be None for multi-device tasks
                        # Create a device-specific message for each device
                        if not message_id:
                            device_short_id = device_id[:12] if len(device_id) > 12 else device_id
                            assistant_message = chat_service.add_message(
                                chat_session_id, 
                                "assistant", 
                                f"📱 设备 {device_short_id}... 执行中"
                            )
                            chat_message_id = assistant_message["id"]
                            logger.info(f"Created device message {chat_message_id} for device {device_short_id}")
                        else:
                            # Use provided message_id (single device or manual flow)
                            chat_message_id = message_id
                            logger.info(f"Using provided message {chat_message_id}")
                    else:
                        logger.warning(f"Session {session_id} not found")
                        chat_session_id = session_id
                        chat_message_id = message_id  # May be None, handle later
                else:
                    # No session_id - create new session (non-Telegram flow)
                    session = chat_service.create_session(device_id, task_content[:50])
                    chat_session_id = session["id"]
                    user_message = chat_service.add_message(chat_session_id, "user", task_content)
                    assistant_message = chat_service.add_message(chat_session_id, "assistant", "执行中...")
                    chat_message_id = assistant_message["id"]
                    logger.info(f"Created new session {chat_session_id} with message {chat_message_id}")
                
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

        # Detect initial lock state immediately (before execution loop) so frontend can access it
        # This is crucial for sequential subtask chains to share the original lock state
        if device_ids:
            first_device_id = device_ids[0]
            try:
                from web_app.services.device_service import device_service
                was_locked = await device_service.is_screen_locked(first_device_id)
                task.initial_lock_state = was_locked
                logger.info(f"🔐 Detected initial lock state for task {task.id}: {'LOCKED' if was_locked else 'UNLOCKED'}")
            except Exception as e:
                logger.warning(f"Failed to detect initial lock state: {e}")
                task.initial_lock_state = None

        self._emit_log(task.id, f"Starting task: {task_content}")
        self._emit_log(task.id, f"Devices: {', '.join(device_ids)}")

        total_devices = len(device_ids)
        completed = 0

        for device_id in device_ids:
            if self._stop_requested:
                self._emit_log(task.id, "Task stopped by user")
                break


            # Message already created in initialization (lines 302-310)
            # Just update model name for the existing message
            if task_type == TaskType.CHAT.value and self._chat_context.message_id:
                try:
                    from web_app.services.chat_service import chat_service
                    from web_app.services.model_service import model_service
                    
                    # Get model name and update the existing message
                    model_name = 'Unknown'
                    try:
                        active_model = model_service.get_active_service_dict()
                        model_name = active_model.get('model_name', 'Unknown') if active_model else 'Unknown'
                    except Exception as e:
                        logger.error(f"Failed to get model name: {e}")
                    
                    # Update existing message with model name
                    chat_service.update_message(
                        message_id=self._chat_context.message_id,
                        model_name=model_name
                    )
                    
                    device_short_id = device_id[:12] if len(device_id) > 12 else device_id
                    logger.info(f"Using message {self._chat_context.message_id} for device {device_short_id} with model {model_name}")
                except Exception as e:
                    logger.error(f"Failed to update message model name: {e}")
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
                # Store initial lock state in task object for frontend to access
                task.initial_lock_state = was_locked
                self._emit_log(task.id, f"🔍 [LOCK_STATE] Initial lock state: {'LOCKED' if was_locked else 'UNLOCKED'}")
                self._emit_log(task.id, f"🔍 [LOCK_STATE] no_auto_lock parameter: {no_auto_lock}")
                if was_locked:
                    self._emit_log(task.id, f"🔒 Device is locked, attempting to unlock...")
                    pin = device_service.get_device_pin(device_id)
                    
                    # Retry unlock up to 3 times (initial + 2 retries)
                    max_unlock_attempts = 3
                    unlock_success = False
                    for attempt in range(1, max_unlock_attempts + 1):
                        unlock_success = await device_service.unlock_device(device_id, pin)
                        if unlock_success:
                            self._emit_log(task.id, f"🔓 Device unlocked successfully" + (f" (attempt {attempt})" if attempt > 1 else ""))
                            break
                        else:
                            if attempt < max_unlock_attempts:
                                self._emit_log(task.id, f"⚠️ Unlock attempt {attempt} failed, retrying in 1 second...")
                                await asyncio.sleep(1)
                            else:
                                self._emit_log(task.id, f"❌ Failed to unlock device after {max_unlock_attempts} attempts - stopping task")
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
                    debug_mode=debug_mode,
                )

                # Create tap preview callback if debug mode is enabled
                tap_preview_callback = None
                if debug_mode:
                    from web_app.routers.websocket import create_tap_preview_callback
                    tap_preview_callback = create_tap_preview_callback()

                # Create agent with proper config objects
                agent = PhoneAgent(
                    model_config=model_cfg,
                    agent_config=agent_cfg,
                    tap_preview_callback=tap_preview_callback,
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

            # === REMOVED: Duplicate screenshot logic (was causing black screens) ===
            # This code was capturing screenshot at lock boundary causing:
            # - Black/partially black screenshots due to timing
            # - Only first device screenshot saved (hasattr check)
            # - Duplicate screenshots for first device
            # Now using ONLY send_device_completion for all screenshot capture

            # === OPTIMIZATION: Send device completion BEFORE lock restoration ===
            # This avoids redundant unlock -> lock -> unlock cycles
            # Device is already unlocked here, so screenshot can be taken directly
            if task_type == TaskType.CHAT.value and self._chat_context.message_id:
                try:
                    from web_app.services.telegram_bot import telegram_bot_service
                    # Get chat_id from bot's tracking
                    telegram_chat_id = None
                    for cid, sid in telegram_bot_service._current_chat_tasks.items():
                        if sid == self._chat_context.session_id:
                            telegram_chat_id = cid
                            break
                    
                    if telegram_chat_id:
                        # Telegram scenario: use telegram_bot_service
                        # Get all logs for this task
                        all_logs = task.logs if hasattr(task, 'logs') and task.logs else []
                        
                        # CRITICAL: await (not create_task) to ensure screenshot completes BEFORE lock
                        # create_task is non-blocking → device locks → black screenshot
                        # Convert status to correct string value for bot
                        status_value = 'completed' if result.status == TaskStatus.COMPLETED.value else 'failed'
                        await telegram_bot_service.send_device_completion(
                            chat_id=telegram_chat_id,
                            device_id=device_id,
                            session_id=self._chat_context.session_id,
                            message_id=self._chat_context.message_id,
                            status=status_value,
                            logs=all_logs,
                            skip_unlock=True  # Device is already unlocked
                        )
                        
                        # Collect screenshot for email report from telegram service
                        if hasattr(telegram_bot_service, '_device_screenshots') and device_id in telegram_bot_service._device_screenshots:
                            if not hasattr(task, '_device_screenshots'):
                                task._device_screenshots = {}
                            task._device_screenshots[device_id] = telegram_bot_service._device_screenshots[device_id]
                            logger.info(f"Collected screenshot from {device_id} for email report")
                        
                        logger.info(f"Completed Telegram device report for {device_id} (before lock restoration)")
                    else:
                        # Web chat scenario: save screenshot directly to chat_storage
                        # Device is already unlocked, get screenshot now
                        try:
                            screenshot_data = await device_service.get_screenshot(device_id)
                            if screenshot_data:
                                from web_app.services.chat_storage import chat_storage
                                # Save to database
                                screenshot = chat_storage.add_screenshot(
                                    session_id=self._chat_context.session_id,
                                    message_id=self._chat_context.message_id,
                                    image_data=screenshot_data,
                                    description="Task completion screenshot"
                                )
                                logger.info(f"Saved web chat screenshot {screenshot.id} for session {self._chat_context.session_id}")
                                
                                # Store screenshot_id for frontend to access
                                if not hasattr(task, '_screenshot_id'):
                                    task._screenshot_id = screenshot.id
                                
                                # Collect screenshot for email report
                                # Store in _device_screenshots dict for multi-device email support
                                if not hasattr(task, '_device_screenshots'):
                                    task._device_screenshots = {}
                                task._device_screenshots[device_id] = screenshot_data
                                
                                # Also keep _screenshot_data for backward compatibility (single device)
                                if not hasattr(task, '_screenshot_data'):
                                    task._screenshot_data = screenshot_data
                                
                                logger.info(f"Completed web chat device report for {device_id} (before lock restoration)")
                            else:
                                logger.warning(f"Failed to get screenshot for web chat device {device_id}")
                        except Exception as screenshot_error:
                            logger.error(f"Failed to save web chat screenshot for {device_id}: {screenshot_error}")
                except Exception as e:
                    logger.error(f"Failed to trigger device completion: {e}")
            
            # Restore lock state if device was locked before (skip if no_auto_lock is True)
            # If restore_lock_to_state is explicitly specified, use that instead of detected state
            should_restore_lock = restore_lock_to_state if restore_lock_to_state is not None else was_locked
            self._emit_log(task.id, f"🔍 [LOCK_STATE] End check - was_locked: {was_locked}, no_auto_lock: {no_auto_lock}, restore_lock_to_state: {restore_lock_to_state}, should_restore: {should_restore_lock}")
            if should_restore_lock and not no_auto_lock:
                try:
                    self._emit_log(task.id, f"🔒 Restoring lock state... (should_restore={should_restore_lock}, no_auto_lock=False)")
                    lock_success = await device_service.lock_device(device_id)
                    if lock_success:
                        self._emit_log(task.id, f"🔒 Device locked")
                    else:
                        self._emit_log(task.id, f"⚠️ Failed to lock device")
                except Exception as e:
                    self._emit_log(task.id, f"⚠️ Lock restore failed: {e}")
            elif should_restore_lock and no_auto_lock:
                self._emit_log(task.id, f"🔓 Keeping device unlocked (should_restore={should_restore_lock} but no_auto_lock=True)")
            else:
                self._emit_log(task.id, f"📱 No lock restoration needed (should_restore={should_restore_lock}, no_auto_lock={no_auto_lock})")

            # === MULTI-DEVICE FIX: Update device message with completion status ===
            if task_type == TaskType.CHAT.value and self._chat_context.message_id:
                try:
                    from web_app.services.chat_service import chat_service
                    device_short_id = device_id[:12] if len(device_id) > 12 else device_id
                    status_emoji = "✅" if result.status == TaskStatus.COMPLETED.value else "❌"
                    
                    # Extract token usage from logs
                    token_text = ""
                    for log in reversed(task.logs if hasattr(task, 'logs') else []):
                        if log.startswith('[TOKENS]'):
                            try:
                                parts = log.replace('[TOKENS]', '').split(',')
                                if len(parts) >= 3:
                                    token_text = f" 📊 {parts[2].strip()} tokens"
                                break
                            except:
                                pass
                    
                    # Standardized completion message format
                    completion_text = f'{status_emoji} {device_short_id}: {task_content[:30]}{token_text}'
                    chat_service.update_message(
                        message_id=self._chat_context.message_id,
                        content=completion_text,
                        status='completed' if result.status == TaskStatus.COMPLETED.value else 'failed'
                    )
                    logger.info(f"Updated device message {self._chat_context.message_id} with status: {result.status}")
                except Exception as e:
                    logger.error(f"Failed to update device message: {e}")

            completed += 1
            task.progress = int((completed / total_devices) * 100)
            self._emit_progress(task.id, task.progress)

        # Finalize task
        task.end_time = datetime.now().isoformat()
        # Calculate success status before conditional to ensure variable is always defined
        all_success = all(r.get("success", False) for r in task.results) if task.results else False
        if self._stop_requested:
            task.status = TaskStatus.STOPPED.value
        else:
            # Check if all succeeded
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
                
                # Update assistant message content AND status (database uses 'completed'/'failed')
                # Frontend will map these to 'success'/'error' for display
                from web_app.services.chat_storage import chat_storage
                response_content = f"✅ 任务执行完成！" if all_success else f"❌ 任务执行失败"
                
                # Update the existing assistant message with BOTH content and status
                with chat_storage._get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE chat_messages SET content = ?, status = ? WHERE id = ?",
                        (response_content, status, self._chat_context.message_id)
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
            screenshot_id,  # 只发送 screenshot_id
            task.task_type  # 传递任务类型
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
            success, message = email_service.send_task_report(
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
                                # Emit [TOKENS] lines (needed for Bot token tracking)
                                if line.startswith('[TOKENS]'):
                                    self._emit_log(task_id, line)
                                    continue
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
