"""ADB utilities for Android device interaction."""

from phone_agent.adb.connection import (
    ADBConnection,
    ConnectionType,
    DeviceInfo,
    list_devices,
    quick_connect,
)
from phone_agent.adb.device import (
    back,
    double_tap,
    get_current_app,
    home,
    launch_app,
    long_press,
    swipe,
    tap,
)
from phone_agent.adb.input import (
    clear_text,
    detect_and_set_adb_keyboard,
    is_adb_keyboard_enabled,
    press_enter,
    restore_keyboard,
    type_text,
)
from phone_agent.adb.screenshot import get_screenshot, set_screenshot_verbose
from phone_agent.adb.unlock import (
    ensure_device_unlocked,
    is_device_locked,
    lock_screen,
    set_pin_request_callback,
    unlock_device,
    wake_screen,
)

__all__ = [
    # Screenshot
    "get_screenshot",
    "set_screenshot_verbose",
    # Input
    "type_text",
    "clear_text",
    "detect_and_set_adb_keyboard",
    "is_adb_keyboard_enabled",
    "press_enter",
    "restore_keyboard",
    # Device control
    "get_current_app",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    # Connection management
    "ADBConnection",
    "DeviceInfo",
    "ConnectionType",
    "quick_connect",
    "list_devices",
    # Unlock
    "ensure_device_unlocked",
    "is_device_locked",
    "lock_screen",
    "set_pin_request_callback",
    "unlock_device",
    "wake_screen",
]
