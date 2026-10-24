import asyncio
import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from phone_agent.model.client import ModelResponse
from web_app.services.automation_runtime import Runtime, Control
from web_app.services.automation_storage import AutomationStorage


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_phone_inference_receives_frozen_conversation_context(self):
        self.model.request.return_value = self.response('finish(message="done")')
        task = await self.execute(conversation_context=[{'role':'user','content':'关键词使用开源工具，仅查看不发送'}])
        self.assertEqual(task['status'], 'completed')
        request = str(self.model.request.call_args.args[0])
        self.assertIn('关键词使用开源工具，仅查看不发送', request)
        self.assertIn('仅执行上面的当前子任务', request)

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.runtime=Runtime(AutomationStorage(Path(self.tmp.name)/'db'),devices=lambda:{'a'})
        self.runtime.device_probe=lambda _:True
        self.factory=SimpleNamespace(get_screenshot=lambda _:SimpleNamespace(base64_data=base64.b64encode(b'screenshot').decode(),
            width=100,height=200,is_sensitive=False),get_current_app=lambda _:'Settings')
        self.model=Mock()
        self.active=SimpleNamespace(base_url='http://example.invalid/v1',api_key='secret',model_name='mock',
                                    max_tokens=100,temperature=0,protocol='openai')
        self.patches=[patch('phone_agent.agent.ModelClient',return_value=self.model),
            patch('phone_agent.agent.get_device_factory',return_value=self.factory),
            patch('phone_agent.device_factory.get_device_factory',return_value=self.factory),
            patch('phone_agent.adb.unlock.get_screen_size',return_value=(100,200)),
            patch('phone_agent.actions.handler.ActionHandler.setup_keyboard'),
            patch('phone_agent.actions.handler.ActionHandler.restore_keyboard'),
            patch('web_app.services.model_service.model_service.get_active_service',return_value=self.active),
            patch('web_app.services.device_service.device_service.is_screen_locked',new=AsyncMock(return_value=True)),
            patch('web_app.services.device_service.device_service.unlock_device',new=AsyncMock(return_value=True)),
            patch('web_app.services.device_service.device_service.lock_device',new=AsyncMock(return_value=True))]
        for p in self.patches:p.start()

    async def asyncTearDown(self):
        await self.runtime.close()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def response(self, raw, action=None):
        return ModelResponse('',action if action is not None else raw,raw,total_tokens=5,input_tokens=3,output_tokens=2)

    async def execute(self, **options):
        task=self.runtime.submit('task',['a'],**options)
        await self.runtime.tick()
        await asyncio.gather(*list(self.runtime.workers.values()))
        return self.runtime.get(task['id'])

    async def test_live_disconnection_is_interrupted_before_model_call(self):
        self.runtime.device_probe=lambda _:False
        task=await self.execute()
        self.assertEqual(task['status'],'interrupted')
        self.model.request.assert_not_called()

    async def test_unverified_completion_and_cleanup(self):
        from web_app.services.device_service import device_service
        self.model.request.return_value=self.response('finish(message="done")')
        task=await self.execute()
        self.assertEqual(task['status'],'completed')
        self.assertEqual(task['executions'][0]['verification']['status'],'not_requested')
        device_service.lock_device.assert_awaited_once()
        self.assertEqual(task['executions'][0]['tokens'],5)

    async def test_visual_verification_and_tokens(self):
        self.model.request.side_effect=[self.response('finish(message="done")'),
                                       self.response('{"status":"passed","explanation":"Visible evidence"}')]
        task=await self.execute(acceptance='Target visible')
        child=task['executions'][0]
        self.assertEqual(task['status'],'completed')
        self.assertEqual(child['verification']['status'],'passed')
        self.assertEqual(child['tokens'],10)
        self.assertTrue(child['verification']['image_id'])

    async def test_verification_failure_not_reexecuted(self):
        self.model.request.side_effect=[self.response('finish(message="done")'),
                                       self.response('{"status":"failed","explanation":"Absent"}')]
        task=await self.execute(acceptance='Target visible')
        self.assertEqual(task['status'],'failed')
        self.assertEqual(task['executions'][0]['verification']['status'],'failed')
        self.assertEqual(self.model.request.call_count,2)

    async def test_malformed_verification_is_inconclusive(self):
        self.model.request.side_effect=[self.response('finish(message="done")'),self.response('not json')]
        task=await self.execute(acceptance='Target visible')
        self.assertEqual(task['status'],'failed')
        self.assertEqual(task['executions'][0]['verification']['status'],'inconclusive')

    async def test_foreground_check_does_not_call_model(self):
        self.model.request.return_value=self.response('finish(message="done")')
        task=await self.execute(acceptance={'foreground_app':'Settings'})
        self.assertEqual(task['executions'][0]['verification']['status'],'passed')
        self.assertEqual(self.model.request.call_count,1)

    async def test_step_and_final_conditions_are_both_checked(self):
        self.model.request.side_effect=[self.response('finish(message="done")'),
            self.response('{"status":"passed","explanation":"Step evidence"}'),
            self.response('{"status":"failed","explanation":"Final evidence absent"}')]
        task=await self.execute(steps=[{'content':'step','acceptance':'step check'}],acceptance='final check')
        self.assertEqual(task['status'],'failed')
        self.assertEqual(len(task['executions'][0]['checks']),2)

    async def test_model_error_and_invalid_action_are_failures(self):
        self.model.request.side_effect=RuntimeError('unavailable')
        task=await self.execute()
        self.assertEqual(task['status'],'failed')
        self.model.request.side_effect=None
        self.model.request.return_value=self.response('garbled action')
        second=await self.execute()
        self.assertEqual(second['status'],'failed')

    async def test_multistep_preserves_initial_lock_until_final(self):
        from web_app.services.device_service import device_service
        self.model.request.return_value=self.response('finish(message="done")')
        task=await self.execute(steps=[{'content':'first'},{'content':'second'}])
        self.assertEqual(task['status'],'completed')
        device_service.lock_device.assert_awaited_once()
        self.assertTrue(task['executions'][0]['initial_lock_state'])

    async def test_pause_while_model_inflight_discards_decision(self):
        started=asyncio.Event()
        release=__import__('threading').Event()
        loop=asyncio.get_running_loop()
        calls=[]
        def request(_):
            calls.append(1)
            if len(calls)==1:
                loop.call_soon_threadsafe(started.set)
                release.wait(2)
                return self.response('do(action="Tap", element=[200,200])')
            return self.response('finish(message="done")')
        self.model.request.side_effect=request
        task=self.runtime.submit('task',['a'])
        await self.runtime.tick();await asyncio.wait_for(started.wait(),1)
        self.runtime.control(task['id'],'pause');release.set()
        for _ in range(100):
            if self.runtime.get(task['id'])['status']=='paused':break
            await asyncio.sleep(.01)
        self.assertEqual(self.runtime.get(task['id'])['status'],'paused')
        self.runtime.control(task['id'],'resume','screen changed')
        await asyncio.gather(*list(self.runtime.workers.values()))
        events=self.runtime.store.events(task['id'])
        actions=[e['data']['action'] for e in events if e['kind']=='action']
        self.assertFalse(any(a.get('action')=='Tap' for a in actions))
        self.assertEqual(self.runtime.get(task['id'])['status'],'completed')

    async def test_sensitive_confirmation_reobserves_after_takeover(self):
        self.model.request.side_effect=[self.response('do(action="Tap", element=[200,200], message="Confirm")'),
                                       self.response('finish(message="done")')]
        task=self.runtime.submit('task',['a'])
        await self.runtime.tick()
        for _ in range(100):
            if self.runtime.get(task['id'])['status']=='waiting_for_user':break
            await asyncio.sleep(.01)
        self.assertEqual(self.runtime.get(task['id'])['status'],'waiting_for_user')
        self.runtime.control(task['id'],'resume','Handled manually')
        await asyncio.gather(*list(self.runtime.workers.values()))
        self.assertEqual(self.runtime.get(task['id'])['status'],'completed')
