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


# Global service instance
device_service = DeviceService()
