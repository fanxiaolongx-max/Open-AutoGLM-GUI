"""Input utilities for Android device text input."""

import base64
import subprocess
from typing import Optional


def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        - For ASCII text: uses 'adb shell input text' command
        - For non-ASCII (Chinese, etc): uses ADB Keyboard broadcast with base64
    """
    if not text:
        return

    adb_prefix = _get_adb_prefix(device_id)

    # Verify ADB keyboard is active before typing
    if not _is_adb_keyboard_active(device_id):
        subprocess.run(
            adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
            capture_output=True,
            text=True,
        )

    # Check if text contains non-ASCII characters (Chinese, etc.)
    if _contains_non_ascii(text):
        # Use ADB Keyboard broadcast for non-ASCII text
        _type_text_broadcast(text, adb_prefix)
    else:
        # Use adb shell input text for ASCII text
        _type_text_input(text, adb_prefix)


def _contains_non_ascii(text: str) -> bool:
    """Check if text contains non-ASCII characters."""
    try:
        text.encode('ascii')
        return False
    except UnicodeEncodeError:
        return True


def _type_text_input(text: str, adb_prefix: list) -> None:
    """Type ASCII text using adb shell input text command."""
    escaped_text = _escape_for_input_text(text)
    subprocess.run(
        adb_prefix + ["shell", "input", "text", escaped_text],
        capture_output=True,
        text=True,
    )


def _type_text_broadcast(text: str, adb_prefix: list) -> None:
    """Type text using ADB Keyboard broadcast (supports Chinese and Unicode)."""
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    subprocess.run(
        adb_prefix + [
            "shell", "am", "broadcast",
            "-a", "ADB_INPUT_B64",
            "--es", "msg", encoded_text,
        ],
        capture_output=True,
        text=True,
    )


def _is_adb_keyboard_active(device_id: str | None = None) -> bool:
    """
    Check if ADB Keyboard is currently the active input method.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        True if ADB Keyboard is active, False otherwise.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Check current IME
    result = subprocess.run(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
    )
    current_ime = (result.stdout + result.stderr).strip()

    return "com.android.adbkeyboard/.AdbIME" in current_ime


def _escape_for_input_text(text: str) -> str:
    """
    Escape text for use with 'adb shell input text' command.

    Args:
        text: The text to escape.

    Returns:
        Escaped text safe for adb shell input text.
    """
    # Characters that need special handling for adb shell input text
    # Space -> %s
    # Special shell characters need escaping
    result = text
    result = result.replace(" ", "%s")
    result = result.replace("&", "\\&")
    result = result.replace("<", "\\<")
    result = result.replace(">", "\\>")
    result = result.replace("(", "\\(")
    result = result.replace(")", "\\)")
    result = result.replace("|", "\\|")
    result = result.replace(";", "\\;")
    result = result.replace("*", "\\*")
    result = result.replace("?", "\\?")
    result = result.replace("$", "\\$")
    result = result.replace('"', '\\"')
    result = result.replace("'", "\\'")
    result = result.replace("`", "\\`")
    result = result.replace("\\", "\\\\")
    return result


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
