import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from web_app.auth import verify_token
from web_app.routers.automation import router
from web_app.routers.tasks import router as task_router
from web_app.services.automation_runtime import Runtime
from web_app.services.automation_storage import AutomationStorage
import web_app.services.automation_runtime as runtime_module


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.runtime=Runtime(AutomationStorage(Path(self.tmp.name)/'db'),devices=lambda:{'a','b'})
        self.patch=patch.object(runtime_module,'_runtime',self.runtime);self.patch.start()
        self.app=FastAPI();self.app.dependency_overrides[verify_token]=lambda:True
        self.app.include_router(task_router);self.app.include_router(router)
        self.client=TestClient(self.app)

    def tearDown(self):
        self.client.close();self.patch.stop();self.tmp.cleanup()

    def post_task(self,**kwargs):
        return self.client.post('/api/tasks/run',json={'task_content':'open settings','device_ids':['a'],**kwargs})

    def test_persisted_id_before_dispatch_and_legacy_conflict(self):
        response=self.post_task();self.assertEqual(response.status_code,200)
        key=response.json()['task_id']
        self.assertEqual(self.client.get('/api/tasks/'+key).json()['status'],'pending')
        self.assertEqual(self.post_task().status_code,409)
        self.assertEqual(self.post_task(queue=True).status_code,200)
        self.assertEqual(self.post_task(device_ids=['b']).status_code,200)

    def test_force_run_preserves_previously_queued_tasks(self):
        first=self.post_task().json()['task_id']
        forced=self.post_task(force_run=True)
        self.assertEqual(forced.status_code,200)
        self.assertEqual(self.runtime.get(first)['status'],'pending')
        self.assertTrue(self.runtime.get(forced.json()['task_id'])['options']['after_current'])

    def test_state_and_missing_routes(self):
        key=self.post_task().json()['task_id']
        self.assertEqual(self.client.post(f'/api/tasks/{key}/resume',json={}).status_code,409)
        self.assertEqual(self.client.get('/api/tasks/missing').status_code,404)
        self.assertEqual(self.client.post(f'/api/tasks/{key}/stop',json={}).status_code,200)
        self.assertEqual(self.client.get('/api/tasks/status').status_code,200)
        self.assertFalse(self.client.get('/api/tasks/status').json()['running'])

    def test_event_cursor_and_expired_image(self):
        key=self.post_task().json()['task_id']
        data=self.client.get(f'/api/tasks/{key}/events').json()
        self.assertTrue(data['events'])
        self.assertFalse(self.client.get(f'/api/tasks/{key}/events?after={data["cursor"]}').json()['events'])
        self.assertEqual(self.client.get('/api/automation/images/missing').status_code,410)

    def test_validation_and_read_auth(self):
        self.assertEqual(self.post_task(steps=[{'content':'send','retry_once':True}]).status_code,422)
        self.assertEqual(self.post_task(device_ids=[]).status_code,422)
        def deny():raise HTTPException(401,'Login required')
        self.app.dependency_overrides[verify_token]=deny
        self.assertEqual(self.client.get('/api/automation/tasks').status_code,401)
        self.assertEqual(self.client.get('/api/automation/images/any').status_code,401)
        self.assertEqual(self.client.get('/api/recipes').status_code,401)

    def test_recipe_revision_and_import(self):
        r=self.client.post('/api/recipes',json={'name':'recipe','steps':[{'content':'settings'}]}).json()
        key=r['id']
        self.assertEqual(self.client.post('/api/recipes/import',json={'format_version':9}).status_code,422)
        self.client.put('/api/recipes/'+key,json={'name':'changed','steps':[{'content':'home'}]})
        task=self.client.post(f'/api/recipes/{key}/run',json={'device_ids':['a'],'revision':1}).json()
        self.assertEqual(task['steps'][0]['content'],'settings')
        self.assertEqual(len(self.client.get(f'/api/recipes/{key}/revisions').json()['revisions']),2)
        self.assertNotIn('id',self.client.get(f'/api/recipes/{key}/export').json())

    def test_demo_states_and_trigger_cycle_errors(self):
        demo=self.client.post('/api/demonstrations',json={'device_id':'a'}).json()
        self.assertEqual(self.client.post('/api/demonstrations',json={'device_id':'a'}).status_code,409)
        self.assertEqual(self.client.post(f'/api/demonstrations/{demo["id"]}/pause',json={}).status_code,200)
        self.assertEqual(self.client.post(f'/api/demonstrations/{demo["id"]}/finish',json={}).status_code,200)
        recipe=self.client.post('/api/recipes',json={'name':'x','steps':[{'content':'x'}]}).json()
        rule={'kind':'recipe_completed','recipe_id':recipe['id'],'source_recipe':recipe['id'],'device_id':'a'}
        self.assertEqual(self.client.post('/api/triggers',json=rule).status_code,422)

    def test_runtime_timezone_validation(self):
        setting=self.client.get('/api/automation/settings').json();setting['timezone']='Bad/Timezone'
        self.assertEqual(self.client.put('/api/automation/settings',json=setting).status_code,422)

    def test_device_sequence_is_persistent_and_ordered(self):
        response=self.post_task(device_ids=['a','b'],sequence=[{'device_id':'b','content':'first'},
            {'device_id':'a','content':'second'},{'device_id':'b','content':'third'}])
        task=self.client.get('/api/tasks/'+response.json()['task_id']).json()
        self.assertEqual([c['device_id'] for c in task['executions']],['b','a','b'])
