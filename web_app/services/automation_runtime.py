"""Persistent per-device queues and cooperative control. Never cancel a live device thread."""
import asyncio
import base64
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

from web_app.services.automation_storage import AutomationStorage

logger = logging.getLogger(__name__)
TERMINAL = {'completed', 'failed', 'stopped', 'expired', 'cancelled'}
ACTIVE = {'running', 'pausing', 'paused', 'waiting_for_user'}


class Conflict(ValueError):
    pass


class Interrupted(RuntimeError):
    pass


class Control:
    def __init__(self, changed, timeout=180, online=lambda: True):
        self.condition = threading.Condition()
        self.changed = changed
        self.online = online
        self.state = 'running'
        self.stopped = False
        self.shutdown = False
        self.generation = 0
        self.seen = 0
        self.note = ''
        self.timeout = timeout
        self.started = time.monotonic()
        self.waited = 0.0

    def pause(self, waiting=False, reason=''):
        # Never block the asyncio thread on an ADB action or a debug confirmation.
        # A committed action may finish; acknowledgement occurs at its next boundary.
        if self.state not in {'running', 'pausing'}:
            return
        self.generation += 1
        self.state = 'waiting_for_user' if waiting else 'pausing'
        self.changed(self.state, reason)

    def checkpoint(self):
        with self.condition:
            if self.state == 'pausing':
                self.state = 'paused'
                self.changed('paused', '')
            start = time.monotonic()
            while self.state in {'paused', 'waiting_for_user'} and not self.stopped:
                self.condition.wait(.25)
            self.waited += time.monotonic() - start
            if self.stopped:
                raise Interrupted('stopped')
            if not self.online():
                raise Interrupted('Device disconnected; confirm resume after reconnection')
            if self.timeout and time.monotonic()-self.started-self.waited > self.timeout:
                raise TimeoutError('Active execution timeout')
            if self.stopped:
                raise Interrupted('stopped')
            stale = self.generation != self.seen
            self.seen = self.generation
            return stale

    def resume(self, note=''):
        with self.condition:
            if self.state not in {'paused', 'waiting_for_user'}:
                raise Conflict('Task is not paused')
            self.note = note
            self.state = 'running'
            self.changed('running', note)
            self.condition.notify_all()

    def stop(self):
        self.stopped = True
        # Paused waiters release this lock; active device actions need not be blocked.
        if self.condition.acquire(blocking=False):
            try:
                self.condition.notify_all()
            finally:
                self.condition.release()


class Runtime:
    def __init__(self, store, runner=None, devices=None):
        self.store = store
        self.runner = runner or self.run_device
        self.device_probe = self.adb_online
        self.devices = devices or self.connected_devices
        self.controls = {}
        self.workers = {}
        self.reservations = {}
        self.loop = None
        self.poller = None
        self.closing = False
        self.listeners = []
        self.notifications = set()
        self.model_configs = {}
        self.manual_busy = {}
        self.settings = self.store.get('settings', 'runtime') or {
            'id': 'runtime', 'concurrency': 2, 'enabled': True, 'recipes_enabled': True,
            'demonstrations_enabled': True, 'triggers_enabled': True,
            'timezone': self.local_timezone()}
        self.store.put('settings', self.settings)
        self.catalog = None
        self.process_lock = None

    @staticmethod
    def local_timezone():
        try:
            return Path('/etc/localtime').resolve().as_posix().split('/zoneinfo/')[1]
        except (IndexError, OSError):
            return 'UTC'

    @staticmethod
    def connected_devices():
        from web_app.services.device_service import device_service
        return {d.id for d in device_service.get_all_devices() if d.status == 'connected'}

    @staticmethod
    def adb_online(device):
        try:
            result = subprocess.run(['adb','-s',device,'get-state'],capture_output=True,text=True,timeout=3)
            return result.returncode == 0 and result.stdout.strip() == 'device'
        except (OSError,subprocess.TimeoutExpired):
            return False

    async def start(self):
        if self.poller:
            return
        # The OS releases the lock on crash; a second worker fails closed.
        self.process_lock = open(str(self.store.path)+'.lock', 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.process_lock.write(b'0')
                self.process_lock.flush()
                self.process_lock.seek(0)
                msvcrt.locking(self.process_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.process_lock.close()
            self.process_lock = None
            raise RuntimeError('Only one backend process may control automation devices')
        self.loop = asyncio.get_running_loop()
        for task in self.store.list('task'):
            for child in task['executions']:
                if child['status'] in ACTIVE:
                    child['status'] = 'interrupted'
                    child['message'] = 'Server restarted; confirm resume'
            self.save(task)
        for demo in self.store.list('demonstration'):
            if demo['status'] in {'recording', 'paused'}:
                demo['status'] = 'interrupted'
                self.store.put('demonstration', demo)
        self.closing = False
        self.poller = asyncio.create_task(self.poll())

    async def close(self):
        self.closing = True
        if self.poller:
            self.poller.cancel()
            await asyncio.gather(self.poller, return_exceptions=True)
            self.poller = None
        for control in self.controls.values():
            control.shutdown = True
            control.stop()
        # Await threads and their cleanup; cancelling asyncio wrappers is unsafe.
        await asyncio.gather(*list(self.workers.values()), return_exceptions=True)
        # Flush scheduled completion listeners before awaiting report delivery.
        await asyncio.sleep(0)
        await asyncio.gather(*list(self.notifications), return_exceptions=True)
        if self.process_lock:
            self.process_lock.close()
            self.process_lock = None

    def get(self, key):
        task = self.store.get('task', key)
        if task is None:
            raise KeyError(key)
        return task

    def save(self, task):
        previous = self.store.get('task', task['id'])
        statuses = [c['status'] for c in task['executions']]
        if all(s in TERMINAL for s in statuses):
            task['status'] = ('completed' if all(s == 'completed' for s in statuses) else
                              'cancelled' if all(s == 'cancelled' for s in statuses) else
                              'stopped' if all(s == 'stopped' for s in statuses) else 'failed')
            task['end_time'] = task.get('end_time') or time.time()
        else:
            task['status'] = next((s for s in ('waiting_for_user', 'pausing', 'paused', 'running', 'interrupted', 'pending') if s in statuses), 'pending')
        task['progress'] = int(100*sum(1 if c['status'] in TERMINAL else
            c['step_index']/max(1,len(c.get('steps') or task['steps'])) for c in task['executions'])/len(statuses))
        task['results'] = [{**c, 'success': c['status'] == 'completed'} for c in task['executions']]
        self.store.put('task', task)
        if previous and previous['status'] not in TERMINAL and task['status'] in TERMINAL:
            self.emit(task['id'], '', 'task_finished', {'status': task['status']})

    def emit(self, task_id, device_id, kind, data):
        data = dict(data)
        encoded = data.pop('image', None)
        if encoded and not data.get('sensitive'):
            data['image_id'] = self.store.image(encoded)
        event = self.store.event(task_id, device_id, kind, data)
        if self.loop:
            self.loop.call_soon_threadsafe(self.deliver, event)
        return event

    def deliver(self, event):
        for listener in self.listeners:
            try:
                listener(event)
            except Exception:
                logger.exception('Automation event listener failed')

    def submit(self, content, device_ids, steps=None, parallel=False, queue=True, **options):
        if not self.settings['enabled']:
            raise Conflict('Automation is disabled')
        if not content.strip() or not device_ids or len(set(device_ids)) != len(device_ids):
            raise ValueError('Provide task content and unique device IDs')
        if not queue and any(self.busy(d) for d in device_ids):
            raise Conflict('Device busy; choose queue or stop the current task')
        if options.get('task_type') == 'chat' and not options.get('message_id'):
            from web_app.services.chat_service import chat_service
            if not options.get('session_id'):
                session = chat_service.create_session(device_ids[0], content[:50])
                options['session_id'] = session['id']
                chat_service.add_message(session['id'], 'user', content)
            message = chat_service.add_message(options['session_id'], 'assistant', '任务已排队')
            chat_service.update_message(message['id'],status='running')
            options['message_id'] = message['id']
        transient_model = options.pop('model_config', None)
        now = time.time()
        task = dict(id=uuid.uuid4().hex, task_content=content, device_ids=device_ids,
                    status='pending', start_time=now, end_time=None, progress=0, logs=[], results=[],
                    parallel=parallel, options=options, steps=steps or [{'content': content, 'timeout': 180}],
                    executions=[dict(id=uuid.uuid4().hex, device_id=d, status='pending', step_index=0,
                                     verification={'status': 'not_requested'}, created=now, queued_at=now,
                                     message='', tokens=0) for d in device_ids])
        if options.get('sequence'):
            sequence = options['sequence']
            task['parallel'] = False
            task['steps'] = [{'content':s['content'],'device_id':s['device_id']} for s in sequence]
            task['executions'] = [dict(id=uuid.uuid4().hex, device_id=segment['device_id'],
                status='pending', step_index=0, verification={'status':'not_requested'}, created=now,
                queued_at=now, message='', tokens=0, steps=[{'content':segment['content'],'timeout':segment.get('timeout',180)}])
                for segment in sequence]
        if transient_model:
            self.model_configs[task['id']] = transient_model
        self.save(task)
        self.emit(task['id'], '', 'submitted', {'status': 'pending'})
        return task

    def busy(self, device):
        return device in self.reservations or self.manual_busy.get(device, 0) > time.monotonic() or any(
            c['device_id'] == device and c['status'] not in TERMINAL
            for t in self.store.list('task') for c in t['executions'])

    def owner(self, device):
        for t in self.store.list('task'):
            for c in t['executions']:
                if c['device_id'] == device and c['status'] in ACTIVE | {'interrupted'}:
                    return t, c
        return None

    def manual_allowed(self, device):
        owner = self.owner(device)
        return not owner or owner[1]['status'] in {'paused', 'waiting_for_user'}

    def control(self, task_id, action, note='', device_ids=None):
        task = self.get(task_id)
        eligible = False
        for child in task['executions']:
            if device_ids is not None and child['device_id'] not in device_ids:
                continue
            control = self.controls.get(child['id'])
            status = child['status']
            if action == 'stop' and status not in TERMINAL:
                eligible = True
                if control:
                    control.stop()
                else:
                    child['status'] = 'stopped'
            elif action == 'pause' and status == 'running' and control:
                eligible = True
                control.pause()
            elif action == 'resume' and status in {'paused', 'waiting_for_user'} and control:
                if self.manual_busy.get(child['device_id'], 0) > time.monotonic():
                    raise Conflict('Manual input is still in progress')
                eligible = True
                control.resume(note)
            elif action == 'resume' and status == 'interrupted':
                if child['device_id'] not in self.devices():
                    raise Conflict('Reconnect device before resuming')
                eligible = True
                child['status'] = 'pending'
                child['queued_at'] = time.time()
                child['resume_note'] = note
        if not eligible:
            raise Conflict('Invalid task state for '+action)
        # Callbacks may have updated the document; merge only non-live children.
        with self.store.lock:
            latest = self.get(task_id)
            for child in task['executions']:
                if child['id'] not in self.controls:
                    next(c for c in latest['executions'] if c['id'] == child['id']).update(child)
            self.save(latest)
        return self.get(task_id)

    async def wait(self, key):
        while True:
            task = self.get(key)
            if task['status'] in TERMINAL:
                return task
            await asyncio.sleep(.1)

    async def poll(self):
        cleanup_at = 0
        while not self.closing:
            try:
                await self.tick()
                if time.time() > cleanup_at:
                    self.store.cleanup()
                    cleanup_at = time.time()+3600
            except Exception:
                logger.exception('Automation dispatch failed')
            await asyncio.sleep(.25)

    async def tick(self):
        with self.store.lock:
            online = self.devices()
            occupied = set(self.reservations) | {d for d, until in self.manual_busy.items() if until > time.monotonic()}
            # Include interrupted owners, preventing later tasks from bypassing recovery.
            for t in self.store.list('task'):
                occupied.update(c['device_id'] for c in t['executions'] if c['status'] in ACTIVE | {'interrupted'})
            head_seen = set()
            records = sorted(self.store.list('task'),key=lambda t:(not t['options'].get('after_current',False),t['start_time']))
            for task in records:
                for index, child in enumerate(task['executions']):
                    d = child['device_id']
                    if child['status'] != 'pending':
                        continue
                    if time.time()-child.get('queued_at', child['created']) > task['options'].get('queue_timeout', 1800):
                        child.update(status='expired', message='Queue timeout')
                        self.save(task)
                        continue
                    if d in head_seen:
                        continue
                    head_seen.add(d)
                    if len(self.workers) >= self.settings['concurrency'] or d in occupied or d not in online:
                        continue
                    if not task['parallel'] and any(c['status'] not in TERMINAL for c in task['executions'][:index]):
                        continue
                    occupied.add(d)
                    child['status'] = 'running'
                    child['started'] = time.time()
                    child['queue_wait'] = child['started']-child.get('queued_at',child['created'])
                    self.save(task)
                    worker = asyncio.create_task(self.execute(task['id'], child['id']))
                    self.workers[child['id']] = worker
                    worker.add_done_callback(lambda _, key=child['id']: self.workers.pop(key, None))

    def update_child(self, task_id, child_id, **changes):
        # Serialize worker-thread updates and asyncio control updates.
        with self.store.lock:
            task = self.get(task_id)
            child = next(c for c in task['executions'] if c['id'] == child_id)
            child.update(changes)
            self.save(task)
            return child

    async def execute(self, task_id, child_id):
        task = self.get(task_id)
        child = next(c for c in task['executions'] if c['id'] == child_id)
        d = child['device_id']
        if child['status'] in TERMINAL:
            return
        def changed(state, reason):
            updates = {'status':state,'message':reason}
            if state == 'waiting_for_user':
                current = next(c for c in self.get(task_id)['executions'] if c['id'] == child_id)
                updates['takeovers'] = current.get('takeovers',0)+1
            self.update_child(task_id, child_id, **updates)
            self.emit(task_id, d, 'state', {'status': state, 'reason': reason})
        control = Control(changed, online=lambda: d in self.devices() and
                          (self.runner != self.run_device or self.device_probe(d)))
        self.controls[child_id] = control
        if self.closing:
            control.shutdown = True
            control.stop()
        try:
            await asyncio.to_thread(control.checkpoint)
            if task['options'].get('trigger_id'):
                from web_app.services.automation_catalog import Catalog
                catalog = self.catalog or Catalog(self)
                if not await catalog.trigger_valid(task):
                    self.update_child(task_id, child_id, status='cancelled', message='Trigger condition no longer applies')
                    catalog.trigger_log(self.store.get('trigger', task['options']['trigger_id']) or {'id':task['options']['trigger_id']}, 'condition_invalid')
                    return
            execution_steps = child.get('steps') or task['steps']
            for index in range(child['step_index'], len(execution_steps)):
                step = execution_steps[index]
                child['step_index'] = index
                self.update_child(task_id, child_id, step_index=index)
                self.emit(task_id, d, 'subtask', {'index': index, 'content': step['content']})
                control.timeout = step.get('timeout', 180)
                control.started = time.monotonic()
                control.waited = 0
                attempts = 2 if step.get('repeatable') and step.get('retry_once') else 1
                for attempt in range(attempts):
                    result = await self.runner(task, child, step, control)
                    await asyncio.to_thread(control.checkpoint)
                    current = next(c for c in self.get(task_id)['executions'] if c['id']==child_id)
                    self.update_child(task_id,child_id,step_results=current.get('step_results',[])+[{
                        **result,'index':index,'attempt':attempt+1}])
                    if result['success'] or control.stopped or result.get('reason','').startswith('verification_'):
                        break
                    self.emit(task_id, d, 'retry', {'index': index, 'attempt': attempt+1})
                if not result['success']:
                    self.update_child(task_id, child_id, status='stopped' if control.stopped else 'failed',
                                      message=result['message'], reason=result.get('reason', 'failed'))
                    break
                self.update_child(task_id, child_id, step_index=index+1)
            else:
                self.update_child(task_id, child_id, status='completed', message=result.get('message','Execution ended') if 'result' in locals() else 'Execution ended')
        except Interrupted as exc:
            self.update_child(task_id, child_id, status='stopped' if control.stopped and not control.shutdown else 'interrupted', message=str(exc))
        except Exception as exc:
            logger.exception('Device execution failed')
            self.update_child(task_id, child_id, status='failed', message=str(exc))
        finally:
            self.controls.pop(child_id, None)
            with self.store.lock:
                final = self.get(task_id)
                ended = next(c for c in final['executions'] if c['id'] == child_id)
                ended['ended'] = time.time()
                ended['active_seconds'] = max(0,time.monotonic()-control.started-control.waited)
                if final['options'].get('sequence') and ended['status'] in TERMINAL and ended['status'] != 'completed':
                    for following in final['executions']:
                        if following['status'] == 'pending':
                            following.update(status='cancelled',message='Earlier device segment failed')
                self.save(final)
            self.emit(task_id, d, 'device_finished', {'execution': next(c for c in final['executions'] if c['id'] == child_id)})
            if final['status'] in TERMINAL:
                self.model_configs.pop(task_id, None)

    async def run_device(self, task, child, step, control):
        from phone_agent.agent import PhoneAgent, AgentConfig
        from phone_agent.model import ModelConfig
        from phone_agent.device_factory import get_device_factory
        from web_app.services.device_service import device_service
        from web_app.services.model_service import model_service
        d = child['device_id']
        config = self.model_configs.get(task['id'])
        if not config:
            active = model_service.get_active_service()
            if not active:
                raise ValueError('No model service configured')
            config = {k: getattr(active, k) for k in ('base_url', 'api_key', 'model_name', 'max_tokens', 'temperature', 'protocol')}
        self.model_configs[task['id']] = config
        # Credentials are resolved at execution time, never stored in task snapshots.
        cfg = ModelConfig(**{k: v for k, v in config.items() if k in ModelConfig.__dataclass_fields__})
        cfg.request_timeout = max(1, step.get('timeout',180))
        def intervention(message):
            control.pause(True, message)
            self.emit(task['id'], d, 'takeover', {'message': message})
            control.checkpoint()
        def confirm(message):
            intervention(message)
            # User may have changed the page; do not execute a stale sensitive action.
            return None
        debug = bool(task['options'].get('debug_mode'))
        preview = None
        if debug:
            from web_app.routers.websocket import create_tap_preview_callback
            preview = create_tap_preview_callback()
        agent = PhoneAgent(cfg, AgentConfig(device_id=d, max_steps=50, verbose=False, debug_mode=debug),
                           confirmation_callback=confirm, takeover_callback=intervention,
                           tap_preview_callback=preview)
        def checkpoint():
            stale = control.checkpoint()
            if control.note:
                agent._resume_feedback = '人工处理说明：'+control.note
                control.note = ''
            return stale
        agent.action_lock = control.condition
        agent.checkpoint_callback = checkpoint
        def event(kind, data):
            if kind == 'model':
                with self.store.lock:
                    latest = self.get(task['id'])
                    c = next(c for c in latest['executions'] if c['id'] == child['id'])
                    c['tokens'] += data.get('total_tokens', 0)
                    self.save(latest)
            self.emit(task['id'], d, kind, {**data, 'subtask': child['step_index']})
        agent.event_callback = event
        was_locked = await device_service.is_screen_locked(d)
        if 'initial_lock_state' not in child:
            child['initial_lock_state'] = was_locked
            self.update_child(task['id'], child['id'], initial_lock_state=was_locked)
        finished_step = False
        try:
            if was_locked and not await device_service.unlock_device(d, device_service.get_device_pin(d)):
                raise ValueError('Failed to unlock device')
            # Keep current task instruction first even when recovering with a note.
            instruction = step['content']
            context = task['options'].get('conversation_context')
            if context:
                instruction += ('\n\n以下是本次提交时同一会话的历史快照，仅作为背景理解参数和约束。'
                                '不要重做历史任务或执行历史中尚未确认的建议；仅执行上面的当前子任务。\n'+
                                json.dumps(context, ensure_ascii=False))
            if child.get('resume_note'):
                instruction += '\n人工恢复说明：'+child['resume_note']
            outcome = await asyncio.to_thread(agent.run_result, instruction)
            await asyncio.to_thread(control.checkpoint)
            factory = get_device_factory()
            screen = await asyncio.to_thread(factory.get_screenshot, d)
            screen_event = self.emit(task['id'], d, 'screen', {'image': screen.base64_data, 'width': screen.width,
                                             'height': screen.height, 'sensitive': screen.is_sensitive, 'final': True})
            is_last = child['step_index'] == len(child.get('steps') or task['steps'])-1
            conditions = [step['acceptance']] if step.get('acceptance') else []
            if is_last and task['options'].get('acceptance') and (not task['options'].get('sequence') or child['id'] == task['executions'][-1]['id']):
                conditions.append(task['options']['acceptance'])
            if outcome.success:
                step_titles = [s.get('content', '') for s in (child.get('steps') or task.get('steps') or []) if s.get('content')]
                for condition in conditions:
                    while True:
                        verification = await self.verify(agent, d, screen, condition, steps=step_titles)
                        if not await asyncio.to_thread(control.checkpoint):
                            break
                        screen = await asyncio.to_thread(factory.get_screenshot, d)
                        screen_event = self.emit(task['id'],d,'screen',{'image':screen.base64_data,
                            'width':screen.width,'height':screen.height,'sensitive':screen.is_sensitive,'final':True})
                    verification['image_id'] = screen_event['data'].get('image_id')
                    verification['subtask'] = child['step_index']
                    current = next(c for c in self.get(task['id'])['executions'] if c['id'] == child['id'])
                    checks = current.get('checks', [])+[verification]
                    changes = {'checks':checks, 'tokens':current['tokens']+verification['tokens']}
                    if is_last or verification['status'] != 'passed':
                        changes['verification'] = verification
                    self.update_child(task['id'], child['id'], **changes)
                    self.emit(task['id'], d, 'verification', verification)
                    if verification['status'] != 'passed':
                        return {'success': False, 'reason': 'verification_'+verification['status'], 'message': verification['explanation']}
            finished_step = outcome.success
            return outcome.__dict__
        finally:
            # run_result has finished before restoring device state or releasing ownership.
            restore = task['options'].get('restore_lock_to_state')
            restore = child['initial_lock_state'] if restore is None else restore
            is_last = child['step_index'] == len(child.get('steps') or task['steps'])-1
            if restore and (not finished_step or is_last) and not task['options'].get('no_auto_lock'):
                await device_service.lock_device(d)

    async def verify(self, agent, device, screen, condition, steps=None):
        from phone_agent.device_factory import get_device_factory
        from phone_agent.model.client import MessageBuilder
        result = {'status': 'inconclusive', 'condition': condition, 'explanation': '', 'tokens': 0}
        if isinstance(condition, dict) and condition.get('foreground_app'):
            app = await asyncio.to_thread(get_device_factory().get_current_app, device)
            result.update(status='passed' if app == condition['foreground_app'] else 'failed', explanation=f'Foreground: {app}')
            return result
        if screen.is_sensitive:
            result['explanation'] = 'Screenshot unavailable or sensitive'
            return result
        try:
            context = f'已执行步骤：{json.dumps(steps, ensure_ascii=False)}。' if steps else ''
            prompt = ('仅观察截图，不执行任何操作。根据验收条件返回 JSON：'
                      '{"status":"passed|failed|inconclusive","explanation":"证据说明"}。'
                      '若已执行步骤包含滑动浏览导致页面停留在同一界面的其他位置（如列表底部），只要能确认处于目标界面即视为满足界面停留条件。'
                      '看不到足够证据时必须 inconclusive。'+context+'验收条件：'+json.dumps(condition, ensure_ascii=False))
            response = await asyncio.to_thread(agent.model_client.request, [MessageBuilder.create_user_message(prompt, screen.base64_data)])
            result['tokens'] = response.total_tokens
            raw = response.raw_content
            parsed = json.loads(raw[raw.index('{'):raw.rindex('}')+1])
            if parsed.get('status') in {'passed', 'failed', 'inconclusive'}:
                result.update(status=parsed['status'], explanation=str(parsed.get('explanation', '')))
        except Exception as exc:
            result['explanation'] = f'Unable to verify: {exc}'
        return result


_runtime = None

def get_runtime():
    global _runtime
    if _runtime is None:
        path = Path(os.environ.get('AUTOGLM_AUTOMATION_DB', str(Path.home()/'.autoglm'/'automation.db')))
        _runtime = Runtime(AutomationStorage(path))
    return _runtime
