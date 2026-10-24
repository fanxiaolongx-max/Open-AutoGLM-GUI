import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from web_app.services.automation_runtime import Runtime
from web_app.services.automation_storage import AutomationStorage
import web_app.services.automation_runtime as rt


class LifecycleTests(unittest.TestCase):
    def test_real_app_dispatch_and_shutdown_without_external_services(self):
        import web_app.main as main
        from web_app.services.automation_catalog import catalog
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            async def runner(task,child,step,control):
                runtime.emit(task['id'],child['device_id'],'action',{'action':{'_metadata':'finish'}})
                return {'success':True,'reason':'completed','message':'mock completed'}
            runtime=Runtime(AutomationStorage(Path(tmp)/'db'),runner,devices=lambda:{'a'})
            stack.enter_context(patch.object(rt,'_runtime',runtime))
            stack.enter_context(patch.object(main.auth_service,'verify_session',return_value=True))
            stack.enter_context(patch.object(main.scheduler_service,'start',new=AsyncMock()))
            stack.enter_context(patch.object(main.scheduler_service,'stop',new=AsyncMock()))
            stack.enter_context(patch.object(main.scheduler_service,'add_task_callback'))
            stack.enter_context(patch.object(main.device_service,'refresh_devices',new=AsyncMock(return_value=[])))
            stack.enter_context(patch.object(catalog,'start',new=AsyncMock()))
            stack.enter_context(patch.object(catalog,'close',new=AsyncMock()))
            stack.enter_context(patch('web_app.routers.telegram.load_telegram_config',return_value={'enabled':False}))
            stack.enter_context(patch('web_app.services.telegram_bot.telegram_bot_service.stop',new=AsyncMock()))
            stack.enter_context(patch('web_app.services.scrcpy_service.scrcpy_service.cleanup_all',new=AsyncMock()))
            stack.enter_context(patch('web_app.routers.tunnel.shutdown_tunnel',new=AsyncMock()))
            with TestClient(main.app) as client:
                created=client.post('/api/tasks/run',json={'task_content':'test','device_ids':['a'],'send_email':False})
                self.assertEqual(created.status_code,200)
                key=created.json()['task_id']
                for _ in range(30):
                    task=client.get('/api/tasks/'+key).json()
                    if task['status']=='completed':break
                    time.sleep(.05)
                self.assertEqual(task['status'],'completed')
                self.assertTrue(client.get(f'/api/tasks/{key}/events').json()['events'])
                self.assertEqual(client.get('/static/automation.html').status_code,200)
                script = client.get('/static/js/main.js')
                self.assertEqual(script.status_code,200)
                self.assertIn('no-cache', script.headers['cache-control'])
            self.assertIsNone(runtime.poller)
            self.assertIsNone(runtime.process_lock)

    def test_new_routes_are_protected_by_real_session_middleware(self):
        import web_app.main as main
        with patch.object(main.auth_service,'verify_session',return_value=False):
            client=TestClient(main.app)
            for path in ['/api/automation/tasks','/api/recipes','/api/demonstrations','/api/triggers',
                         '/api/automation/images/image']:
                self.assertEqual(client.get(path).status_code,401)
            client.close()

    def test_health_advertises_automation_without_requiring_login(self):
        import web_app.main as main
        with patch.object(main.auth_service,'verify_session',return_value=False):
            client=TestClient(main.app)
            response=client.get('/health')
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()['capabilities']['automation'])
            client.close()

    def test_maintenance_suppression_is_consumed_once(self):
        from web_app.main import consume_quiet_start_once
        with tempfile.TemporaryDirectory() as tmp:
            flag=Path(tmp)/'quiet'
            self.assertFalse(consume_quiet_start_once(flag))
            flag.touch()
            self.assertTrue(consume_quiet_start_once(flag))
            self.assertFalse(flag.exists())
            self.assertFalse(consume_quiet_start_once(flag))
