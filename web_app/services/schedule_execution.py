"""All scheduled executions submit through the same persistent device queue."""
import asyncio

from web_app.services.automation_runtime import get_runtime, TERMINAL
from web_app.services.automation_catalog import catalog


def submit_schedule(task):
    runtime = get_runtime()
    devices = task.devices or sorted(runtime.devices())
    if not devices:
        raise ValueError('No target devices configured or online')
    for old in runtime.store.list('task'):
        if old['options'].get('schedule_id') == task.id and old['status'] not in TERMINAL:
            return old
    if task.busy_policy == 'skip' and any(runtime.busy(d) for d in devices):
        raise ValueError('Skipped: target device is busy')
    if task.recipe_id:
        return catalog.run_recipe(task.recipe_id, devices, task.recipe_parameters,
                                  task.recipe_revision, schedule_id=task.id, is_scheduled=True,
                                  task_type='scheduled')
    return runtime.submit(task.task_content, devices, queue=True, schedule_id=task.id,
                          is_scheduled=True, task_type='scheduled')


async def watch_schedule(task, record):
    from web_app.services.scheduler_service import scheduler_service
    try:
        final = await get_runtime().wait(record['id'])
        scheduler_service.add_task_log(task.id, final['status'] == 'completed', final['status'],
                                       '\n'.join(c.get('message', '') for c in final['executions']))
    finally:
        scheduler_service.mark_task_finished(task.id)
