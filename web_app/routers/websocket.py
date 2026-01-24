# -*- coding: utf-8 -*-
"""
WebSocket router for real-time communication.
"""

import asyncio
import json
import logging
from typing import Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from web_app.config import config_manager
from web_app.services.task_service import task_service
from web_app.services.device_service import device_service

logger = logging.getLogger(__name__)

# Store the main event loop for thread-safe callback scheduling
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop for thread-safe operations."""
    global _main_loop
    _main_loop = loop

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and store a new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connections."""
        if not self.active_connections:
            return

        data = json.dumps(message, ensure_ascii=False)
        dead_connections = set()

        # Iterate over a copy of the set to avoid "Set changed size during iteration"
        for connection in list(self.active_connections):
            try:
                await connection.send_text(data)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections.discard(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a message to a specific connection."""
        try:
            data = json.dumps(message, ensure_ascii=False)
            await websocket.send_text(data)
        except Exception:
            pass


# Global connection manager
manager = ConnectionManager()


# Task service callbacks
def on_task_log(task_id: str, message: str, task_type: str = None):
    """Callback for task log messages (thread-safe)."""
    global _main_loop
    if _main_loop is None:
        return
    try:
        _main_loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast({
                "type": "task_log",
                "task_id": task_id,
                "message": message,
                "task_type": task_type,  # Include task type for filtering
            }))
        )
    except Exception as e:
        logger.error(f"Failed to broadcast log: {e}")


def on_task_progress(task_id: str, progress: int):
    """Callback for task progress updates (thread-safe)."""
    global _main_loop
    if _main_loop is None:
        return
    try:
        _main_loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast({
                "type": "task_progress",
                "task_id": task_id,
                "progress": progress,
            }))
        )
    except Exception as e:
        logger.error(f"Failed to broadcast progress: {e}")


def on_task_finished(task_id: str, success: bool, message: str, screenshot: str = None, screenshot_id: str = None, task_type: str = None):
    """Callback for task completion (thread-safe)."""
    global _main_loop
    if _main_loop is None:
        return
    try:
        _main_loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast({
                "type": "task_finished",
                "task_id": task_id,
                "success": success,
                "message": message,
                # 不再发送 base64 截图，只发送 screenshot_id，前端从数据库加载
                "screenshot_id": screenshot_id,
                "task_type": task_type,  # 包含任务类型，让前端知道是定时任务还是手动任务
            }))
        )
    except Exception as e:
        logger.error(f"Failed to broadcast task finished: {e}")


def on_task_tokens(task_id: str, input_tokens: int, output_tokens: int, total_tokens: int):
    """Callback for token usage updates (thread-safe)."""
    global _main_loop
    if _main_loop is None:
        return
    try:
        _main_loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast({
                "type": "task_tokens",
                "task_id": task_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }))
        )
    except Exception as e:
        logger.error(f"Failed to broadcast tokens: {e}")


# Register callbacks
task_service.add_log_callback(on_task_log)
task_service.add_progress_callback(on_task_progress)
task_service.add_finished_callback(on_task_finished)
task_service.add_token_callback(on_task_tokens)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    # Check authentication if enabled
    config = config_manager.get_config()
    if config.auth_enabled:
        # Try to get token from query params
        token = websocket.query_params.get("token", "")
        if not config_manager.validate_token(token):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    await manager.connect(websocket)

    try:
        # Send initial status
        task_status = task_service.get_task_status()
        await manager.send_personal(websocket, {
            "type": "init",
            "task_status": task_status,
        })

        # Keep connection alive and handle messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # Ping every 30 seconds
                )

                # Handle client messages
                try:
                    message = json.loads(data)
                    await handle_client_message(websocket, message)
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send ping
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)


async def handle_client_message(websocket: WebSocket, message: dict):
    """Handle messages from the client."""
    msg_type = message.get("type", "")

    if msg_type == "pong":
        # Client responding to ping
        pass

    elif msg_type == "get_devices":
        # Request device list
        devices = device_service.get_all_devices()
        await manager.send_personal(websocket, {
            "type": "devices",
            "devices": [d.to_dict() for d in devices],
        })

    elif msg_type == "get_task_status":
        # Request task status
        status = task_service.get_task_status()
        await manager.send_personal(websocket, {
            "type": "task_status",
            "status": status,
        })

    elif msg_type == "refresh_devices":
        # Refresh devices and broadcast
        devices = await device_service.refresh_devices()
        await manager.broadcast({
            "type": "devices",
            "devices": [d.to_dict() for d in devices],
        })


async def broadcast_device_update():
    """Broadcast device status update to all clients."""
    devices = device_service.get_all_devices()
    await manager.broadcast({
        "type": "device_status",
        "devices": [d.to_dict() for d in devices],
    })


async def broadcast_task_finished(task_id: str, success: bool, message: str, screenshot: str = None):
    """Broadcast task completion to all clients (deprecated - use on_task_finished callback instead)."""
    # 不再发送 base64 截图，只发送消息
    await manager.broadcast({
        "type": "task_finished",
        "task_id": task_id,
        "success": success,
        "message": message,
        # 不再发送 base64 截图
    })
