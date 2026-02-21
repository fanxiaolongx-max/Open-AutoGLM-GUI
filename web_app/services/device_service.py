# -*- coding: utf-8 -*-
"""
Device service for managing connected devices.
Uses phone_agent.device_factory for device management (same as GUI).
"""

import asyncio
import base64
import json
import logging
import shlex
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Device information."""
    id: str
    name: str
    platform: str  # "android" or "ios"
    status: str  # "connected", "offline", "unauthorized"
    model: str = ""
    sdk_version: str = ""
    screen_size: str = ""
    connection_type: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DeviceService:
    """Service for managing devices using phone_agent."""

    def __init__(self):
        self._devices: dict[str, DeviceInfo] = {}
        self._device_pins: dict[str, str] = {}
        self._load_pins()
        # Initialize device factory with ADB
        set_device_type(DeviceType.ADB)
        # Device monitoring
        self._previous_devices: set[str] = set()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._telegram_bot = None  # Will be set by main.py


    def _load_pins(self):
        """Load device PINs from database."""
        try:
            from web_app.services.config_storage import config_storage
            self._device_pins = config_storage.get_device_pins()
        except Exception:
            self._device_pins = {}

    def _save_pins(self):
        """Save device PINs to database."""
        try:
            from web_app.services.config_storage import config_storage
            config_storage.set("device_pins", self._device_pins, config_storage.CATEGORY_DEVICE)
        except Exception:
            pass

    def get_device_pin(self, device_id: str) -> Optional[str]:
        """Get PIN for a device."""
        return self._device_pins.get(device_id)

    def get_all_pins(self) -> dict[str, str]:
        """Get all stored device PINs."""
        return self._device_pins.copy()

    def set_device_pin(self, device_id: str, pin: str):
        """Set PIN for a device."""
        self._device_pins[device_id] = pin
        self._save_pins()

    async def refresh_devices(self) -> list[DeviceInfo]:
        """Refresh and return the list of connected devices using phone_agent."""
        devices = []
        previous_count = len(self._devices)

        try:
            # Use phone_agent's device factory (same as GUI)
            factory = get_device_factory()
            device_list = factory.list_devices()
            new_devices: dict[str, DeviceInfo] = {}

            for device in device_list:
                status = "connected" if device.status == "device" else device.status
                connection_type = device.connection_type.value if hasattr(device.connection_type, 'value') else str(device.connection_type)

                device_info = DeviceInfo(
                    id=device.device_id,
                    name=device.model or device.device_id,
                    platform="android",
                    status=status,
                    model=device.model or "",
                    connection_type=connection_type,
                )

                devices.append(device_info)
                new_devices[device.device_id] = device_info

            # Replace cache only on successful refresh.
            self._devices = new_devices

            # Only log if device count changed
            if len(devices) != previous_count:
                logger.info(f"Device count changed: {previous_count} -> {len(devices)} device(s)")

        except Exception as e:
            logger.error(f"Error refreshing devices: {e}")
            # Keep previous cache on transient ADB errors/timeouts.
            devices = list(self._devices.values())

        return devices

    def get_all_devices(self) -> list[DeviceInfo]:
        """Get all cached devices."""
        return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Get a specific device by ID."""
        return self._devices.get(device_id)

    async def get_screenshot(self, device_id: str) -> Optional[bytes]:
        """Get screenshot from a device as PNG bytes using phone_agent."""
        device = self._devices.get(device_id)
        if not device:
            return None

        try:
            # Use phone_agent's screenshot function
            from phone_agent.adb import get_screenshot
            import base64

            loop = asyncio.get_event_loop()

            def get_screenshot_sync():
                # get_screenshot returns a Screenshot object with base64_data
                screenshot = get_screenshot(device_id)
                if screenshot and screenshot.base64_data:
                    # Decode base64 to bytes
                    return base64.b64decode(screenshot.base64_data)
                return None

            png_data = await loop.run_in_executor(None, get_screenshot_sync)
            return png_data

        except Exception as e:
            logger.error(f"Error getting screenshot for {device_id}: {e}")

        return None

    async def get_screenshot_base64(self, device_id: str) -> Optional[str]:
        """Get screenshot as base64 encoded string."""
        png_data = await self.get_screenshot(device_id)
        if png_data:
            return base64.b64encode(png_data).decode("utf-8")
        return None

    async def unlock_device(self, device_id: str, pin: Optional[str] = None) -> bool:
        """Unlock a device using PIN or swipe via phone_agent."""
        device = self._devices.get(device_id)
        if not device or device.status != "connected":
            return False

        # Use stored PIN if not provided
        if not pin:
            pin = self.get_device_pin(device_id)

        try:
            from phone_agent.adb import unlock_device, wake_screen

            loop = asyncio.get_event_loop()

            def unlock_sync():
                wake_screen(device_id)
                # unlock_device returns (success, message) tuple
                result = unlock_device(device_id, pin)
                if isinstance(result, tuple):
                    return result[0]
                return result

            success = await loop.run_in_executor(None, unlock_sync)
            return success

        except Exception as e:
            logger.error(f"Error unlocking device {device_id}: {e}")

        return False

    async def lock_device(self, device_id: str) -> bool:
        """Lock a device screen."""
        device = self._devices.get(device_id)
        if not device or device.status != "connected":
            return False

        try:
            from phone_agent.adb import lock_screen

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, lambda: lock_screen(device_id))
            return success

        except Exception as e:
            logger.error(f"Error locking device {device_id}: {e}")

        return False

    async def is_screen_locked(self, device_id: str) -> bool:
        """Check if device screen is locked."""
        device = self._devices.get(device_id)
        if not device or device.status != "connected":
            return False

        try:
            from phone_agent.adb import is_device_locked, wake_screen

            loop = asyncio.get_event_loop()

            def check_sync():
                # First wake the screen to check lock status
                wake_screen(device_id)
                import time
                time.sleep(0.3)

                # Check if device is locked
                return is_device_locked(device_id)

            return await loop.run_in_executor(None, check_sync)

        except Exception as e:
            logger.error(f"Error checking screen lock for {device_id}: {e}")

        return False

    async def wireless_pair(self, pair_address: str, pair_code: str) -> tuple[bool, str, list[str]]:
        """
        Perform ADB wireless pairing.

        Args:
            pair_address: The pairing address (e.g., 192.168.1.100:37000)
            pair_code: The 6-digit pairing code

        Returns:
            (success, message, logs) tuple
        """
        logs = []
        logs.append(f"开始无线配对...")
        logs.append(f"配对地址: {pair_address}")
        logs.append(f"配对码: {'*' * 6}")

        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def pair_sync():
                result = subprocess.run(
                    ["adb", "pair", pair_address],
                    input=pair_code + "\n",
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result

            result = await loop.run_in_executor(None, pair_sync)
            output = (result.stdout + result.stderr).strip()
            logs.append(f"配对输出: {output}")

            if "Successfully paired" in output or "成功" in output:
                logs.append("✅ 配对成功！")
                return True, "配对成功", logs
            else:
                logs.append("❌ 配对失败")
                return False, f"配对失败: {output}", logs

        except subprocess.TimeoutExpired:
            logs.append("❌ 配对超时")
            return False, "配对超时", logs
        except Exception as e:
            logs.append(f"❌ 配对错误: {str(e)}")
            return False, f"配对错误: {str(e)}", logs

    async def tcp_connect(self, connect_address: str) -> tuple[bool, str, list[str]]:
        """
        Connect to a device via TCP/IP (adb connect).

        Args:
            connect_address: The connection address (e.g., 192.168.1.100:5555)

        Returns:
            (success, message, logs) tuple
        """
        logs = []
        logs.append(f"正在连接设备...")
        logs.append(f"连接地址: {connect_address}")

        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def connect_sync():
                result = subprocess.run(
                    ["adb", "connect", connect_address],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return result

            result = await loop.run_in_executor(None, connect_sync)
            output = (result.stdout + result.stderr).strip()
            logs.append(f"连接输出: {output}")

            if "connected" in output.lower() and "cannot" not in output.lower():
                logs.append("✅ 连接成功！")
                return True, "连接成功", logs
            elif "already connected" in output.lower():
                logs.append("✅ 设备已连接")
                return True, "设备已连接", logs
            else:
                logs.append("❌ 连接失败")
                return False, f"连接失败: {output}", logs

        except subprocess.TimeoutExpired:
            logs.append("❌ 连接超时")
            return False, "连接超时", logs
        except Exception as e:
            logs.append(f"❌ 连接错误: {str(e)}")
            return False, f"连接错误: {str(e)}", logs

    async def disconnect_device(self, device_id: str) -> tuple[bool, str]:
        """
        Disconnect a device.

        Args:
            device_id: The device ID to disconnect

        Returns:
            (success, message) tuple
        """
        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def disconnect_sync():
                result = subprocess.run(
                    ["adb", "disconnect", device_id],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result

            result = await loop.run_in_executor(None, disconnect_sync)
            output = (result.stdout + result.stderr).strip()

            if "disconnected" in output.lower() or result.returncode == 0:
                return True, "设备已断开"
            else:
                return False, f"断开失败: {output}"

        except Exception as e:
            return False, f"断开错误: {str(e)}"

    async def install_apk(self, device_id: str, apk_path: str) -> tuple[bool, str, list[str]]:
        """
        Install an APK file on a device.

        Args:
            device_id: The device ID to install on
            apk_path: Path to the APK file

        Returns:
            (success, message, logs) tuple
        """
        import os
        logs = []
        filename = os.path.basename(apk_path)
        logs.append(f"开始安装: {filename}")
        logs.append(f"目标设备: {device_id}")

        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def install_sync():
                cmd = ["adb"]
                if device_id:
                    cmd.extend(["-s", device_id])
                cmd.extend(["install", "-r", apk_path])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes timeout for large APKs
                )
                return result

            logs.append("正在安装，请稍候...")
            result = await loop.run_in_executor(None, install_sync)
            output = (result.stdout + result.stderr).strip()
            logs.append(f"安装输出: {output}")

            if result.returncode == 0 and "Success" in output:
                logs.append("✅ 安装成功！")
                return True, "安装成功", logs
            else:
                logs.append("❌ 安装失败")
                return False, f"安装失败: {output}", logs

        except subprocess.TimeoutExpired:
            logs.append("❌ 安装超时（超过5分钟）")
            return False, "安装超时", logs
        except Exception as e:
            logs.append(f"❌ 安装错误: {str(e)}")
            return False, f"安装错误: {str(e)}", logs

    async def list_files(self, device_id: str, path: str) -> tuple[bool, list[dict], str]:
        """
        List files in a directory on the device.

        Returns:
            (success, files_list, message) tuple
        """
        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def list_sync():
                cmd = ["adb"]
                if device_id:
                    cmd.extend(["-s", device_id])
                cmd.extend(["shell", "ls", "-la", path])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result

            result = await loop.run_in_executor(None, list_sync)

            if result.returncode != 0:
                return False, [], f"无法访问目录: {result.stderr.strip()}"

            files = []
            lines = result.stdout.strip().split('\n')

            for line in lines:
                if not line.strip() or line.startswith('total'):
                    continue

                parts = line.split()
                if len(parts) >= 8:
                    perms = parts[0]
                    size = parts[4] if len(parts) > 4 else "0"
                    name = ' '.join(parts[7:]) if len(parts) > 7 else parts[-1]

                    # Skip . and ..
                    if name in ['.', '..']:
                        continue

                    is_dir = perms.startswith('d')
                    is_link = perms.startswith('l')

                    files.append({
                        "name": name,
                        "is_dir": is_dir,
                        "is_link": is_link,
                        "size": size,
                        "permissions": perms,
                    })

            # Sort: directories first, then files
            files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

            return True, files, "成功"

        except subprocess.TimeoutExpired:
            return False, [], "列出文件超时"
        except Exception as e:
            return False, [], f"列出文件错误: {str(e)}"

    async def pull_file(self, device_id: str, remote_path: str) -> tuple[bool, bytes, str, str]:
        """
        Pull a file from the device.

        Returns:
            (success, content, filename, message) tuple
        """
        import os
        import tempfile

        filename = os.path.basename(remote_path)
        temp_dir = tempfile.mkdtemp()
        local_path = os.path.join(temp_dir, filename)

        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def pull_sync():
                cmd = ["adb"]
                if device_id:
                    cmd.extend(["-s", device_id])
                cmd.extend(["pull", remote_path, local_path])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                return result

            result = await loop.run_in_executor(None, pull_sync)

            if result.returncode != 0 or not os.path.exists(local_path):
                return False, b"", filename, f"下载失败: {result.stderr.strip()}"

            with open(local_path, 'rb') as f:
                content = f.read()

            return True, content, filename, "下载成功"

        except subprocess.TimeoutExpired:
            return False, b"", filename, "下载超时"
        except Exception as e:
            return False, b"", filename, f"下载错误: {str(e)}"
        finally:
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    async def push_file(self, device_id: str, local_path: str, remote_path: str) -> tuple[bool, str]:
        """
        Push a file to the device.

        Returns:
            (success, message) tuple
        """
        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def push_sync():
                cmd = ["adb"]
                if device_id:
                    cmd.extend(["-s", device_id])
                cmd.extend(["push", local_path, remote_path])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                return result

            result = await loop.run_in_executor(None, push_sync)
            output = (result.stdout + result.stderr).strip()

            if result.returncode == 0:
                return True, "上传成功"
            else:
                return False, f"上传失败: {output}"

        except subprocess.TimeoutExpired:
            return False, "上传超时"
        except Exception as e:
            return False, f"上传错误: {str(e)}"

    async def delete_file(self, device_id: str, remote_path: str) -> tuple[bool, str]:
        """
        Delete a file on the device.

        Returns:
            (success, message) tuple
        """
        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def delete_sync():
                cmd = ["adb"]
                if device_id:
                    cmd.extend(["-s", device_id])
                cmd.extend(["shell", "rm", "-rf", remote_path])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result

            result = await loop.run_in_executor(None, delete_sync)

            if result.returncode == 0:
                return True, "删除成功"
            else:
                return False, f"删除失败: {result.stderr.strip()}"

        except subprocess.TimeoutExpired:
            return False, "删除超时"
        except Exception as e:
            return False, f"删除错误: {str(e)}"

    @staticmethod
    def _build_adb_args_from_chat_command(command: str) -> tuple[list[str], str]:
        """
        Parse chat slash command and convert to adb args.
        Supported formats:
        - /adb <raw adb args>
        - /shell <cmd...>
        - /tap <x> <y>
        - /swipe <x1> <y1> <x2> <y2> [duration_ms]
        - /text <content>
        - /key <keycode>
        - /keyevent <keycode>
        - /am <args...>
        - /input <args...>
        - /pm|wm|dumpsys|getprop|settings|cmd|ime|svc <args...>
        """
        content = (command or "").strip()
        if not content.startswith("/"):
            raise ValueError("命令必须以 / 开头")

        raw = content[1:].strip()
        if not raw:
            raise ValueError("空命令，请输入例如 /shell wm size")

        try:
            tokens = shlex.split(raw)
        except ValueError as e:
            raise ValueError(f"命令解析失败: {e}") from e

        if not tokens:
            raise ValueError("空命令，请输入例如 /shell wm size")

        head = tokens[0].lower()
        tail = tokens[1:]
        shell_heads = {
            "pm",
            "wm",
            "dumpsys",
            "getprop",
            "setprop",
            "settings",
            "cmd",
            "ime",
            "svc",
            "appops",
            "content",
            "device_config",
            "monkey",
            "logcat",
        }

        if head == "adb":
            if not tail:
                raise ValueError("缺少 adb 参数，例如 /adb shell wm size")
            adb_args = tail
        elif head == "shell":
            if not tail:
                raise ValueError("缺少 shell 参数，例如 /shell wm size")
            adb_args = ["shell", *tail]
        elif head == "tap":
            if len(tail) != 2:
                raise ValueError("tap 用法: /tap <x> <y>")
            adb_args = ["shell", "input", "tap", tail[0], tail[1]]
        elif head == "swipe":
            if len(tail) not in (4, 5):
                raise ValueError("swipe 用法: /swipe <x1> <y1> <x2> <y2> [duration_ms]")
            adb_args = ["shell", "input", "swipe", *tail]
        elif head == "text":
            if not tail:
                raise ValueError("text 用法: /text <内容>")
            text_payload = " ".join(tail).replace(" ", "%s")
            adb_args = ["shell", "input", "text", text_payload]
        elif head in ("key", "keyevent"):
            if len(tail) != 1:
                raise ValueError("key 用法: /key <KEYCODE_HOME|3>")
            adb_args = ["shell", "input", "keyevent", tail[0]]
        elif head == "am":
            if not tail:
                raise ValueError("am 用法: /am start -n package/.Activity")
            adb_args = ["shell", "am", *tail]
        elif head == "broadcast":
            if not tail:
                raise ValueError("broadcast 用法: /broadcast -a ACTION ...")
            adb_args = ["shell", "am", "broadcast", *tail]
        elif head == "input":
            if not tail:
                raise ValueError("input 用法: /input keyevent 3")
            adb_args = ["shell", "input", *tail]
        elif head in shell_heads:
            adb_args = ["shell", head, *tail]
        else:
            raise ValueError(
                "不支持的命令。可用前缀: /adb /shell /tap /swipe /text /key /keyevent /am /input /pm /wm /dumpsys /getprop /settings /cmd /ime /svc"
            )

        return adb_args, "adb " + " ".join(adb_args)

    async def execute_adb_chat_command(
        self,
        device_id: str,
        command: str,
        timeout_seconds: int = 20,
    ) -> dict:
        """Execute a slash-style adb command for chat direct mode."""
        if timeout_seconds < 3:
            timeout_seconds = 3
        if timeout_seconds > 120:
            timeout_seconds = 120

        if not device_id:
            return {
                "success": False,
                "message": "缺少设备 ID",
                "command": command,
                "normalized_command": "",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "duration_ms": 0,
                "truncated": False,
            }

        # Use cached device list check to avoid obvious errors.
        if device_id not in self._devices:
            await self.refresh_devices()
        if device_id not in self._devices:
            return {
                "success": False,
                "message": f"设备未连接: {device_id}",
                "command": command,
                "normalized_command": "",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "duration_ms": 0,
                "truncated": False,
            }

        try:
            adb_args, normalized = self._build_adb_args_from_chat_command(command)
        except ValueError as e:
            return {
                "success": False,
                "message": str(e),
                "command": command,
                "normalized_command": "",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "duration_ms": 0,
                "truncated": False,
            }

        loop = asyncio.get_event_loop()

        def run_sync():
            started = time.perf_counter()
            result = subprocess.run(
                ["adb", "-s", device_id, *adb_args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return result, duration_ms

        try:
            result, duration_ms = await loop.run_in_executor(None, run_sync)
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            ok = result.returncode == 0
            return {
                "success": ok,
                "message": "命令执行成功" if ok else "命令执行失败",
                "command": command,
                "normalized_command": normalized,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": duration_ms,
                "truncated": False,
            }
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            return {
                "success": False,
                "message": f"命令执行超时（>{timeout_seconds}s）",
                "command": command,
                "normalized_command": normalized,
                "exit_code": None,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "duration_ms": timeout_seconds * 1000,
                "truncated": False,
            }
        except Exception as e:
            logger.exception("Failed to execute adb chat command")
            return {
                "success": False,
                "message": f"执行异常: {e}",
                "command": command,
                "normalized_command": normalized,
                "exit_code": None,
                "stdout": "",
                "stderr": str(e),
                "duration_ms": 0,
                "truncated": False,
            }

    def set_telegram_bot(self, telegram_bot):
        """Set telegram bot reference for notifications."""
        self._telegram_bot = telegram_bot
        logger.info("Telegram bot reference set for device monitoring")

    async def start_device_monitoring(self):
        """Start monitoring device connections for changes."""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Device monitoring already running")
            return
        
        # Initialize with current devices
        current_devices = await self.refresh_devices()
        self._previous_devices = {device.id for device in current_devices}
        logger.info(f"Starting device monitoring with {len(self._previous_devices)} devices")
        
        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._monitor_device_changes())
    
    async def _monitor_device_changes(self):
        """Background task to monitor device connections/disconnections."""
        logger.info("Device monitoring task started (10s interval)")
        
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                # Get current devices
                current_devices = await self.refresh_devices()
                current_device_ids = {device.id for device in current_devices}
                
                # Detect changes
                connected = current_device_ids - self._previous_devices
                disconnected = self._previous_devices - current_device_ids
                
                # Send notifications for connections
                for device_id in connected:
                    device_info = self._devices.get(device_id)
                    device_name = device_info.name if device_info else device_id
                    
                    message = (
                        f"📱 *Device Connected*\n\n"
                        f"Device: `{device_name}`\n"
                        f"ID: `{device_id}`\n"
                        f"Status: ✅ Online"
                    )
                    logger.info(f"Device connected: {device_id}")
                    
                    if self._telegram_bot:
                        await self._telegram_bot.send_system_notification(message)
                
                # Send notifications for disconnections
                for device_id in disconnected:
                    message = (
                        f"⚠️ *Device Disconnected*\n\n"
                        f"Device: `{device_id}`\n"
                        f"Status: ❌ Offline"
                    )
                    logger.warning(f"Device disconnected: {device_id}")
                    
                    if self._telegram_bot:
                        await self._telegram_bot.send_system_notification(message)
                
                # Update previous state
                self._previous_devices = current_device_ids
                
            except asyncio.CancelledError:
                logger.info("Device monitoring task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in device monitoring: {e}")
                # Continue monitoring despite errors
                await asyncio.sleep(5)


# Global service instance
device_service = DeviceService()
