"""Screenshot utilities for capturing iOS device screen."""

import base64
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from phone_agent.config.screenshot import SCREENSHOT_CONFIG


def _compress_image(img: Image.Image) -> tuple[str, int, int]:
    """
    Compress an image for API transmission.
    
    - Resizes if larger than configured max dimension
    - Converts to JPEG with configured quality
    - Returns base64 encoded data and dimensions
    """
    width, height = img.size
    
    # Resize if too large (use configured max dimension)
    max_dimension = SCREENSHOT_CONFIG.max_image_dimension
    if width > max_dimension or height > max_dimension:
        ratio = min(max_dimension / width, max_dimension / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        width, height = new_width, new_height
    
    # Convert RGBA to RGB (JPEG doesn't support alpha channel)
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Compress as JPEG (use configured quality)
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=SCREENSHOT_CONFIG.jpeg_quality, optimize=True)
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return base64_data, width, height


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False


def get_screenshot(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    device_id: str | None = None,
    timeout: int = 10,
) -> Screenshot:
    """
    Capture a screenshot from the connected iOS device.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        device_id: Optional device UDID (for idevicescreenshot fallback).
        timeout: Timeout in seconds for screenshot operations.

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        Tries WebDriverAgent first, falls back to idevicescreenshot if available.
        If both fail, returns a black fallback image.
    """
    # Try WebDriverAgent first (preferred method)
    screenshot = _get_screenshot_wda(wda_url, session_id, timeout)
    if screenshot:
        return screenshot

    # Fallback to idevicescreenshot
    screenshot = _get_screenshot_idevice(device_id, timeout)
    if screenshot:
        return screenshot

    # Return fallback black image
    return _create_fallback_screenshot(is_sensitive=False)


def _get_screenshot_wda(
    wda_url: str, session_id: str | None, timeout: int
) -> Screenshot | None:
    """
    Capture screenshot using WebDriverAgent.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        timeout: Timeout in seconds.

    Returns:
        Screenshot object or None if failed.
    """
    try:
        import requests

        url = f"{wda_url.rstrip('/')}/screenshot"

        response = requests.get(url, timeout=timeout, verify=False)

        if response.status_code == 200:
            data = response.json()
            base64_data = data.get("value", "")

            if base64_data:
                # Decode and compress image
                img_data = base64.b64decode(base64_data)
                img = Image.open(BytesIO(img_data))
                compressed_data, width, height = _compress_image(img)

                return Screenshot(
                    base64_data=compressed_data,
                    width=width,
                    height=height,
                    is_sensitive=False,
                )

    except ImportError:
        print("Note: requests library not installed. Install: pip install requests")
    except Exception as e:
        print(f"WDA screenshot failed: {e}")

    return None


def _get_screenshot_idevice(
    device_id: str | None, timeout: int
) -> Screenshot | None:
    """
    Capture screenshot using idevicescreenshot (libimobiledevice).

    Args:
        device_id: Optional device UDID.
        timeout: Timeout in seconds.

    Returns:
        Screenshot object or None if failed.
    """
    try:
        temp_path = os.path.join(
            tempfile.gettempdir(), f"ios_screenshot_{uuid.uuid4()}.png"
        )

        cmd = ["idevicescreenshot"]
        if device_id:
            cmd.extend(["-u", device_id])
        cmd.append(temp_path)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )

        if result.returncode == 0 and os.path.exists(temp_path):
            # Read and compress image
            img = Image.open(temp_path)
            base64_data, width, height = _compress_image(img)

            # Cleanup
            os.remove(temp_path)

            return Screenshot(
                base64_data=base64_data, width=width, height=height, is_sensitive=False
            )

    except FileNotFoundError:
        print(
            "Note: idevicescreenshot not found. Install: brew install libimobiledevice"
        )
    except Exception as e:
        print(f"idevicescreenshot failed: {e}")

    return None


def _create_fallback_screenshot(is_sensitive: bool) -> Screenshot:
    """
    Create a black fallback image when screenshot fails.

    Args:
        is_sensitive: Whether the failure was due to sensitive content.

    Returns:
        Screenshot object with black image.
    """
    # Default iPhone screen size (iPhone 14 Pro)
    default_width, default_height = 1179, 2556

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


def save_screenshot(
    screenshot: Screenshot,
    file_path: str,
) -> bool:
    """
    Save a screenshot to a file.

    Args:
        screenshot: Screenshot object.
        file_path: Path to save the screenshot.

    Returns:
        True if successful, False otherwise.
    """
    try:
        img_data = base64.b64decode(screenshot.base64_data)
        img = Image.open(BytesIO(img_data))
        img.save(file_path)
        return True
    except Exception as e:
        print(f"Error saving screenshot: {e}")
        return False


def get_screenshot_png(
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
    device_id: str | None = None,
) -> bytes | None:
    """
    Get screenshot as PNG bytes.

    Args:
        wda_url: WebDriverAgent URL.
        session_id: Optional WDA session ID.
        device_id: Optional device UDID.

    Returns:
        PNG bytes or None if failed.
    """
    screenshot = get_screenshot(wda_url, session_id, device_id)

    try:
        return base64.b64decode(screenshot.base64_data)
    except Exception:
        return None
