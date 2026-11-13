# -*- coding: utf-8 -*-
"""
Tests for Open API (v1), API Key authentication, and Agent SKILL packaging.
"""

import io
import zipfile
import unittest
from fastapi.testclient import TestClient

from web_app.main import app
from web_app.services.api_key_service import api_key_service
from web_app.services.skill_packager import generate_skill_zip


class OpenAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Ensure at least one primary key exists
        self.key_record = api_key_service.get_primary_key(unmasked=True)
        self.api_key = self.key_record["key"]

    def test_health_and_ping_public(self):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app"], "Open-AutoGLM-GUI")

        resp_ping = self.client.get("/api/v1/ping")
        self.assertEqual(resp_ping.status_code, 200)

    def test_api_key_bearer_and_x_api_key_auth(self):
        # 1. Without auth, protected endpoint returns 401
        unauthed = self.client.get("/api/v1/devices")
        self.assertEqual(unauthed.status_code, 401)

        # 2. With Authorization: Bearer <key>
        authed_bearer = self.client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self.assertEqual(authed_bearer.status_code, 200)
        self.assertIn("devices", authed_bearer.json())

        # 3. With X-API-Key
        authed_header = self.client.get(
            "/api/v1/devices",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(authed_header.status_code, 200)

        # 4. Invalid key returns 401
        invalid = self.client.get(
            "/api/v1/devices",
            headers={"Authorization": "Bearer ak_invalid_random_key_123"},
        )
        self.assertEqual(invalid.status_code, 401)

    def test_generate_and_list_api_keys(self):
        # Generate new key
        gen_resp = self.client.post(
            "/api/v1/keys/generate",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"name": "Test Key for Agent"},
        )
        self.assertEqual(gen_resp.status_code, 200)
        data = gen_resp.json()
        self.assertTrue(data["success"])
        new_key = data["api_key"]
        self.assertTrue(new_key.startswith("ak_autoglm_"))

        # Test authenticating with the new key
        test_call = self.client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {new_key}"},
        )
        self.assertEqual(test_call.status_code, 200)

        # List keys
        list_resp = self.client.get(
            "/api/v1/keys",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self.assertEqual(list_resp.status_code, 200)
        keys_data = list_resp.json()
        self.assertIn("keys", keys_data)
        self.assertIn("primary_key", keys_data)

    def test_skill_download_and_zip_integrity(self):
        resp = self.client.get(
            f"/api/v1/skill/download?api_key={self.api_key}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/zip")
        self.assertIn("open-autoglm-skill.zip", resp.headers.get("content-disposition", ""))

        # Verify ZIP contents
        zip_bytes = resp.content
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = zf.namelist()
            self.assertIn("open-autoglm/SKILL.md", namelist)
            self.assertIn("open-autoglm/README.md", namelist)
            self.assertIn("open-autoglm/scripts/autoglm_client.py", namelist)
            self.assertIn("open-autoglm/references/api_reference.md", namelist)

            # Check SKILL.md embeds the api_key
            skill_md = zf.read("open-autoglm/SKILL.md").decode("utf-8")
            self.assertIn("name: open-autoglm", skill_md)
            self.assertIn(self.api_key, skill_md)

            # Check autoglm_client.py is valid python code
            client_py = zf.read("open-autoglm/scripts/autoglm_client.py").decode("utf-8")
            self.assertIn("class AutoGLMClient", client_py)
            self.assertIn(self.api_key, client_py)
            compile(client_py, "autoglm_client.py", "exec")


if __name__ == "__main__":
    unittest.main()
