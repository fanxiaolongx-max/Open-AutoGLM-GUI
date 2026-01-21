# -*- coding: utf-8 -*-
"""
Tasks API router.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from web_app.auth import verify_token
from web_app.services.task_service import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class RunTaskRequest(BaseModel):
    task_content: str
    device_ids: list[str]
    model_settings: Optional[dict] = None
    send_email: Optional[bool] = True  # Default True for backward compatibility


class TaskResponse(BaseModel):
    id: str
    task_content: str
    device_ids: list[str]
    status: str
    start_time: str
    end_time: str = ""
    results: list = []
    logs: list = []
    progress: int = 0


class TaskStatusResponse(BaseModel):
    running: bool
    task: Optional[TaskResponse] = None


@router.post("/run")
async def run_task(
    request: RunTaskRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_token)
):
    """
    Run a task on specified devices.

    This starts the task in the background and returns immediately.
    Use /api/tasks/status to check progress or connect via WebSocket for real-time updates.
    """
    # Check if a task is already running
    current = task_service.get_current_task()
    if current:
        raise HTTPException(
            status_code=409,
            detail="A task is already running. Stop it first or wait for completion."
        )

    if not request.device_ids:
        raise HTTPException(status_code=400, detail="No devices specified")

    # Start task in background
    async def run_in_background():
        try:
            result = await task_service.run_task(
                task_content=request.task_content,
                device_ids=request.device_ids,
                model_config=request.model_settings,
                send_email=request.send_email if request.send_email is not None else True
            )
            # Broadcast task finished with screenshot
            from web_app.routers.websocket import broadcast_task_finished
            import base64
            success = result.status == "completed"
            message = f"Task {result.status}: {len([r for r in result.results if r.get('success')])} succeeded"
            # Get screenshot captured before lock (stored in task)
            screenshot_b64 = None
            screenshot_data = getattr(result, '_screenshot_data', None)
            if screenshot_data:
                screenshot_b64 = base64.b64encode(screenshot_data).decode('utf-8')
            await broadcast_task_finished(result.id, success, message, screenshot_b64)
        except Exception as e:
            # Broadcast error
            from web_app.routers.websocket import broadcast_task_finished
            await broadcast_task_finished("", False, f"Task failed: {str(e)}", None)

    background_tasks.add_task(run_in_background)

    return {
        "success": True,
        "message": "Task started",
        "task_content": request.task_content,
        "device_ids": request.device_ids
    }


@router.post("/stop")
async def stop_tasks(_: bool = Depends(verify_token)):
    """Stop all running tasks."""
    success = await task_service.stop_all_tasks()
    return {"success": success, "message": "Stop signal sent"}


@router.get("/status", response_model=TaskStatusResponse)
async def get_task_status(_: bool = Depends(verify_token)):
    """Get current task status."""
    status = task_service.get_task_status()
    return TaskStatusResponse(
        running=status["running"],
        task=TaskResponse(**status["task"]) if status["task"] else None
    )


@router.get("/history")
async def get_task_history(
    limit: int = 10,
    _: bool = Depends(verify_token)
):
    """Get recent task history."""
    history = task_service.get_task_history(limit)
    return {"tasks": history}
