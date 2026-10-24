import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from phone_agent.model.client import ModelConfig, ModelResponse
from web_app.services.chat_storage import ChatStorage
from web_app.services.context_service import (ContextManager, ContextBudgetError, estimate_tokens,
    snapshot, state_payload, active_compactions)


class CompactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'chat.db'
        self.store = ChatStorage(self.path)
        self.session = self.store.create_session('phone').id
        self.config = ModelConfig(model_name='fake', max_tokens=256)
        self.active = SimpleNamespace(context_window=4096)
        self.calls = []
        self.cost = 0
        self.system = {'role':'system','content':'Only discuss until explicitly asked to execute.'}
        def factory(config):
            def request(messages):
                self.calls.append((config, messages))
                self.assertLess(estimate_tokens(messages)+config.max_tokens, self.active.context_window)
                return ModelResponse('', '', '用户要求制定搜索方案；关键词为开源工具，仅查看，不发送。方案尚未执行。', total_tokens=23)
            return SimpleNamespace(request_text=request)
        self.factory = factory
        def account(tokens):
            self.cost += tokens
        self.manager = ContextManager(self.store, factory, self.config, self.active, account)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def long_history(self, count=12):
        for i in range(count):
            self.store.add_message(self.session,'user',f'旧问题{i} '+('old context '*35))
            self.store.add_message(self.session,'assistant',f'方案{i}：'+('plan '*15),status='replied')
        user = self.store.add_message(self.session,'user','先讨论，不要执行')
        assistant = self.store.add_message(self.session,'assistant','thinking',status='thinking')
        return user, assistant

    async def prepare(self, pair):
        return await self.manager.prepare(self.session,pair[0].id,pair[1].id,self.system)

    async def test_below_threshold_preserves_entire_history_without_model_call(self):
        pair = self.long_history(1)
        result = await self.prepare(pair)
        self.assertEqual(len(result), 3)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.context_events(self.session), [])

    async def test_compacts_above_ninety_and_keeps_recent_request_exactly(self):
        pair = self.long_history()
        result = await self.prepare(pair)
        event = self.store.context_events(self.session)[0]
        self.assertGreaterEqual(event['before']['ratio'], .9)
        self.assertLess(event['after']['ratio'], .9)
        self.assertEqual(event['status'],'completed')
        self.assertIn('仅查看，不发送',result[0]['content'])
        self.assertEqual(result[-1]['content'], pair[0].content)
        self.assertEqual(len(self.store.get_messages(self.session,-1)), 27)
        history = self.store.get_session_detail(self.session)['messages']
        marker = next(m for m in history if m['source']=='context_compaction')
        self.assertEqual(marker['context_event']['summary'],event['summary'])
        self.assertEqual(self.cost, event['tokens'])

    async def test_restart_reuses_completed_summary_without_recompressing(self):
        pair = self.long_history()
        await self.prepare(pair)
        self.store.update_message(pair[1].id,content='继续讨论',status='replied')
        count = len(self.calls)
        restored = ChatStorage(self.path)
        manager = ContextManager(restored,self.factory,self.config,self.active,lambda _:None)
        user = restored.add_message(self.session,'user','方案中的关键词是什么？')
        assistant = restored.add_message(self.session,'assistant','thinking',status='thinking')
        context = await manager.prepare(self.session,user.id,assistant.id,self.system)
        self.assertEqual(len(self.calls),count)
        self.assertIn('开源工具',context[0]['content'])

    async def test_incremental_compaction_retains_previous_summary_and_originals(self):
        await self.prepare(self.long_history())
        first = self.store.context_events(self.session)[0]
        calls = len(self.calls)
        pair = self.long_history()
        await self.prepare(pair)
        events = self.store.context_events(self.session)
        self.assertEqual(len(events),2)
        self.assertEqual(events[-1]['previous_id'],first['id'])
        self.assertGreater(events[-1]['covered_messages'],first['covered_messages'])
        self.assertTrue(any('仅查看，不发送' in m['content'] for _,ms in self.calls[calls:] for m in ms))

    async def test_old_single_huge_message_is_chunked_without_oversized_requests(self):
        self.store.add_message(self.session,'user','历史内容中文'*3000)
        pair = self.long_history(1)
        await self.prepare(pair)
        self.assertGreater(len(self.calls), 5)
        self.assertEqual(self.store.context_events(self.session)[0]['status'],'completed')

    async def test_large_previous_summary_is_itself_chunked_for_smaller_model(self):
        pair=self.long_history()
        await self.prepare(pair)
        event=self.store.context_events(self.session)[0]
        event['summary']='previous summary '*600
        self.store.save_context_event(event)
        before=len(self.calls)
        context=await self.prepare(pair)
        self.assertGreater(len(self.calls)-before,1)
        self.assertLess(self.manager.metrics([self.system]+context)['ratio'],.9)

    async def test_failed_compaction_preserves_history_and_previous_checkpoint(self):
        await self.prepare(self.long_history())
        previous = self.store.context_events(self.session)[0]
        pair = self.long_history()
        self.manager.factory = lambda cfg: SimpleNamespace(request_text=Mock(side_effect=TimeoutError()))
        with self.assertRaises(ContextBudgetError):
            await self.prepare(pair)
        events = self.store.context_events(self.session)
        self.assertEqual(events[-1]['status'],'failed')
        self.assertEqual(events[0]['summary'],previous['summary'])
        current = snapshot(self.store,self.session,pair[0].id)
        self.assertIn(previous['summary'],current[0]['content'])
        self.assertEqual(current[-1]['content'], pair[0].content)
        self.assertEqual(state_payload(self.store,self.session)['status'],'failed')

    async def test_oversized_current_message_is_rejected_not_truncated(self):
        pair = self.long_history(0)
        self.store.update_message(pair[0].id,content='本次完整指令'*2000)
        with self.assertRaises(ContextBudgetError):
            await self.prepare(pair)
        self.assertEqual(self.calls,[])
        self.assertEqual(len(self.store.get_message(pair[0].id).content),12000)

    async def test_concurrent_preparations_share_one_session_checkpoint(self):
        pair = self.long_history()
        await asyncio.gather(self.prepare(pair),self.prepare(pair))
        self.assertEqual(len(self.store.context_events(self.session)),1)

    async def test_context_does_not_leak_later_or_foreign_summaries(self):
        old = self.long_history(0)
        newer = self.long_history()
        await self.prepare(newer)
        historical = snapshot(self.store,self.session,old[0].id)
        self.assertEqual(len(historical),1)
        other = self.store.create_session('other').id
        self.store.add_message(other,'user','secret')
        self.assertNotIn('secret',json.dumps(snapshot(self.store,self.session,newer[0].id)))

    async def test_visible_in_progress_journal_and_recovered_interruption(self):
        pair = self.long_history()
        started, release = asyncio.Event(), asyncio.Event()
        original = self.manager.summarize
        async def wait_summary(*args):
            started.set()
            await release.wait()
            return await original(*args)
        self.manager.summarize = wait_summary
        job = asyncio.create_task(self.prepare(pair))
        await started.wait()
        during = state_payload(self.store,self.session)
        self.assertEqual(during['status'],'compressing')
        self.assertEqual(during['events'][0]['status'],'compressing')
        release.set()
        await job
        self.assertEqual(state_payload(self.store,self.session)['events'][0]['status'],'compressed')
        event = self.store.context_events(self.session)[0]
        event['status']='compressing'
        self.store.save_context_event(event)
        active_compactions.discard(event['id'])
        self.assertEqual(state_payload(self.store,self.session)['events'][0]['context_event']['status'],'interrupted')

    async def test_model_capacity_change_rechecks_budget(self):
        self.active.context_window = 16000
        large = ContextManager(self.store,self.factory,self.config,self.active,lambda _:None)
        pair = self.long_history()
        await large.prepare(self.session,pair[0].id,pair[1].id,self.system)
        self.assertEqual(self.calls,[])
        self.active.context_window=4096
        await self.prepare(pair)
        self.assertTrue(self.calls)


class ContextMigrationTests(unittest.TestCase):
    def test_additive_migration_backup_keeps_original_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'chat.db'
            store=ChatStorage(path)
            session=store.create_session('phone')
            store.add_message(session.id,'user','旧数据库会话')
            with sqlite3.connect(path) as db:
                for table in ['chat_context_schema','chat_context_events','chat_context_status']:
                    db.execute('DROP TABLE '+table)
            restored=ChatStorage(path)
            self.assertEqual(restored.get_messages(session.id)[0].content,'旧数据库会话')
            backups=list(Path(folder).glob('*.bak'))
            self.assertEqual(len(backups),1)
            with sqlite3.connect(backups[0]) as db:
                self.assertEqual(db.execute('SELECT content FROM chat_messages').fetchone()[0],'旧数据库会话')
