"""Conversation intent/history regression tests: no real model or phone access."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from phone_agent.model.client import ModelClient, ModelConfig, ModelResponse
from web_app.auth import verify_token
from web_app.routers.chat import router
from web_app.routers.tasks import router as tasks_router
from web_app.services.automation_runtime import Runtime
from web_app.services.automation_storage import AutomationStorage
from web_app.services.chat_storage import ChatStorage
from web_app.services import conversation_service as conversation


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = ChatStorage(Path(self.tmp.name)/'chat.db')
        self.runtime = Runtime(AutomationStorage(Path(self.tmp.name)/'run.db'), devices=lambda: {'phone'})
        self.model = Mock()
        self.model.request_text.return_value = ModelResponse('', '', json.dumps({
            'intent': 'chat', 'reply': '你好！可以先讨论方案。', 'task': ''}), total_tokens=12)
        self.patches = [
            patch.object(conversation, 'chat_storage', self.storage),
            patch.object(importlib.import_module('web_app.services.chat_service'), 'chat_storage', self.storage),
            patch('web_app.services.chat_storage.chat_storage', self.storage),
            patch('web_app.services.automation_runtime._runtime', self.runtime),
            patch.object(conversation, 'ModelClient', return_value=self.model),
            patch.object(conversation.model_service, 'get_active_service', return_value=SimpleNamespace(
                base_url='http://model.invalid/v1', api_key='fake', model_name='test-model',
                max_tokens=3000, temperature=0, protocol='openai')),
        ]
        for item in self.patches:
            item.start()
        app = FastAPI()
        app.dependency_overrides[verify_token] = lambda: True
        app.include_router(router)
        app.include_router(tasks_router)
        self.app = app
        self.client = TestClient(app)
        self.session = self.storage.create_session('default', '').id

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def pair(self, content='你好', session=None):
        session = session or self.session
        user = self.storage.add_message(session, 'user', content)
        assistant = self.storage.add_message(session, 'assistant', '正在理解你的消息…')
        return user, assistant

    def respond(self, pair):
        return self.client.post(f'/api/chat/sessions/{self.session}/respond', json={
            'user_message_id': pair[0].id, 'assistant_message_id': pair[1].id})

    def decision(self, intent, reply='先讨论方案', task=''):
        self.model.request_text.return_value.raw_content = json.dumps(dict(intent=intent, reply=reply, task=task))

    def test_greeting_without_device_is_reply_and_never_task(self):
        pair = self.pair()
        response = self.respond(pair)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['intent'], 'chat')
        self.assertEqual(self.runtime.store.list('task'), [])
        stored = self.storage.get_message(pair[1].id)
        self.assertEqual(stored.status, 'replied')
        self.assertEqual(stored.tokens, 12)
        self.assertEqual(self.storage.get_session(self.session).total_tokens, 12)

    def test_plan_and_ambiguous_intent_do_not_execute_even_with_task_field(self):
        for intent in ['plan', 'clarify']:
            with self.subTest(intent=intent):
                self.decision(intent, task='应忽略这个字段')
                result = self.respond(self.pair('先商量怎么操作，不要执行')).json()
                self.assertEqual(result['task'], '')
                self.assertEqual(result['intent'], intent)
                self.assertEqual(self.runtime.store.list('task'), [])

    def test_followup_contains_same_session_history_without_placeholder_or_other_session(self):
        old = self.pair('帮我制定明早八点闹钟的方案')
        self.storage.update_message(old[1].id, content='方案：打开时钟，创建明早08:00闹钟。', status='replied')
        other = self.storage.create_session('other', '').id
        self.pair('OTHER SESSION SECRET', other)
        pair = self.pair('按刚才的方案执行')
        # A later turn must not leak into this model request.
        self.pair('FUTURE MESSAGE')
        self.decision('execute', task='打开时钟，创建明早08:00闹钟')
        self.assertEqual(self.respond(pair).json()['intent'], 'execute')
        messages = self.model.request_text.call_args.args[0]
        joined = json.dumps(messages, ensure_ascii=False)
        self.assertIn('创建明早08:00', joined)
        self.assertNotIn('OTHER SESSION SECRET', joined)
        self.assertNotIn('FUTURE MESSAGE', joined)
        self.assertNotIn('正在理解你的消息…', joined)
        self.assertEqual(messages[-1]['content'], '按刚才的方案执行')
        self.assertEqual(self.runtime.store.list('task'), [])

    def test_task_captures_history_at_submit_for_execution(self):
        previous = self.pair('搜索关键词用“开源工具”，仅查看，不发送。')
        self.storage.update_message(previous[1].id, content='方案：打开浏览器搜索开源工具，仅查看结果。', status='replied')
        pair = self.pair('开始执行')
        self.decision('execute', task='打开浏览器搜索开源工具，仅查看结果')
        self.respond(pair)
        result = self.client.post('/api/tasks/run', json={
            'task_content': '打开浏览器搜索开源工具，仅查看结果', 'device_ids': ['phone'],
            'task_type': 'chat', 'session_id': self.session, 'message_id': pair[1].id, 'queue': True})
        self.assertEqual(result.status_code, 200, result.text)
        task = self.runtime.get(result.json()['task_id'])
        context = task['options']['conversation_context']
        self.assertIn('仅查看，不发送', context[0]['content'])
        self.assertEqual(task['options']['conversation_tokens'], 12)
        self.pair('稍后又讨论的内容')
        self.assertNotIn('稍后又讨论', json.dumps(task, ensure_ascii=False))

    def test_history_preserves_all_messages_before_compaction(self):
        for i in range(115):
            self.storage.add_message(self.session, 'user', f'message-{i}')
        pair = self.pair('最新问题')
        history = conversation.history_snapshot(self.session, pair[0].id)
        self.assertEqual(len(history), 116)
        self.assertEqual(history[-1]['content'], '最新问题')
        self.assertIn('message-0"', json.dumps(history))
        self.assertIn('message-114', json.dumps(history))

    def test_history_is_not_silently_character_truncated(self):
        for i in range(20):
            self.storage.add_message(self.session, 'user', str(i)*3000)
        pair = self.pair()
        history = conversation.history_snapshot(self.session, pair[0].id)
        self.assertGreater(sum(len(m['content']) for m in history), 24000)
        self.assertEqual(history[-1]['content'], '你好')

    def test_invalid_model_output_fails_closed(self):
        for raw in ['finish(message="ok")', '{"intent":"execute","reply":"ok","task":""}',
                    '{"intent":"unknown","reply":"ok"}', '[]']:
            with self.subTest(raw=raw):
                self.model.request_text.return_value.raw_content = raw
                pair = self.pair()
                self.assertEqual(self.respond(pair).status_code, 409)
                self.assertEqual(self.storage.get_message(pair[1].id).status, 'error')
                self.assertEqual(self.runtime.store.list('task'), [])

    def test_model_timeout_fails_without_creating_task(self):
        self.model.request_text.side_effect = TimeoutError()
        pair = self.pair()
        response = self.respond(pair)
        self.assertEqual(response.status_code, 502)
        self.assertIn('尚未操作设备', response.json()['detail'])
        self.assertEqual(self.runtime.store.list('task'), [])

    def test_cross_session_and_nonadjacent_message_ids_are_rejected_before_model(self):
        first, second = self.pair(), self.pair()
        self.assertEqual(self.respond((first[0], second[1])).status_code, 409)
        other = self.storage.create_session('other', '').id
        foreign = self.pair(session=other)
        self.assertEqual(self.respond(foreign).status_code, 404)
        self.model.request_text.assert_not_called()

    def test_duplicate_reply_does_not_call_model_or_charge_twice(self):
        pair = self.pair()
        self.respond(pair)
        self.respond(pair)
        self.assertEqual(self.model.request_text.call_count, 1)
        self.assertEqual(self.storage.get_session(self.session).total_tokens, 12)

    def test_endpoint_requires_authentication(self):
        def deny():
            raise HTTPException(401, 'Login required')
        self.app.dependency_overrides[verify_token] = deny
        self.assertEqual(self.respond(self.pair()).status_code, 401)
        self.model.request_text.assert_not_called()

    def test_refresh_observes_inflight_reply_and_detects_restart(self):
        pair = self.pair()
        self.storage.update_message(pair[1].id, status='thinking')
        endpoint = f'/api/chat/sessions/{self.session}/messages/{pair[1].id}'
        conversation.pending_replies.add(pair[1].id)
        try:
            self.assertEqual(self.client.get(endpoint).json()['status'], 'thinking')
        finally:
            conversation.pending_replies.discard(pair[1].id)
        result = self.client.get(endpoint).json()
        self.assertEqual(result['status'], 'error')
        self.assertIn('尚未提交手机任务', result['content'])
        self.assertEqual(self.runtime.store.list('task'), [])

    def test_refresh_ready_intent_never_automatically_submits_task(self):
        pair = self.pair('开始执行')
        self.decision('execute', task='打开时钟')
        self.respond(pair)
        result = self.client.get(f'/api/chat/sessions/{self.session}/messages/{pair[1].id}').json()
        self.assertEqual(result['status'], 'ready')
        self.assertIn('尚未提交设备队列', result['content'])
        self.assertEqual(self.runtime.store.list('task'), [])
        self.assertEqual(self.client.get(f'/api/chat/sessions/other/messages/{pair[1].id}').status_code, 404)

    def test_compaction_precedes_intent_and_is_visible_in_authenticated_history(self):
        active=conversation.model_service.get_active_service()
        active.context_window=8192
        active.max_tokens=256
        for i in range(16):
            self.storage.add_message(self.session,'user',f'历史问题{i} '+('仅查看，不发送。'*40))
            self.storage.add_message(self.session,'assistant','方案尚未执行',status='replied')
        def request(messages):
            if messages[0]['content'].startswith('压缩对话资料'):
                return ModelResponse('','','历史讨论要求搜索开源工具，仅查看，不发送；尚未授权执行。',total_tokens=30)
            self.assertIn('历史对话压缩摘要',messages[1]['content'])
            return ModelResponse('','',json.dumps({'intent':'plan','reply':'继续讨论方案','task':''}),total_tokens=12)
        self.model.request_text.side_effect=request
        response=self.respond(self.pair('继续讨论'))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['intent'],'plan')
        self.assertEqual(response.json()['context']['compaction_count'],1)
        state=self.client.get(f'/api/chat/sessions/{self.session}/context').json()
        self.assertEqual(state['events'][0]['status'],'compressed')
        self.assertEqual(self.runtime.store.list('task'),[])

    def test_compaction_failure_does_not_fall_through_to_execution(self):
        active=conversation.model_service.get_active_service()
        active.context_window=8192
        active.max_tokens=256
        self.storage.add_message(self.session,'user','旧资料 '*4000)
        self.model.request_text.side_effect=TimeoutError()
        response=self.respond(self.pair('按刚才计划执行'))
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.runtime.store.list('task'),[])
        self.assertEqual(self.client.get(f'/api/chat/sessions/{self.session}/context').json()['events'][0]['status'],'compression_failed')


class TextModelTests(unittest.TestCase):
    def test_openai_and_ollama_text_has_no_action_parsing(self):
        for protocol in ['openai', 'ollama']:
            client = object.__new__(ModelClient)
            client.config = ModelConfig(protocol=protocol)
            client.client = Mock()
            client.client.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"intent":"plan"}'))],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4))
            result = client.request_text([{'role': 'user', 'content': '讨论计划'}])
            self.assertEqual(result.raw_content, '{"intent":"plan"}')
            self.assertEqual(result.total_tokens, 15)

    def test_anthropic_preserves_system_and_history(self):
        client = object.__new__(ModelClient)
        client.config = ModelConfig(protocol='anthropic')
        client.client = Mock()
        client.client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type='text', text='hello')],
            usage=SimpleNamespace(input_tokens=8, output_tokens=2))
        result = client.request_text([{'role':'system','content':'route'}, {'role':'user','content':'你好'}])
        self.assertEqual(result.total_tokens, 10)
        self.assertEqual(client.client.messages.create.call_args.kwargs['system'], 'route')

    def test_gemini_system_and_turns(self):
        client = object.__new__(ModelClient)
        client.config = ModelConfig(protocol='gemini')
        with patch('phone_agent.model.client.genai') as gemini:
            gemini.GenerativeModel.return_value.generate_content.return_value = SimpleNamespace(
                text='hello', usage_metadata=SimpleNamespace(prompt_token_count=8, candidates_token_count=3))
            result = client.request_text([{'role':'system','content':'route'},
                                         {'role':'user','content':'制定计划'},
                                         {'role':'assistant','content':'方案'},
                                         {'role':'user','content':'继续讨论'}])
            self.assertEqual(result.total_tokens, 11)
            self.assertEqual(gemini.GenerativeModel.call_args.kwargs['system_instruction'], 'route')
            turns = gemini.GenerativeModel.return_value.generate_content.call_args.args[0]
            self.assertEqual([t['role'] for t in turns], ['user', 'model', 'user'])
