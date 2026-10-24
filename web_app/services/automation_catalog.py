"""Recipes, browser demonstrations and bounded state-change triggers."""
import asyncio
import copy
import json
import re
import subprocess
import time
import uuid
from datetime import date, time as daytime

from web_app.services.automation_runtime import Conflict, get_runtime, TERMINAL


class Catalog:
    def __init__(self, runtime=None):
        self._runtime = runtime
        if runtime is not None:
            runtime.catalog = self
        self.previous = {}
        self.monitor = None
        self.gestures = {}

    @property
    def runtime(self):
        return self._runtime or get_runtime()

    @property
    def store(self):
        return self.runtime.store

    def require(self, feature):
        if not self.runtime.settings.get(feature+'_enabled', True):
            raise Conflict(feature+' is disabled')

    def recipe(self, key, revision=None):
        recipe = self.store.get('recipe', key)
        if not recipe:
            raise KeyError(key)
        if revision is not None:
            recipe = self.store.get('revision', f'{key}:{revision}')
            if not recipe:
                raise KeyError(f'{key}:{revision}')
        return recipe

    def save_recipe(self, value, key=None):
        self.require('recipes')
        value = copy.deepcopy(value)
        if value.get('format_version', 1) != 1:
            raise ValueError('Unsupported recipe format version')
        if not isinstance(value.get('name'), str) or not value['name'].strip():
            raise ValueError('Recipe name required')
        steps = value.get('steps')
        if not isinstance(steps, list) or not steps or len(steps) > 100:
            raise ValueError('Provide 1–100 sequential steps')
        params = value.get('parameters', [])
        if not isinstance(params, list) or any(not isinstance(p, dict) for p in params):
            raise ValueError('Parameters must be a list of definitions')
        names = set()
        for param in params:
            name = param.get('name', '')
            if not re.fullmatch(r'[\w\u4e00-\u9fff]+', name) or name in names:
                raise ValueError('Parameter names must be unique identifiers')
            names.add(name)
            if param.get('type', 'text') not in {'text', 'number', 'date', 'time', 'enum'}:
                raise ValueError('Unsupported parameter type')
            if param.get('type') == 'enum' and not param.get('options'):
                raise ValueError('Enum requires options')
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError('Steps must be objects')
            if not isinstance(step.get('content'), str) or not step['content'].strip():
                raise ValueError('Step content required')
            if not 1 <= float(step.get('timeout', 180)) <= 3600:
                raise ValueError('Step timeout must be between 1 and 3600 seconds')
            if step.get('retry_once') and not step.get('repeatable'):
                raise ValueError('Retry requires an explicitly repeatable step')
            for name in re.findall(r'{([\w\u4e00-\u9fff]+)}', json.dumps(step, ensure_ascii=False)):
                if name not in names:
                    raise ValueError('Undefined parameter: '+name)
        value['steps'] = [{k:step[k] for k in ('content','timeout','repeatable','retry_once','acceptance') if k in step} for step in steps]
        params = [{k:param[k] for k in ('name','type','default','options') if k in param} for param in params]
        previous = self.recipe(key) if key else None
        revision = previous['revision']+1 if previous else 1
        # Whitelist the portable schema; imported runtime state and credentials are discarded.
        saved = {k: value[k] for k in ('name', 'description', 'parameters', 'steps', 'target_app', 'acceptance') if k in value}
        saved.update(id=key or uuid.uuid4().hex, revision=revision, format_version=1,
                     parameters=params, archived=bool(value.get('archived', False)), verified=False,
                     created=previous['created'] if previous else time.time())
        self.store.put('recipe', saved)
        self.store.put('revision', {**saved, 'recipe_id': saved['id'], 'id': f"{saved['id']}:{revision}"})
        return saved

    @staticmethod
    def bind(recipe, values):
        if not isinstance(values, dict):
            raise ValueError('Parameters must be an object')
        bound = {}
        for p in recipe.get('parameters', []):
            name, kind = p['name'], p.get('type', 'text')
            value = values.get(name, p.get('default'))
            if value is None:
                raise ValueError('Missing parameter: '+name)
            if kind == 'number':
                if isinstance(value, bool):
                    raise ValueError('Invalid number: '+name)
                value = float(value)
                import math
                if not math.isfinite(value):
                    raise ValueError('Number must be finite')
            elif kind == 'date':
                value = date.fromisoformat(str(value)).isoformat()
            elif kind == 'time':
                value = daytime.fromisoformat(str(value)).isoformat()
            elif kind == 'enum' and value not in p['options']:
                raise ValueError('Invalid enum: '+name)
            elif kind == 'text':
                if not isinstance(value, str):
                    raise ValueError('Text parameter required: '+name)
            bound[name] = value
        def expand(value):
            if isinstance(value, str):
                return re.sub(r'{([\w\u4e00-\u9fff]+)}', lambda m: str(bound[m[1]]), value)
            if isinstance(value, list):
                return [expand(v) for v in value]
            if isinstance(value, dict):
                return {k: expand(v) for k, v in value.items()}
            return value
        return expand(recipe['steps']), expand(recipe.get('acceptance')), bound

    def run_recipe(self, key, devices, values=None, revision=None, **options):
        self.require('recipes')
        recipe = self.recipe(key, revision)
        if self.recipe(key).get('archived'):
            raise Conflict('Recipe is archived')
        steps, acceptance, bound = self.bind(recipe, values or {})
        if options.get('trial'):
            from web_app.services.automation_runtime import TERMINAL
            for existing in self.store.list('task'):
                opt = existing.get('options', {})
                if (existing.get('status') not in TERMINAL and opt.get('trial')
                        and opt.get('recipe_id') == key and opt.get('recipe_revision') == recipe['revision']
                        and existing.get('device_ids') == list(devices) and opt.get('parameters') == bound):
                    return existing
        return self.runtime.submit(recipe['name'], devices, steps=steps, queue=True, parallel=options.pop('parallel', False),
                                   recipe_id=key, recipe_revision=recipe['revision'], parameters=bound,
                                   acceptance=acceptance, **options)

    def export_recipe(self, key):
        r = self.recipe(key)
        return {k: r[k] for k in ('format_version', 'name', 'description', 'parameters', 'steps', 'target_app', 'acceptance') if k in r}

    def start_demo(self, device, record_text=False, record_images=True):
        self.require('demonstrations')
        if device not in self.runtime.devices():
            raise Conflict('Connect device before recording')
        if self.runtime.busy(device):
            raise Conflict('Device busy; finish or stop its task before recording')
        demo = dict(id=uuid.uuid4().hex, device_id=device, record_text=record_text, record_images=record_images,
                    status='recording', actions=[], created=time.time())
        self.runtime.reservations[device] = demo['id']
        return self.store.put('demonstration', demo)

    def demo_action(self, key, action):
        demo = self.store.get('demonstration', key)
        if not demo:
            raise KeyError(key)
        if action not in {'pause', 'resume', 'finish'}:
            raise ValueError('Unknown demonstration operation')
        allowed = {'pause': {'recording'}, 'resume': {'paused'}, 'finish': {'recording', 'paused', 'interrupted'}}
        if demo['status'] not in allowed[action]:
            raise Conflict('Invalid demonstration state')
        demo['status'] = {'pause': 'paused', 'resume': 'recording', 'finish': 'finished'}[action]
        self.gestures.pop(demo['device_id'], None)
        if action == 'finish':
            self.runtime.reservations.pop(demo['device_id'], None)
        return self.store.put('demonstration', demo)

    async def capture_manual_frame(self, device, kind, data):
        key = self.runtime.reservations.get(device)
        demo = self.store.get('demonstration', key) if key else None
        if not demo or demo['status'] != 'recording' or not demo.get('record_images',demo['record_text']):
            return None
        if kind == 'touch' and data.get('action') != 'down':
            return None
        try:
            # H.264 sessions have no decoded JPEG last_frame. ADB also covers this path.
            from phone_agent.device_factory import get_device_factory
            screen = await asyncio.to_thread(get_device_factory().get_screenshot, device)
            if screen.is_sensitive or not screen.base64_data:
                raise ValueError('当前画面受保护，无法保存截图')
            return self.store.image(screen.base64_data)
        except Exception as exc:
            latest = self.store.get('demonstration',key)
            if latest:
                latest['capture_error'] = '关键截图获取失败：'+type(exc).__name__
                self.store.put('demonstration',latest)
            return None

    def record(self, device, kind, data, image_id=None):
        key = self.runtime.reservations.get(device)
        demo = self.store.get('demonstration', key) if key else None
        if not demo or demo['status'] != 'recording':
            return
        data = copy.deepcopy(data)
        if kind == 'touch':
            phase = data.get('action')
            if phase == 'cancel':
                self.gestures.pop(device,None)
                return
            if phase == 'down':
                self.gestures[device] = {**data, 'started': time.monotonic(), 'image_id':image_id}
                return
            if phase != 'up':
                return
            first = self.gestures.pop(device, None)
            if not first:
                return
            image_id = first.get('image_id')
            data = dict(start=[first['x'], first['y']], end=[data['x'], data['y']],
                        width=first.get('width'), height=first.get('height'), duration=time.monotonic()-first['started'])
            distance = abs(data['start'][0]-data['end'][0])+abs(data['start'][1]-data['end'][1])
            kind = 'swipe' if distance > 10 else 'long_press' if data['duration'] > .6 else 'tap'
        if kind == 'text' and not demo['record_text']:
            data = {'text': '{输入内容}', 'redacted': True}
        printable = set(range(7,17)) | set(range(29,57)) | {62,69,70,71,72,73,74,75,76}
        if kind == 'key' and not demo['record_text'] and int(data.get('keycode', 0)) in printable:
            # Printable keycodes would disclose text even with text recording disabled.
            data = {'redacted': True}
        if kind == 'key' and demo['actions'] and demo['actions'][-1]['kind'] == kind and demo['actions'][-1]['data'] == data and time.time()-demo['actions'][-1]['created'] < .15:
            return
        entry = {'kind': kind, 'data': data, 'created': time.time()}
        if image_id:
            entry['image_id'] = image_id
        # Capture locally only; no model requests until explicit draft generation.
        try:
            from web_app.services.scrcpy_service import scrcpy_service
            session = scrcpy_service.get_session(device)
            if not image_id and demo.get('record_images',demo['record_text']) and session and session.last_frame:
                import base64
                entry['image_id'] = self.store.image(base64.b64encode(session.last_frame).decode())
        except Exception:
            pass
        demo['actions'].append(entry)
        self.store.put('demonstration', demo)

    async def draft_demo(self, key, name):
        demo = self.store.get('demonstration', key)
        if not demo:
            raise KeyError(key)
        if demo['status'] != 'finished' or not demo['actions']:
            raise Conflict('Finish a demonstration with recorded actions first')
        from phone_agent.model import ModelClient, ModelConfig
        from phone_agent.model.client import MessageBuilder
        from web_app.services.model_service import model_service
        active = model_service.get_active_service()
        if not active:
            raise ValueError('No active model service')
        client = ModelClient(ModelConfig(**{k: getattr(active, k) for k in ('base_url', 'api_key', 'model_name', 'max_tokens', 'temperature', 'protocol')}))
        prompt = ('将示教动作转换为按意图执行的手机任务配方。不要用固定坐标作为执行指令；'
                  '目标不明确时要求人工接管。注意每个动作附带的画面为该动作执行前的截图；'
                  '若最后一步包含滑动或滚动，最终画面会停留在滚动后的位置，因此 acceptance 只需检验最终所在的目标页面特征，'
                  '不要要求必须同时看到滚动前页面顶部的特定列表项。返回 JSON：'
                  '{"name":"名称","parameters":[{"name":"输入内容","type":"text"}],'
                  '"steps":[{"content":"操作意图","timeout":180}],"acceptance":"最终验收建议"}。'
                  '仅声明实际需要的参数；redacted 的输入必须参数化。动作：'+json.dumps(demo['actions'], ensure_ascii=False))
        messages = [MessageBuilder.create_user_message(prompt)]
        for entry in demo['actions'][:12]:
            data = self.store.get_image(entry.get('image_id', ''))
            if data:
                import base64
                messages.append(MessageBuilder.create_user_message('示教关键画面', base64.b64encode(data).decode()))
        response = await asyncio.to_thread(client.request, messages)
        raw = response.raw_content
        draft = json.loads(raw[raw.index('{'):raw.rindex('}')+1])
        draft['name'] = name or draft.get('name', '示教配方')
        demo['draft'] = draft
        self.store.put('demonstration', demo)
        return draft

    def save_trigger(self, data, key=None):
        self.require('triggers')
        kind = data.get('kind')
        if kind not in {'online', 'charging', 'recipe_completed'}:
            raise ValueError('Unsupported trigger')
        if not data.get('device_id'):
            raise ValueError('Trigger device required')
        recipe = self.recipe(data['recipe_id'], data.get('revision') or None)
        self.bind(recipe, data.get('parameters', {}))
        source = data.get('source_recipe')
        if kind == 'recipe_completed':
            if not source:
                raise ValueError('source_recipe is required')
            self.recipe(source)
            graph = {}
            for t in self.store.list('trigger'):
                if t['id'] != key and t['kind'] == 'recipe_completed':
                    graph.setdefault(t['source_recipe'], []).append(t['recipe_id'])
            graph.setdefault(source, []).append(data['recipe_id'])
            def visit(node, path):
                if node in path:
                    raise ValueError('Trigger dependency cycle')
                for target in graph.get(node, []):
                    visit(target, path | {node})
            visit(source, set())
        existing = self.store.get('trigger', key) if key else None
        trigger = {k: data[k] for k in ('name', 'kind', 'device_id', 'recipe_id', 'parameters', 'source_recipe', 'enabled') if k in data}
        trigger.update(id=key or uuid.uuid4().hex, revision=recipe['revision'], enabled=data.get('enabled', True),
                       cooldown=max(0, int(data.get('cooldown', 300))), failures=0,
                       last_fired=existing.get('last_fired', 0) if existing else 0)
        self.store.put('trigger', trigger)
        return trigger

    def trigger_log(self, rule, state, message='', **extra):
        self.store.put('trigger_log', dict(id=uuid.uuid4().hex, trigger_id=rule['id'], state=state,
                                         message=message, created=time.time(), **extra))

    async def charging(self, device):
        def read():
            result = subprocess.run(['adb', '-s', device, 'shell', 'dumpsys', 'battery'], capture_output=True, text=True, timeout=5)
            if result.returncode:
                return None
            matches = re.findall(r'(?:AC|USB|Wireless|Dock) powered:\s*(true|false)', result.stdout, re.I)
            return any(m.lower() == 'true' for m in matches) if matches else None
        try:
            return await asyncio.to_thread(read)
        except (OSError, subprocess.TimeoutExpired):
            return None

    async def trigger_valid(self, task):
        options = task['options']
        rule = self.store.get('trigger', options['trigger_id'])
        if not rule or not rule['enabled']:
            return False
        if rule['kind'] == 'charging':
            return await self.charging(rule['device_id']) is True
        if rule['kind'] == 'online':
            return rule['device_id'] in self.runtime.devices()
        return True

    async def fire(self, rule, source=None):
        if source and self.store.get('trigger_seen', rule['id']+':'+source):
            return
        if source:
            self.store.put('trigger_seen', {'id': rule['id']+':'+source})
        pending = any(t['options'].get('trigger_id') == rule['id'] and t['status'] not in TERMINAL
                      for t in self.store.list('task'))
        if pending:
            self.trigger_log(rule, 'merged')
        elif time.time()-rule['last_fired'] < rule['cooldown']:
            self.trigger_log(rule, 'cooldown')
        else:
            task = self.run_recipe(rule['recipe_id'], [rule['device_id']], rule.get('parameters'),
                                   rule['revision'], trigger_id=rule['id'])
            rule['last_fired'] = time.time()
            self.store.put('trigger', rule)
            self.trigger_log(rule, 'submitted', task_id=task['id'])

    async def tick(self):
        if not self.runtime.settings.get('triggers_enabled'):
            return
        online = self.runtime.devices()
        for rule in self.store.list('trigger'):
            if not rule['enabled']:
                continue
            if rule['kind'] in {'online', 'charging'}:
                current = rule['device_id'] in online if rule['kind'] == 'online' else await self.charging(rule['device_id'])
                prior = self.previous.get(rule['id'])
                self.previous[rule['id']] = current
                if current is None:
                    # Unknown must not fabricate an edge when readings recover.
                    rule['diagnostic'] = 'Charging state unavailable'
                    self.store.put('trigger', rule)
                if prior is False and current is True:
                    await self.fire(rule)
            else:
                for task in self.store.list('task'):
                    if task['status'] == 'completed' and task['options'].get('recipe_id') == rule.get('source_recipe'):
                        await self.fire(rule, task['id'])
            for task in self.store.list('task'):
                marker = f"result:{rule['id']}:{task['id']}"
                if task['options'].get('trigger_id') != rule['id'] or task['status'] not in TERMINAL or self.store.get('trigger_seen', marker):
                    continue
                self.store.put('trigger_seen', {'id': marker})
                actual_status = task['executions'][0]['status']
                if actual_status not in {'completed','failed'}:
                    self.trigger_log(rule,actual_status,task_id=task['id'])
                    continue
                rule['failures'] = 0 if task['status'] == 'completed' else rule['failures']+1
                self.trigger_log(rule, 'completed' if task['status'] == 'completed' else 'failed', task_id=task['id'])
                if rule['failures'] >= 3:
                    rule['enabled'] = False
                    self.trigger_log(rule, 'disabled', 'Three consecutive failures')
                    from web_app.services.automation_notifications import notify
                    errors = await notify('自动化规则连续失败已暂停：'+rule.get('name',rule['id']))
                    for error in errors:
                        self.trigger_log(rule,'notification_failed',error)
                self.store.put('trigger', rule)

    async def start(self):
        self.runtime.catalog = self
        # Completed runs existing at startup are baseline, never replayed as new edges.
        for rule in self.store.list('trigger'):
            if rule['kind'] == 'recipe_completed':
                for task in self.store.list('task'):
                    if task['status'] in TERMINAL:
                        self.store.put('trigger_seen', {'id': rule['id']+':'+task['id']})
        async def monitor():
            import logging
            while True:
                try:
                    from web_app.services.device_service import device_service
                    await device_service.refresh_devices()
                    await self.tick()
                except Exception:
                    logging.getLogger(__name__).exception('Trigger monitor failed')
                await asyncio.sleep(30)
        self.monitor = asyncio.create_task(monitor())

    async def close(self):
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
            self.monitor = None


catalog = Catalog()
