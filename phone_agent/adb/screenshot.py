"""Screenshot utilities for capturing Android device screen."""

import base64
import os
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Tuple

from PIL import Image

# Global lock to prevent concurrent screenshot operations
# This avoids conflicts between preview and task execution screenshots
_screenshot_lock = threading.Lock()

# Verbose logging flag
_verbose = False


def set_screenshot_verbose(verbose: bool) -> None:
    """Enable or disable verbose logging for screenshot operations."""
    global _verbose
    _verbose = verbose


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

    Uses 'adb exec-out screencap -p' to output PNG directly to stdout,
    avoiding temp file conflicts between preview and task execution.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        timeout: Timeout in seconds for screenshot operations.

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        If the screenshot fails (e.g., on sensitive screens like payment pages),
        a black fallback image is returned with is_sensitive=True.
    """
    adb_prefix = _get_adb_prefix(device_id)
    start_time = time.time()

    if _verbose:
        print(f"[Screenshot] Starting capture for device: {device_id or 'default'}")

    # Use lock to prevent concurrent screenshot operations
    with _screenshot_lock:
        if _verbose:
            print(f"[Screenshot] Acquired lock, executing screencap...")

        try:
            # Method 1: Use exec-out to get PNG directly (no temp file on device)
            # This avoids file conflicts between concurrent screenshot operations
            result = subprocess.run(
                adb_prefix + ["exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='ignore')
                if _verbose:
                    print(f"[Screenshot] exec-out failed: {stderr}")
                # Fallback to traditional method
                return _get_screenshot_traditional(device_id, timeout)

            png_data = result.stdout

            # Check if we got valid data
            if len(png_data) < 1000:
                if _verbose:
                    print(f"[Screenshot] Data too small ({len(png_data)} bytes), likely failed")
                return _create_fallback_screenshot(is_sensitive=True)

            # Check PNG magic bytes
            if not png_data.startswith(b'\x89PNG'):
                if _verbose:
                    print(f"[Screenshot] Invalid PNG header, trying traditional method")
                return _get_screenshot_traditional(device_id, timeout)

            # Parse the image
            img = Image.open(BytesIO(png_data))
            width, height = img.size

            # Re-encode to ensure clean PNG
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

            elapsed = time.time() - start_time
            if _verbose:
                print(f"[Screenshot] Success: {width}x{height}, {len(png_data)} bytes, {elapsed:.2f}s")

            return Screenshot(
                base64_data=base64_data, width=width, height=height, is_sensitive=False
            )

        except subprocess.TimeoutExpired:
            if _verbose:
                print(f"[Screenshot] Timeout after {timeout}s")
            return _create_fallback_screenshot(is_sensitive=False)

        except Exception as e:
            error_str = str(e)
            # Only log unexpected errors
            if "cannot identify" not in error_str and "truncated" not in error_str and "broken" not in error_str:
                print(f"[Screenshot] Error: {e}")
            elif _verbose:
                print(f"[Screenshot] Image decode error: {e}")
            return _create_fallback_screenshot(is_sensitive=False)


def _get_screenshot_traditional(device_id: str | None = None, timeout: int = 10) -> Screenshot:
    """
    Fallback screenshot method using temp file on device.
    Used when exec-out doesn't work properly.
    """
    temp_path = os.path.join(tempfile.gettempdir(), f"screenshot_{uuid.uuid4()}.png")
    adb_prefix = _get_adb_prefix(device_id)
    # Use unique temp file name on device to avoid conflicts
    device_temp = f"/sdcard/tmp_{uuid.uuid4().hex[:8]}.png"

    if _verbose:
        print(f"[Screenshot] Using traditional method with {device_temp}")

    try:
        # Execute screenshot command
        result = subprocess.run(
            adb_prefix + ["shell", "screencap", "-p", device_temp],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Check for screenshot failure (sensitive screen)
        output = result.stdout + result.stderr
        if "Status: -1" in output or "Failed" in output:
            if _verbose:
                print(f"[Screenshot] Sensitive screen detected")
            return _create_fallback_screenshot(is_sensitive=True)

        # Pull screenshot to local temp path
        subprocess.run(
            adb_prefix + ["pull", device_temp, temp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Clean up device temp file
        subprocess.run(
            adb_prefix + ["shell", "rm", "-f", device_temp],
            capture_output=True,
            timeout=3,
        )

        if not os.path.exists(temp_path):
            if _verbose:
                print(f"[Screenshot] Failed to pull file")
            return _create_fallback_screenshot(is_sensitive=False)

        # Check file size
        file_size = os.path.getsize(temp_path)
        if file_size < 1000:
            os.remove(temp_path)
            if _verbose:
                print(f"[Screenshot] File too small: {file_size} bytes")
            return _create_fallback_screenshot(is_sensitive=True)

        # Read and encode image
        img = Image.open(temp_path)
        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Cleanup local temp
        os.remove(temp_path)

        if _verbose:
            print(f"[Screenshot] Traditional method success: {width}x{height}")

        return Screenshot(
            base64_data=base64_data, width=width, height=height, is_sensitive=False
        )

    except Exception as e:
        error_str = str(e)
        if "cannot identify" not in error_str and "truncated" not in error_str:
            print(f"[Screenshot] Traditional method error: {e}")
        # Clean up temp files
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        # Try to clean device temp
        try:
            subprocess.run(
                adb_prefix + ["shell", "rm", "-f", device_temp],
                capture_output=True,
                timeout=3,
            )
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

    if _verbose:
        print(f"[Screenshot] Created fallback image (sensitive={is_sensitive})")

    return Screenshot(
        base64_data=base64_data,
        width=default_width,
        height=default_height,
        is_sensitive=is_sensitive,
    )
