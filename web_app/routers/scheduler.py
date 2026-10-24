# -*- coding: utf-8 -*-
"""
Scheduler API router.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from web_app.models.scheduler import ScheduledTask
from web_app.auth import verify_token
from web_app.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class ScheduledTaskCreate(BaseModel):
    name: str
    task_content: str
    enabled: bool = True
    schedule_type: str = "daily"
    run_at: str = ""
    interval_minutes: int = 60
    daily_time: str = "09:00"
    weekly_days: list[int] = [0]
    weekly_time: str = "09:00"
    monthly_day: int = 1
    monthly_time: str = "09:00"
    devices: list[str] = []
    timezone: str = ""
    busy_policy: str = "queue"
    recipe_id: str = ""
    recipe_revision: Optional[int] = None
    recipe_parameters: dict = {}



class ScheduledTaskUpdate(BaseModel):
    id: str
    name: str
    task_content: str
    enabled: bool = True
    schedule_type: str = "daily"
    run_at: str = ""
    interval_minutes: int = 60
    daily_time: str = "09:00"
    weekly_days: list[int] = [0]
    weekly_time: str = "09:00"
    monthly_day: int = 1
    monthly_time: str = "09:00"
    devices: list[str] = []
    timezone: str = ""
    busy_policy: str = "queue"
    recipe_id: str = ""
    recipe_revision: Optional[int] = None
    recipe_parameters: dict = {}



class ToggleRequest(BaseModel):
    enabled: bool


@router.get("/tasks")
async def get_scheduled_tasks(_: bool = Depends(verify_token)):
    """Get all scheduled tasks."""
    tasks = scheduler_service.get_all_tasks_dict()
    return {"tasks": tasks}


@router.get("/tasks/{task_id}")
async def get_scheduled_task(task_id: str, _: bool = Depends(verify_token)):
    """Get a specific scheduled task."""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/tasks")
async def create_scheduled_task(
    request: ScheduledTaskCreate,
    _: bool = Depends(verify_token)
):
    """Create a new scheduled task."""
    if request.busy_policy not in {'queue', 'skip'}:
        raise HTTPException(422, 'busy_policy must be queue or skip')
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    from web_app.services.automation_runtime import get_runtime
    try:
        ZoneInfo(request.timezone or get_runtime().settings['timezone'])
    except ZoneInfoNotFoundError:
        raise HTTPException(422, 'Unknown timezone')
    if request.recipe_id:
        from web_app.services.automation_catalog import catalog
        try:
            recipe = catalog.recipe(request.recipe_id, request.recipe_revision)
            catalog.bind(recipe, request.recipe_parameters)
            request.recipe_revision = recipe['revision']
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, str(exc))
    task = ScheduledTask(
        name=request.name,
        task_content=request.task_content,
        enabled=request.enabled,
        schedule_type=request.schedule_type,
        run_at=request.run_at,
        interval_minutes=request.interval_minutes,
        daily_time=request.daily_time,
        weekly_days=request.weekly_days,
        weekly_time=request.weekly_time,
        monthly_day=request.monthly_day,
        monthly_time=request.monthly_time,
        devices=request.devices,
        timezone=request.timezone, busy_policy=request.busy_policy,
        recipe_id=request.recipe_id, recipe_revision=request.recipe_revision,
        recipe_parameters=request.recipe_parameters,
    )
    task_id = scheduler_service.add_task(task)
    return {"success": True, "task_id": task_id, "task": task.to_dict()}


@router.put("/tasks/{task_id}")
async def update_scheduled_task(
    task_id: str,
    request: ScheduledTaskUpdate,
    _: bool = Depends(verify_token)
):
    """Update an existing scheduled task."""
    existing = scheduler_service.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    for field in ('timezone','busy_policy','recipe_id','recipe_revision','recipe_parameters'):
        if field not in request.model_fields_set:
            setattr(request,field,getattr(existing,field))
    if request.busy_policy not in {'queue', 'skip'}:
        raise HTTPException(422, 'busy_policy must be queue or skip')
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    from web_app.services.automation_runtime import get_runtime
    try:
        ZoneInfo(request.timezone or get_runtime().settings['timezone'])
    except ZoneInfoNotFoundError:
        raise HTTPException(422, 'Unknown timezone')
    if request.recipe_id:
        from web_app.services.automation_catalog import catalog
        try:
            recipe = catalog.recipe(request.recipe_id, request.recipe_revision)
            catalog.bind(recipe, request.recipe_parameters)
            request.recipe_revision = recipe['revision']
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, str(exc))
    task = ScheduledTask(
        id=task_id,
        name=request.name,
        task_content=request.task_content,
        enabled=request.enabled,
        schedule_type=request.schedule_type,
        run_at=request.run_at,
        interval_minutes=request.interval_minutes,
        daily_time=request.daily_time,
        weekly_days=request.weekly_days,
        weekly_time=request.weekly_time,
        monthly_day=request.monthly_day,
        monthly_time=request.monthly_time,
        devices=request.devices,
        timezone=request.timezone, busy_policy=request.busy_policy,
        recipe_id=request.recipe_id, recipe_revision=request.recipe_revision,
        recipe_parameters=request.recipe_parameters,
        last_run=existing.last_run,
        run_count=existing.run_count,
        created_at=existing.created_at,
    )

    success = scheduler_service.update_task(task)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update task")

    return {"success": True, "task": task.to_dict()}


@router.delete("/tasks/{task_id}")
async def delete_scheduled_task(task_id: str, _: bool = Depends(verify_token)):
    """Delete a scheduled task."""
    success = scheduler_service.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": "Task deleted"}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str, background_tasks: BackgroundTasks, _: bool = Depends(verify_token)):
    """Immediately run a scheduled task."""
    from web_app.services.task_service import task_service
    from web_app.services.device_service import device_service

    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from web_app.services.schedule_execution import submit_schedule, watch_schedule
    from web_app.services.automation_runtime import Conflict
    import asyncio
    try:
        record = submit_schedule(task)
    except (ValueError, Conflict) as exc:
        raise HTTPException(409, str(exc))
    scheduler_service.running_tasks.add(task.id)
    asyncio.create_task(watch_schedule(task, record))
    return {'success': True, 'task_id': record['id'], 'message': 'Task queued'}


@router.patch("/tasks/{task_id}/toggle")
async def toggle_task(
    task_id: str,
    request: ToggleRequest,
    _: bool = Depends(verify_token)
):
    """Enable or disable a scheduled task."""
    success = scheduler_service.set_task_enabled(task_id, request.enabled)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "enabled": request.enabled}


@router.get("/logs")
async def get_all_logs(limit: int = 50, _: bool = Depends(verify_token)):
    """Get all execution logs across all tasks."""
    logs = scheduler_service.get_all_logs(limit)
    return {"logs": logs}


@router.delete("/logs")
async def clear_all_logs(_: bool = Depends(verify_token)):
    """Clear all execution logs."""
    scheduler_service.clear_all_logs()
    return {"success": True, "message": "All logs cleared"}


@router.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, limit: int = 20, _: bool = Depends(verify_token)):
    """Get execution logs for a specific task."""
    task = scheduler_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logs = scheduler_service.get_task_logs(task_id, limit)
    return {"task_id": task_id, "task_name": task.name, "logs": logs}


@router.delete("/tasks/{task_id}/logs")
async def clear_task_logs(task_id: str, _: bool = Depends(verify_token)):
    """Clear logs for a specific task."""
    scheduler_service.clear_task_logs(task_id)
    return {"success": True, "message": "Logs cleared"}
