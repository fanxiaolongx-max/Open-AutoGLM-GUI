"""Input utilities for Android device text input."""

import base64
import subprocess
from typing import Optional


def is_adb_keyboard_enabled(device_id: str | None = None) -> bool:
    """
    Check if ADB Keyboard is currently set as the default input method.

    Uses standard adb command to check the current IME setting.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        True if ADB Keyboard is enabled, False otherwise.
    """
    adb_prefix = _get_adb_prefix(device_id)

    try:
        result = subprocess.run(
            adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        current_ime = result.stdout.strip()
        is_enabled = "com.android.adbkeyboard/.AdbIME" in current_ime
        print(f"[ADB Input] Current IME: {current_ime}, ADB Keyboard enabled: {is_enabled}")
        return is_enabled
    except Exception as e:
        print(f"[ADB Input] Failed to check IME: {e}")
        return False


def type_text(text: str, device_id: str | None = None) -> bool:
    """
    Type text into the currently focused input field.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        True if text was typed successfully, False if ADB Keyboard is not enabled.

    Note:
        This function always checks if ADB Keyboard is enabled using standard adb command.
        If enabled, uses ADB broadcast method to input text.
        If not enabled, returns False immediately without attempting input.
    """
    if not text:
        return True

    adb_prefix = _get_adb_prefix(device_id)

    # Check if ADB Keyboard is enabled using standard adb command
    if not is_adb_keyboard_enabled(device_id):
        print("[ADB Input] ADB Keyboard is not enabled, cannot input text")
        return False

    # ADB Keyboard is enabled, use broadcast method
    print(f"[ADB Input] ADB Keyboard enabled, using broadcast method")
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    cmd = adb_prefix + [
        "shell", "am", "broadcast",
        "-a", "ADB_INPUT_B64",
        "--es", "msg", encoded_text,
    ]
    print(f"[ADB Input] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"[ADB Input] Broadcast result: {result.stdout.strip()}")
    return True


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Uses key events to select all and delete text.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Select all text (Ctrl+A equivalent: KEYCODE_MOVE_HOME with SHIFT to select all)
    # Then delete with DEL key
    # Method: Use multiple DEL keypresses and backspace to clear
    # First try to select all using KEYCODE_MOVE_END with shift, then KEYCODE_MOVE_HOME with shift
    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_MOVE_END"],
        capture_output=True,
        text=True,
    )
    # Send multiple backspaces to clear text (assuming max 200 chars)
    for _ in range(20):
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL"],
            capture_output=True,
            text=True,
        )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Get current IME
    result = subprocess.run(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
    )
    current_ime = (result.stdout + result.stderr).strip()

    # Switch to ADB Keyboard if not already set
    if "com.android.adbkeyboard/.AdbIME" not in current_ime:
        subprocess.run(
            adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
            capture_output=True,
            text=True,
        )

    # Verify the keyboard is now set
    verify_result = subprocess.run(
        adb_prefix + ["shell", "ime", "list", "-s"],
        capture_output=True,
        text=True,
    )
    if "com.android.adbkeyboard/.AdbIME" in verify_result.stdout:
        # ADB Keyboard is available, ensure it's selected
        subprocess.run(
            adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
            capture_output=True,
            text=True,
        )

    return current_ime


def press_enter(device_id: str | None = None) -> None:
    """
    Press Enter key on the device.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)
    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_ENTER"],
        capture_output=True,
        text=True,
    )


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "ime", "set", ime], capture_output=True, text=True
    )


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
