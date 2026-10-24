"""Run with: venv/bin/python -m unittest discover -s tests -v"""
import asyncio
import base64
import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from web_app.services.automation_storage import AutomationStorage
from web_app.services.automation_runtime import Runtime, Control, Conflict, Interrupted
from web_app.services.automation_catalog import Catalog


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'automation.db'
        self.store = AutomationStorage(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reopen_preserves_records(self):
        self.store.put('task', {'id':'old', 'status':'failed'})
        self.assertEqual(AutomationStorage(self.path).get('task','old')['status'], 'failed')

    def test_event_cursor_and_isolation(self):
        a = self.store.event('a','phone1','action',{'success':False})
        b = self.store.event('b','phone2','action',{})
        c = self.store.event('a','phone1','action',{})
        self.assertEqual([e['seq'] for e in self.store.events('a',a['seq'])], [c['seq']])
        self.assertNotIn(b['seq'], [e['seq'] for e in self.store.events('a')])

    def test_image_cleanup_keeps_logs_and_pins(self):
        first = self.store.image(base64.b64encode(b'image1').decode())
        pinned = self.store.image(base64.b64encode(b'image2').decode())
        self.store.event('a','p','screen',{'image_id':first})
        with self.store.connection() as conn:
            conn.execute('UPDATE images SET pinned=1 WHERE id=?',(pinned,))
        self.store.cleanup(max_bytes=1)
        self.assertIsNone(self.store.get_image(first))
        self.assertEqual(self.store.get_image(pinned), b'image2')
        self.assertEqual(len(self.store.events('a')),1)

    def test_future_schema_refused(self):
        with self.store.connection() as conn:
            conn.execute('PRAGMA user_version=999')
        with self.assertRaises(RuntimeError):
            AutomationStorage(self.path)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AutomationStorage(Path(self.tmp.name)/'db')
        self.online = {'a','b'}
        self.entered = []
        self.active = set()
        self.release = asyncio.Event()
        async def runner(task, child, step, control):
            d = child['device_id']
            self.assertNotIn(d,self.active)
            self.active.add(d)
            self.entered.append((task['id'],d))
            await self.release.wait()
            self.active.remove(d)
            return {'success':not control.stopped,'message':'done','reason':'completed'}
        self.runtime = Runtime(self.store,runner,lambda:self.online)

    async def asyncTearDown(self):
        self.release.set()
        await self.runtime.close()
        self.tmp.cleanup()

    async def dispatch(self):
        await self.runtime.tick()
        await asyncio.sleep(.02)

    async def drain(self):
        self.release.set()
        for _ in range(10):
            await self.dispatch()
            if not self.runtime.workers and not any(t['status'] == 'pending' for t in self.store.list('task')):
                break

    async def test_same_device_fifo_different_device_parallel(self):
        first=self.runtime.submit('first',['a'])
        second=self.runtime.submit('second',['a'])
        other=self.runtime.submit('other',['b'])
        await self.dispatch()
        self.assertEqual(set(self.entered),{(first['id'],'a'),(other['id'],'b')})
        self.assertEqual(self.runtime.get(second['id'])['status'],'pending')
        await self.drain()
        self.assertEqual(self.runtime.get(second['id'])['status'],'completed')

    async def test_concurrency_limit(self):
        self.runtime.settings['concurrency']=1
        self.runtime.submit('a',['a']); self.runtime.submit('b',['b'])
        await self.dispatch()
        self.assertEqual(len(self.entered),1)

    async def test_busy_legacy_conflict_and_explicit_queue(self):
        self.runtime.submit('first',['a'])
        with self.assertRaises(Conflict):self.runtime.submit('second',['a'],queue=False)
        self.runtime.submit('second',['a'],queue=True)

    async def test_stop_waits_for_worker_release(self):
        a=self.runtime.submit('first',['a']);b=self.runtime.submit('second',['a'])
        await self.dispatch();self.runtime.control(a['id'],'stop');await self.dispatch()
        self.assertEqual(self.runtime.get(b['id'])['status'],'pending')
        await self.drain()
        self.assertEqual(self.runtime.get(a['id'])['status'],'stopped')
        self.assertEqual(self.runtime.get(b['id'])['status'],'completed')

    async def test_stop_queued_does_not_stop_other(self):
        a=self.runtime.submit('first',['a']);b=self.runtime.submit('second',['b'])
        self.runtime.control(a['id'],'stop');await self.drain()
        self.assertEqual(self.runtime.get(a['id'])['status'],'stopped')
        self.assertEqual(self.runtime.get(b['id'])['status'],'completed')

    async def test_offline_expiry(self):
        task=self.runtime.submit('offline',['offline'],queue_timeout=.001)
        await asyncio.sleep(.01);await self.dispatch()
        self.assertEqual(self.runtime.get(task['id'])['executions'][0]['status'],'expired')

    async def test_serial_parent_waits_for_previous_device(self):
        task=self.runtime.submit('both',['a','b'],parallel=False)
        await self.dispatch();self.assertEqual(len(self.entered),1)
        await self.drain();self.assertEqual(self.runtime.get(task['id'])['status'],'completed')

    async def test_restart_marks_active_interrupted_and_keeps_pending(self):
        a=self.runtime.submit('running',['a']);b=self.runtime.submit('queued',['a'])
        a['executions'][0]['status']='running';self.runtime.save(a)
        await self.runtime.start()
        self.assertEqual(self.runtime.get(a['id'])['status'],'interrupted')
        self.assertEqual(self.runtime.get(b['id'])['status'],'pending')
        await self.dispatch();self.assertEqual(self.entered,[])
        self.runtime.control(a['id'],'resume','check state');await self.drain()
        self.assertEqual(self.runtime.get(a['id'])['status'],'completed')

    async def test_invalid_transition_and_missing_id(self):
        task=self.runtime.submit('pending',['a'])
        with self.assertRaises(Conflict):self.runtime.control(task['id'],'resume')
        with self.assertRaises(KeyError):self.runtime.get('missing')

    async def test_model_credentials_not_persisted(self):
        task=self.runtime.submit('test',['a'],model_config={'api_key':'private-secret'})
        self.assertNotIn('private-secret',str(self.store.list('task')))

    async def test_safe_retry_only_when_repeatable(self):
        calls=[]
        async def fail(task,child,step,control):
            calls.append(1);return {'success':False,'message':'no','reason':'failed'}
        self.runtime.runner=fail
        task=self.runtime.submit('fail',['a'],steps=[{'content':'send','retry_once':True,'repeatable':False}])
        await self.drain();self.assertEqual(len(calls),1)

    async def test_failure_stops_later_steps(self):
        calls=[]
        async def fail(task,child,step,control):
            calls.append(step['content']);return {'success':False,'message':'no','reason':'failed'}
        self.runtime.runner=fail
        task=self.runtime.submit('fail',['a'],steps=[{'content':'one'},{'content':'two'}])
        await self.drain();self.assertEqual(calls,['one'])
        self.assertEqual(self.runtime.get(task['id'])['status'],'failed')

    async def test_sensitive_images_are_not_saved(self):
        task=self.runtime.submit('x',['a'])
        e=self.runtime.emit(task['id'],'a','screen',{'image':base64.b64encode(b'x').decode(),'sensitive':True})
        self.assertNotIn('image_id',e['data'])


class ControlTests(unittest.TestCase):
    def test_pause_resume_invalidates_decision(self):
        states=[];c=Control(lambda state,note:states.append(state))
        c.pause();thread=threading.Thread(target=lambda:self.assertTrue(c.checkpoint()))
        thread.start()
        for _ in range(100):
            if c.state=='paused':break
            time.sleep(.001)
        self.assertEqual(c.state,'paused');c.resume('logged in');thread.join(1)
        self.assertFalse(thread.is_alive());self.assertEqual(c.note,'logged in')
        self.assertEqual(states,['pausing','paused','running'])

    def test_stop_unblocks_waiter(self):
        c=Control(lambda *args:None);c.pause(True)
        c.stop()
        with self.assertRaises(Interrupted):c.checkpoint()

    def test_active_timeout(self):
        c=Control(lambda *args:None,timeout=.001);time.sleep(.002)
        with self.assertRaises(TimeoutError):c.checkpoint()

    def test_disconnection_is_interruption(self):
        c=Control(lambda *args:None,online=lambda:False)
        with self.assertRaises(Interrupted):c.checkpoint()

    def test_wait_time_excluded_from_timeout(self):
        c=Control(lambda *args:None,timeout=.08);c.pause(True)
        t=threading.Thread(target=c.checkpoint);t.start();time.sleep(.1);c.resume();t.join()
        self.assertGreater(c.waited,.08)
        c.checkpoint()


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.runtime=Runtime(AutomationStorage(Path(self.tmp.name)/'db'),devices=lambda:{'a'})
        self.catalog=Catalog(self.runtime)
        self.recipe=self.catalog.save_recipe({'name':'search','parameters':[{'name':'query','type':'text'}],
            'steps':[{'content':'Search {query}'}]})

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_bound_parameters_and_immutable_revision(self):
        task=self.catalog.run_recipe(self.recipe['id'],['a'],{'query':'$(echo safe)'})
        dup=self.catalog.run_recipe(self.recipe['id'],['a'],{'query':'$(echo safe)'},trial=True)
        dup2=self.catalog.run_recipe(self.recipe['id'],['a'],{'query':'$(echo safe)'},trial=True)
        self.assertEqual(dup['id'],dup2['id'])
        self.catalog.save_recipe({'name':'changed','steps':[{'content':'other'}]},self.recipe['id'])
        self.assertEqual(task['steps'][0]['content'],'Search $(echo safe)')
        old=self.catalog.recipe(self.recipe['id'],1)
        self.assertEqual(old['steps'][0]['content'],'Search {query}')

    async def test_missing_parameter_and_enum_rejected(self):
        with self.assertRaises(ValueError):self.catalog.run_recipe(self.recipe['id'],['a'])
        r={'parameters':[{'name':'x','type':'enum','options':['a']}],'steps':[]}
        with self.assertRaises(ValueError):self.catalog.bind(r,{'x':'b'})

    async def test_import_validation(self):
        for bad in [{'name':'bad','steps':[]},{'name':'bad','steps':[{'content':'{missing}'}]},
                    {'name':'bad','format_version':2,'steps':[{'content':'x'}]},
                    {'name':'bad','steps':[{'content':'x','retry_once':True}]}]:
            with self.assertRaises(ValueError):self.catalog.save_recipe(bad)

    async def test_export_excludes_runtime_fields(self):
        exported=self.catalog.export_recipe(self.recipe['id'])
        self.assertNotIn('id',exported);self.assertNotIn('verified',exported)

    async def test_demo_occupancy_and_text_redaction(self):
        demo=self.catalog.start_demo('a')
        with self.assertRaises(Conflict):self.catalog.start_demo('a')
        self.catalog.record('a','text',{'text':'secret'})
        self.catalog.demo_action(demo['id'],'pause')
        self.catalog.record('a','text',{'text':'hidden'})
        record=self.runtime.store.get('demonstration',demo['id'])
        self.assertEqual(len(record['actions']),1)
        self.assertNotIn('secret',str(record));self.assertNotIn('hidden',str(record))
        self.catalog.demo_action(demo['id'],'finish')
        self.assertNotIn('a',self.runtime.reservations)

    async def test_gesture_coalescing(self):
        demo=self.catalog.start_demo('a')
        self.catalog.record('a','touch',{'action':'down','x':10,'y':20,'width':100,'height':200})
        self.catalog.record('a','touch',{'action':'move','x':20,'y':50})
        self.catalog.record('a','touch',{'action':'up','x':20,'y':50})
        actions=self.runtime.store.get('demonstration',demo['id'])['actions']
        self.assertEqual(len(actions),1);self.assertEqual(actions[0]['kind'],'swipe')

    def trigger(self,**changes):
        return self.catalog.save_trigger({'kind':'online','device_id':'a','recipe_id':self.recipe['id'],
                                         'parameters':{'query':'x'},**changes})

    async def test_trigger_startup_baseline_and_edge(self):
        rule=self.trigger();await self.catalog.tick()
        self.assertFalse(self.runtime.store.list('task'))
        self.runtime.devices=lambda:set();await self.catalog.tick()
        self.runtime.devices=lambda:{'a'};await self.catalog.tick()
        self.assertEqual(len(self.runtime.store.list('task')),1)

    async def test_trigger_dedup_and_merge(self):
        rule=self.trigger();await self.catalog.fire(rule,'source');await self.catalog.fire(rule,'source')
        await self.catalog.fire(rule,'other')
        self.assertEqual(len(self.runtime.store.list('task')),1)
        self.assertIn('merged',[l['state'] for l in self.runtime.store.list('trigger_log')])

    async def test_trigger_dependency_cycle(self):
        other=self.catalog.save_recipe({'name':'other','steps':[{'content':'x'}]})
        self.trigger(kind='recipe_completed',source_recipe=other['id'])
        with self.assertRaises(ValueError):self.catalog.save_trigger({'kind':'recipe_completed','device_id':'a',
            'recipe_id':other['id'],'source_recipe':self.recipe['id']})

    async def test_unknown_charging_never_fabricates_edge(self):
        self.trigger(kind='charging')
        values=iter([None,True,None,True])
        async def charge(_):return next(values)
        self.catalog.charging=charge
        for _ in range(4):await self.catalog.tick()
        self.assertFalse(self.runtime.store.list('task'))


class AgentTests(unittest.TestCase):
    def make_agent(self, responses):
        from phone_agent.agent import PhoneAgent, AgentConfig
        from phone_agent.model.client import ModelResponse
        with patch('phone_agent.agent.ModelClient') as client, patch('phone_agent.agent.ActionHandler') as handler:
            agent=PhoneAgent(agent_config=AgentConfig(max_steps=2,verbose=False))
            agent.model_client.request.side_effect=[ModelResponse('',r,r) for r in responses]
            agent.action_handler.execute.return_value=SimpleNamespace(success=True,should_finish=False,message='done')
        return agent

    def test_max_steps_not_success_and_cli_wrapper(self):
        from phone_agent.agent import StepResult
        agent=self.make_agent([])
        agent._execute_step=Mock(return_value=StepResult(True,False,{},''))
        # Mock still advances the step count, as a real step does.
        def step(*args):agent._step_count+=1;return StepResult(True,False,{},'')
        agent._execute_step.side_effect=step
        outcome=agent.run_result('task')
        self.assertFalse(outcome.success);self.assertEqual(outcome.reason,'max_steps')
        self.assertEqual(agent.run('task'),'Max steps reached')

    def test_explicit_failure_not_success(self):
        from phone_agent.agent import StepResult
        agent=self.make_agent([])
        agent._execute_step=Mock(return_value=StepResult(False,True,None,'','Model error'))
        self.assertFalse(agent.run_result('task').success)
        agent.action_handler.restore_keyboard.assert_called_once()

    def test_stop_before_start_is_preserved(self):
        agent=self.make_agent([]);agent.request_stop()
        result=agent.run_result('task')
        self.assertEqual(result.reason,'stopped');agent.model_client.request.assert_not_called()

    def test_inflight_pause_discards_action(self):
        agent=self.make_agent(['do(action="Tap", element=[100, 100])'])
        calls=iter([False,True])
        agent.checkpoint_callback=lambda:next(calls)
        factory=SimpleNamespace(get_screenshot=lambda _:SimpleNamespace(base64_data='',width=100,height=200,is_sensitive=False),get_current_app=lambda _:'Settings')
        with patch('phone_agent.agent.get_device_factory',return_value=factory):
            result=agent._execute_step('task',True)
        self.assertFalse(result.finished);agent.action_handler.execute.assert_not_called()


if __name__=='__main__':unittest.main()
