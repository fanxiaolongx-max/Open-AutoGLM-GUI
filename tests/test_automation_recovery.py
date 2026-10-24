import asyncio
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from web_app.services.automation_runtime import Runtime, Control
from web_app.services.automation_storage import AutomationStorage
from web_app.services.automation_catalog import Catalog


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'db'
        self.runtime=Runtime(AutomationStorage(self.path),devices=lambda:{'a','b'})
        self.catalog=Catalog(self.runtime)

    async def asyncTearDown(self):
        await self.runtime.close()
        self.tmp.cleanup()

    async def test_process_lock_rejects_second_worker(self):
        await self.runtime.start()
        other=Runtime(AutomationStorage(self.path),devices=lambda:set())
        with self.assertRaises(RuntimeError):await other.start()
        await other.close()

    async def test_pause_and_stop_do_not_block_on_committed_action(self):
        import threading
        control=Control(lambda *args:None)
        acquired=threading.Event();release=threading.Event()
        def action():
            with control.condition:
                acquired.set();release.wait(2)
        thread=threading.Thread(target=action);thread.start()
        await asyncio.to_thread(acquired.wait)
        before=time.monotonic();control.pause();control.stop()
        self.assertLess(time.monotonic()-before,.1)
        release.set();await asyncio.to_thread(thread.join)

    async def test_manual_ownership_blocks_dispatch_and_resume(self):
        task=self.runtime.submit('task',['a'])
        self.runtime.manual_busy['a']=time.monotonic()+10
        await self.runtime.tick()
        self.assertEqual(self.runtime.get(task['id'])['status'],'pending')
        self.assertFalse(self.runtime.workers)

    async def test_failed_sequence_cancels_remaining_segments(self):
        calls=[]
        async def fail(task,child,step,control):
            calls.append(child['device_id']);return {'success':False,'reason':'failed','message':'failed'}
        self.runtime.runner=fail
        task=self.runtime.submit('sequence',['a','b'],sequence=[{'device_id':'a','content':'one'},
                                                             {'device_id':'b','content':'two'}])
        await self.runtime.tick();await asyncio.gather(*list(self.runtime.workers.values()))
        await self.runtime.tick()
        final=self.runtime.get(task['id'])
        self.assertEqual([c['status'] for c in final['executions']],['failed','cancelled'])
        self.assertEqual(calls,['a'])

    async def test_stop_before_worker_starts_prevents_any_action(self):
        runner=AsyncMock(return_value={'success':True,'message':'done'})
        self.runtime.runner=runner
        task=self.runtime.submit('stop',['a'])
        await self.runtime.tick()
        self.runtime.control(task['id'],'stop')
        await asyncio.gather(*list(self.runtime.workers.values()))
        runner.assert_not_awaited()

    async def test_final_checkpoint_does_not_block_asyncio_while_paused(self):
        release=asyncio.Event()
        async def runner(*args):
            await release.wait()
            return {'success':True,'message':'done'}
        self.runtime.runner=runner
        task=self.runtime.submit('pause',['a'])
        await self.runtime.tick()
        for _ in range(20):
            if self.runtime.controls:break
            await asyncio.sleep(.005)
        self.runtime.control(task['id'],'pause')
        release.set()
        for _ in range(100):
            if self.runtime.get(task['id'])['status']=='paused':break
            await asyncio.sleep(.005)
        self.assertEqual(self.runtime.get(task['id'])['status'],'paused')
        self.runtime.control(task['id'],'resume')
        await asyncio.gather(*list(self.runtime.workers.values()))
        self.assertEqual(self.runtime.get(task['id'])['status'],'completed')

    async def test_selected_device_stop_preserves_other_device(self):
        task=self.runtime.submit('both',['a','b'],parallel=True)
        self.runtime.control(task['id'],'stop',device_ids=['a'])
        self.assertEqual([c['status'] for c in self.runtime.get(task['id'])['executions']],['stopped','pending'])

    async def test_stale_charging_trigger_cancelled_before_actions(self):
        r=self.catalog.save_recipe({'name':'x','steps':[{'content':'x'}]})
        rule=self.catalog.save_trigger({'kind':'charging','device_id':'a','recipe_id':r['id']})
        task=self.catalog.run_recipe(r['id'],['a'],trigger_id=rule['id'])
        self.catalog.charging=AsyncMock(return_value=False)
        async def never(*args):raise AssertionError('Actions must not run after unplugging')
        self.runtime.runner=never
        await self.runtime.tick();await asyncio.gather(*list(self.runtime.workers.values()))
        self.assertEqual(self.runtime.get(task['id'])['status'],'cancelled')

    async def test_three_failures_disable_rule_and_notify_once(self):
        recipe=self.catalog.save_recipe({'name':'x','steps':[{'content':'x'}]})
        rule=self.catalog.save_trigger({'kind':'online','device_id':'a','recipe_id':recipe['id'],'cooldown':0})
        with patch('web_app.services.telegram_bot.telegram_bot_service.send_system_notification',new=AsyncMock()) as notify, \
             patch('web_app.services.email_service.email_service.send_task_report',return_value=(True,'mock')):
            for _ in range(3):
                task=self.catalog.run_recipe(recipe['id'],['a'],trigger_id=rule['id'])
                task['executions'][0]['status']='failed';self.runtime.save(task)
                await self.catalog.tick()
            saved=self.runtime.store.get('trigger',rule['id'])
            self.assertFalse(saved['enabled']);self.assertEqual(saved['failures'],3)
            notify.assert_awaited_once()

    async def test_cooldown_and_persistent_source_dedup(self):
        recipe=self.catalog.save_recipe({'name':'x','steps':[{'content':'x'}]})
        rule=self.catalog.save_trigger({'kind':'online','device_id':'a','recipe_id':recipe['id'],'cooldown':300})
        await self.catalog.fire(rule,'source1')
        task=self.runtime.store.list('task')[0];task['executions'][0]['status']='completed';self.runtime.save(task)
        restored=Catalog(self.runtime)
        await restored.fire(rule,'source1');await restored.fire(rule,'source2')
        self.assertEqual(len(self.runtime.store.list('task')),1)
        self.assertIn('cooldown',[e['state'] for e in self.runtime.store.list('trigger_log')])

    async def test_old_database_backup_preserves_unrelated_tables(self):
        path=Path(self.tmp.name)/'legacy.db'
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE legacy_chat(message TEXT)')
            conn.execute("INSERT INTO legacy_chat VALUES ('keep me')")
        upgraded=AutomationStorage(path)
        backups=list(path.parent.glob('legacy.db.v0.*.bak'))
        self.assertEqual(len(backups),1)
        with sqlite3.connect(backups[0]) as conn:
            self.assertEqual(conn.execute('SELECT message FROM legacy_chat').fetchone()[0],'keep me')
        with upgraded.connection() as conn:
            self.assertEqual(conn.execute('SELECT message FROM legacy_chat').fetchone()[0],'keep me')

    async def test_legacy_scheduler_data_and_timezone_roundtrip(self):
        from web_app.services.scheduler_storage import SchedulerStorage
        from web_app.models.scheduler import ScheduledTask
        import web_app.services.automation_runtime as rt
        path=Path(self.tmp.name)/'chat.db'
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE chat_messages(id TEXT, content TEXT)')
            conn.execute("INSERT INTO chat_messages VALUES ('old','history')")
        with patch.object(rt,'_runtime',self.runtime),patch.object(SchedulerStorage,'_migrate_from_json'):
            storage=SchedulerStorage(path)
            task=ScheduledTask(name='legacy',task_content='x',timezone='Africa/Cairo',
                               recipe_id='recipe',recipe_revision=1,recipe_parameters={'x':'y'})
            storage.save_task(task)
            loaded=storage.get_task(task.id)
            self.assertEqual(loaded.timezone,'Africa/Cairo')
            self.assertEqual(loaded.recipe_parameters,{'x':'y'})
            self.assertIsNotNone(loaded.calculate_next_run().tzinfo)
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('SELECT content FROM chat_messages').fetchone()[0],'history')
