# -*- coding: utf-8 -*-
"""
Agent SKILL & MCP Server Packager.
Dynamically packages Open-AutoGLM into a standard, ready-to-use Agent SKILL (.zip).
Includes SKILL.md, standalone Python client script, standard MCP Server script, README, and API reference.
"""

import io
import zipfile
from typing import Optional


def generate_skill_zip(base_url: str, api_key: str) -> bytes:
    """
    Generate an in-memory zip archive containing the Open-AutoGLM Agent SKILL.
    Pre-populates base_url and api_key into SKILL.md, client scripts, MCP server, and docs.
    """
    base_url = (base_url or "http://127.0.0.1:8080").rstrip("/")
    api_key = api_key or ""

    skill_md_content = f"""---
name: open-autoglm
description: Control and automate Android mobile devices via Open-AutoGLM. Use to query device status, run AI phone automation tasks, capture screens, and perform remote ADB gestures (tap, swipe, text, key, shell).
---

# Open-AutoGLM Agent Skill

Remotely control and automate Android devices using the Open-AutoGLM Web Server API, Python CLI, or native MCP Server.

## ⚠️ CRITICAL INSTRUCTION FOR AI AGENTS (请务必阅读):
1. **禁止凭空臆造工具**：你当前**没有**名为 `open-autoglm__xxx` 的内置函数工具！切勿尝试直接调用类似 `open-autoglm__get_screenshot` 的不存在工具。
2. **正确执行途径**：
   - 如果你的环境具备**终端/命令行工具**（如 `run_command`、`bash`、`terminal`）：请直接运行 `python scripts/autoglm_client.py <action>` 或 `curl`！
   - 如果你的环境缺少终端工具（例如在 Dragon Claw 或网页端聊天，未挂载工作区）：请提醒用户在对话界面**“选择工作空间”（开启完全访问权限）**，或者将本项目作为 **MCP Server** 挂载运行。
   - **严禁使用 `browser_navigate` 或 `browser_evaluate`** 试图用浏览器去强行打开或跨域 fetch API 接口。

## Preset Environment
- **Server Base URL**: `{base_url}` (Can be overridden by `AUTOGLM_BASE_URL` env variable)
- **API Key**: `{api_key}` (Can be overridden by `AUTOGLM_API_KEY` env variable)

## When to Use This Skill
Activate this skill whenever the user asks to:
1. **Control or inspect an Android device**: Check connected phones, screen size, battery, or device status.
2. **Execute autonomous mobile AI tasks**: E.g. "打开微信发送消息", "在小红书搜索xx", "完成每日签到".
3. **Inspect phone screens**: Capture real-time screenshots of the device.
4. **Perform direct UI actions**: Tap specific coordinates `(x, y)`, swipe/scroll, enter text, press navigation keys (`home`, `back`, `enter`, `power`), or execute ADB shell commands.

---

## 1. Zero-Dependency Python CLI (`scripts/autoglm_client.py`)

A standalone CLI script is located in `scripts/autoglm_client.py` (uses standard library only, no pip dependencies required).

### Common CLI Examples:
```bash
# 1. Check server health & list connected devices
python scripts/autoglm_client.py devices

# 2. Run an autonomous AI task on the phone (wait for finish)
python scripts/autoglm_client.py run "打开设置，进入关于手机页面" --wait

# 3. Query running task status & logs
python scripts/autoglm_client.py status <task_id>

# 4. Stop a running task
python scripts/autoglm_client.py stop <task_id>

# 5. Take a screenshot and save locally
python scripts/autoglm_client.py screenshot --out phone_screen.png

# 6. Direct phone gestures & input
python scripts/autoglm_client.py tap 500 1000
python scripts/autoglm_client.py swipe 500 1600 500 600 --duration 300
python scripts/autoglm_client.py text "你好 AutoGLM"
python scripts/autoglm_client.py key home
python scripts/autoglm_client.py key back

# 7. Execute custom ADB shell command
python scripts/autoglm_client.py shell "dumpsys battery"
```

---

## 2. Python SDK Client

You can also import and use `AutoGLMClient` directly in any Python script:

```python
import sys
sys.path.append("./scripts")
from autoglm_client import AutoGLMClient

client = AutoGLMClient(base_url="{base_url}", api_key="{api_key}")

# List devices
devices = client.get_devices()
print("Connected devices:", devices)

# Run an AI automation task
task = client.run_task("打开网易云音乐播放每日推荐", wait=True)
print("Task status:", task.get("status"))

# Tap, swipe, type text
client.tap(300, 800)
client.text("Hello from Agent")
client.key("home")

# Take a screenshot
client.get_screenshot(save_path="screenshot.png")
```

---

## 3. Direct REST API Specification

All endpoints support `Authorization: Bearer <API_KEY>` or `X-API-Key: <API_KEY>`.

### 1) List Devices
- **Endpoint**: `GET {base_url}/api/v1/devices`
- **Curl Example**:
  ```bash
  curl -s -H "Authorization: Bearer {api_key}" "{base_url}/api/v1/devices"
  ```

### 2) Run AI Autonomous Task
- **Endpoint**: `POST {base_url}/api/v1/tasks/run`
- **Body**:
  ```json
  {{
    "task": "打开微信给小明发信息",
    "device_id": "optional_device_serial",
    "timeout": 1800,
    "force_run": false
  }}
  ```
- **Curl Example**:
  ```bash
  curl -s -X POST "{base_url}/api/v1/tasks/run" \\
    -H "Authorization: Bearer {api_key}" \\
    -H "Content-Type: application/json" \\
    -d '{{"task": "打开微信给小明发信息"}}'
  ```

### 3) Query Task Status
- **Endpoint**: `GET {base_url}/api/v1/tasks/{{task_id}}`
- **Curl Example**:
  ```bash
  curl -s -H "Authorization: Bearer {api_key}" "{base_url}/api/v1/tasks/TASK_ID"
  ```

### 4) Stop Task
- **Endpoint**: `POST {base_url}/api/v1/tasks/{{task_id}}/stop`

### 5) Device Remote Action
- **Endpoint**: `POST {base_url}/api/v1/devices/{{device_id}}/action`
- **Supported Actions**:
  - `tap`: `{{"action": "tap", "x": 500, "y": 1000}}`
  - `swipe`: `{{"action": "swipe", "x1": 500, "y1": 1500, "x2": 500, "y2": 500, "duration_ms": 300}}`
  - `text`: `{{"action": "text", "text": "Hello World"}}`
  - `key`: `{{"action": "key", "key": "home"}}` (or `back`, `enter`, `power`)
  - `shell`: `{{"action": "shell", "command": "dumpsys battery"}}`
  - `unlock`: `{{"action": "unlock"}}`
  - `lock`: `{{"action": "lock"}}`

### 6) Capture Screenshot
- **Endpoint**: `GET {base_url}/api/v1/devices/{{device_id}}/screenshot`
- Returns binary `image/png`. Add `?format=base64` to receive JSON with base64 string.
"""

    client_py_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open-AutoGLM Standalone Client SDK & CLI.
Zero external dependencies (uses standard library urllib and json).
Generated for: {base_url}
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List

DEFAULT_BASE_URL = "{base_url}"
DEFAULT_API_KEY = "{api_key}"


class AutoGLMClient:
    """Client for Open-AutoGLM Web & Agent API."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (
            base_url
            or os.environ.get("AUTOGLM_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("AUTOGLM_API_KEY")
            or DEFAULT_API_KEY
        ).strip()

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        raw_response: bool = False,
    ) -> Any:
        url = f"{{self.base_url}}{{path}}"
        headers = {{
            "User-Agent": "Open-AutoGLM-Client/1.0",
        }}
        if self.api_key:
            headers["Authorization"] = f"Bearer {{self.api_key}}"
            headers["X-API-Key"] = self.api_key

        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if raw_response:
                    return resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                text = resp.read().decode(charset)
                return json.loads(text) if text else {{}}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("detail", err_json.get("message", err_body))
            except Exception:
                msg = err_body
            raise RuntimeError(f"HTTP {{exc.code}}: {{msg}}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to connect to {{self.base_url}}: {{exc.reason}}") from exc

    def health(self) -> Dict[str, Any]:
        """Check server health and connectivity."""
        return self._request("GET", "/api/v1/health")

    def get_devices(self) -> List[Dict[str, Any]]:
        """List all connected Android devices."""
        res = self._request("GET", "/api/v1/devices")
        return res.get("devices", [])

    def get_device(self, device_id: str) -> Dict[str, Any]:
        """Get details of a specific device."""
        return self._request("GET", f"/api/v1/devices/{{device_id}}")

    def get_screenshot(
        self,
        device_id: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> bytes:
        """Capture screenshot from device (as bytes or save to disk)."""
        if not device_id:
            devs = self.get_devices()
            if not devs:
                raise RuntimeError("No connected devices found")
            device_id = devs[0]["id"]
        img_bytes = self._request("GET", f"/api/v1/devices/{{device_id}}/screenshot", raw_response=True)
        if save_path:
            with open(save_path, "wb") as f:
                f.write(img_bytes)
        return img_bytes

    def get_screenshot_base64(self, device_id: Optional[str] = None) -> str:
        """Capture screenshot as base64 string."""
        if not device_id:
            devs = self.get_devices()
            if not devs:
                raise RuntimeError("No connected devices found")
            device_id = devs[0]["id"]
        res = self._request("GET", f"/api/v1/devices/{{device_id}}/screenshot?format=base64")
        return res.get("image", "")

    def execute_action(
        self,
        action: str,
        device_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a remote device action (tap, swipe, text, key, shell, unlock, lock)."""
        if not device_id:
            devs = self.get_devices()
            if not devs:
                raise RuntimeError("No connected devices found")
            device_id = devs[0]["id"]
        payload = {{"action": action, **kwargs}}
        return self._request("POST", f"/api/v1/devices/{{device_id}}/action", data=payload)

    def tap(self, x: int, y: int, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Tap at screen coordinates (x, y)."""
        return self.execute_action("tap", device_id=device_id, x=x, y=y)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Swipe from (x1, y1) to (x2, y2)."""
        return self.execute_action(
            "swipe",
            device_id=device_id,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            duration_ms=duration_ms,
        )

    def text(self, text_content: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Input text to the focused field."""
        return self.execute_action("text", device_id=device_id, text=text_content)

    def key(self, key_name: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Send keyevent (e.g. 'home', 'back', 'enter', 'power', or keycode)."""
        return self.execute_action("key", device_id=device_id, key=key_name)

    def shell(self, command: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute ADB shell command on the device."""
        return self.execute_action("shell", device_id=device_id, command=command)

    def run_task(
        self,
        task_instruction: str,
        device_id: Optional[str] = None,
        wait: bool = False,
        timeout: int = 1800,
        force_run: bool = False,
    ) -> Dict[str, Any]:
        """Submit an autonomous AutoGLM AI task."""
        payload = {{
            "task": task_instruction,
            "device_id": device_id,
            "timeout": timeout,
            "force_run": force_run,
        }}
        res = self._request("POST", "/api/v1/tasks/run", data=payload)
        task_id = res.get("task_id")
        if not wait or not task_id:
            return res

        print(f"Task submitted (ID: {{task_id}}). Monitoring progress...", file=sys.stderr)
        start_t = time.time()
        last_log_idx = 0
        while time.time() - start_t < timeout:
            status_data = self.get_task(task_id)
            status = status_data.get("status", "")
            logs = status_data.get("latest_logs", [])
            while last_log_idx < len(logs):
                print(f"[AutoGLM] {{logs[last_log_idx]}}", file=sys.stderr)
                last_log_idx += 1

            if status in ("completed", "success", "failed", "stopped", "interrupted"):
                return status_data
            time.sleep(2)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get task status and logs by task ID."""
        return self._request("GET", f"/api/v1/tasks/{{task_id}}")

    def stop_task(self, task_id: str) -> Dict[str, Any]:
        """Stop a running task."""
        return self._request("POST", f"/api/v1/tasks/{{task_id}}/stop")

    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent tasks."""
        res = self._request("GET", f"/api/v1/tasks?limit={{limit}}")
        return res.get("tasks", [])


def main():
    parser = argparse.ArgumentParser(description="Open-AutoGLM CLI & Agent Tool")
    parser.add_argument("--base-url", default=None, help=f"Server base URL (default: {{DEFAULT_BASE_URL}})")
    parser.add_argument("--api-key", default=None, help="API Key")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # health
    subparsers.add_parser("health", help="Check server health")

    # devices
    subparsers.add_parser("devices", help="List connected Android devices")

    # screenshot
    p_screen = subparsers.add_parser("screenshot", help="Capture device screenshot")
    p_screen.add_argument("--device", help="Device ID / serial")
    p_screen.add_argument("--out", default="screenshot.png", help="Output file path (default: screenshot.png)")

    # tap
    p_tap = subparsers.add_parser("tap", help="Tap screen coordinates")
    p_tap.add_argument("x", type=int, help="X coordinate")
    p_tap.add_argument("y", type=int, help="Y coordinate")
    p_tap.add_argument("--device", help="Device ID")

    # swipe
    p_swipe = subparsers.add_parser("swipe", help="Swipe gesture")
    p_swipe.add_argument("x1", type=int)
    p_swipe.add_argument("y1", type=int)
    p_swipe.add_argument("x2", type=int)
    p_swipe.add_argument("y2", type=int)
    p_swipe.add_argument("--duration", type=int, default=300, help="Duration in ms")
    p_swipe.add_argument("--device", help="Device ID")

    # text
    p_text = subparsers.add_parser("text", help="Input text into current field")
    p_text.add_argument("content", help="Text to input")
    p_text.add_argument("--device", help="Device ID")

    # key
    p_key = subparsers.add_parser("key", help="Send key event (home, back, enter, power, etc.)")
    p_key.add_argument("key_name", help="Key name or keycode")
    p_key.add_argument("--device", help="Device ID")

    # shell
    p_shell = subparsers.add_parser("shell", help="Execute ADB shell command")
    p_shell.add_argument("cmd", help="Shell command to execute")
    p_shell.add_argument("--device", help="Device ID")

    # run
    p_run = subparsers.add_parser("run", help="Run autonomous AI task")
    p_run.add_argument("instruction", help="Task description in natural language")
    p_run.add_argument("--device", help="Device ID")
    p_run.add_argument("--wait", action="store_true", help="Wait for task to complete")
    p_run.add_argument("--timeout", type=int, default=1800, help="Timeout in seconds")
    p_run.add_argument("--force", action="store_true", help="Force interrupt active tasks")

    # status
    p_status = subparsers.add_parser("status", help="Query task status")
    p_status.add_argument("task_id", help="Task ID")

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop task")
    p_stop.add_argument("task_id", help="Task ID")

    # list-tasks
    p_tasks = subparsers.add_parser("list-tasks", help="List recent tasks")
    p_tasks.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()
    client = AutoGLMClient(base_url=args.base_url, api_key=args.api_key)

    try:
        if args.command == "health":
            res = client.health()
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "devices":
            devs = client.get_devices()
            if not devs:
                print("No connected Android devices.")
            else:
                print(f"Connected devices ({{len(devs)}}):")
                for d in devs:
                    print(f"  - [{{d.get('id')}}] {{d.get('name')}} (Status: {{d.get('status')}}, Model: {{d.get('model')}}, Res: {{d.get('screen_size')}})")
        elif args.command == "screenshot":
            client.get_screenshot(device_id=args.device, save_path=args.out)
            print(f"Screenshot saved to {{args.out}}")
        elif args.command == "tap":
            res = client.tap(args.x, args.y, device_id=args.device)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "swipe":
            res = client.swipe(args.x1, args.y1, args.x2, args.y2, duration_ms=args.duration, device_id=args.device)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "text":
            res = client.text(args.content, device_id=args.device)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "key":
            res = client.key(args.key_name, device_id=args.device)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "shell":
            res = client.shell(args.cmd, device_id=args.device)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "run":
            res = client.run_task(args.instruction, device_id=args.device, wait=args.wait, timeout=args.timeout, force_run=args.force)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "status":
            res = client.get_task(args.task_id)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "stop":
            res = client.stop_task(args.task_id)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "list-tasks":
            res = client.list_tasks(limit=args.limit)
            print(json.dumps(res, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"Error: {{exc}}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
'''

    mcp_server_py_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open-AutoGLM Model Context Protocol (MCP) Standard Server.
Provides native Tools to any MCP-compliant Agent (Dragon Claw, Claude Desktop, Antigravity, Cursor).
Zero external dependencies (uses standard library JSON-RPC over stdio).
Pre-configured for: {base_url}
"""

import sys
import json
import os
import urllib.request
import urllib.error

DEFAULT_BASE_URL = "{base_url}"
DEFAULT_API_KEY = "{api_key}"

BASE_URL = os.environ.get("AUTOGLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
API_KEY = os.environ.get("AUTOGLM_API_KEY", DEFAULT_API_KEY).strip()


def api_request(method: str, path: str, data: dict = None) -> dict:
    url = f"{{BASE_URL}}{{path}}"
    headers = {{
        "User-Agent": "Open-AutoGLM-MCP/1.0",
    }}
    if API_KEY:
        headers["Authorization"] = f"Bearer {{API_KEY}}"
        headers["X-API-Key"] = API_KEY

    payload = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            return json.loads(text) if text else {{}}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("detail", err_json.get("message", err_body))
        except Exception:
            msg = err_body
        raise RuntimeError(f"HTTP {{exc.code}}: {{msg}}")
    except Exception as exc:
        raise RuntimeError(f"Failed to connect to {{BASE_URL}}: {{exc}}")


TOOLS = [
    {{
        "name": "open_autoglm_list_devices",
        "description": "List all connected Android devices with online status, model name, and screen size.",
        "inputSchema": {{
            "type": "object",
            "properties": {{}},
        }},
    }},
    {{
        "name": "open_autoglm_get_screenshot",
        "description": "Capture the real-time screen of the Android device and return base64 image data.",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "device_id": {{
                    "type": "string",
                    "description": "Target device serial ID (optional, defaults to first online device)",
                }},
            }},
        }},
    }},
    {{
        "name": "open_autoglm_run_task",
        "description": "Submit an autonomous AI phone operation task in natural language (e.g. '打开微信发朋友圈', '打开设置查看版本号').",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "task": {{
                    "type": "string",
                    "description": "Natural language instruction for AutoGLM",
                }},
                "device_id": {{
                    "type": "string",
                    "description": "Target device serial ID (optional)",
                }},
            }},
            "required": ["task"],
        }},
    }},
    {{
        "name": "open_autoglm_device_action",
        "description": "Perform low-level touch, gesture, or key on the device: tap(x, y), swipe(x1, y1, x2, y2), text(content), key(home/back/enter/power), shell(command).",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "action": {{
                    "type": "string",
                    "enum": ["tap", "swipe", "text", "key", "shell", "unlock", "lock"],
                    "description": "Action type",
                }},
                "x": {{"type": "integer", "description": "X coordinate for tap"}},
                "y": {{"type": "integer", "description": "Y coordinate for tap"}},
                "x1": {{"type": "integer", "description": "Swipe start X"}},
                "y1": {{"type": "integer", "description": "Swipe start Y"}},
                "x2": {{"type": "integer", "description": "Swipe end X"}},
                "y2": {{"type": "integer", "description": "Swipe end Y"}},
                "duration_ms": {{"type": "integer", "default": 300}},
                "text": {{"type": "string", "description": "Text to type"}},
                "key": {{"type": "string", "description": "Key name (home, back, enter, power)"}},
                "command": {{"type": "string", "description": "ADB shell command"}},
                "device_id": {{"type": "string", "description": "Target device ID (optional)"}},
            }},
            "required": ["action"],
        }},
    }},
    {{
        "name": "open_autoglm_task_status",
        "description": "Query the execution progress and logs of an autonomous AutoGLM task by task_id.",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "task_id": {{
                    "type": "string",
                    "description": "Task ID returned from open_autoglm_run_task",
                }},
            }},
            "required": ["task_id"],
        }},
    }},
]


def handle_tool_call(name: str, args: dict) -> list:
    if name == "open_autoglm_list_devices":
        res = api_request("GET", "/api/v1/devices")
        return [{{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}}]

    elif name == "open_autoglm_get_screenshot":
        device_id = args.get("device_id")
        if not device_id:
            devs = api_request("GET", "/api/v1/devices").get("devices", [])
            if not devs:
                return [{{"type": "text", "text": "Error: No connected Android devices found."}}]
            device_id = devs[0]["id"]
        res = api_request("GET", f"/api/v1/devices/{{device_id}}/screenshot?format=base64")
        img_b64 = res.get("image", "")
        if not img_b64:
            return [{{"type": "text", "text": "Failed to capture screenshot."}}]
        return [
            {{"type": "text", "text": f"Screenshot captured from device {{device_id}}."}},
            {{"type": "image", "data": img_b64, "mimeType": "image/png"}},
        ]

    elif name == "open_autoglm_run_task":
        res = api_request("POST", "/api/v1/tasks/run", data=args)
        return [{{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}}]

    elif name == "open_autoglm_device_action":
        device_id = args.get("device_id")
        if not device_id:
            devs = api_request("GET", "/api/v1/devices").get("devices", [])
            if not devs:
                return [{{"type": "text", "text": "Error: No connected Android devices found."}}]
            device_id = devs[0]["id"]
        res = api_request("POST", f"/api/v1/devices/{{device_id}}/action", data=args)
        return [{{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}}]

    elif name == "open_autoglm_task_status":
        task_id = args.get("task_id")
        res = api_request("GET", f"/api/v1/tasks/{{task_id}}")
        return [{{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}}]

    else:
        raise ValueError(f"Unknown tool: {{name}}")


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        method = req.get("method")
        msg_id = req.get("id")

        if method == "initialize":
            res = {{
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {{
                    "protocolVersion": "2024-11-05",
                    "capabilities": {{"tools": {{}}}},
                    "serverInfo": {{"name": "open-autoglm-mcp", "version": "1.0.0"}},
                }},
            }}
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            # No reply needed
            pass

        elif method == "tools/list":
            res = {{
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {{"tools": TOOLS}},
            }}
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()

        elif method == "tools/call":
            params = req.get("params", {{}})
            name = params.get("name")
            args = params.get("arguments", {{}})
            try:
                content = handle_tool_call(name, args)
                res = {{
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {{"content": content}},
                }}
            except Exception as exc:
                res = {{
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {{
                        "content": [{{"type": "text", "text": f"Error: {{exc}}"}}],
                        "isError": True,
                    }},
                }}
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()

        elif msg_id is not None:
            # Fallback for unhandled methods
            res = {{
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {{"code": -32601, "message": "Method not found"}},
            }}
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
'''

    readme_content = f"""# Open-AutoGLM Agent Skill, Python SDK & MCP Server

Welcome to the **Open-AutoGLM** Agent Skill package!

This package lets any AI coding agent (such as Antigravity, Dragon Claw, Claude Code, Cursor, Copilot, LangChain) or external program connect to your Open-AutoGLM server at `{base_url}`.

## Included Files
- `SKILL.md`: Standard Agent Skill definition with complete tool usage prompt and REST references.
- `scripts/autoglm_client.py`: Zero-dependency standalone Python CLI & SDK.
- `scripts/mcp_server.py`: Standard MCP (Model Context Protocol) Server for platforms like Dragon Claw, Claude Desktop, Cursor.
- `references/api_reference.md`: Detailed HTTP API endpoints and request/response specifications.

## Quick Installation

### Option 1: Install as an Agent Skill (Antigravity / Claude Code / Dragon Claw)
Copy the entire `open-autoglm` folder into your agent's skills directory:
- **Antigravity / Gemini**: `~/.gemini/antigravity/skills/open-autoglm/` or `<workspace>/.gemini/skills/open-autoglm/`
- **Claude Code**: `~/.claude/skills/open-autoglm/` or `.claude/skills/open-autoglm/`
- **Dragon Claw / General**: Inside your workspace. (⚠️ 注意：在 Dragon Claw 中使用时，请在会话界面左下角**选择工作空间**，以授权 Agent 终端执行权限！)

### Option 2: Configure as a Native MCP Server (Dragon Claw / Claude Desktop)
在 Dragon Claw 的 **“技能·插件·工具” -> MCP 服务** 或 Claude Desktop 的 `claude_desktop_config.json` 中添加：
```json
{{
  "mcpServers": {{
    "open-autoglm": {{
      "command": "python",
      "args": ["/path/to/open-autoglm/scripts/mcp_server.py"],
      "env": {{
        "AUTOGLM_BASE_URL": "{base_url}",
        "AUTOGLM_API_KEY": "{api_key}"
      }}
    }}
  }}
}}
```
**配置为 MCP 后，Agent 无需终端权限即可直接原生调用 `open_autoglm_get_screenshot`、`open_autoglm_run_task` 等工具！**

### Option 3: Use as a Python CLI / Script
```bash
# Check connected phones
python scripts/autoglm_client.py devices

# Send AI task
python scripts/autoglm_client.py run "打开相机拍照" --wait
```
"""

    api_ref_content = f"""# Open-AutoGLM REST API Reference (v1)

Base URL: `{base_url}`
Authentication: Include `Authorization: Bearer <API_KEY>` or `X-API-Key: <API_KEY>` in headers.

## 1. System Health
- **Method**: `GET /api/v1/health`
- **Response**:
  ```json
  {{
    "status": "ok",
    "app": "Open-AutoGLM-GUI",
    "version": "1.0.0",
    "timestamp": "2026-11-14T00:00:00Z"
  }}
  ```

## 2. Devices
### List Devices
- **Method**: `GET /api/v1/devices`
- **Response**:
  ```json
  {{
    "devices": [
      {{
        "id": "3B1QYFE32239E",
        "name": "MEIZU 20",
        "status": "online",
        "model": "MEIZU 20",
        "screen_size": "1080x2400",
        "connection_type": "usb"
      }}
    ],
    "count": 1
  }}
  ```

### Device Screenshot
- **Method**: `GET /api/v1/devices/{{device_id}}/screenshot`
- **Query Params**: `format=raw` (returns image/png binary) or `format=base64` (returns JSON).

### Device Remote Action
- **Method**: `POST /api/v1/devices/{{device_id}}/action`
- **Body**:
  - Tap: `{{"action": "tap", "x": 500, "y": 1000}}`
  - Swipe: `{{"action": "swipe", "x1": 500, "y1": 1500, "x2": 500, "y2": 500, "duration_ms": 300}}`
  - Text: `{{"action": "text", "text": "Hello AutoGLM"}}`
  - Key: `{{"action": "key", "key": "home"}}`
  - Shell: `{{"action": "shell", "command": "dumpsys battery"}}`
  - Unlock: `{{"action": "unlock"}}`
  - Lock: `{{"action": "lock"}}`

## 3. Tasks
### Run Autonomous AI Task
- **Method**: `POST /api/v1/tasks/run`
- **Body**:
  ```json
  {{
    "task": "打开微信给小明发信息",
    "device_id": "optional_device_id",
    "timeout": 1800,
    "force_run": false
  }}
  ```

### Query Task Status
- **Method**: `GET /api/v1/tasks/{{task_id}}`

### Stop Task
- **Method**: `POST /api/v1/tasks/{{task_id}}/stop`

### List Recent Tasks
- **Method**: `GET /api/v1/tasks?limit=10`
"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("open-autoglm/SKILL.md", skill_md_content)
        zf.writestr("open-autoglm/README.md", readme_content)
        zf.writestr("open-autoglm/scripts/autoglm_client.py", client_py_content)
        zf.writestr("open-autoglm/scripts/mcp_server.py", mcp_server_py_content)
        zf.writestr("open-autoglm/references/api_reference.md", api_ref_content)

    buffer.seek(0)
    return buffer.getvalue()
