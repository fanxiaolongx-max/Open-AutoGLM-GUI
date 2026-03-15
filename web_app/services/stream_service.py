# -*- coding: utf-8 -*-
"""
RTSP stream service: pull RTSP on the server, transcode to MJPEG, stream to web.
Supports multiple cameras in a grid; works through Cloudflare tunnel (same-origin).
"""

import asyncio
import logging
from typing import List

from web_app.services.config_storage import config_storage

logger = logging.getLogger(__name__)

CONFIG_KEY = "rtsp_streams"
CONFIG_CATEGORY = "streams"

# Default: 4 slots, first two filled with user's URLs
DEFAULT_STREAMS = [
    {"url": "rtsp://admin:20180825@192.168.100.20:8554/live", "name": "摄像头 1"},
    {"url": "rtsp://admin:20180825@192.168.100.97:8554/live", "name": "摄像头 2"},
    {"url": "", "name": "摄像头 3"},
    {"url": "", "name": "摄像头 4"},
]


def get_stream_config() -> List[dict]:
    """Return list of 4 stream configs { url, name }."""
    raw = config_storage.get(CONFIG_KEY)
    if not raw or not isinstance(raw, list):
        return list(DEFAULT_STREAMS)
    # Ensure exactly 4 slots
    out = []
    for i in range(4):
        if i < len(raw) and isinstance(raw[i], dict):
            out.append({
                "url": (raw[i].get("url") or "").strip(),
                "name": (raw[i].get("name") or f"摄像头 {i + 1}").strip() or f"摄像头 {i + 1}",
            })
        else:
            out.append({"url": "", "name": f"摄像头 {i + 1}"})
    return out


def set_stream_config(streams: List[dict]) -> List[dict]:
    """Save stream config; expects up to 4 items with url and name."""
    normalized = []
    for i in range(4):
        if i < len(streams) and isinstance(streams[i], dict):
            normalized.append({
                "url": (streams[i].get("url") or "").strip(),
                "name": (streams[i].get("name") or f"摄像头 {i + 1}").strip() or f"摄像头 {i + 1}",
            })
        else:
            normalized.append({"url": "", "name": f"摄像头 {i + 1}"})
    config_storage.set(CONFIG_KEY, normalized, CONFIG_CATEGORY)
    return normalized


def _parse_boundary_from_first_chunk(first_chunk: bytes) -> str:
    """Extract multipart boundary from first chunk (e.g. --ffserver or --frame)."""
    if not first_chunk:
        return "ffserver"
    first_line = first_chunk.split(b"\r\n")[0] if b"\r\n" in first_chunk else first_chunk.split(b"\n")[0]
    if first_line.startswith(b"--") and len(first_line) > 2:
        return first_line[2:].decode("ascii", errors="ignore").strip() or "ffserver"
    return "ffserver"


async def stream_rtsp_as_mjpeg(stream_index: int):
    """
    Async generator: pull RTSP at stream_index, run ffmpeg to MJPEG, yield bytes.
    On generator close (e.g. client disconnect), ffmpeg is terminated.
    """
    config = get_stream_config()
    if stream_index < 0 or stream_index >= 4:
        return
    entry = config[stream_index]
    url = entry.get("url") or ""
    if not url or not url.startswith("rtsp://"):
        return

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", url,
            "-f", "mpjpeg",
            "-q:v", "8",
            "-r", "8",
            "-an",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Read first chunk to get boundary and initial data
        first = await asyncio.wait_for(proc.stdout.read(4096), timeout=15.0)
        if not first:
            return
        boundary = _parse_boundary_from_first_chunk(first)
        media_type = f'multipart/x-mixed-replace; boundary={boundary}'
        yield (first, media_type)
        while True:
            chunk = await proc.stdout.read(8192)
            if not chunk:
                break
            yield (chunk, None)
    except asyncio.TimeoutError:
        logger.warning(f"Stream {stream_index}: ffmpeg first read timeout")
    except FileNotFoundError:
        logger.error("ffmpeg not found; install ffmpeg to use RTSP streams")
    except Exception as e:
        logger.exception(f"Stream {stream_index} error: {e}")
    finally:
        if proc is not None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
