import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from web_app.auth import verify_token
from web_app.routers.models import router, model_service
from web_app.models.model_services import ModelServiceConfig


class ContextConfigTests(unittest.TestCase):
    def test_model_capacity_is_distinct_from_output_and_old_updates_preserve_it(self):
        self.assertEqual(ModelServiceConfig(max_tokens=3000,context_window=128000).context_window,128000)
        app=FastAPI();app.dependency_overrides[verify_token]=lambda:True;app.include_router(router)
        payload=dict(id='model',name='fake',base_url='http://fake.invalid',model_name='fake',max_tokens=256)
        with TestClient(app) as client, \
             patch.object(model_service,'get_service_by_id',return_value={**payload,'context_window':8192}), \
             patch.object(model_service,'update_service',return_value=True) as save:
            self.assertEqual(client.put('/api/models/model',json=payload).status_code,200)
            self.assertEqual(save.call_args.args[0]['context_window'],8192)
            self.assertEqual(client.put('/api/models/model',json={**payload,'context_window':16384}).status_code,200)
            self.assertEqual(save.call_args.args[0]['context_window'],16384)
            self.assertEqual(client.put('/api/models/model',json={**payload,'context_window':-1}).status_code,422)
