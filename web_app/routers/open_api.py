# -*- coding: utf-8 -*-
"""
Open API Router (v1).
Provides high-level, standardized REST APIs for external systems, scripts,
and Agent SKILLs to interact with Open-AutoGLM.
"""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from web_app.auth import verify_token
from web_app.services.api_key_service import api_key_service
from web_app.services.device_service import device_service
from web_app.services.skill_packager import generate_skill_zip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Open API v1"])


class ActionRequest(BaseModel):
    action: str = Field(
        ...,
        description="Action type: tap, swipe, text, key, shell, unlock, lock",
    )
    x: Optional[int] = Field(default=None, description="X coordinate for tap")
    y: Optional[int] = Field(default=None, description="Y coordinate for tap")
    x1: Optional[int] = Field(default=None, description="Start X for swipe")
    y1: Optional[int] = Field(default=None, description="Start Y for swipe")
    x2: Optional[int] = Field(default=None, description="End X for swipe")
    y2: Optional[int] = Field(default=None, description="End Y for swipe")
    duration_ms: Optional[int] = Field(default=300, description="Swipe duration in ms")
    text: Optional[str] = Field(default=None, description="Text string to type")
    key: Optional[str] = Field(default=None, description="Key name (home, back, enter, power)")
    command: Optional[str] = Field(default=None, description="ADB shell command to execute")
    pin: Optional[str] = Field(default=None, description="Optional PIN for unlock")
    timeout_seconds: Optional[int] = Field(default=20, ge=1, le=120)


class RunTaskRequest(BaseModel):
    task: str = Field(..., min_length=1, description="Natural language instructions for AutoGLM")
    device_id: Optional[str] = Field(default=None, description="Target device serial (optional if only 1 device)")
    timeout: Optional[int] = Field(default=1800, ge=10, le=86400, description="Task timeout in seconds")
    force_run: Optional[bool] = Field(default=False, description="Whether to interrupt active task if conflicting")
    send_email: Optional[bool] = Field(default=False, description="Send completion email")


class GenerateKeyRequest(BaseModel):
    name: Optional[str] = Field(default="Agent Key", description="Name/label for the API key")


# ==========================================
# 1. System Health & Ping
# ==========================================
@router.get("/health")
@router.get("/ping")
async def health_check():
    """Public health check endpoint."""
    devices = device_service.get_all_devices()
    return {
        "status": "ok",
        "app": "Open-AutoGLM-GUI",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "devices_connected": len(devices),
    }


# ==========================================
# 2. Devices APIs
# ==========================================
@router.get("/devices")
async def list_devices(_: bool = Depends(verify_token)):
    """List all connected Android devices with detailed status."""
    devices = device_service.get_all_devices()
    if not devices:
        devices = await device_service.refresh_devices()

    result = []
    for d in devices:
        info = d.to_dict()
        result.append({
            "id": info.get("id"),
            "name": info.get("name"),
            "status": info.get("status"),
            "model": info.get("model", ""),
            "screen_size": info.get("screen_size", ""),
            "connection_type": info.get("connection_type", ""),
            "sdk_version": info.get("sdk_version", ""),
        })
    return {"devices": result, "count": len(result)}


@router.get("/devices/{device_id}")
async def get_device(device_id: str, _: bool = Depends(verify_token)):
    """Get details of a specific device."""
    dev = device_service.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"device": dev.to_dict()}


@router.get("/devices/{device_id}/screenshot")
async def get_device_screenshot(
    device_id: str,
    format: str = Query(default="raw", description="raw for binary image/png, base64 for JSON"),
    _: bool = Depends(verify_token),
):
    """Capture real-time screenshot of the device."""
    if format == "base64":
        img_b64 = await device_service.get_screenshot_base64(device_id)
        if not img_b64:
            raise HTTPException(status_code=500, detail="Failed to capture device screenshot")
        return {"success": True, "device_id": device_id, "image": img_b64}

    img_bytes = await device_service.get_screenshot(device_id)
    if not img_bytes:
        raise HTTPException(status_code=500, detail="Failed to capture device screenshot")
    return Response(content=img_bytes, media_type="image/png")


@router.post("/devices/{device_id}/action")
async def execute_device_action(
    device_id: str,
    req: ActionRequest,
    _: bool = Depends(verify_token),
):
    """
    Execute a low-level phone action (tap, swipe, text, key, shell, unlock, lock).
    """
    action = req.action.lower().strip()

    if action == "unlock":
        success = await device_service.unlock_device(device_id, pin=req.pin)
        return {"success": success, "action": action, "device_id": device_id}

    elif action == "lock":
        success = await device_service.lock_device(device_id)
        return {"success": success, "action": action, "device_id": device_id}

    elif action == "tap":
        if req.x is None or req.y is None:
            raise HTTPException(status_code=422, detail="tap requires 'x' and 'y'")
        command = f"/tap {req.x} {req.y}"
        result = await device_service.execute_adb_chat_command(
            device_id=device_id,
            command=command,
            timeout_seconds=req.timeout_seconds,
        )
        return {"success": result.get("exit_code") == 0, "action": action, "result": result}

    elif action == "swipe":
        if None in (req.x1, req.y1, req.x2, req.y2):
            raise HTTPException(status_code=422, detail="swipe requires 'x1', 'y1', 'x2', 'y2'")
        duration = req.duration_ms or 300
        command = f"/swipe {req.x1} {req.y1} {req.x2} {req.y2} {duration}"
        result = await device_service.execute_adb_chat_command(
            device_id=device_id,
            command=command,
            timeout_seconds=req.timeout_seconds,
        )
        return {"success": result.get("exit_code") == 0, "action": action, "result": result}

    elif action == "text":
        if not req.text:
            raise HTTPException(status_code=422, detail="text requires 'text' content")
        command = f"/text {req.text}"
        result = await device_service.execute_adb_chat_command(
            device_id=device_id,
            command=command,
            timeout_seconds=req.timeout_seconds,
        )
        return {"success": result.get("exit_code") == 0, "action": action, "result": result}

    elif action == "key":
        if not req.key:
            raise HTTPException(status_code=422, detail="key requires 'key' name or keycode")
        command = f"/key {req.key}"
        result = await device_service.execute_adb_chat_command(
            device_id=device_id,
            command=command,
            timeout_seconds=req.timeout_seconds,
        )
        return {"success": result.get("exit_code") == 0, "action": action, "result": result}

    elif action == "shell":
        if not req.command:
            raise HTTPException(status_code=422, detail="shell requires 'command'")
        command = f"/shell {req.command}"
        result = await device_service.execute_adb_chat_command(
            device_id=device_id,
            command=command,
            timeout_seconds=req.timeout_seconds,
        )
        return {"success": result.get("exit_code") == 0, "action": action, "result": result}

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported action '{action}'. Valid actions: tap, swipe, text, key, shell, unlock, lock",
        )


# ==========================================
# 3. Tasks APIs
# ==========================================
@router.post("/tasks/run")
async def run_ai_task(
    req: RunTaskRequest,
    _: bool = Depends(verify_token),
):
    """
    Submit an autonomous mobile AI task to Open-AutoGLM.
    If device_id is omitted, automatically routes to the first connected device.
    """
    target_device = req.device_id
    if not target_device:
        devices = device_service.get_all_devices()
        if not devices:
            devices = await device_service.refresh_devices()
        if not devices:
            raise HTTPException(
                status_code=400,
                detail="未检测到任何连接的 Android 设备，请连接设备后重试",
            )
        target_device = devices[0].id

    from web_app.services.automation_runtime import get_runtime, Conflict
    runtime = get_runtime()

    if req.force_run:
        for old in runtime.store.list('task'):
            if any(child.get('device_id') == target_device and child.get('status') in {'running', 'pausing', 'paused', 'waiting_for_user', 'interrupted'} for child in old.get('executions', [])):
                runtime.control(old['id'], 'stop', device_ids=[target_device])

    try:
        task = runtime.submit(
            req.task,
            [target_device],
            queue=True,
            queue_timeout=req.timeout,
            after_current=bool(req.force_run),
            send_email=req.send_email,
            task_type="api_open",
        )
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "success": True,
        "task_id": task["id"],
        "status": task.get("status", "pending"),
        "task": req.task,
        "device_id": target_device,
    }


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, _: bool = Depends(verify_token)):
    """Get status, execution steps, and logs of a task."""
    from web_app.services.automation_runtime import get_runtime
    runtime = get_runtime()
    task = runtime.store.get('task', task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    executions = task.get("executions", [])
    overall_status = task.get("status", "unknown")
    latest_logs = []
    if executions:
        overall_status = executions[-1].get("status", overall_status)
        latest_logs = executions[-1].get("logs", [])

    return {
        "id": task["id"],
        "status": overall_status,
        "task_content": task.get("task_content", ""),
        "device_ids": task.get("device_ids", []),
        "created_at": task.get("created_at"),
        "executions": executions,
        "latest_logs": latest_logs[-30:],
    }


@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str, _: bool = Depends(verify_token)):
    """Stop a running task."""
    from web_app.services.automation_runtime import get_runtime
    runtime = get_runtime()
    task = runtime.store.get('task', task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    runtime.control(task_id, 'stop')
    return {"success": True, "task_id": task_id, "message": "Task stopped"}


@router.get("/tasks")
async def list_tasks(
    limit: int = Query(default=15, ge=1, le=100),
    _: bool = Depends(verify_token),
):
    """List recent tasks."""
    from web_app.services.automation_runtime import get_runtime
    runtime = get_runtime()
    all_tasks = runtime.store.list('task')
    sorted_tasks = sorted(all_tasks, key=lambda t: t.get("created_at", ""), reverse=True)[:limit]

    clean_list = []
    for t in sorted_tasks:
        executions = t.get("executions", [])
        status_val = t.get("status", "unknown")
        if executions:
            status_val = executions[-1].get("status", status_val)
        clean_list.append({
            "id": t.get("id"),
            "task_content": t.get("task_content", ""),
            "status": status_val,
            "device_ids": t.get("device_ids", []),
            "created_at": t.get("created_at"),
        })
    return {"tasks": clean_list, "count": len(clean_list)}


# ==========================================
# 4. API Key Management & SKILL Export
# ==========================================
@router.get("/keys")
async def list_keys(
    unmask: bool = Query(default=False, description="Whether to include full unmasked primary key"),
    _: bool = Depends(verify_token),
):
    """List API keys or get current active primary key."""
    keys = api_key_service.get_all_keys(mask=not unmask)
    primary = api_key_service.get_primary_key(unmasked=unmask)
    return {
        "primary_key": primary,
        "keys": keys,
    }


@router.post("/keys/generate")
async def generate_new_key(
    req: GenerateKeyRequest = None,
    _: bool = Depends(verify_token),
):
    """Generate a new API key."""
    name = (req.name if req else "") or "Agent Key"
    new_record = api_key_service.generate_key(name=name)
    return {
        "success": True,
        "api_key": new_record["key"],
        "name": new_record["name"],
        "created_at": new_record["created_at"],
    }


@router.post("/keys/{key_id}/revoke")
async def revoke_key(key_id: str, _: bool = Depends(verify_token)):
    """Revoke an API key."""
    success = api_key_service.revoke_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"success": True, "message": "Key revoked"}


@router.get("/skill/download")
async def download_skill_package(
    request: Request,
    api_key: Optional[str] = Query(default=None),
    _: bool = Depends(verify_token),
):
    """
    Download a pre-packaged, zero-dependency Agent SKILL (.zip).
    Automatically embeds the current server URL and active API Key.
    """
    # Determine base URL from incoming request
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "127.0.0.1:8080"
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    base_url = f"{scheme}://{host}"

    # Determine API key to embed
    target_key = api_key
    if not target_key:
        primary = api_key_service.get_primary_key(unmasked=True)
        target_key = primary.get("key", "")

    zip_bytes = generate_skill_zip(base_url=base_url, api_key=target_key)
    filename = "open-autoglm-skill.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-cache",
        },
    )
