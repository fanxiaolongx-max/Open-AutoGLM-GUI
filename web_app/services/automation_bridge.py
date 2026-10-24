"""Adapt structured runtime events to existing chat, websocket and report consumers."""
import asyncio
import base64
import json
import logging

logger = logging.getLogger(__name__)


def install_bridge(runtime):
    if getattr(runtime, '_bridge_installed', False):
        return
    runtime._bridge_installed = True
    from web_app.routers.websocket import manager
    from web_app.services.task_service import task_service
    from web_app.services.chat_service import chat_service

    async def finished(task):
        task_id = task['id']
        options = task['options']
        success = task['status'] == 'completed'
        message = '; '.join(c.get('message', '') for c in task['executions'])
        screenshot_id = None
        screenshots = {}
        events = runtime.store.events(task_id, 0, 500)
        # Fetch all pages for long tasks.
        while len(events) and len(events) % 500 == 0:
            page = runtime.store.events(task_id, events[-1]['seq'], 500)
            if not page:
                break
            events.extend(page)
        for event in events:
            image_id = event['data'].get('image_id')
            if image_id:
                image = runtime.store.get_image(image_id)
                if image:
                    screenshots[event['device_id']] = base64.b64encode(image).decode()
        session, msg = options.get('session_id'), options.get('message_id')
        if session and msg:
            for device, encoded in screenshots.items():
                saved = chat_service.add_screenshot(session, msg, base64.b64decode(encoded), 'Final state: '+device)
                screenshot_id = saved.get('id')
            chat_service.update_message(msg, content=(('已验证完成' if all(c['verification']['status']=='passed' for c in task['executions']) else '执行结束，未验证') if success else message),
                                        tokens=options.get('conversation_tokens',0)+sum(c['tokens'] for c in task['executions']),
                                        status='success' if success else 'error',
                                        todo_list=[{**s, 'status': 'completed' if all(c['step_index'] > i for c in task['executions']) else 'failed'} for i, s in enumerate(task['steps'])])
        task_service._emit_finished(task_id, success, message, screenshot_id=screenshot_id,
                                    task_type=options.get('task_type', 'manual'))
        if options.get('recipe_id'):
            recipe = runtime.store.get('recipe', options['recipe_id'])
            if recipe:
                recipe['last_run'] = {'task_id': task_id, 'device_ids': task['device_ids'], 'status': task['status'], 'revision': options['recipe_revision']}
                if success and options.get('trial') and recipe['revision'] == options['recipe_revision']:
                    recipe['verified'] = True
                runtime.store.put('recipe', recipe)
        report = task_service.from_runtime(task)
        report.logs = [f"{e['device_id']} {e['kind']}: {json.dumps(e['data'], ensure_ascii=False)}" for e in events if e['kind'] != 'screen']
        if screenshots:
            report._device_screenshots = screenshots
            report._screenshot_data = next(iter(screenshots.values()))
        if options.get('send_email', True):
            delivery = await task_service._send_email_report(report)
            if delivery:
                runtime.emit(task_id,'','notification',{'channel':'email','success':delivery[0],'message':delivery[1]})
                from web_app.services.email_service import email_service
                if not delivery[0] and email_service.config.enabled:
                    raise RuntimeError(delivery[1])

    def on_event(event):
        asyncio.create_task(manager.broadcast({'type': 'automation_event', **event}))
        task = runtime.get(event['task_id'])
        options = task['options']
        kind, data = event['kind'], event['data']
        if kind in {'subtask','device_finished'}:
            task_service._emit_progress(task['id'],task['progress'])
        if kind == 'model':
            if options.get('session_id'):
                chat_service.update_session_tokens(options['session_id'],data.get('total_tokens',0))
            if options.get('message_id'):
                chat_service.update_message(options['message_id'],tokens=options.get('conversation_tokens',0)+sum(c['tokens'] for c in task['executions']))
            task_service._emit_log(task['id'], f"[TOKENS]{data.get('input_tokens',0)},{data.get('output_tokens',0)},{data.get('total_tokens',0)}[/TOKENS]")
            task_service._emit_tokens(task['id'], data.get('input_tokens', 0), data.get('output_tokens', 0), data.get('total_tokens', 0))
        if kind in {'action', 'action_result', 'state', 'subtask', 'verification', 'takeover'}:
            line = kind+': '+json.dumps(data, ensure_ascii=False)
            task_service._emit_log(task['id'], line)
            if options.get('session_id') and options.get('message_id'):
                chat_service.add_log(options['session_id'], options['message_id'], line, 'action' if kind == 'action' else 'info')
        if kind == 'verification' and options.get('session_id'):
            chat_service.update_session_tokens(options['session_id'],data.get('tokens',0))
        if kind == 'takeover':
            async def notify():
                try:
                    from web_app.services.automation_notifications import notify as send_alert
                    errors = await send_alert('任务需要人工接管：'+data['message']+'\n任务入口：/?task_id='+task['id'])
                    for error in errors:
                        runtime.emit(task['id'],event['device_id'],'notification',{'success':False,'message':error})
                except Exception:
                    logger.exception('Takeover notification failed')
            asyncio.create_task(notify())
        if kind == 'task_finished' and not runtime.store.get('notification', task['id']):
            runtime.store.put('notification', {'id': task['id'], 'status': 'pending'})
            async def complete():
                try:
                    await finished(task)
                    runtime.store.put('notification', {'id': task['id'], 'status': 'sent'})
                except Exception as exc:
                    runtime.store.put('notification', {'id': task['id'], 'status': 'failed', 'error': str(exc)})
                    logger.exception('Completion notification failed')
            pending = asyncio.create_task(complete())
            runtime.notifications.add(pending)
            pending.add_done_callback(runtime.notifications.discard)
    runtime.listeners.append(on_event)
