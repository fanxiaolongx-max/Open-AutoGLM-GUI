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

from phone_agent.config.screenshot import SCREENSHOT_CONFIG

# Global lock to prevent concurrent screenshot operations
# This avoids conflicts between preview and task execution screenshots
_screenshot_lock = threading.Lock()

# Verbose logging flag
_verbose = False


def set_screenshot_verbose(verbose: bool) -> None:
    """Enable or disable verbose logging for screenshot operations."""
    global _verbose
    _verbose = verbose


def _compress_image(img: Image.Image) -> tuple[str, int, int]:
    """
    Compress an image for API transmission.
    
    - Resizes if larger than configured max dimension
    - Converts to JPEG with configured quality
    - Returns base64 encoded data and dimensions
    """
    width, height = img.size
    original_size = width * height
    
    # Resize if too large (use configured max dimension)
    max_dimension = SCREENSHOT_CONFIG.max_image_dimension
    if width > max_dimension or height > max_dimension:
        ratio = min(max_dimension / width, max_dimension / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        width, height = new_width, new_height
        if _verbose:
            print(f"[Screenshot] Resized from {original_size} to {width}x{height}")
    
    # Convert RGBA to RGB (JPEG doesn't support alpha channel)
    if img.mode == 'RGBA':
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Compress as JPEG (use configured quality)
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=SCREENSHOT_CONFIG.jpeg_quality, optimize=True)
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    if _verbose:
        compressed_size = len(buffered.getvalue())
        print(f"[Screenshot] Compressed to JPEG: {compressed_size / 1024:.1f}KB")
    
    return base64_data, width, height


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
            orig_width, orig_height = img.size

            # Compress image for API transmission
            base64_data, width, height = _compress_image(img)

            elapsed = time.time() - start_time
            if _verbose:
                print(f"[Screenshot] Success: {orig_width}x{orig_height} -> {width}x{height}, {elapsed:.2f}s")

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
        orig_width, orig_height = img.size

        # Compress image for API transmission
        base64_data, width, height = _compress_image(img)

        # Cleanup local temp
        os.remove(temp_path)

        if _verbose:
            print(f"[Screenshot] Traditional method success: {orig_width}x{orig_height} -> {width}x{height}")

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
