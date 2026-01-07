"""Screenshot utilities for capturing Android device screen."""

import base64
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Tuple

from PIL import Image


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False


def get_screenshot(device_id: str | None = None, timeout: int = 10) -> Screenshot:
    """
    Capture a screenshot from the connected Android device.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        timeout: Timeout in seconds for screenshot operations.

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        If the screenshot fails (e.g., on sensitive screens like payment pages),
        a black fallback image is returned with is_sensitive=True.
    """
    temp_path = os.path.join(tempfile.gettempdir(), f"screenshot_{uuid.uuid4()}.png")
    adb_prefix = _get_adb_prefix(device_id)

    try:
        # Execute screenshot command
        result = subprocess.run(
            adb_prefix + ["shell", "screencap", "-p", "/sdcard/tmp.png"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Check for screenshot failure (sensitive screen)
        output = result.stdout + result.stderr
        if "Status: -1" in output or "Failed" in output:
            return _create_fallback_screenshot(is_sensitive=True)

        # Pull screenshot to local temp path
        subprocess.run(
            adb_prefix + ["pull", "/sdcard/tmp.png", temp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if not os.path.exists(temp_path):
            return _create_fallback_screenshot(is_sensitive=False)

        # 检查文件大小，空文件或过小的文件表示截图失败
        file_size = os.path.getsize(temp_path)
        if file_size < 1000:  # 小于1KB的文件通常是无效的
            os.remove(temp_path)
            return _create_fallback_screenshot(is_sensitive=True)

        # Read and encode image
        img = Image.open(temp_path)
        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Cleanup
        os.remove(temp_path)

        return Screenshot(
            base64_data=base64_data, width=width, height=height, is_sensitive=False
        )

    except Exception as e:
        # 静默处理常见的截图失败，避免刷屏
        error_str = str(e)
        if "cannot identify" not in error_str and "truncated" not in error_str:
            print(f"Screenshot error: {e}")
        # 清理临时文件
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return _create_fallback_screenshot(is_sensitive=False)


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def _create_fallback_screenshot(is_sensitive: bool) -> Screenshot:
    """Create a black fallback image when screenshot fails."""
    default_width, default_height = 1080, 2400

    black_img = Image.new("RGB", (default_width, default_height), color="black")
    buffered = BytesIO()
    black_img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return Screenshot(
        base64_data=base64_data,
        width=default_width,
        height=default_height,
        is_sensitive=is_sensitive,
    )
