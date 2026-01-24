# -*- coding: utf-8 -*-
"""
Device service for managing connected devices.
Uses phone_agent.device_factory for device management (same as GUI).
"""

import asyncio
import base64
import json
import logging
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
        self._pins_file = Path.home() / ".autoglm" / "device_pins.json"
        self._load_pins()
        # Initialize device factory with ADB
        set_device_type(DeviceType.ADB)

    def _load_pins(self):
        """Load device PINs from config."""
        if self._pins_file.exists():
            try:
                self._device_pins = json.loads(
                    self._pins_file.read_text(encoding="utf-8")
                )
            except Exception:
                self._device_pins = {}

    def _save_pins(self):
        """Save device PINs to config."""
        self._pins_file.parent.mkdir(parents=True, exist_ok=True)
        self._pins_file.write_text(
            json.dumps(self._device_pins, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

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
        self._devices.clear()

        try:
            # Use phone_agent's device factory (same as GUI)
            factory = get_device_factory()
            device_list = factory.list_devices()

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
                self._devices[device.device_id] = device_info

            logger.info(f"Found {len(devices)} device(s)")

        except Exception as e:
            logger.error(f"Error refreshing devices: {e}")

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


# Global service instance
device_service = DeviceService()
