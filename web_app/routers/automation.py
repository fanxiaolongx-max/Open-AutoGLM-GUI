"""Authenticated automation API. Legacy static task routes are registered first."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Optional

from web_app.models.automation import RecipeDefinition, TriggerDefinition
from web_app.auth import verify_token
from web_app.services.automation_runtime import get_runtime, Conflict
from web_app.services.automation_catalog import catalog

router = APIRouter(dependencies=[Depends(verify_token)], tags=['automation'])


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, 'Not found: '+str(exc))
    except Conflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))


class Resume(BaseModel):
    note: str = ''


class RecipeRun(BaseModel):
    device_ids: list[str] = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)
    revision: Optional[int] = None
    parallel: bool = False
    trial: bool = False


class DemoStart(BaseModel):
    device_id: str
    record_text: bool = False
    record_images: bool = True


class DraftRequest(BaseModel):
    name: str = ''


class RuntimeSettings(BaseModel):
    concurrency: int = Field(default=2, ge=1, le=16)
    enabled: bool = True
    recipes_enabled: bool = True
    demonstrations_enabled: bool = True
    triggers_enabled: bool = True
    timezone: str


@router.get('/api/automation/settings')
async def get_settings():
    return get_runtime().settings


@router.put('/api/automation/settings')
async def settings(request: RuntimeSettings):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(request.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, 'Unknown IANA timezone')
    runtime = get_runtime()
    runtime.settings = {'id': 'runtime', **request.model_dump()}
    return runtime.store.put('settings', runtime.settings)


@router.get('/api/automation/tasks')
async def tasks(limit: int = Query(50, ge=1, le=500)):
    return {'tasks': get_runtime().store.list('task')[-limit:][::-1]}


@router.get('/api/tasks/{task_id}')
async def task(task_id: str):
    return call(get_runtime().get, task_id)


@router.post('/api/tasks/{task_id}/pause')
async def pause(task_id: str):
    return call(get_runtime().control, task_id, 'pause')


@router.post('/api/tasks/{task_id}/resume')
async def resume(task_id: str, request: Resume):
    return call(get_runtime().control, task_id, 'resume', request.note)


@router.post('/api/tasks/{task_id}/stop')
async def stop(task_id: str):
    return call(get_runtime().control, task_id, 'stop')


@router.get('/api/tasks/{task_id}/events')
async def events(task_id: str, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    call(get_runtime().get, task_id)
    items = get_runtime().store.events(task_id, after, limit)
    return {'events': items, 'cursor': items[-1]['seq'] if items else after}


@router.post('/api/tasks/{task_id}/rerun')
async def rerun(task_id: str, request: dict):
    runtime = get_runtime()
    original = call(runtime.get, task_id)
    index = request.get('step_index', 0)
    if not isinstance(index, int) or not 0 <= index < len(original['steps']):
        raise HTTPException(422, 'Invalid subtask index')
    if original['options'].get('sequence'):
        sequence=original['options']['sequence'][index:]
        devices=list(dict.fromkeys(s['device_id'] for s in sequence))
        return call(runtime.submit,original['task_content'],devices,sequence=sequence,queue=True,
                    parent_task_id=task_id,acceptance=original['options'].get('acceptance'))
    return call(runtime.submit, original['task_content'], request.get('device_ids') or original['device_ids'],
                steps=original['steps'][index:], queue=True, parent_task_id=task_id,
                acceptance=original['options'].get('acceptance'))


@router.get('/api/automation/images/{image_id}')
async def image(image_id: str):
    data = get_runtime().store.get_image(image_id)
    if not data:
        raise HTTPException(410, 'Screenshot expired or unavailable')
    return Response(data, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store'})


@router.post('/api/automation/images/{image_id}/pin')
async def pin(image_id: str, value: dict):
    if not get_runtime().store.get_image(image_id):
        raise HTTPException(410, 'Screenshot expired or unavailable')
    with get_runtime().store.connection() as conn:
        conn.execute('UPDATE images SET pinned=? WHERE id=?', (int(bool(value.get('pinned', True))), image_id))
    return {'success': True}


@router.get('/api/recipes')
async def recipes():
    return {'recipes': get_runtime().store.list('recipe')}


@router.post('/api/recipes')
async def create_recipe(request: RecipeDefinition):
    return call(catalog.save_recipe, request.model_dump(exclude_none=True))


@router.post('/api/recipes/import')
async def import_recipe(request: RecipeDefinition):
    return call(catalog.save_recipe, request.model_dump(exclude_none=True))


@router.post('/api/recipes/from-task/{task_id}')
async def from_task(task_id: str):
    task = call(get_runtime().get, task_id)
    if task['options'].get('sequence'):
        raise HTTPException(409,'多设备分段任务请先拆为单设备配方')
    if task['status'] != 'completed':
        raise HTTPException(409, 'Only completed tasks can be saved as recipes')
    return call(catalog.save_recipe, {'name': task['task_content'], 'steps': task['steps'],
                                     'acceptance': task['options'].get('acceptance')})


@router.get('/api/recipes/{recipe_id}')
async def recipe(recipe_id: str):
    return call(catalog.recipe, recipe_id)


@router.get('/api/recipes/{recipe_id}/revisions')
async def revisions(recipe_id: str):
    call(catalog.recipe, recipe_id)
    return {'revisions': [r for r in get_runtime().store.list('revision') if r['recipe_id'] == recipe_id]}


@router.put('/api/recipes/{recipe_id}')
async def update_recipe(recipe_id: str, request: RecipeDefinition):
    return call(catalog.save_recipe, request.model_dump(exclude_none=True), recipe_id)


@router.post('/api/recipes/{recipe_id}/copy')
async def copy_recipe(recipe_id: str):
    source = call(catalog.export_recipe, recipe_id)
    source['name'] += '（副本）'
    return call(catalog.save_recipe, source)


@router.delete('/api/recipes/{recipe_id}')
async def archive_recipe(recipe_id: str):
    source = call(catalog.recipe, recipe_id)
    source['archived'] = True
    return call(catalog.save_recipe, source, recipe_id)


@router.get('/api/recipes/{recipe_id}/export')
async def export_recipe(recipe_id: str):
    return call(catalog.export_recipe, recipe_id)


@router.post('/api/recipes/{recipe_id}/run')
async def run_recipe(recipe_id: str, request: RecipeRun):
    return call(catalog.run_recipe, recipe_id, request.device_ids, request.parameters,
                request.revision, parallel=request.parallel, trial=request.trial)


@router.get('/api/demonstrations')
async def demos():
    return {'demonstrations': get_runtime().store.list('demonstration')}


@router.post('/api/demonstrations')
async def start_demo(request: DemoStart):
    return call(catalog.start_demo, request.device_id, request.record_text, request.record_images)


@router.get('/api/demonstrations/{demo_id}')
async def demo(demo_id: str):
    item = get_runtime().store.get('demonstration', demo_id)
    if item is None:
        raise HTTPException(404, 'Demonstration not found')
    return item


@router.post('/api/demonstrations/{demo_id}/draft')
async def draft_demo(demo_id: str, request: DraftRequest):
    try:
        return await catalog.draft_demo(demo_id, request.name)
    except KeyError:
        raise HTTPException(404, 'Demonstration not found')
    except Conflict as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(422, str(exc))


@router.post('/api/demonstrations/{demo_id}/{action}')
async def demo_action(demo_id: str, action: str):
    return call(catalog.demo_action, demo_id, action)


@router.get('/api/triggers')
async def triggers():
    return {'triggers': get_runtime().store.list('trigger')}


@router.post('/api/triggers')
async def create_trigger(request: TriggerDefinition):
    return call(catalog.save_trigger, request.model_dump(exclude_none=True))


@router.put('/api/triggers/{trigger_id}')
async def update_trigger(trigger_id: str, request: TriggerDefinition):
    if not get_runtime().store.get('trigger', trigger_id):
        raise HTTPException(404, 'Trigger not found')
    return call(catalog.save_trigger, request.model_dump(exclude_none=True), trigger_id)


@router.delete('/api/triggers/{trigger_id}')
async def disable_trigger(trigger_id: str, cancel_pending: bool = False):
    runtime = get_runtime()
    rule = runtime.store.get('trigger', trigger_id)
    if rule is None:
        raise HTTPException(404, 'Trigger not found')
    rule['enabled'] = False
    runtime.store.put('trigger', rule)
    if cancel_pending:
        for task in runtime.store.list('task'):
            if task['options'].get('trigger_id') == trigger_id and task['status'] == 'pending':
                runtime.control(task['id'], 'stop')
    return rule


@router.get('/api/triggers/{trigger_id}/history')
async def trigger_history(trigger_id: str):
    if not get_runtime().store.get('trigger',trigger_id):
        raise HTTPException(404,'Trigger not found')
    return {'history': [log for log in get_runtime().store.list('trigger_log') if log['trigger_id'] == trigger_id][-100:][::-1]}


class DeviceInput(BaseModel):
    kind: str
    text: str = ''
    package: str = ''


@router.post('/api/automation/devices/{device_id}/input')
async def device_input(device_id: str, request: DeviceInput):
    import asyncio
    import re
    import subprocess
    from web_app.services.manual_control import ensure_manual
    try:
        ensure_manual(device_id)
    except PermissionError as exc:
        raise HTTPException(409, str(exc))
    import time
    runtime = get_runtime()
    runtime.manual_busy[device_id] = time.monotonic()+60
    try:
        image_id = await catalog.capture_manual_frame(device_id, request.kind, {})
        if request.kind == 'text':
            from phone_agent.device_factory import get_device_factory
            # Switch/restore the input method exactly as the agent does.
            from phone_agent.actions.handler import ActionHandler
            handler = ActionHandler(device_id)
            def type_text():
                try:
                    handler.setup_keyboard()
                    get_device_factory().type_text(request.text, device_id)
                finally:
                    handler.restore_keyboard()
            await asyncio.to_thread(type_text)
            catalog.record(device_id, 'text', {'text': request.text}, image_id=image_id)
        elif request.kind == 'launch':
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', request.package):
                raise HTTPException(422, 'Valid Android package name required')
            result = await asyncio.to_thread(subprocess.run,
                                            ['adb','-s',device_id,'shell','monkey','-p',request.package,'1'],
                                            capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise HTTPException(422, 'Application launch failed')
            catalog.record(device_id, 'launch', {'package': request.package}, image_id=image_id)
        else:
            raise HTTPException(422, 'Input kind must be text or launch')
    finally:
        runtime.manual_busy.pop(device_id, None)
    return {'success': True}
