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


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


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

    def to_dict(self) -> dict:
        return asdict(self)


class TaskService:
    """Service for executing automation tasks."""

    def __init__(self):
        self._current_task: Optional[TaskExecution] = None
        self._task_history: list[TaskExecution] = []
        self._stop_requested = False
        self._log_callbacks: list[Callable[[str, str], None]] = []
        self._progress_callbacks: list[Callable[[str, int], None]] = []
        self._running_agents: dict[str, asyncio.Task] = {}

    def add_log_callback(self, callback: Callable[[str, str], None]):
        """Add a callback for log messages. Callback receives (task_id, message)."""
        self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: Callable[[str, str], None]):
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

    def _emit_log(self, task_id: str, message: str):
        """Emit a log message to all callbacks and store in current task."""
        # Store log in current task for email report
        if self._current_task and self._current_task.id == task_id:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._current_task.logs.append(f"[{timestamp}] {message}")

        for callback in self._log_callbacks:
            try:
                callback(task_id, message)
            except Exception:
                pass

    def _emit_progress(self, task_id: str, progress: int):
        """Emit progress update to all callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(task_id, progress)
            except Exception:
                pass

    async def run_task(
        self,
        task_content: str,
        device_ids: list[str],
        model_config: Optional[dict] = None,
        is_scheduled: bool = False,
        send_email: bool = True
    ) -> TaskExecution:
        """
        Run a task on specified devices.

        Args:
            task_content: The task instruction to execute
            device_ids: List of device IDs to run the task on
            model_config: Optional model configuration override
            is_scheduled: Whether this is a scheduled task

        Returns:
            TaskExecution object with results
        """
        self._stop_requested = False

        # Create task execution
        task = TaskExecution(
            task_content=task_content,
            device_ids=device_ids,
            status=TaskStatus.RUNNING.value,
            start_time=datetime.now().isoformat(),
            is_scheduled=is_scheduled,
            send_email=send_email,
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

            # Check and record initial lock state, then unlock if needed
            was_locked = False
            try:
                from web_app.services.device_service import device_service
                was_locked = await device_service.is_screen_locked(device_id)
                if was_locked:
                    self._emit_log(task.id, f"🔒 Device is locked, attempting to unlock...")
                    pin = device_service.get_device_pin(device_id)
                    unlock_success = await device_service.unlock_device(device_id, pin)
                    if unlock_success:
                        self._emit_log(task.id, f"🔓 Device unlocked successfully")
                    else:
                        self._emit_log(task.id, f"⚠️ Failed to unlock device")
                else:
                    self._emit_log(task.id, f"📱 Device is already unlocked")
            except Exception as e:
                self._emit_log(task.id, f"⚠️ Lock check failed: {e}")

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
                finally:
                    self._running_agents.pop(device_id, None)

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
                except Exception as e:
                    self._emit_log(task.id, f"⚠️ Failed to capture screenshot: {e}")

            # Restore lock state if device was locked before
            if was_locked:
                try:
                    self._emit_log(task.id, f"🔒 Restoring lock state...")
                    lock_success = await device_service.lock_device(device_id)
                    if lock_success:
                        self._emit_log(task.id, f"🔒 Device locked")
                    else:
                        self._emit_log(task.id, f"⚠️ Failed to lock device")
                except Exception as e:
                    self._emit_log(task.id, f"⚠️ Lock restore failed: {e}")

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
        self._current_task = None

        # Send email report after task completion
        await self._send_email_report(task)

        return task

    async def _send_email_report(self, task: TaskExecution):
        """Send email report after task completion."""
        # Check if email should be sent for this task
        if not task.send_email:
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

        # Cancel all running agent tasks
        for device_id, agent_task in list(self._running_agents.items()):
            if not agent_task.done():
                agent_task.cancel()

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


# Global service instance
task_service = TaskService()
