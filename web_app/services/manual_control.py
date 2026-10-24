"""Gate and record browser-originated input independently of scrcpy transport."""
import inspect
import time
from functools import wraps


def ensure_manual(device):
    from web_app.services.automation_runtime import get_runtime
    runtime = get_runtime()
    owner = runtime.owner(device)
    if owner and not runtime.manual_allowed(device):
        if owner[1]['status'] == 'running':
            runtime.control(owner[0]['id'], 'pause')
        raise PermissionError('正在暂停自动任务；状态变为已暂停后可操作设备')


def manual_input(kind):
    def decorate(fn):
        @wraps(fn)
        async def wrapped(self, device_id, *args, **kwargs):
            ensure_manual(device_id)
            from web_app.services.automation_runtime import get_runtime
            from web_app.services.automation_catalog import catalog
            runtime = get_runtime()
            bound = inspect.signature(fn).bind(self, device_id, *args, **kwargs)
            data = {k: v for k, v in bound.arguments.items() if k not in {'self', 'device_id'}}
            # Reserve between pointer down/up as well as during awaited ADB work.
            runtime.manual_busy[device_id] = time.monotonic()+60
            try:
                image_id = await catalog.capture_manual_frame(device_id, kind, data)
                result = await fn(self, device_id, *args, **kwargs)
                if result is not False or (kind == 'touch' and data.get('action') == 'cancel'):
                    catalog.record(device_id, kind, data, image_id=image_id)
                return result
            finally:
                if kind != 'touch' or data.get('action') in {'up', 'cancel'}:
                    runtime.manual_busy.pop(device_id, None)
        return wrapped
    return decorate


def manual_endpoint(fn):
    """Reserve the device while an HTTP screen-control command is in flight."""
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        from fastapi import HTTPException
        from web_app.services.automation_runtime import get_runtime
        device = kwargs.get('device_id') or args[0]
        try:
            ensure_manual(device)
        except PermissionError as exc:
            raise HTTPException(409, str(exc))
        runtime = get_runtime()
        runtime.manual_busy[device] = time.monotonic()+60
        try:
            return await fn(*args, **kwargs)
        finally:
            runtime.manual_busy.pop(device, None)
    return wrapped
