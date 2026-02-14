# -*- coding: utf-8 -*-
"""
Scrcpy streaming service for real-time device screen mirroring and touch control.

Supports three modes (auto-selected in priority order):
1. scrcpy mode (scrcpy-server v3 JAR + ffmpeg): raw H.264 via socket → ffmpeg → rawvideo → PIL JPEG, ~24fps
2. screenrecord mode (adb screenrecord + ffmpeg): true real-time H.264 stream → rawvideo → PIL JPEG, ~24fps
3. screencap mode (adb screencap loop): per-frame screenshots, ~10fps
"""

import asyncio
import io
import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Set

from PIL import Image

logger = logging.getLogger(__name__)

# Locate scrcpy-server v3 JAR (from homebrew scrcpy or manual path)
_scrcpy_server_jar = ""
for candidate in [
    "/opt/homebrew/share/scrcpy/scrcpy-server",
    "/usr/local/share/scrcpy/scrcpy-server",
    "/usr/share/scrcpy/scrcpy-server",
]:
    if os.path.exists(candidate):
        _scrcpy_server_jar = candidate
        break

if _scrcpy_server_jar:
    logger.info(f"scrcpy-server JAR found: {_scrcpy_server_jar}")
else:
    logger.info("scrcpy-server JAR not found (install scrcpy via homebrew)")

# Check if ffmpeg is available
_ffmpeg_available = bool(shutil.which("ffmpeg"))
if _ffmpeg_available:
    logger.info("ffmpeg found, H.264 decoding available")
else:
    logger.info("ffmpeg not found, will use screencap fallback")

try:
    _scrcpy_first_frame_timeout = float(os.getenv("SCRCPY_FIRST_FRAME_TIMEOUT", "40"))
except ValueError:
    _scrcpy_first_frame_timeout = 40.0
if _scrcpy_first_frame_timeout < 5:
    _scrcpy_first_frame_timeout = 5.0

try:
    _scrcpy_auto_stop_delay = int(os.getenv("SCRCPY_AUTO_STOP_DELAY", "0"))
except ValueError:
    _scrcpy_auto_stop_delay = 0
if _scrcpy_auto_stop_delay < 0:
    _scrcpy_auto_stop_delay = 0

_scrcpy_auto_nudge_on_start = os.getenv("SCRCPY_AUTO_NUDGE_ON_START", "0") == "1"
_scrcpy_auto_nudge_emulator_only = os.getenv("SCRCPY_AUTO_NUDGE_EMULATOR_ONLY", "1") == "1"
try:
    _scrcpy_auto_nudge_delay_ms = int(os.getenv("SCRCPY_AUTO_NUDGE_DELAY_MS", "350"))
except ValueError:
    _scrcpy_auto_nudge_delay_ms = 350
if _scrcpy_auto_nudge_delay_ms < 0:
    _scrcpy_auto_nudge_delay_ms = 0

_scrcpy_auto_unlock_on_start = os.getenv("SCRCPY_AUTO_UNLOCK_ON_START", "1") == "1"

# Main event loop reference for thread-safe scheduling
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_scrcpy_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop for thread-safe operations."""
    global _main_loop
    _main_loop = loop


@dataclass
class ScrcpySession:
    """Represents a streaming session for a device."""
    device_id: str
    is_streaming: bool = False
    is_scrcpy: bool = False
    stream_mode: str = ""  # "scrcpy", "screenrecord", "screencap"
    last_frame: Optional[bytes] = None  # Latest JPEG frame
    connected_websockets: Set = field(default_factory=set)
    screen_width: int = 0
    screen_height: int = 0
    frame_rate: int = 15
    client: Optional[object] = None  # unused, kept for compatibility
    _fallback_task: Optional[asyncio.Task] = None
    _client_thread: Optional[threading.Thread] = None
    _stop_event: Optional[threading.Event] = None
    _auto_stop_task: Optional[asyncio.Task] = None
    _adb_proc: Optional[subprocess.Popen] = None
    _ffmpeg_proc: Optional[subprocess.Popen] = None
    _server_proc: Optional[subprocess.Popen] = None
    _video_socket: Optional[object] = None
    _scrcpy_scid: Optional[str] = None
    _local_port: int = 0


class ScrcpyService:
    """Manages streaming sessions for all devices."""

    _next_port = 27183  # Starting port for adb forward

    def __init__(self):
        self._sessions: dict[str, ScrcpySession] = {}

    def get_session(self, device_id: str) -> Optional[ScrcpySession]:
        """Get existing session for a device."""
        return self._sessions.get(device_id)

    def get_or_create_session(self, device_id: str) -> ScrcpySession:
        """Get or create a session for a device."""
        if device_id not in self._sessions:
            self._sessions[device_id] = ScrcpySession(device_id=device_id)
        return self._sessions[device_id]

    def _alloc_port(self) -> int:
        port = ScrcpyService._next_port
        ScrcpyService._next_port += 1
        return port

    @staticmethod
    def _is_emulator_device(device_id: str, session: Optional[ScrcpySession] = None) -> bool:
        text = (device_id or "").lower()
        if text.startswith("emulator-") or "sdk_gphone" in text:
            return True
        if session and session.screen_width > 0 and session.screen_height > 0:
            # Emulator streams are commonly reported with small scaled dimensions from header meta.
            if session.screen_width <= 600 and session.screen_height <= 1200:
                return True
        return False

    def _schedule_start_nudge(self, device_id: str, session: ScrcpySession):
        """Issue a tiny left-right swipe after stream start to trigger encoder output."""
        if not _scrcpy_auto_nudge_on_start:
            return
        if _scrcpy_auto_nudge_emulator_only and not self._is_emulator_device(device_id, session):
            return
        if session.screen_width <= 0 or session.screen_height <= 0:
            return

        w = int(session.screen_width)
        h = int(session.screen_height)
        delay_s = _scrcpy_auto_nudge_delay_ms / 1000.0

        def _run():
            try:
                if delay_s > 0:
                    time.sleep(delay_s)
                # Keep movement very small to minimize side effects.
                y = max(1, min(h - 2, int(h * 0.55)))
                dx = max(12, min(64, int(w * 0.05)))
                x_mid = w // 2
                x1 = max(1, min(w - 2, x_mid - dx))
                x2 = max(1, min(w - 2, x_mid + dx))
                for sx, ex in ((x1, x2), (x2, x1)):
                    result = subprocess.run(
                        ["adb", "-s", device_id, "shell", "input", "swipe",
                         str(sx), str(y), str(ex), str(y), "120"],
                        capture_output=True, timeout=3
                    )
                    if result.returncode != 0:
                        logger.warning(
                            f"auto-nudge adb failed {device_id}: "
                            f"stderr={result.stderr.decode('utf-8', errors='replace').strip()}"
                        )
                        break
            except Exception as e:
                logger.warning(f"auto-nudge failed for {device_id}: {e}")

        threading.Thread(target=_run, daemon=True, name=f"scrcpy-nudge-{device_id}").start()

    async def _auto_unlock_if_needed(self, device_id: str):
        """Auto-unlock device when preview stream is starting (if currently locked)."""
        if not _scrcpy_auto_unlock_on_start:
            return
        try:
            from web_app.services.device_service import device_service

            # Device cache may be stale if just connected.
            if not device_service.get_device(device_id):
                await device_service.refresh_devices()

            is_locked = await device_service.is_screen_locked(device_id)
            if not is_locked:
                return

            logger.info(f"scrcpy auto-unlock: device {device_id} is locked, trying unlock")
            max_attempts = 3  # initial + 2 retries
            for attempt in range(1, max_attempts + 1):
                unlocked = await device_service.unlock_device(device_id)
                if unlocked:
                    logger.info(
                        f"scrcpy auto-unlock: device {device_id} unlocked"
                        + (f" (attempt {attempt})" if attempt > 1 else "")
                    )
                    break

                if attempt < max_attempts:
                    logger.warning(
                        f"scrcpy auto-unlock failed for {device_id} "
                        f"(attempt {attempt}/{max_attempts}), retrying..."
                    )
                    await asyncio.sleep(0.8)
                else:
                    logger.warning(
                        f"scrcpy auto-unlock failed for {device_id} after {max_attempts} attempts, "
                        "continue starting stream"
                    )
        except Exception as e:
            logger.warning(f"scrcpy auto-unlock error for {device_id}: {e}")

    def _schedule_auto_unlock(self, device_id: str):
        """Schedule auto-unlock asynchronously after stream pipeline is up."""
        if not _scrcpy_auto_unlock_on_start:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        logger.info(f"[AUTO-UNLOCK#SEQ] stream pipeline started, scheduling auto-unlock for {device_id} 🔒")
        loop.create_task(self._auto_unlock_if_needed(device_id))

    async def start_stream(self, device_id: str, max_size: int = 960,
                           bit_rate: int = 4_000_000, frame_rate: int = 24,
                           restart: bool = False) -> dict:
        """
        Start streaming for a device.
        Tries scrcpy → screenrecord+ffmpeg → screencap in priority order.
        """
        session = self.get_or_create_session(device_id)

        if session.is_streaming and restart:
            try:
                await self.stop_stream(device_id)
            except Exception as e:
                # ADB may be temporarily busy; continue and try to start a fresh stream.
                logger.warning(f"restart stop_stream failed for {device_id}: {e}")
            session = self.get_or_create_session(device_id)

        if session.is_streaming:
            return {
                "status": "already_running",
                "mode": session.stream_mode,
                "width": session.screen_width,
                "height": session.screen_height,
                "fps": session.frame_rate,
            }

        # Cancel any pending auto-stop
        if session._auto_stop_task and not session._auto_stop_task.done():
            session._auto_stop_task.cancel()
            session._auto_stop_task = None

        # 1. Try scrcpy-server v3 + ffmpeg (best quality, supports Android 15)
        if _scrcpy_server_jar and _ffmpeg_available:
            # Retry order:
            # 1) requested profile
            # 2) same profile restart once (helps transient encoder/socket hiccups)
            # 3) conservative fallback (prefer frame_meta=False)
            frame_meta_default = os.getenv("SCRCPY_FRAME_META", "1") == "1"
            scrcpy_profiles = [
                ("requested", max_size, bit_rate, frame_rate, frame_meta_default),
                ("same-retry", max_size, bit_rate, frame_rate, frame_meta_default),
            ]
            low_profile = (
                min(max_size, 540),
                min(bit_rate, 2_000_000),
                min(frame_rate, 15),
            )
            if low_profile != (max_size, bit_rate, frame_rate):
                # On retry prefer no frame-meta path to avoid device-specific frame-meta corruption.
                scrcpy_profiles.append(("low-retry", low_profile[0], low_profile[1], low_profile[2], False))
            elif frame_meta_default:
                # Same profile: still retry once with frame-meta disabled.
                scrcpy_profiles.append(("no-meta-retry", max_size, bit_rate, frame_rate, False))

            scrcpy_errors = []
            for idx, (tag, size_i, br_i, fps_i, frame_meta_i) in enumerate(scrcpy_profiles, start=1):
                if tag != "requested":
                    logger.warning(
                        f"scrcpy retry for {device_id}: profile={tag}, max_size={size_i}, "
                        f"frame_rate={fps_i}, bit_rate={br_i}, frame_meta={frame_meta_i}"
                    )
                try:
                    result = await self._start_scrcpy_stream(
                        session, device_id, size_i, br_i, fps_i, frame_meta=frame_meta_i
                    )
                    self._schedule_start_nudge(device_id, session)
                    return result
                except Exception as e:
                    scrcpy_errors.append((tag, size_i, br_i, fps_i, frame_meta_i, e))
                    logger.warning(
                        f"scrcpy attempt {idx}/{len(scrcpy_profiles)} failed for {device_id} "
                        f"(profile={tag}, max_size={size_i}, frame_rate={fps_i}, "
                        f"bit_rate={br_i}, frame_meta={frame_meta_i}): {e}"
                    )
                    # Ensure any partial resources from this attempt are cleaned up before retry/fallback.
                    try:
                        if session._stop_event:
                            session._stop_event.set()
                        self._cleanup_scrcpy(session, device_id)
                    except Exception as cleanup_err:
                        logger.debug(f"scrcpy cleanup after failed attempt error for {device_id}: {cleanup_err}")
                    session.is_streaming = False
                    session.is_scrcpy = False
                    session.stream_mode = ""
                    session.last_frame = None
                    if idx < len(scrcpy_profiles):
                        await asyncio.sleep(0.4)

            if scrcpy_errors:
                logger.warning(f"scrcpy stream failed for {device_id}: {scrcpy_errors[-1][5]}")

        # 2. Try screenrecord + ffmpeg
        if _ffmpeg_available:
            try:
                result = await self._start_screenrecord_stream(session, device_id, frame_rate)
                self._schedule_start_nudge(device_id, session)
                return result
            except Exception as e:
                logger.warning(f"screenrecord stream failed for {device_id}: {e}, falling back to screencap")

        # 3. Fall back to screencap loop (always works)
        result = await self._start_screencap_stream(session, device_id, frame_rate)
        self._schedule_start_nudge(device_id, session)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Mode 1: scrcpy-server v3.3.4 JAR + ffmpeg H.264 decode
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_sps_offset(data: bytes) -> int:
        """Find offset of first SPS NAL unit (type 7) with 3/4-byte start code."""
        for off, nal_type in ScrcpyService._scan_nals(data):
            if nal_type == 7:
                return off
        return -1

    @staticmethod
    def _scan_nals(data: bytes) -> list[tuple[int, int]]:
        """Return list of (offset, nal_type) for Annex-B start codes."""
        nals = []
        i = 0
        end = len(data)
        while i + 4 < end:
            if data[i:i+4] == b'\x00\x00\x00\x01':
                if i + 4 < end:
                    nals.append((i, data[i+4] & 0x1F))
                i += 4
                continue
            if data[i:i+3] == b'\x00\x00\x01':
                if i + 3 < end:
                    nals.append((i, data[i+3] & 0x1F))
                i += 3
                continue
            i += 1
        return nals

    class _LenPrefixedToAnnexB:
        """Convert length-prefixed H.264 (AVCC) to Annex-B start codes."""
        def __init__(self):
            self._buf = bytearray()

        def feed(self, data: bytes) -> bytes:
            self._buf.extend(data)
            out = bytearray()
            while True:
                if len(self._buf) < 4:
                    break
                nal_len = int.from_bytes(self._buf[0:4], "big", signed=False)
                if nal_len <= 0 or nal_len > 2_000_000:
                    # Not a valid length-prefixed stream, stop converting.
                    break
                if len(self._buf) < 4 + nal_len:
                    break
                out.extend(b"\x00\x00\x00\x01")
                out.extend(self._buf[4:4 + nal_len])
                del self._buf[:4 + nal_len]
            return bytes(out)

    @staticmethod
    def _analyze_len_prefixed(data: bytes) -> tuple[int, int, bool]:
        """Return (consumed_bytes, nal_count, has_sps) for 4-byte length-prefixed."""
        off = 0
        nals = 0
        has_sps = False
        end = len(data)
        while off + 4 <= end and nals < 10000:
            nal_len = int.from_bytes(data[off:off + 4], "big", signed=False)
            if nal_len <= 0 or nal_len > end - off - 4:
                break
            if off + 4 < end:
                nal_type = data[off + 4] & 0x1F
                if nal_type == 7:
                    has_sps = True
            off += 4 + nal_len
            nals += 1
        return off, nals, has_sps

    @staticmethod
    def _convert_len_prefixed_frame(data: bytes) -> tuple[bytes, int, int]:
        """Convert one complete AVCC-style frame payload to Annex-B."""
        out = bytearray()
        off = 0
        nals = 0
        end = len(data)
        while off + 4 <= end:
            nal_len = int.from_bytes(data[off:off + 4], "big", signed=False)
            if nal_len <= 0 or off + 4 + nal_len > end:
                break
            out.extend(b"\x00\x00\x00\x01")
            out.extend(data[off + 4:off + 4 + nal_len])
            off += 4 + nal_len
            nals += 1
        return bytes(out), nals, off

    @staticmethod
    def _extract_sps_pps_annexb(data: bytes) -> bytes:
        """Extract SPS/PPS NAL units (if present) from Annex-B payload."""
        nals = ScrcpyService._scan_nals(data)
        if not nals:
            return b""
        out = bytearray()
        for i, (off, nal_type) in enumerate(nals):
            if nal_type not in (7, 8):
                continue
            end = nals[i + 1][0] if i + 1 < len(nals) else len(data)
            unit = data[off:end]
            if unit.startswith(b"\x00\x00\x01"):
                unit = b"\x00\x00\x00\x01" + unit[3:]
            out.extend(unit)
        return bytes(out)

    async def _start_scrcpy_stream(self, session: ScrcpySession, device_id: str,
                                    max_size: int, bit_rate: int, frame_rate: int,
                                    frame_meta: Optional[bool] = None) -> dict:
        """
        Deploy scrcpy-server v3 JAR, connect raw H.264 socket, decode via ffmpeg.

        Pipeline: socket → [buffer+SPS-trim] → ffmpeg H.264→rawvideo → PIL JPEG → WebSocket

        Key design decisions:
        - rawvideo output instead of MJPEG: ffmpeg's image2pipe/MJPEG buffers all output
          until stdin EOF, making it unusable for real-time streaming. rawvideo flushes
          each frame immediately.
        - SPS-first trimming: scrcpy-server v3.3.4 emits an orphaned 3-byte PPS NAL before
          the SPS, which corrupts ffmpeg's H.264 extradata in pipe mode. We buffer initial
          data and skip to the first SPS NAL.
        - Initial buffering (~50KB): ensures ffmpeg receives the complete SPS+PPS+IDR
          keyframe in one write, preventing probe failures.
        """
        import re
        import socket as socket_mod

        loop = asyncio.get_event_loop()
        session._stop_event = threading.Event()
        stop_event = session._stop_event
        session.frame_rate = frame_rate
        if frame_meta is None:
            use_frame_meta = os.getenv("SCRCPY_FRAME_META", "1") == "1"
        else:
            use_frame_meta = frame_meta
        # SCID must fit in Java signed 32-bit int (max 0x7FFFFFFF)
        scid = f"{os.getpid() & 0x7FFFFFFF:08x}"
        local_port = self._alloc_port()
        session._scrcpy_scid = scid
        session._local_port = local_port

        # Output scale width for rawvideo frames
        out_width = 360
        out_height = [0]

        def _deploy_and_connect():
            """Push JAR, start server, connect socket (blocking)."""
            # Push server JAR
            subprocess.run(
                ["adb", "-s", device_id, "push", _scrcpy_server_jar,
                 "/data/local/tmp/scrcpy-server.jar"],
                capture_output=True, timeout=10
            )

            # Setup adb forward
            subprocess.run(
                ["adb", "-s", device_id, "forward",
                 f"tcp:{local_port}", f"localabstract:scrcpy_{scid}"],
                capture_output=True, timeout=5
            )

            # Start server process
            server_proc = subprocess.Popen(
                ["adb", "-s", device_id, "shell",
                 "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
                 "app_process", "/", "com.genymobile.scrcpy.Server", "3.3.4",
                 f"scid={scid}",
                 "video=true", "audio=false", "control=false",
                 "video_codec=h264",
                 f"max_size={max_size}",
                 f"max_fps={frame_rate}",
                 f"video_bit_rate={bit_rate}",
                 "tunnel_forward=true",
                 f"send_frame_meta={'true' if use_frame_meta else 'false'}",
                 "log_level=info"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
            # Drain server stdout in background to prevent blocking
            threading.Thread(target=lambda: server_proc.stdout.read(), daemon=True).start()
            time.sleep(2)

            # Connect video socket
            sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
            sock.settimeout(10)
            for attempt in range(30):
                try:
                    sock.connect(("127.0.0.1", local_port))
                    break
                except (ConnectionRefusedError, OSError):
                    time.sleep(0.2)
            else:
                server_proc.terminate()
                raise ConnectionError(f"Failed to connect to scrcpy-server on port {local_port}")

            # Read 69-byte header: [1B dummy] [64B device name] [4B codec]
            header = b''
            while len(header) < 69:
                chunk = sock.recv(69 - len(header))
                if not chunk:
                    raise ConnectionError("Socket closed during handshake")
                header += chunk

            device_name = header[1:65].decode('utf-8', errors='replace').rstrip('\x00')
            codec = header[65:69].decode('ascii', errors='replace')
            logger.info(f"scrcpy v3 connected: device={device_name}, codec={codec}")

            # Some scrcpy versions send 8 bytes of video size right after header.
            # If present, consume them to keep stream aligned.
            try:
                sock.settimeout(0.2)
                peek = sock.recv(8, socket_mod.MSG_PEEK)
                if len(peek) == 8:
                    w = int.from_bytes(peek[0:4], "big", signed=False)
                    h = int.from_bytes(peek[4:8], "big", signed=False)
                    if 100 <= w <= 10000 and 100 <= h <= 10000:
                        sock.recv(8)  # consume
                        logger.info(f"scrcpy header meta: size={w}x{h}")
            except Exception:
                pass
            finally:
                try:
                    sock.settimeout(10)
                except Exception:
                    pass

            return server_proc, sock

        server_proc, video_socket = await loop.run_in_executor(None, _deploy_and_connect)

        session._server_proc = server_proc
        session._video_socket = video_socket
        session.stream_mode = "scrcpy"
        session.is_scrcpy = True
        session.is_streaming = True

        # Get screen size
        w, h = await self._get_screen_size(device_id)
        session.screen_width = w
        session.screen_height = h
        if w > 0 and h > 0:
            out_height[0] = int(h * out_width / w)
            if out_height[0] % 2:
                out_height[0] += 1

        _valid_frame_event = threading.Event()

        def stream_thread():
            """Socket → ffmpeg (rawvideo) → PIL JPEG → WebSocket broadcast."""
            ffmpeg_proc = None
            dump_on_fail = os.getenv("SCRCPY_DUMP_ON_FAIL", "0") == "1"
            dump_hdr = os.getenv("SCRCPY_DUMP_HEADER") == "1"
            raw_dump_buf = bytearray()
            raw_dump_max = 2_000_000
            ffmpeg_in_buf = bytearray()
            ffmpeg_in_max = 4_000_000
            bytes_sent = [0]
            try:
                # Use rawvideo output: only format that flushes in real-time via pipe.
                # MJPEG (image2pipe) buffers all output until stdin EOF.
                vf_scale = (
                    f"scale={out_width}:{out_height[0]}"
                    if out_height[0] > 0 else f"scale={out_width}:-2"
                )
                # Prebuffer to ensure SPS+IDR before starting ffmpeg probe.
                def read_exact(sock, n: int) -> Optional[bytes]:
                    buf = bytearray()
                    while len(buf) < n:
                        try:
                            chunk = sock.recv(n - len(buf))
                            if not chunk:
                                return None
                            buf.extend(chunk)
                        except Exception:
                            return None
                    return bytes(buf)

                prebuf = bytearray()
                prebuf_deadline = time.monotonic() + 8.0
                sps_off = -1
                idr_off = -1
                uses_len_prefixed = False
                len2annex = ScrcpyService._LenPrefixedToAnnexB()
                if not use_frame_meta:
                    while time.monotonic() < prebuf_deadline and len(prebuf) < 400000:
                        try:
                            chunk = video_socket.recv(65536)
                            if not chunk:
                                break
                            prebuf.extend(chunk)
                            if dump_on_fail and len(raw_dump_buf) < raw_dump_max:
                                take = min(raw_dump_max - len(raw_dump_buf), len(chunk))
                                if take > 0:
                                    raw_dump_buf.extend(chunk[:take])
                            if len(prebuf) >= 30000:
                                buf_bytes = bytes(prebuf)
                                nals = ScrcpyService._scan_nals(buf_bytes)
                                sps_off = ScrcpyService._find_sps_offset(buf_bytes)
                                if sps_off >= 0:
                                    for off, nal_type in nals:
                                        if off >= sps_off and nal_type == 5:
                                            idr_off = off
                                            break
                                    if idr_off >= 0:
                                        break
                                else:
                                    consumed, nal_count, has_sps = (
                                        ScrcpyService._analyze_len_prefixed(buf_bytes)
                                    )
                                    if consumed >= int(len(buf_bytes) * 0.6) and nal_count >= 2 and has_sps:
                                        uses_len_prefixed = True
                                        logger.info(
                                            "scrcpy len-prefixed detected: "
                                            f"consumed={consumed} nals={nal_count}"
                                        )
                                        break
                        except Exception:
                            break

                ffmpeg_proc = subprocess.Popen(
                    ["ffmpeg",
                     "-flags", "low_delay",
                     "-probesize", "5000000",
                     "-analyzeduration", "5000000",
                     "-f", "h264", "-i", "pipe:0",
                     "-an",
                     "-vf", vf_scale,
                     "-f", "rawvideo", "-pix_fmt", "rgb24",
                     "-flush_packets", "1",
                     "-threads", "1",
                     "pipe:1"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, bufsize=0
                )
                session._ffmpeg_proc = ffmpeg_proc
                logger.info(
                    f"scrcpy ffmpeg start: {vf_scale} "
                    f"probesize=5000000 analyzeduration=5000000"
                )

                # Parse ffmpeg stderr to detect output dimensions
                stderr_tail = deque(maxlen=50)

                def parse_stderr():
                    try:
                        for line in ffmpeg_proc.stderr:
                            decoded = line.decode('utf-8', errors='replace').strip()
                            if decoded:
                                stderr_tail.append(decoded)
                            if 'Stream #0:0' in decoded and 'Video:' in decoded:
                                m = re.search(r'(\d+)x(\d+)', decoded)
                                if m:
                                    pw, ph = int(m.group(1)), int(m.group(2))
                                    if pw == out_width and out_height[0] == 0:
                                        out_height[0] = ph
                                        logger.info(f"scrcpy ffmpeg output: {pw}x{ph}")
                            if 'error' in decoded.lower() or 'invalid' in decoded.lower():
                                logger.warning(f"scrcpy ffmpeg stderr: {decoded}")
                    except Exception:
                        pass

                threading.Thread(target=parse_stderr, daemon=True,
                                name=f"scrcpy-stderr-{device_id}").start()

                # Feed initial prebuffer immediately.
                if not use_frame_meta and prebuf:
                    if sps_off >= 0:
                        to_feed = bytes(prebuf[sps_off:])
                        logger.info(
                            f"scrcpy initial feed: total={len(prebuf)} sps_off={sps_off} "
                            f"idr_off={idr_off} fed={len(to_feed)}"
                        )
                    elif uses_len_prefixed:
                        converted = len2annex.feed(bytes(prebuf))
                        to_feed = converted
                        logger.warning(
                            f"scrcpy initial feed: len-prefixed converted "
                            f"{len(prebuf)}B -> {len(converted)}B"
                        )
                    else:
                        to_feed = bytes(prebuf)
                        logger.warning(
                            f"scrcpy initial feed fallback: no SPS found in {len(prebuf)} bytes"
                        )
                    try:
                        ffmpeg_proc.stdin.write(to_feed)
                        ffmpeg_proc.stdin.flush()
                        bytes_sent[0] += len(to_feed)
                        if dump_on_fail and len(ffmpeg_in_buf) < ffmpeg_in_max:
                            take = min(ffmpeg_in_max - len(ffmpeg_in_buf), len(to_feed))
                            if take > 0:
                                ffmpeg_in_buf.extend(to_feed[:take])
                    except Exception:
                        pass

                # Feeder thread: video_socket → ffmpeg stdin
                def feed_ffmpeg():
                    nonlocal sps_off
                    try:
                        while not stop_event.is_set():
                            if use_frame_meta:
                                buf = bytearray()
                                last_warn = 0.0
                                hdr_dumped = False
                                frame_debug = os.getenv("SCRCPY_FRAME_DEBUG", "0") == "1"
                                frame_debug_limit = 12
                                frame_count = 0
                                parser_mode = "fixed12"
                                codec_config = b""
                                decode_locked = False
                                seen_sps = False
                                seen_pps = False
                                seen_idr = False
                                last_sync_warn = 0.0

                                def has_start_code(payload: bytes) -> bool:
                                    return payload.startswith(b"\x00\x00\x00\x01") or payload.startswith(b"\x00\x00\x01")

                                def looks_like_h264(payload: bytes) -> bool:
                                    if payload.startswith(b"\x00\x00\x01") or payload.startswith(b"\x00\x00\x00\x01"):
                                        return True
                                    if len(payload) >= 5:
                                        nlen = int.from_bytes(payload[0:4], "big", signed=False)
                                        ntype = payload[4] & 0x1F
                                        if 0 < nlen <= len(payload) - 4 and 1 <= ntype <= 12:
                                            return True
                                    if len(payload) >= 1:
                                        b0 = payload[0]
                                        if (b0 & 0x80) == 0 and 1 <= (b0 & 0x1F) <= 12:
                                            return True
                                    return False

                                def try_parse_frame(b: bytearray) -> tuple[str, Optional[tuple[int, int]]]:
                                    # Find Annex-B start code and infer header length from preceding 4 bytes.
                                    saw_prefix = False
                                    for idx in range(12, len(b) - 4):
                                        if b[idx:idx+3] == b"\x00\x00\x01" or b[idx:idx+4] == b"\x00\x00\x00\x01":
                                            saw_prefix = True
                                            if idx < 4:
                                                continue
                                            size_bytes = b[idx-4:idx]
                                            frame_len = int.from_bytes(size_bytes, "big", signed=False)
                                            if not (0 < frame_len <= 5_000_000):
                                                frame_len = int.from_bytes(size_bytes, "little", signed=False)
                                            if not (0 < frame_len <= 5_000_000):
                                                continue
                                            if len(b) < idx + frame_len:
                                                return "need_more", None
                                            payload = b[idx: idx + frame_len]
                                            if looks_like_h264(payload):
                                                # return payload start and length
                                                return "ok", (idx, frame_len)
                                    if saw_prefix:
                                        return "need_more", None
                                    return "no_frame", None

                                def parse_fixed12(b: bytearray) -> tuple[str, Optional[tuple[int, int]]]:
                                    if len(b) < 12:
                                        return "need_more", None
                                    size_bytes = b[8:12]
                                    len_be = int.from_bytes(size_bytes, "big", signed=False)
                                    len_le = int.from_bytes(size_bytes, "little", signed=False)
                                    frame_len = len_be if 0 < len_be <= 5_000_000 else None
                                    if frame_len is None and 0 < len_le <= 5_000_000:
                                        frame_len = len_le
                                    if frame_len is None:
                                        if frame_debug and frame_count < frame_debug_limit:
                                            logger.warning(
                                                f"scrcpy fixed12 bad header: head={bytes(b[:12]).hex()} "
                                                f"len_be={len_be} len_le={len_le}"
                                            )
                                        return "bad_header", None
                                    if len(b) < 12 + frame_len:
                                        return "need_more", None
                                    return "ok", (12, frame_len)

                                def normalize_frame_payload(frame: bytes) -> tuple[bytes, str]:
                                    if not frame:
                                        return b"", "empty"
                                    if frame.startswith(b"\x00\x00\x01") or frame.startswith(b"\x00\x00\x00\x01"):
                                        return frame, "annexb"
                                    converted, nals, consumed = ScrcpyService._convert_len_prefixed_frame(frame)
                                    if nals > 0 and consumed == len(frame):
                                        return converted, "avcc"
                                    b0 = frame[0]
                                    if (b0 & 0x80) == 0 and 1 <= (b0 & 0x1F) <= 12:
                                        return b"\x00\x00\x00\x01" + frame, "raw_nal"
                                    return b"", "unknown"

                                while not stop_event.is_set():
                                    try:
                                        chunk = video_socket.recv(65536)
                                    except TimeoutError:
                                        continue
                                    except OSError:
                                        break
                                    if not chunk:
                                        break
                                    buf.extend(chunk)
                                    if dump_hdr and not hdr_dumped and len(buf) >= 64:
                                        hex64 = buf[:64].hex()
                                        logger.warning(f"scrcpy frame-meta head(64): {hex64}")
                                        hdr_dumped = True
                                    if dump_on_fail and len(raw_dump_buf) < raw_dump_max:
                                        take = min(raw_dump_max - len(raw_dump_buf), len(chunk))
                                        if take > 0:
                                            raw_dump_buf.extend(chunk[:take])
                                    while True:
                                        if parser_mode == "fixed12":
                                            status, parsed = parse_fixed12(buf)
                                            if status == "need_more":
                                                break
                                            if status != "ok" or not parsed:
                                                parser_mode = "resync"
                                                logger.warning(
                                                    "scrcpy frame-meta fixed12 header invalid, switching to resync"
                                                )
                                                continue
                                        else:
                                            status, parsed = try_parse_frame(buf)
                                            if status == "need_more":
                                                break
                                            if status != "ok" or not parsed:
                                                if len(buf) > 256:
                                                    del buf[0]
                                                    if time.monotonic() - last_warn > 1.0:
                                                        logger.warning("scrcpy frame-meta resync: dropping bytes")
                                                        last_warn = time.monotonic()
                                                break
                                        start, frame_len = parsed
                                        frame = bytes(buf[start: start + frame_len])
                                        del buf[:start + frame_len]

                                        normalized, frame_fmt = normalize_frame_payload(frame)
                                        if not normalized:
                                            if frame_debug and frame_count < frame_debug_limit:
                                                logger.warning(
                                                    f"scrcpy frame[{frame_count}] dropped: "
                                                    f"fmt={frame_fmt} len={len(frame)} head={frame[:16].hex()}"
                                                )
                                            frame_count += 1
                                            continue

                                        nal_types = [t for _, t in ScrcpyService._scan_nals(normalized)]
                                        has_sps = 7 in nal_types
                                        has_pps = 8 in nal_types
                                        has_idr = 5 in nal_types
                                        if has_sps and has_pps:
                                            cfg = ScrcpyService._extract_sps_pps_annexb(normalized)
                                            if cfg:
                                                codec_config = cfg
                                        injected_cfg = False
                                        if has_idr and not has_sps and codec_config:
                                            normalized = codec_config + normalized
                                            injected_cfg = True
                                            nal_types = [t for _, t in ScrcpyService._scan_nals(normalized)]
                                            has_sps = 7 in nal_types
                                            has_pps = 8 in nal_types
                                            has_idr = 5 in nal_types

                                        if sps_off < 0:
                                            sps_off = ScrcpyService._find_sps_offset(normalized)
                                            if sps_off > 0:
                                                normalized = normalized[sps_off:]
                                                nal_types = [t for _, t in ScrcpyService._scan_nals(normalized)]
                                                has_sps = 7 in nal_types
                                                has_pps = 8 in nal_types
                                                has_idr = 5 in nal_types

                                        if not has_start_code(normalized):
                                            if decode_locked:
                                                decode_locked = False
                                                seen_sps = False
                                                seen_pps = False
                                                seen_idr = False
                                                parser_mode = "resync"
                                                codec_config = b""
                                                logger.warning(
                                                    "scrcpy frame sync lost: payload has no Annex-B start code, resyncing"
                                                )
                                            frame_count += 1
                                            continue

                                        seen_sps = seen_sps or has_sps
                                        seen_pps = seen_pps or has_pps
                                        seen_idr = seen_idr or has_idr
                                        if not decode_locked:
                                            if seen_sps and seen_pps and seen_idr:
                                                decode_locked = True
                                                logger.info(
                                                    "scrcpy frame sync locked: SPS+PPS+IDR detected, feeding ffmpeg"
                                                )
                                            else:
                                                now = time.monotonic()
                                                if now - last_sync_warn > 1.0:
                                                    logger.warning(
                                                        f"scrcpy sync waiting: sps={seen_sps} pps={seen_pps} idr={seen_idr}"
                                                    )
                                                    last_sync_warn = now
                                                frame_count += 1
                                                continue

                                        if frame_debug and frame_count < frame_debug_limit:
                                            logger.warning(
                                                f"scrcpy frame[{frame_count}] mode={parser_mode} "
                                                f"fmt={frame_fmt} len={len(frame)} "
                                                f"nals={nal_types[:6]} sps={has_sps} pps={has_pps} "
                                                f"idr={has_idr} inject_cfg={injected_cfg} "
                                                f"head={normalized[:16].hex()}"
                                            )
                                        frame_count += 1
                                        ffmpeg_proc.stdin.write(normalized)
                                        ffmpeg_proc.stdin.flush()
                                        bytes_sent[0] += len(normalized)
                                        if dump_on_fail and len(ffmpeg_in_buf) < ffmpeg_in_max:
                                            take = min(ffmpeg_in_max - len(ffmpeg_in_buf), len(normalized))
                                            if take > 0:
                                                ffmpeg_in_buf.extend(normalized[:take])
                                    if stop_event.is_set():
                                        break
                            else:
                                try:
                                    data = video_socket.recv(65536)
                                    if not data:
                                        break
                                    if dump_on_fail and len(raw_dump_buf) < raw_dump_max:
                                        take = min(raw_dump_max - len(raw_dump_buf), len(data))
                                        if take > 0:
                                            raw_dump_buf.extend(data[:take])
                                    if uses_len_prefixed:
                                        converted = len2annex.feed(data)
                                        if converted:
                                            ffmpeg_proc.stdin.write(converted)
                                            ffmpeg_proc.stdin.flush()
                                            bytes_sent[0] += len(converted)
                                            if dump_on_fail and len(ffmpeg_in_buf) < ffmpeg_in_max:
                                                take = min(ffmpeg_in_max - len(ffmpeg_in_buf), len(converted))
                                                if take > 0:
                                                    ffmpeg_in_buf.extend(converted[:take])
                                    else:
                                        ffmpeg_proc.stdin.write(data)
                                        ffmpeg_proc.stdin.flush()
                                        bytes_sent[0] += len(data)
                                        if dump_on_fail and len(ffmpeg_in_buf) < ffmpeg_in_max:
                                            take = min(ffmpeg_in_max - len(ffmpeg_in_buf), len(data))
                                            if take > 0:
                                                ffmpeg_in_buf.extend(data[:take])
                                except (OSError, BrokenPipeError):
                                    break
                    finally:
                        try:
                            ffmpeg_proc.stdin.close()
                        except Exception:
                            pass

                feeder = threading.Thread(target=feed_ffmpeg, daemon=True,
                                         name=f"scrcpy-feed-{device_id}")
                feeder.start()

                # Wait for output dimensions from stderr
                for _ in range(100):
                    if out_height[0] > 0 or stop_event.is_set():
                        break
                    time.sleep(0.1)

                if out_height[0] == 0:
                    # Fallback: compute from screen aspect ratio
                    if w > 0 and h > 0:
                        out_height[0] = int(h * out_width / w)
                        # Ensure even (required by rawvideo)
                        if out_height[0] % 2:
                            out_height[0] += 1
                    else:
                        out_height[0] = 800
                    logger.debug(f"scrcpy output height not detected, "
                                 f"using {out_width}x{out_height[0]}")
                logger.info(f"scrcpy rawvideo frame_size={out_width}x{out_height[0]}")

                frame_size = out_width * out_height[0] * 3  # RGB24

                # Read raw frames and convert to JPEG via PIL
                first_frame = True
                while not stop_event.is_set():
                    raw = b''
                    while len(raw) < frame_size:
                        remaining = frame_size - len(raw)
                        chunk = ffmpeg_proc.stdout.read(remaining)
                        if not chunk:
                            break
                        raw += chunk

                    if len(raw) < frame_size:
                        break
                    if stop_event.is_set():
                        break

                    # Convert raw RGB to JPEG
                    img = Image.frombytes('RGB', (out_width, out_height[0]), raw)
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=65)
                    jpeg_bytes = buf.getvalue()

                    if first_frame:
                        logger.info("scrcpy first frame decoded ✅")
                        first_frame = False
                    _valid_frame_event.set()
                    session.last_frame = jpeg_bytes
                    if _main_loop and not _main_loop.is_closed():
                        _main_loop.call_soon_threadsafe(
                            lambda data=jpeg_bytes: asyncio.ensure_future(
                                self._broadcast_frame(session, data)
                            )
                        )

            except Exception as e:
                if not stop_event.is_set():
                    logger.error(f"scrcpy stream error for {device_id}: {e}")
            finally:
                if not _valid_frame_event.is_set() and stderr_tail:
                    tail = "; ".join(list(stderr_tail)[-10:])
                    logger.warning(f"scrcpy ffmpeg stderr tail: {tail}")
                if not _valid_frame_event.is_set():
                    logger.warning(f"scrcpy bytes fed to ffmpeg: {bytes_sent[0]}")
                if dump_on_fail and ffmpeg_in_buf and not _valid_frame_event.is_set():
                    try:
                        fed_path = f"/tmp/scrcpy_{device_id}_ffmpeg_in.h264"
                        with open(fed_path, "wb") as f:
                            f.write(ffmpeg_in_buf)
                        logger.warning(
                            f"scrcpy ffmpeg input dump: {fed_path} ({len(ffmpeg_in_buf)} bytes)"
                        )
                        if _ffmpeg_available:
                            probe2 = subprocess.run(
                                ["ffprobe", "-v", "error", "-show_streams", "-print_format", "json", fed_path],
                                capture_output=True, text=True, timeout=5
                            )
                            if probe2.stdout:
                                logger.warning(f"scrcpy ffprobe(ffmpeg_in): {probe2.stdout.strip()}")
                            if probe2.stderr:
                                logger.warning(f"scrcpy ffprobe(ffmpeg_in) stderr: {probe2.stderr.strip()}")
                    except Exception as e:
                        logger.warning(f"scrcpy ffmpeg input dump failed: {e}")
                if dump_on_fail and raw_dump_buf and not _valid_frame_event.is_set():
                    try:
                        dump_path = f"/tmp/scrcpy_{device_id}_raw.h264"
                        with open(dump_path, "wb") as f:
                            f.write(raw_dump_buf)
                        logger.warning(f"scrcpy dump written: {dump_path} ({len(raw_dump_buf)} bytes)")
                        if _ffmpeg_available:
                            probe = subprocess.run(
                                ["ffprobe", "-v", "error", "-show_streams", "-print_format", "json", dump_path],
                                capture_output=True, text=True, timeout=5
                            )
                            if probe.stdout:
                                logger.warning(f"scrcpy ffprobe: {probe.stdout.strip()}")
                            if probe.stderr:
                                logger.warning(f"scrcpy ffprobe stderr: {probe.stderr.strip()}")
                    except Exception as e:
                        logger.warning(f"scrcpy dump failed: {e}")
                if ffmpeg_proc:
                    try:
                        ffmpeg_proc.terminate()
                        ffmpeg_proc.wait(timeout=3)
                    except Exception:
                        try:
                            ffmpeg_proc.kill()
                        except Exception:
                            pass
                session._ffmpeg_proc = None

        session._client_thread = threading.Thread(target=stream_thread, daemon=True,
                                                   name=f"scrcpy-{device_id}")
        session._client_thread.start()
        # Unlock after stream pipeline starts so unlock action can help trigger first frame.
        self._schedule_auto_unlock(device_id)

        # Wait for first valid frame (older/slower devices may need longer startup).
        got_valid = await loop.run_in_executor(
            None, lambda: _valid_frame_event.wait(timeout=_scrcpy_first_frame_timeout)
        )

        if not got_valid:
            logger.warning(f"scrcpy+ffmpeg produced no frames for {device_id}")
            stop_event.set()
            self._cleanup_scrcpy(session, device_id)
            session.is_streaming = False
            session.is_scrcpy = False
            session.stream_mode = ""
            session.last_frame = None
            raise RuntimeError(f"scrcpy+ffmpeg produced no frames for {device_id}")

        logger.info(f"scrcpy stream started for {device_id} ({w}x{h} @{frame_rate}fps) ✅ ✅")
        return {
            "status": "started",
            "mode": "scrcpy",
            "width": w,
            "height": h,
            "fps": frame_rate,
        }

    def _cleanup_scrcpy(self, session: ScrcpySession, device_id: str):
        """Clean up scrcpy-specific resources."""
        if session._ffmpeg_proc:
            try:
                session._ffmpeg_proc.terminate()
                session._ffmpeg_proc.wait(timeout=3)
            except Exception:
                try:
                    session._ffmpeg_proc.kill()
                except Exception:
                    pass
            session._ffmpeg_proc = None

        if session._video_socket:
            try:
                session._video_socket.close()
            except Exception:
                pass
            session._video_socket = None

        if session._server_proc:
            try:
                session._server_proc.terminate()
                session._server_proc.wait(timeout=3)
            except Exception:
                try:
                    session._server_proc.kill()
                except Exception:
                    pass
            session._server_proc = None

        if session._local_port:
            try:
                subprocess.run(
                    ["adb", "-s", device_id, "forward", f"--remove", f"tcp:{session._local_port}"],
                    capture_output=True, timeout=5
                )
            except subprocess.TimeoutExpired as e:
                logger.warning(f"adb forward remove timeout for {device_id}: {e}")
            except Exception as e:
                logger.warning(f"adb forward remove failed for {device_id}: {e}")
            session._local_port = 0

    # ──────────────────────────────────────────────────────────────────────
    # Mode 2: adb screenrecord + ffmpeg pipeline
    # ──────────────────────────────────────────────────────────────────────

    async def _get_screen_size(self, device_id: str) -> tuple[int, int]:
        """Get device screen dimensions via adb."""
        loop = asyncio.get_event_loop()

        def _get():
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "wm", "size"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if 'size' in line.lower():
                    parts = line.split(':')[-1].strip().split('x')
                    if len(parts) == 2:
                        try:
                            return int(parts[0]), int(parts[1])
                        except ValueError:
                            pass
            return 0, 0

        return await loop.run_in_executor(None, _get)

    async def _detect_screenrecord_caps(self, device_id: str) -> dict:
        """Detect screenrecord capabilities on the device."""
        loop = asyncio.get_event_loop()

        def _detect():
            caps = {"supported": False, "output_format": False, "formats": [], "version": ""}
            try:
                result = subprocess.run(
                    ["adb", "-s", device_id, "exec-out", "screenrecord", "--help"],
                    capture_output=True, text=True, timeout=5
                )
                help_text = result.stdout + result.stderr

                if "screenrecord" not in help_text.lower():
                    return caps

                caps["supported"] = True

                import re
                ver_match = re.search(r'screenrecord v([\d.]+)', help_text)
                if ver_match:
                    caps["version"] = ver_match.group(1)

                if "--output-format" in help_text:
                    caps["output_format"] = True
                    fmt_match = re.search(r'(?:format|fmt)[s]?[:\s]+([\w\-]+(?:,\s*[\w\-]+)*)', help_text, re.IGNORECASE)
                    if fmt_match:
                        caps["formats"] = [f.strip() for f in fmt_match.group(1).split(',')]
                    else:
                        caps["formats"] = ["h264"]

            except Exception as e:
                logger.debug(f"screenrecord detection error: {e}")

            return caps

        caps = await loop.run_in_executor(None, _detect)
        logger.info(f"screenrecord caps for {device_id}: version={caps['version']}, "
                     f"output_format={caps['output_format']}, formats={caps['formats']}")
        return caps

    async def _start_screenrecord_stream(self, session: ScrcpySession,
                                          device_id: str, frame_rate: int) -> dict:
        """Start real-time stream: adb screenrecord → H.264 → ffmpeg → rawvideo → JPEG."""
        import re

        caps = await self._detect_screenrecord_caps(device_id)

        if not caps["output_format"]:
            raise RuntimeError(
                f"screenrecord on {device_id} (v{caps['version']}) does not support "
                f"--output-format (required for stdout streaming)")

        if "h264" in caps["formats"]:
            output_format = "h264"
            ffmpeg_input_fmt = "h264"
        elif caps["formats"]:
            output_format = caps["formats"][0]
            ffmpeg_input_fmt = output_format
        else:
            output_format = "h264"
            ffmpeg_input_fmt = "h264"

        w, h = await self._get_screen_size(device_id)
        session.screen_width = w
        session.screen_height = h
        session.is_scrcpy = False
        session.stream_mode = "screenrecord"
        session.frame_rate = frame_rate
        session.is_streaming = True
        session._stop_event = threading.Event()

        # Output scale width for rawvideo frames
        out_width = 800 if w <= 0 else min(800, w)
        out_height = [0]
        if w > 0 and h > 0:
            out_height[0] = int(h * out_width / w)
            if out_height[0] % 2:
                out_height[0] += 1

        def stream_thread():
            while not session._stop_event.is_set():
                adb_proc = None
                ffmpeg_proc = None
                try:
                    adb_proc = subprocess.Popen(
                        ["adb", "-s", device_id, "exec-out", "screenrecord",
                         f"--output-format={output_format}", "--bit-rate", "2000000", "-"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
                    )
                    ffmpeg_proc = subprocess.Popen(
                        ["ffmpeg",
                         "-flags", "low_delay",
                         "-probesize", "500000",
                         "-analyzeduration", "1000000",
                         "-f", ffmpeg_input_fmt, "-i", "pipe:0", "-an",
                         "-vf", f"fps={frame_rate},scale={out_width}:-2",
                         "-f", "rawvideo", "-pix_fmt", "rgb24",
                         "-flush_packets", "1",
                         "-threads", "1",
                         "pipe:1"],
                        stdin=adb_proc.stdout, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, bufsize=0
                    )
                    adb_proc.stdout.close()
                    session._adb_proc = adb_proc
                    session._ffmpeg_proc = ffmpeg_proc
                    # If size not known, parse stderr to detect output dimensions.
                    # Otherwise, drain stderr to avoid pipe blocking.
                    if out_height[0] == 0:
                        def parse_stderr():
                            try:
                                for line in ffmpeg_proc.stderr:
                                    decoded = line.decode('utf-8', errors='replace').strip()
                                    if 'Stream #0:0' in decoded and 'rawvideo' in decoded:
                                        m = re.search(r'(\d+)x(\d+)', decoded)
                                        if m:
                                            pw, ph = int(m.group(1)), int(m.group(2))
                                            if pw == out_width:
                                                out_height[0] = ph
                                                logger.info(
                                                    f"screenrecord ffmpeg output: {pw}x{ph}")
                            except Exception:
                                pass

                        threading.Thread(target=parse_stderr, daemon=True,
                                         name=f"screenrecord-stderr-{device_id}").start()

                        for _ in range(100):
                            if out_height[0] > 0 or session._stop_event.is_set():
                                break
                            time.sleep(0.1)

                        if out_height[0] == 0:
                            out_height[0] = 800
                            logger.debug("screenrecord output height not detected, "
                                         f"using {out_width}x{out_height[0]}")
                    else:
                        threading.Thread(
                            target=lambda: ffmpeg_proc.stderr.read(),
                            daemon=True,
                            name=f"screenrecord-stderr-{device_id}",
                        ).start()

                    frame_size = out_width * out_height[0] * 3  # RGB24

                    while not session._stop_event.is_set():
                        raw = b''
                        while len(raw) < frame_size:
                            remaining = frame_size - len(raw)
                            chunk = ffmpeg_proc.stdout.read(remaining)
                            if not chunk:
                                break
                            raw += chunk

                        if len(raw) < frame_size:
                            break

                        img = Image.frombytes('RGB', (out_width, out_height[0]), raw)
                        buf = io.BytesIO()
                        img.save(buf, format='JPEG', quality=65)
                        jpeg_bytes = buf.getvalue()

                        session.last_frame = jpeg_bytes
                        if _main_loop and not _main_loop.is_closed():
                            _main_loop.call_soon_threadsafe(
                                lambda data=jpeg_bytes: asyncio.ensure_future(
                                    self._broadcast_frame(session, data)
                                )
                            )

                    if not session._stop_event.is_set():
                        logger.debug(f"screenrecord cycle ended for {device_id}, restarting")

                except Exception as e:
                    if not session._stop_event.is_set():
                        logger.error(f"screenrecord error for {device_id}: {e}")
                finally:
                    for proc in [ffmpeg_proc, adb_proc]:
                        if proc:
                            try:
                                proc.terminate()
                                proc.wait(timeout=3)
                            except Exception:
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                    session._adb_proc = None
                    session._ffmpeg_proc = None
                    if not session._stop_event.is_set():
                        time.sleep(0.3)

        session._client_thread = threading.Thread(
            target=stream_thread, daemon=True, name=f"screenrecord-{device_id}")
        session._client_thread.start()
        self._schedule_auto_unlock(device_id)
        await asyncio.sleep(2.0)

        if session.last_frame is None:
            session._stop_event.set()
            session.is_streaming = False
            session.stream_mode = ""
            raise RuntimeError(f"screenrecord produced no frames for {device_id}")

        logger.info(f"screenrecord stream started for {device_id} ({w}x{h} @{frame_rate}fps)")
        return {"status": "started", "mode": "screenrecord", "width": w, "height": h, "fps": frame_rate}

    # ──────────────────────────────────────────────────────────────────────
    # Mode 3: adb screencap loop (last resort)
    # ──────────────────────────────────────────────────────────────────────

    async def _start_screencap_stream(self, session: ScrcpySession,
                                       device_id: str, frame_rate: int) -> dict:
        """Start screenshot-based fallback streaming."""
        session.is_scrcpy = False
        session.stream_mode = "screencap"
        session.frame_rate = min(frame_rate, 10)
        session.is_streaming = True
        session._fallback_task = asyncio.create_task(self._screencap_loop(session, device_id))
        self._schedule_auto_unlock(device_id)
        logger.info(f"screencap stream started for {device_id} @{session.frame_rate}fps")
        return {
            "status": "started", "mode": "screencap",
            "width": session.screen_width, "height": session.screen_height,
            "fps": session.frame_rate,
        }

    async def _screencap_loop(self, session: ScrcpySession, device_id: str):
        """Capture screenshots in a loop."""
        interval = 1.0 / session.frame_rate
        loop = asyncio.get_event_loop()
        while session.is_streaming:
            try:
                t0 = time.monotonic()

                def capture():
                    result = subprocess.run(
                        ["adb", "-s", device_id, "exec-out", "screencap", "-p"],
                        capture_output=True, timeout=5
                    )
                    return result.stdout if result.returncode == 0 else None

                png_data = await loop.run_in_executor(None, capture)
                if png_data and len(png_data) > 100:
                    def process(data):
                        img = Image.open(io.BytesIO(data))
                        if img.mode == 'RGBA':
                            img = img.convert('RGB')
                        session.screen_width = img.width
                        session.screen_height = img.height
                        if img.width > 800:
                            ratio = 800 / img.width
                            img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)
                        buf = io.BytesIO()
                        img.save(buf, format='JPEG', quality=65)
                        return buf.getvalue()

                    jpeg_bytes = await loop.run_in_executor(None, process, png_data)
                    session.last_frame = jpeg_bytes
                    await self._broadcast_frame(session, jpeg_bytes)

                sleep_time = max(0, interval - (time.monotonic() - t0))
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"screencap error for {device_id}: {e}")
                await asyncio.sleep(1)

    # ──────────────────────────────────────────────────────────────────────
    # Stream control
    # ──────────────────────────────────────────────────────────────────────

    async def stop_stream(self, device_id: str) -> dict:
        """Stop streaming for a device."""
        session = self._sessions.get(device_id)
        if not session or not session.is_streaming:
            return {"status": "not_running"}

        session.is_streaming = False

        if session._stop_event:
            session._stop_event.set()

        # Scrcpy cleanup
        if session.is_scrcpy:
            self._cleanup_scrcpy(session, device_id)

        # ffmpeg/adb process cleanup
        for proc in [session._ffmpeg_proc, session._adb_proc]:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        session._adb_proc = None
        session._ffmpeg_proc = None
        session._client_thread = None

        # Screencap task cleanup
        if session._fallback_task and not session._fallback_task.done():
            session._fallback_task.cancel()
            try:
                await session._fallback_task
            except asyncio.CancelledError:
                pass
            session._fallback_task = None

        session.stream_mode = ""
        logger.info(f"Stream stopped for {device_id}")
        return {"status": "stopped"}

    def get_stream_status(self, device_id: str) -> dict:
        """Get stream status for a device."""
        session = self._sessions.get(device_id)
        if not session:
            return {"streaming": False}
        return {
            "streaming": session.is_streaming, "mode": session.stream_mode,
            "width": session.screen_width, "height": session.screen_height,
            "fps": session.frame_rate, "viewers": len(session.connected_websockets),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Touch / Key input (via adb for all modes)
    # ──────────────────────────────────────────────────────────────────────

    async def send_touch(self, device_id: str, action: str, x: float, y: float,
                          width: float, height: float):
        """Send touch event. Coordinates mapped from canvas to device screen."""
        session = self._sessions.get(device_id)
        if not session:
            return

        if width > 0 and height > 0 and session.screen_width > 0 and session.screen_height > 0:
            device_x = int(x * session.screen_width / width)
            device_y = int(y * session.screen_height / height)
        else:
            device_x, device_y = int(x), int(y)

        device_x = max(0, min(device_x, session.screen_width - 1))
        device_y = max(0, min(device_y, session.screen_height - 1))

        await self._send_touch_adb(device_id, session, action, device_x, device_y)

    async def _send_touch_adb(self, device_id: str, session: ScrcpySession,
                               action: str, device_x: int, device_y: int):
        """Send touch via adb shell input."""
        if action == "down":
            session._touch_start = (device_x, device_y)
            session._touch_moved = False
            session._touch_start_time = time.monotonic()
            session._touch_last = (device_x, device_y)
        elif action == "move":
            start = getattr(session, '_touch_start', (device_x, device_y))
            sx, sy = start
            # Ignore tiny jitter so long-press is not misclassified as swipe.
            if abs(device_x - sx) > 12 or abs(device_y - sy) > 12:
                session._touch_moved = True
            session._touch_last = (device_x, device_y)
        elif action == "up":
            loop = asyncio.get_event_loop()
            start = getattr(session, '_touch_start', None)
            sx, sy = start if start else (device_x, device_y)
            press_ms = int((time.monotonic() - getattr(session, '_touch_start_time', time.monotonic())) * 1000)
            moved = getattr(session, '_touch_moved', False)
            if moved:
                ex, ey = getattr(session, '_touch_last', (device_x, device_y))
                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda: subprocess.run(
                            ["adb", "-s", device_id, "shell", "input", "swipe",
                             str(sx), str(sy), str(ex), str(ey), "300"],
                            capture_output=True, timeout=5
                        )
                    )
                except subprocess.TimeoutExpired:
                    logger.warning(f"touch adb {device_id}: swipe timeout")
                    return
                except Exception as e:
                    logger.warning(f"touch adb {device_id}: swipe error: {e}")
                    return
                if result.returncode != 0:
                    logger.warning(
                        f"touch adb swipe failed {device_id}: stderr={result.stderr.decode('utf-8', errors='replace').strip()}"
                    )
            else:
                # Convert long press to swipe(same point, duration) for reliable press-and-hold.
                if press_ms >= 550:
                    hold_ms = max(550, min(1800, press_ms))
                    try:
                        result = await loop.run_in_executor(
                            None,
                            lambda: subprocess.run(
                                ["adb", "-s", device_id, "shell", "input", "swipe",
                                 str(sx), str(sy), str(sx), str(sy), str(hold_ms)],
                                capture_output=True, timeout=5
                            )
                        )
                    except subprocess.TimeoutExpired:
                        logger.warning(f"touch adb {device_id}: longpress timeout")
                        return
                    except Exception as e:
                        logger.warning(f"touch adb {device_id}: longpress error: {e}")
                        return
                    if result.returncode != 0:
                        logger.warning(
                            f"touch adb longpress failed {device_id}: stderr={result.stderr.decode('utf-8', errors='replace').strip()}"
                        )
                    return
                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda: subprocess.run(
                            ["adb", "-s", device_id, "shell", "input", "tap",
                             str(device_x), str(device_y)],
                            capture_output=True, timeout=5
                        )
                    )
                except subprocess.TimeoutExpired:
                    logger.warning(f"touch adb {device_id}: tap timeout")
                    return
                except Exception as e:
                    logger.warning(f"touch adb {device_id}: tap error: {e}")
                    return
                if result.returncode != 0:
                    logger.warning(
                        f"touch adb tap failed {device_id}: stderr={result.stderr.decode('utf-8', errors='replace').strip()}"
                    )

    async def send_scroll(self, device_id: str, x: float, y: float,
                          width: float, height: float, delta_y: float):
        """Send wheel scroll as vertical swipe around pointer location."""
        session = self._sessions.get(device_id)
        if not session or session.screen_width <= 0 or session.screen_height <= 0:
            return

        if width > 0 and height > 0:
            device_x = int(x * session.screen_width / width)
            device_y = int(y * session.screen_height / height)
        else:
            device_x, device_y = int(x), int(y)

        device_x = max(0, min(device_x, session.screen_width - 1))
        device_y = max(0, min(device_y, session.screen_height - 1))
        distance = max(120, min(520, int(session.screen_height * 0.18)))
        half = distance // 2

        # delta_y > 0 means wheel down -> content down -> finger swipe up.
        if delta_y > 0:
            sy = min(session.screen_height - 2, device_y + half)
            ey = max(1, device_y - half)
        else:
            sy = max(1, device_y - half)
            ey = min(session.screen_height - 2, device_y + half)

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["adb", "-s", device_id, "shell", "input", "swipe",
                     str(device_x), str(sy), str(device_x), str(ey), "220"],
                    capture_output=True, timeout=5
                )
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"scroll adb {device_id}: timeout")
            return
        except Exception as e:
            logger.warning(f"scroll adb {device_id}: error: {e}")
            return

        if result.returncode != 0:
            logger.warning(
                f"scroll adb failed {device_id}: stderr={result.stderr.decode('utf-8', errors='replace').strip()}"
            )

    async def send_key(self, device_id: str, keycode: int):
        """Send key event. Common: Back=4, Home=3."""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["adb", "-s", device_id, "shell", "input", "keyevent", str(keycode)],
                    capture_output=True, timeout=5
                )
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"key adb {device_id}: keycode={keycode} timeout")
            return
        except Exception as e:
            logger.warning(f"key adb {device_id}: keycode={keycode} error: {e}")
            return
        if result.returncode != 0:
            logger.warning(
                f"key adb failed {device_id}: stderr={result.stderr.decode('utf-8', errors='replace').strip()}"
            )

    # ──────────────────────────────────────────────────────────────────────
    # WebSocket management
    # ──────────────────────────────────────────────────────────────────────

    async def _broadcast_frame(self, session: ScrcpySession, jpeg_bytes: bytes):
        """Broadcast JPEG frame to all connected WebSockets."""
        if not session.connected_websockets:
            return
        dead = set()
        for ws in list(session.connected_websockets):
            try:
                await ws.send_bytes(jpeg_bytes)
            except Exception:
                dead.add(ws)
        for ws in dead:
            session.connected_websockets.discard(ws)

    def add_viewer(self, device_id: str, websocket) -> ScrcpySession:
        """Add a WebSocket viewer to a session."""
        session = self.get_or_create_session(device_id)
        session.connected_websockets.add(websocket)
        if session._auto_stop_task and not session._auto_stop_task.done():
            session._auto_stop_task.cancel()
            session._auto_stop_task = None
        return session

    def remove_viewer(self, device_id: str, websocket):
        """Remove a WebSocket viewer and schedule optional auto-stop."""
        session = self._sessions.get(device_id)
        if not session:
            return
        session.connected_websockets.discard(websocket)
        if not session.connected_websockets and session.is_streaming:
            if _scrcpy_auto_stop_delay <= 0:
                logger.info(
                    f"No-viewer auto-stop disabled for {device_id}; stream kept alive"
                )
                return
            if _main_loop and not _main_loop.is_closed():
                session._auto_stop_task = asyncio.ensure_future(
                    self._auto_stop_after_delay(device_id, _scrcpy_auto_stop_delay)
                )

    async def _auto_stop_after_delay(self, device_id: str, delay: int):
        try:
            await asyncio.sleep(delay)
            session = self._sessions.get(device_id)
            if session and not session.connected_websockets and session.is_streaming:
                logger.info(f"Auto-stopping stream for {device_id} (no viewers for {delay}s)")
                await self.stop_stream(device_id)
        except asyncio.CancelledError:
            pass

    async def cleanup_all(self):
        """Stop all sessions (called on app shutdown)."""
        for device_id in list(self._sessions.keys()):
            try:
                await self.stop_stream(device_id)
            except Exception as e:
                logger.warning(f"Error cleaning up stream for {device_id}: {e}")
        self._sessions.clear()
        logger.info("All streaming sessions cleaned up")


# Global service instance
scrcpy_service = ScrcpyService()
