# -*- coding: utf-8 -*-
"""
Scrcpy streaming service for real-time device screen mirroring and touch control.

Pure scrcpy mode:
1. scrcpy-server v3 JAR + ffmpeg: raw H.264 via socket → ffmpeg → rawvideo → PIL JPEG
2. scrcpy control socket injection for touch/scroll/key
3. independent scrcpy audio passthrough channel
"""

import asyncio
import io
import json
import logging
import os
import shutil
import struct
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
    logger.warning("ffmpeg not found, scrcpy streaming will be unavailable")

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
_scrcpy_control_debug = os.getenv("SCRCPY_CONTROL_DEBUG", "0") == "1"
try:
    _scrcpy_rotation_check_interval_sec = float(os.getenv("SCRCPY_ROTATION_CHECK_INTERVAL_SEC", "0.8"))
except ValueError:
    _scrcpy_rotation_check_interval_sec = 0.8
if _scrcpy_rotation_check_interval_sec < 0.5:
    _scrcpy_rotation_check_interval_sec = 0.5
try:
    _scrcpy_recover_cooldown_sec = float(os.getenv("SCRCPY_RECOVER_COOLDOWN_SEC", "3"))
except ValueError:
    _scrcpy_recover_cooldown_sec = 3.0
if _scrcpy_recover_cooldown_sec < 1.0:
    _scrcpy_recover_cooldown_sec = 1.0
try:
    _scrcpy_stale_frame_watchdog_sec = float(os.getenv("SCRCPY_STALE_FRAME_WATCHDOG_SEC", "45"))
except ValueError:
    _scrcpy_stale_frame_watchdog_sec = 45.0
if _scrcpy_stale_frame_watchdog_sec < 5.0:
    _scrcpy_stale_frame_watchdog_sec = 5.0
try:
    _scrcpy_decode_error_streak_threshold = int(
        os.getenv("SCRCPY_DECODE_ERROR_STREAK_THRESHOLD", "32")
    )
except ValueError:
    _scrcpy_decode_error_streak_threshold = 32
if _scrcpy_decode_error_streak_threshold < 8:
    _scrcpy_decode_error_streak_threshold = 8

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
    stream_mode: str = ""  # "scrcpy"
    last_frame: Optional[bytes] = None  # Latest JPEG frame
    last_frame_ts: float = 0.0
    connected_websockets: Set = field(default_factory=set)
    connected_audio_websockets: Set = field(default_factory=set)
    screen_width: int = 0
    screen_height: int = 0
    video_width: int = 0
    video_height: int = 0
    audio_enabled: bool = False
    audio_codec: str = ""
    audio_sample_rate: int = 48_000
    audio_channels: int = 2
    display_rotation: int = -1
    frame_rate: int = 15
    client: Optional[object] = None  # unused, kept for compatibility
    _client_thread: Optional[threading.Thread] = None
    _stop_event: Optional[threading.Event] = None
    _auto_stop_task: Optional[asyncio.Task] = None
    _adb_proc: Optional[subprocess.Popen] = None
    _ffmpeg_proc: Optional[subprocess.Popen] = None
    _server_proc: Optional[subprocess.Popen] = None
    _video_socket: Optional[object] = None
    _audio_socket: Optional[object] = None
    _control_socket: Optional[object] = None
    control_enabled: bool = False
    _control_lock: threading.Lock = field(default_factory=threading.Lock)
    _scrcpy_scid: Optional[str] = None
    _local_port: int = 0
    max_size: int = 960
    bit_rate: int = 4_000_000
    _recover_task: Optional[object] = None
    _last_recover_ts: float = 0.0
    _last_rotation_check_ts: float = 0.0
    _prefer_no_meta: bool = False
    _current_frame_meta: bool = False


class ScrcpyService:
    """Manages streaming sessions for all devices."""

    _next_port = 27183  # Starting port for adb forward

    def __init__(self):
        self._sessions: dict[str, ScrcpySession] = {}
        self._start_locks: dict[str, asyncio.Lock] = {}

    def _get_start_lock(self, device_id: str) -> asyncio.Lock:
        lock = self._start_locks.get(device_id)
        if lock is None:
            lock = asyncio.Lock()
            self._start_locks[device_id] = lock
        return lock

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

    @staticmethod
    def _float_to_u16_fixed_point(value: float) -> int:
        v = max(0.0, min(1.0, float(value)))
        return int(round(v * 0xFFFF))

    @staticmethod
    def _float_to_i16_fixed_point(value: float) -> int:
        v = max(-1.0, min(1.0, float(value)))
        return int(round(v * 32767.0))

    @staticmethod
    def _pack_scrcpy_key_message(action: int, keycode: int, repeat: int = 0, meta_state: int = 0) -> bytes:
        # TYPE_INJECT_KEYCODE = 0
        return struct.pack(
            ">BBiii",
            0,
            action & 0xFF,
            int(keycode),
            int(repeat),
            int(meta_state),
        )

    @staticmethod
    def _pack_scrcpy_touch_message(
        action: int,
        pointer_id: int,
        x: int,
        y: int,
        screen_width: int,
        screen_height: int,
        pressure: float,
        action_button: int = 0,
        buttons: int = 0,
    ) -> bytes:
        # TYPE_INJECT_TOUCH_EVENT = 2
        return struct.pack(
            ">BBqiiHHHii",
            2,
            action & 0xFF,
            int(pointer_id),
            int(x),
            int(y),
            max(0, min(0xFFFF, int(screen_width))),
            max(0, min(0xFFFF, int(screen_height))),
            ScrcpyService._float_to_u16_fixed_point(pressure),
            int(action_button),
            int(buttons),
        )

    @staticmethod
    def _pack_scrcpy_scroll_message(
        x: int,
        y: int,
        screen_width: int,
        screen_height: int,
        h_scroll: float,
        v_scroll: float,
        buttons: int = 0,
    ) -> bytes:
        # TYPE_INJECT_SCROLL_EVENT = 3
        return struct.pack(
            ">BiiHHhhi",
            3,
            int(x),
            int(y),
            max(0, min(0xFFFF, int(screen_width))),
            max(0, min(0xFFFF, int(screen_height))),
            ScrcpyService._float_to_i16_fixed_point(h_scroll),
            ScrcpyService._float_to_i16_fixed_point(v_scroll),
            int(buttons),
        )

    @staticmethod
    def _can_use_scrcpy_control(session: Optional[ScrcpySession]) -> bool:
        return bool(session and session.is_scrcpy and session.control_enabled and session._control_socket)

    def _send_scrcpy_control_packet(self, session: ScrcpySession, device_id: str, payload: bytes, label: str) -> bool:
        sock = session._control_socket
        if not sock:
            return False
        try:
            with session._control_lock:
                sock.sendall(payload)
            return True
        except Exception as e:
            logger.warning(f"scrcpy control send failed for {device_id} ({label}): {e}")
            try:
                sock.close()
            except Exception:
                pass
            session._control_socket = None
            return False

    def _schedule_stream_recovery(
        self,
        device_id: str,
        reason: str,
        *,
        max_size: Optional[int] = None,
        bit_rate: Optional[int] = None,
        frame_rate: Optional[int] = None,
        control_enabled: Optional[bool] = None,
        audio_enabled: Optional[bool] = None,
    ) -> bool:
        session = self._sessions.get(device_id)
        if not session or not session.is_streaming:
            return False

        now = time.monotonic()
        if session._recover_task and not session._recover_task.done():
            return False
        if now - float(session._last_recover_ts or 0.0) < _scrcpy_recover_cooldown_sec:
            return False

        restart_size = int(max_size if max_size is not None else (session.max_size or 960))
        restart_br = int(bit_rate if bit_rate is not None else (session.bit_rate or 4_000_000))
        restart_fps = int(frame_rate if frame_rate is not None else (session.frame_rate or 24))
        restart_control = bool(
            session.control_enabled if control_enabled is None else control_enabled
        )
        restart_audio = bool(
            session.audio_enabled if audio_enabled is None else audio_enabled
        )

        async def _recover():
            try:
                logger.warning(
                    f"[SCRCPY-RECOVER] 🔧 restarting stream for {device_id}: reason={reason} "
                    f"control={restart_control} audio={restart_audio} "
                    f"max_size={restart_size} fps={restart_fps} bit_rate={restart_br}"
                )
                await self.start_stream(
                    device_id,
                    max_size=restart_size,
                    bit_rate=restart_br,
                    frame_rate=restart_fps,
                    restart=True,
                    control_enabled=restart_control,
                    audio_enabled=restart_audio,
                )
                logger.info(f"[SCRCPY-RECOVER] 🔧 stream recovered for {device_id}: reason={reason}")
                session_after = self._sessions.get(device_id)
                if session_after and reason.startswith("orientation_"):
                    await self._broadcast_control(
                        session_after,
                        {"type": "rotation_recovery_done", "reason": reason},
                    )
            except Exception as e:
                logger.warning(f"[SCRCPY-RECOVER] 🔧 restart failed for {device_id}: reason={reason}, error={e}")
                session_after = self._sessions.get(device_id)
                if session_after and reason.startswith("orientation_"):
                    await self._broadcast_control(
                        session_after,
                        {"type": "rotation_recovery_failed", "reason": reason, "error": str(e)},
                    )
            finally:
                s = self._sessions.get(device_id)
                if s:
                    s._recover_task = None

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and not running_loop.is_closed():
            session._last_recover_ts = now
            session._recover_task = running_loop.create_task(_recover())
            return True

        loop = _main_loop
        if not loop or loop.is_closed():
            return False
        session._last_recover_ts = now
        session._recover_task = asyncio.run_coroutine_threadsafe(_recover(), loop)
        return True

    def watchdog_recover_if_stale(
        self,
        device_id: str,
        *,
        max_size: Optional[int] = None,
        bit_rate: Optional[int] = None,
        frame_rate: Optional[int] = None,
        control_enabled: Optional[bool] = None,
        audio_enabled: Optional[bool] = None,
    ) -> bool:
        session = self._sessions.get(device_id)
        if not session or not session.is_streaming or not session.is_scrcpy:
            return False
        if not session.connected_websockets:
            return False

        thread_alive = bool(session._client_thread and session._client_thread.is_alive())
        if not thread_alive:
            return self._schedule_stream_recovery(
                device_id,
                "video_thread_dead",
                max_size=max_size,
                bit_rate=bit_rate,
                frame_rate=frame_rate,
                control_enabled=control_enabled,
                audio_enabled=audio_enabled,
            )

        if session.last_frame_ts > 0:
            frame_age = time.monotonic() - float(session.last_frame_ts)
            if frame_age >= _scrcpy_stale_frame_watchdog_sec and not session._control_socket:
                return self._schedule_stream_recovery(
                    device_id,
                    f"stale_frame_{frame_age:.1f}s_control_socket_lost",
                    max_size=max_size,
                    bit_rate=bit_rate,
                    frame_rate=frame_rate,
                    control_enabled=control_enabled,
                    audio_enabled=audio_enabled,
                )

        return False

    async def watchdog_check_rotation(self, device_id: str):
        """Low-frequency rotation check for active scrcpy sessions."""
        session = self._sessions.get(device_id)
        if not session or not session.is_streaming or not session.is_scrcpy:
            return
        if not session.connected_websockets:
            return
        await self._check_rotation_and_recover(device_id, session, "ws_timeout")

    async def start_stream(self, device_id: str, max_size: int = 960,
                           bit_rate: int = 4_000_000, frame_rate: int = 24,
                           restart: bool = False, control_enabled: bool = False,
                           audio_enabled: bool = False) -> dict:
        """
        Start streaming for a device.
        Pure scrcpy mode only.
        """
        start_lock = self._get_start_lock(device_id)
        lock_wait_start = time.monotonic()
        async with start_lock:
            lock_wait_ms = (time.monotonic() - lock_wait_start) * 1000.0
            if lock_wait_ms >= 120.0:
                logger.warning(
                    f"[SCRCPY-START] start lock waited {lock_wait_ms:.0f}ms for {device_id}"
                )
            session = self.get_or_create_session(device_id)
            logger.info(
                f"[SCRCPY-START] request: device={device_id} restart={restart} "
                f"control={control_enabled} audio={audio_enabled} "
                f"max_size={max_size} fps={frame_rate} bit_rate={bit_rate} "
                f"session_streaming={session.is_streaming} session_mode={session.stream_mode or 'none'} "
                f"prefer_no_meta={session._prefer_no_meta}"
            )
            session.max_size = int(max_size)
            session.bit_rate = int(bit_rate)
            session.frame_rate = int(frame_rate)

            if (
                session.is_streaming
                and session.is_scrcpy
                and (session.control_enabled != control_enabled or session.audio_enabled != audio_enabled)
            ):
                restart = True

            if session.is_streaming and restart:
                logger.info(
                    f"[SCRCPY-START] restart requested: device={device_id} "
                    f"current_control={session.control_enabled} current_audio={session.audio_enabled}"
                )
                try:
                    await self.stop_stream(device_id)
                except Exception as e:
                    # ADB may be temporarily busy; continue and try to start a fresh stream.
                    logger.warning(f"restart stop_stream failed for {device_id}: {e}")
                session = self.get_or_create_session(device_id)

            if session.is_streaming:
                logger.info(
                    f"[SCRCPY-START] already running: device={device_id} "
                    f"control={session.control_enabled} audio={session.audio_enabled} "
                    f"video={session.video_width}x{session.video_height} "
                    f"screen={session.screen_width}x{session.screen_height} "
                    f"rotation={session.display_rotation}"
                )
                return {
                    "status": "already_running",
                    "mode": session.stream_mode,
                    "width": session.screen_width,
                    "height": session.screen_height,
                    "fps": session.frame_rate,
                    "control": session.control_enabled,
                    "audio": session.audio_enabled,
                    "audio_codec": session.audio_codec,
                }

            # Cancel any pending auto-stop
            if session._auto_stop_task and not session._auto_stop_task.done():
                session._auto_stop_task.cancel()
                session._auto_stop_task = None

            if not _scrcpy_server_jar:
                raise RuntimeError("scrcpy-server JAR not found; install scrcpy first")
            if not _ffmpeg_available:
                raise RuntimeError("ffmpeg not found; scrcpy streaming requires ffmpeg")

            frame_meta_default = os.getenv("SCRCPY_FRAME_META", "1") == "1"
            if session._prefer_no_meta:
                # Device remembered as frame-meta unstable: start directly with no-meta.
                logger.warning(
                    f"[SCRCPY-META] force no-meta profile for {device_id} (remembered unstable meta)"
                )
                scrcpy_profiles = [
                    ("preferred-no-meta", max_size, bit_rate, frame_rate, False),
                    ("no-meta-retry", max_size, bit_rate, frame_rate, False),
                ]
            else:
                # Retry order:
                # 1) requested profile
                # 2) same profile retry once (helps transient encoder/socket hiccups)
                # 3) requested profile with frame_meta disabled
                scrcpy_profiles = [
                    ("requested", max_size, bit_rate, frame_rate, frame_meta_default),
                    ("same-retry", max_size, bit_rate, frame_rate, frame_meta_default),
                ]
                if frame_meta_default:
                    scrcpy_profiles.append(("no-meta-retry", max_size, bit_rate, frame_rate, False))

            last_error: Optional[Exception] = None
            for idx, (tag, size_i, br_i, fps_i, frame_meta_i) in enumerate(scrcpy_profiles, start=1):
                if idx > 1:
                    logger.warning(
                        f"scrcpy retry for {device_id}: profile={tag}, max_size={size_i}, "
                        f"frame_rate={fps_i}, bit_rate={br_i}, frame_meta={frame_meta_i}, audio={audio_enabled}"
                    )
                try:
                    result = await self._start_scrcpy_stream(
                        session, device_id, size_i, br_i, fps_i,
                        frame_meta=frame_meta_i, control_enabled=control_enabled,
                        audio_enabled=audio_enabled,
                    )
                    if not frame_meta_i and not session._prefer_no_meta:
                        session._prefer_no_meta = True
                        logger.warning(
                            f"[SCRCPY-META] remember no-meta for {device_id}: "
                            "stream started only after frame_meta disabled"
                        )
                    self._schedule_start_nudge(device_id, session)
                    return result
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"scrcpy attempt {idx}/{len(scrcpy_profiles)} failed for {device_id} "
                        f"(profile={tag}, max_size={size_i}, frame_rate={fps_i}, "
                        f"bit_rate={br_i}, frame_meta={frame_meta_i}, audio={audio_enabled}): {e}"
                    )
                    try:
                        if session._stop_event:
                            session._stop_event.set()
                        self._cleanup_scrcpy(session, device_id)
                    except Exception as cleanup_err:
                        logger.debug(f"scrcpy cleanup after failed attempt error for {device_id}: {cleanup_err}")
                    session.is_streaming = False
                    session.is_scrcpy = False
                    session.stream_mode = ""
                    session.control_enabled = False
                    session._control_socket = None
                    session.audio_enabled = False
                    session.audio_codec = ""
                    session._audio_socket = None
                    session.last_frame = None
                    session.last_frame_ts = 0.0
                    session._current_frame_meta = False
                    if idx < len(scrcpy_profiles):
                        await asyncio.sleep(0.4)

            raise RuntimeError(f"scrcpy stream failed for {device_id}: {last_error}")

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
                                    frame_meta: Optional[bool] = None,
                                    control_enabled: bool = False,
                                    audio_enabled: bool = False) -> dict:
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
        stream_begin_ts = time.monotonic()
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

        # Output size for rawvideo frames (long edge follows requested max_size).
        out_width = 0
        out_height = [0]
        target_long_edge = int(max(240, min(2160, max_size)))

        def _ensure_even(v: int) -> int:
            iv = int(max(2, round(v)))
            if iv % 2:
                iv += 1
            return iv

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
            server_cmd = [
                "adb", "-s", device_id, "shell",
                "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
                "app_process", "/", "com.genymobile.scrcpy.Server", "3.3.4",
                f"scid={scid}",
                "video=true", f"audio={'true' if audio_enabled else 'false'}",
                f"control={'true' if control_enabled else 'false'}",
                "video_codec=h264",
                f"max_size={max_size}",
                f"max_fps={frame_rate}",
                f"video_bit_rate={bit_rate}",
                "tunnel_forward=true",
                f"send_frame_meta={'true' if use_frame_meta else 'false'}",
                "log_level=info",
            ]
            if audio_enabled:
                server_cmd.append("audio_codec=raw")
            server_proc = subprocess.Popen(
                server_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
            # Drain server stdout in background to prevent blocking
            threading.Thread(target=lambda: server_proc.stdout.read(), daemon=True).start()
            time.sleep(0.15)

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

            audio_sock = None
            if audio_enabled:
                audio_sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
                audio_sock.settimeout(10)
                for attempt in range(30):
                    try:
                        audio_sock.connect(("127.0.0.1", local_port))
                        break
                    except (ConnectionRefusedError, OSError):
                        time.sleep(0.2)
                else:
                    try:
                        audio_sock.close()
                    except Exception:
                        pass
                    server_proc.terminate()
                    raise ConnectionError(f"Failed to connect scrcpy audio socket on port {local_port}")

            control_sock = None
            if control_enabled:
                control_sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
                control_sock.settimeout(10)
                for attempt in range(30):
                    try:
                        control_sock.connect(("127.0.0.1", local_port))
                        break
                    except (ConnectionRefusedError, OSError):
                        time.sleep(0.2)
                else:
                    try:
                        control_sock.close()
                    except Exception:
                        pass
                    server_proc.terminate()
                    raise ConnectionError(f"Failed to connect scrcpy control socket on port {local_port}")

                # Optional dummy byte from server on control channel.
                try:
                    control_sock.settimeout(0.2)
                    _ = control_sock.recv(1)
                except Exception:
                    pass
                finally:
                    try:
                        control_sock.settimeout(10)
                    except Exception:
                        pass

            video_w = 0
            video_h = 0
            audio_codec = "raw"

            # Read 69-byte header: [1B dummy] [64B device name] [4B codec]
            header = b''
            while len(header) < 69:
                chunk = sock.recv(69 - len(header))
                if not chunk:
                    raise ConnectionError("Socket closed during handshake")
                header += chunk

            device_name = header[1:65].decode('utf-8', errors='replace').rstrip('\x00')
            codec = header[65:69].decode('ascii', errors='replace')
            logger.info(
                f"scrcpy v3 connected: device={device_name}, codec={codec}, "
                f"control={control_enabled}"
            )

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
                        video_w = w
                        video_h = h
                        logger.info(f"scrcpy header meta: size={w}x{h}")
            except Exception:
                pass
            finally:
                try:
                    sock.settimeout(10)
                except Exception:
                    pass

            if audio_sock:
                try:
                    audio_sock.settimeout(0.5)
                    codec_meta = b""
                    while len(codec_meta) < 4:
                        chunk = audio_sock.recv(4 - len(codec_meta))
                        if not chunk:
                            break
                        codec_meta += chunk
                    if len(codec_meta) == 4:
                        audio_codec = codec_meta.decode("ascii", errors="replace").rstrip("\x00")
                except Exception:
                    pass
                finally:
                    try:
                        audio_sock.settimeout(10)
                    except Exception:
                        pass

            return server_proc, sock, audio_sock, control_sock, video_w, video_h, audio_codec

        server_proc, video_socket, audio_socket, control_socket, video_w, video_h, audio_codec = await loop.run_in_executor(None, _deploy_and_connect)
        connect_ready_ms = (time.monotonic() - stream_begin_ts) * 1000.0
        logger.info(
            f"[SCRCPY-START] transport ready: device={device_id} meta={use_frame_meta} "
            f"control={control_enabled} audio={audio_enabled} connect_ms={connect_ready_ms:.0f}"
        )

        session._server_proc = server_proc
        session._video_socket = video_socket
        session._audio_socket = audio_socket
        session._control_socket = control_socket
        session.control_enabled = bool(control_enabled and control_socket)
        session.audio_enabled = bool(audio_enabled and audio_socket)
        session.audio_codec = audio_codec or "raw"
        session.audio_sample_rate = 48_000
        session.audio_channels = 2
        session.video_width = int(video_w or 0)
        session.video_height = int(video_h or 0)
        session.stream_mode = "scrcpy"
        session.is_scrcpy = True
        session.is_streaming = True
        session._current_frame_meta = bool(use_frame_meta)

        # Get logical screen size for ADB coordinate mapping (rotation-aware).
        base_w, base_h = await self._get_screen_size(device_id)
        rotation = await self._get_display_rotation(device_id)
        session.display_rotation = rotation
        w, h = self._apply_rotation_to_size(base_w, base_h, rotation)
        if w <= 0 or h <= 0:
            w, h = base_w, base_h
        session.screen_width = w
        session.screen_height = h
        src_w = int(session.video_width or w or 0)
        src_h = int(session.video_height or h or 0)
        if src_w > 0 and src_h > 0:
            src_long = max(src_w, src_h)
            long_edge = min(target_long_edge, src_long)
            if src_w >= src_h:
                out_width = long_edge
                out_height[0] = int(round(src_h * long_edge / src_w))
            else:
                out_height[0] = long_edge
                out_width = int(round(src_w * long_edge / src_h))
            out_width = _ensure_even(out_width)
            out_height[0] = _ensure_even(out_height[0])
        else:
            out_width = _ensure_even(target_long_edge)
            if w > 0 and h > 0:
                out_height[0] = _ensure_even(int(round(h * out_width / w)))
            else:
                out_height[0] = _ensure_even(800)
        logger.info(
            f"scrcpy output target: source={src_w}x{src_h} long_edge={target_long_edge} "
            f"scaled={out_width}x{out_height[0]}"
        )

        _valid_frame_event = threading.Event()

        def _switch_no_meta_and_recover(reason: str) -> bool:
            if not use_frame_meta:
                return False
            if not session._prefer_no_meta:
                session._prefer_no_meta = True
                logger.warning(
                    f"[SCRCPY-META] mark device as no-meta preferred: {device_id}, reason={reason}"
                )
            scheduled = self._schedule_stream_recovery(device_id, reason)
            if scheduled:
                stop_event.set()
            return scheduled

        def audio_thread():
            """Audio socket (PCM packets) -> WebSocket broadcast."""
            if not session._audio_socket:
                return
            logger.info(
                f"[SCRCPY-AUDIO] pipe start: device={device_id}, codec={session.audio_codec}, "
                f"meta={use_frame_meta}"
            )

            def read_exact(sock, n: int) -> Optional[bytes]:
                buf = bytearray()
                while len(buf) < n and not stop_event.is_set():
                    try:
                        chunk = sock.recv(n - len(buf))
                        if not chunk:
                            return None
                        buf.extend(chunk)
                    except socket_mod.timeout:
                        continue
                    except Exception:
                        return None
                return bytes(buf) if len(buf) == n else None

            try:
                while not stop_event.is_set():
                    if use_frame_meta:
                        hdr = read_exact(session._audio_socket, 12)
                        if not hdr:
                            break
                        pts_flags = int.from_bytes(hdr[0:8], "big", signed=False)
                        payload_len = int.from_bytes(hdr[8:12], "big", signed=False)
                        if payload_len <= 0 or payload_len > 512_000:
                            logger.warning(
                                f"[SCRCPY-AUDIO] invalid packet length for {device_id}: {payload_len}"
                            )
                            _switch_no_meta_and_recover("audio_invalid_packet_len")
                            break
                        payload = read_exact(session._audio_socket, payload_len)
                        if not payload:
                            break
                        # config packet marker (highest bit) has no PCM payload to play
                        if pts_flags & (1 << 63):
                            continue
                        if _main_loop and not _main_loop.is_closed():
                            asyncio.run_coroutine_threadsafe(
                                self._broadcast_audio(session, payload), _main_loop
                            )
                    else:
                        try:
                            data = session._audio_socket.recv(8192)
                        except socket_mod.timeout:
                            continue
                        if not data:
                            break
                        if _main_loop and not _main_loop.is_closed():
                            asyncio.run_coroutine_threadsafe(
                                self._broadcast_audio(session, data), _main_loop
                            )
            except Exception as e:
                logger.warning(f"[SCRCPY-AUDIO] thread stopped for {device_id}: {e}")
            finally:
                logger.info(f"[SCRCPY-AUDIO] pipe stopped for {device_id}")

        if session.audio_enabled and session._audio_socket:
            threading.Thread(target=audio_thread, daemon=True, name=f"scrcpy-audio-{device_id}").start()

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
                decode_error_streak = 0
                decode_recover_triggered = False
                decode_error_markers = (
                    "error while decoding",
                    "failed to parse header of nalu",
                    "invalid data found when processing input",
                    "mb_skip_run",
                    "concealing ",
                )

                def parse_stderr():
                    nonlocal decode_error_streak, decode_recover_triggered
                    try:
                        for line in ffmpeg_proc.stderr:
                            if stop_event.is_set():
                                break
                            decoded = line.decode('utf-8', errors='replace').strip()
                            if not decoded:
                                continue
                            stderr_tail.append(decoded)
                            if 'Stream #0:0' in decoded and 'Video:' in decoded:
                                m = re.search(r'(\d+)x(\d+)', decoded)
                                if m:
                                    pw, ph = int(m.group(1)), int(m.group(2))
                                    if pw == out_width and out_height[0] == 0:
                                        out_height[0] = ph
                                        logger.info(f"scrcpy ffmpeg output: {pw}x{ph}")
                            lower = decoded.lower()
                            is_decode_error = any(marker in lower for marker in decode_error_markers)
                            if is_decode_error:
                                decode_error_streak += 1
                                logger.warning(f"scrcpy ffmpeg stderr: {decoded}")
                                if (
                                    not decode_recover_triggered
                                    and decode_error_streak >= _scrcpy_decode_error_streak_threshold
                                ):
                                    decode_recover_triggered = True
                                    if use_frame_meta and not session._prefer_no_meta:
                                        session._prefer_no_meta = True
                                        logger.warning(
                                            f"[SCRCPY-META] mark device as no-meta preferred: {device_id}, "
                                            "reason=decode_error_streak"
                                        )
                                    logger.warning(
                                        f"[SCRCPY-DECODE] decode error streak hit {decode_error_streak} "
                                        f"for {device_id}, forcing stream rebuild "
                                        f"(rotation={session.display_rotation}, "
                                        f"video={session.video_width}x{session.video_height}, "
                                        f"screen={session.screen_width}x{session.screen_height}, "
                                        f"meta={session._current_frame_meta})"
                                    )
                                    scheduled = self._schedule_stream_recovery(
                                        device_id, f"decode_error_streak_{decode_error_streak}"
                                    )
                                    if scheduled:
                                        stop_event.set()
                            else:
                                decode_error_streak = 0
                                if 'error' in lower or 'invalid' in lower:
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
                                                logger.warning(
                                                    "scrcpy frame-meta fixed12 header invalid, forcing no-meta restart"
                                                )
                                                _switch_no_meta_and_recover("frame_meta_fixed12_invalid")
                                                break
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
                        first_frame_ms = (time.monotonic() - stream_begin_ts) * 1000.0
                        logger.info(f"scrcpy first frame decoded ✅ ({first_frame_ms:.0f}ms)")
                        first_frame = False
                    _valid_frame_event.set()
                    session.last_frame = jpeg_bytes
                    session.last_frame_ts = time.monotonic()
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
        def _wait_first_frame_or_stop() -> bool:
            deadline = time.monotonic() + _scrcpy_first_frame_timeout
            while time.monotonic() < deadline:
                if _valid_frame_event.wait(timeout=0.2):
                    return True
                if stop_event.is_set():
                    return False
            return _valid_frame_event.is_set()

        got_valid = await loop.run_in_executor(
            None, _wait_first_frame_or_stop
        )

        if not got_valid:
            logger.warning(f"scrcpy+ffmpeg produced no frames for {device_id}")
            stop_event.set()
            self._cleanup_scrcpy(session, device_id)
            session.is_streaming = False
            session.is_scrcpy = False
            session.stream_mode = ""
            session.last_frame = None
            session.last_frame_ts = 0.0
            raise RuntimeError(f"scrcpy+ffmpeg produced no frames for {device_id}")

        logger.info(f"scrcpy stream started for {device_id} ({w}x{h} @{frame_rate}fps) ✅ ✅")
        logger.info(
            f"[SCRCPY-START] ready summary: device={device_id} "
            f"screen={w}x{h} video_meta={session.video_width}x{session.video_height} "
            f"output={out_width}x{out_height[0]} rotation={session.display_rotation} "
            f"meta={use_frame_meta} total_ms={(time.monotonic() - stream_begin_ts) * 1000.0:.0f}"
        )
        return {
            "status": "started",
            "mode": "scrcpy",
            "width": w,
            "height": h,
            "fps": frame_rate,
            "control": session.control_enabled,
            "audio": session.audio_enabled,
            "audio_codec": session.audio_codec,
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

        if session._audio_socket:
            try:
                session._audio_socket.close()
            except Exception:
                pass
            session._audio_socket = None
        session.audio_enabled = False
        session.audio_codec = ""
        session.audio_sample_rate = 48_000
        session.audio_channels = 2

        if session._control_socket:
            try:
                session._control_socket.close()
            except Exception:
                pass
            session._control_socket = None
        session.control_enabled = False
        session.video_width = 0
        session.video_height = 0
        session._current_frame_meta = False

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

    async def _get_display_rotation(self, device_id: str) -> int:
        """Get current display rotation (0/1/2/3). Returns -1 if unavailable."""
        loop = asyncio.get_event_loop()

        def _get():
            import re

            def parse_rotation(text: str) -> int:
                if not text:
                    return -1
                patterns = (
                    r"SurfaceOrientation:\s*([0-3])",
                    r"Surface orientation:\s*([0-3])",
                    r"SurfaceOrientation(?:=|\s+)([0-3])",
                    r"mCurrentRotation(?:=|:\s*)([0-3])",
                    r"mRotation(?:=|:\s*)([0-3])",
                    r"mCurrentOrientation(?:=|:\s*)([0-3])",
                    r"orientation(?:=|:\s*|\s+)([0-3])",
                    r"rotation(?:=|:\s*)([0-3])",
                )
                for pattern in patterns:
                    m = re.search(pattern, text, re.IGNORECASE)
                    if not m:
                        continue
                    try:
                        value = int(m.group(1))
                    except Exception:
                        continue
                    if 0 <= value <= 3:
                        return value

                # Some devices print symbolic rotation names.
                symbolic_patterns = (
                    r"mCurrentRotation(?:=|:\s*)ROTATION_(0|90|180|270)",
                    r"mRotation(?:=|:\s*)ROTATION_(0|90|180|270)",
                    r"rotation(?:=|:\s*)ROTATION_(0|90|180|270)",
                )
                symbolic_map = {0: 0, 90: 1, 180: 2, 270: 3}
                for pattern in symbolic_patterns:
                    m = re.search(pattern, text, re.IGNORECASE)
                    if not m:
                        continue
                    try:
                        deg = int(m.group(1))
                    except Exception:
                        continue
                    if deg in symbolic_map:
                        return symbolic_map[deg]

                m = re.search(r"^\s*([0-3])\s*$", text.strip())
                if m:
                    try:
                        return int(m.group(1))
                    except Exception:
                        pass
                return -1

            cmds = [
                ["adb", "-s", device_id, "shell", "dumpsys", "input"],
                ["adb", "-s", device_id, "shell", "dumpsys", "window", "displays"],
                ["adb", "-s", device_id, "shell", "dumpsys", "display"],
                ["adb", "-s", device_id, "shell", "settings", "get", "system", "user_rotation"],
                ["adb", "-s", device_id, "shell", "settings", "get", "secure", "user_rotation"],
            ]

            for cmd in cmds:
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    text = (result.stdout or "") + "\n" + (result.stderr or "")
                    rotation = parse_rotation(text)
                    if rotation >= 0:
                        return rotation
                except Exception:
                    continue

            return -1

        return await loop.run_in_executor(None, _get)

    @staticmethod
    def _apply_rotation_to_size(width: int, height: int, rotation: int) -> tuple[int, int]:
        if width <= 0 or height <= 0:
            return width, height
        if rotation in (1, 3):
            return height, width
        return width, height

    async def _check_rotation_and_recover(self, device_id: str, session: ScrcpySession, trigger: str) -> bool:
        """Check device rotation; restart stream if orientation changed."""
        if not session.is_scrcpy or not session.is_streaming:
            return False

        now = time.monotonic()
        if now - float(session._last_rotation_check_ts or 0.0) < _scrcpy_rotation_check_interval_sec:
            return False
        session._last_rotation_check_ts = now

        rotation = await self._get_display_rotation(device_id)
        if rotation < 0:
            return False
        if session.display_rotation < 0:
            session.display_rotation = rotation
            frame_landscape = False
            if session.video_width > 0 and session.video_height > 0:
                frame_landscape = session.video_width > session.video_height
            logical_landscape = rotation in (1, 3)
            if frame_landscape != logical_landscape:
                logger.warning(
                    f"[SCRCPY-ROTATE] baseline rotation fixed for {device_id}: -1->{rotation}, "
                    f"trigger={trigger}, scheduling stream restart "
                    f"(video={session.video_width}x{session.video_height}, "
                    f"screen={session.screen_width}x{session.screen_height}, meta={session._current_frame_meta})"
                )
                return self._schedule_stream_recovery(
                    device_id, f"orientation_unknown_to_{rotation}"
                )
            return False
        if rotation == session.display_rotation:
            return False

        old_rotation = session.display_rotation
        session.display_rotation = rotation

        base_w, base_h = await self._get_screen_size(device_id)
        logical_w, logical_h = self._apply_rotation_to_size(base_w, base_h, rotation)
        if logical_w > 0 and logical_h > 0:
            session.screen_width = logical_w
            session.screen_height = logical_h

        logger.warning(
            f"[SCRCPY-ROTATE] orientation changed for {device_id}: {old_rotation}->{rotation}, "
            f"trigger={trigger}, scheduling stream restart "
            f"(video={session.video_width}x{session.video_height}, "
            f"screen={session.screen_width}x{session.screen_height}, meta={session._current_frame_meta})"
        )
        scheduled = self._schedule_stream_recovery(device_id, f"orientation_{old_rotation}_to_{rotation}")
        if scheduled:
            try:
                await self._broadcast_control(
                    session,
                    {
                        "type": "rotation_switching",
                        "from": old_rotation,
                        "to": rotation,
                        "trigger": trigger,
                    },
                )
            except Exception:
                pass
        return scheduled

    # ──────────────────────────────────────────────────────────────────────
    # Stream control
    # ──────────────────────────────────────────────────────────────────────

    async def stop_stream(self, device_id: str) -> dict:
        """Stop streaming for a device."""
        session = self._sessions.get(device_id)
        if not session or not session.is_streaming:
            return {"status": "not_running"}

        recover_task = session._recover_task
        if recover_task:
            try:
                current_task = asyncio.current_task()
            except RuntimeError:
                current_task = None
            try:
                should_cancel = (
                    hasattr(recover_task, "done")
                    and hasattr(recover_task, "cancel")
                    and not recover_task.done()
                    and recover_task is not current_task
                )
            except Exception:
                should_cancel = False
            if should_cancel:
                try:
                    recover_task.cancel()
                except Exception:
                    pass
                session._recover_task = None
            elif hasattr(recover_task, "done") and recover_task.done():
                session._recover_task = None

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

        session.stream_mode = ""
        session.is_scrcpy = False
        session.control_enabled = False
        session._control_socket = None
        session.audio_enabled = False
        session.audio_codec = ""
        session._audio_socket = None
        session.video_width = 0
        session.video_height = 0
        session._current_frame_meta = False
        session.display_rotation = -1
        session._last_rotation_check_ts = 0.0
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
            "fps": session.frame_rate,
            "viewers": len(session.connected_websockets),
            "audio_viewers": len(session.connected_audio_websockets),
            "control": session.control_enabled,
            "audio": session.audio_enabled,
            "audio_codec": session.audio_codec,
            "video_width": session.video_width,
            "video_height": session.video_height,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Touch / Key input
    # ──────────────────────────────────────────────────────────────────────

    async def send_touch(self, device_id: str, action: str, x: float, y: float,
                          width: float, height: float):
        """Send touch event. Coordinates mapped from canvas to device screen."""
        session = self._sessions.get(device_id)
        if not session:
            return
        if action == "down" and session.is_scrcpy:
            restarted_for_rotation = False
            try:
                restarted_for_rotation = await self._check_rotation_and_recover(
                    device_id, session, "touch_down"
                )
            except Exception:
                restarted_for_rotation = False
            if restarted_for_rotation:
                # Drop current touch; stream is restarting with new orientation.
                return
            if not (session._client_thread and session._client_thread.is_alive()):
                self._schedule_stream_recovery(device_id, "touch_video_thread_dead")

        # For scrcpy control injection, map from current canvas/frame size to scrcpy video size.
        src_w = int(max(1, round(width))) if width > 0 else 0
        src_h = int(max(1, round(height))) if height > 0 else 0
        ctrl_w = int(session.video_width or 0)
        ctrl_h = int(session.video_height or 0)
        if ctrl_w <= 0 or ctrl_h <= 0:
            ctrl_w = src_w if src_w > 0 else max(1, int(session.screen_width or 1))
            ctrl_h = src_h if src_h > 0 else max(1, int(session.screen_height or 1))
        if src_w > 0 and src_h > 0:
            ctrl_x = int(x * ctrl_w / src_w)
            ctrl_y = int(y * ctrl_h / src_h)
        else:
            ctrl_x = int(max(0, round(x)))
            ctrl_y = int(max(0, round(y)))
        ctrl_x = max(0, min(ctrl_x, ctrl_w - 1))
        ctrl_y = max(0, min(ctrl_y, ctrl_h - 1))

        if width > 0 and height > 0 and session.screen_width > 0 and session.screen_height > 0:
            device_x = int(x * session.screen_width / width)
            device_y = int(y * session.screen_height / height)
        else:
            device_x, device_y = int(x), int(y)

        device_x = max(0, min(device_x, session.screen_width - 1))
        device_y = max(0, min(device_y, session.screen_height - 1))

        if self._can_use_scrcpy_control(session):
            action_map = {"down": 0, "up": 1, "move": 2}
            action_i = action_map.get(action)
            if action_i is not None:
                pressure = 0.0 if action_i == 1 else 1.0
                if _scrcpy_control_debug and action in ("down", "up"):
                    logger.debug(
                        "[SCRCPY-CTRL] touch enqueue: "
                        f"device={device_id} action={action} ctrl=({ctrl_x},{ctrl_y}) "
                        f"frame={ctrl_w}x{ctrl_h} src={src_w}x{src_h} adb_map=({device_x},{device_y}) "
                        f"video_meta={session.video_width}x{session.video_height}"
                    )
                payload = self._pack_scrcpy_touch_message(
                    action=action_i,
                    pointer_id=0,
                    x=ctrl_x,
                    y=ctrl_y,
                    screen_width=ctrl_w,
                    screen_height=ctrl_h,
                    pressure=pressure,
                    action_button=0,
                    buttons=0,
                )
                if self._send_scrcpy_control_packet(session, device_id, payload, "touch"):
                    if _scrcpy_control_debug and action in ("down", "up"):
                        logger.debug(
                            "[SCRCPY-CTRL] touch sent: "
                            f"device={device_id} action={action}"
                        )
                    return
                logger.warning(
                    "[SCRCPY-CTRL] touch control send failed, fallback adb: "
                    f"device={device_id} action={action}"
                )
                self._schedule_stream_recovery(device_id, "touch_control_send_failed")
        elif action == "down" and session.is_scrcpy and _scrcpy_control_debug:
            logger.debug(
                "[SCRCPY-CTRL] touch control inactive, use adb: "
                f"device={device_id} control_enabled={session.control_enabled} "
                f"has_socket={bool(session._control_socket)}"
            )
            if not session._control_socket:
                self._schedule_stream_recovery(device_id, "touch_control_socket_missing")

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

        # For scrcpy control injection, map from current canvas/frame size to scrcpy video size.
        src_w = int(max(1, round(width))) if width > 0 else 0
        src_h = int(max(1, round(height))) if height > 0 else 0
        ctrl_w = int(session.video_width or 0)
        ctrl_h = int(session.video_height or 0)
        if ctrl_w <= 0 or ctrl_h <= 0:
            ctrl_w = src_w if src_w > 0 else max(1, int(session.screen_width or 1))
            ctrl_h = src_h if src_h > 0 else max(1, int(session.screen_height or 1))
        if src_w > 0 and src_h > 0:
            ctrl_x = int(x * ctrl_w / src_w)
            ctrl_y = int(y * ctrl_h / src_h)
        else:
            ctrl_x = int(max(0, round(x)))
            ctrl_y = int(max(0, round(y)))
        ctrl_x = max(0, min(ctrl_x, ctrl_w - 1))
        ctrl_y = max(0, min(ctrl_y, ctrl_h - 1))

        if width > 0 and height > 0:
            device_x = int(x * session.screen_width / width)
            device_y = int(y * session.screen_height / height)
        else:
            device_x, device_y = int(x), int(y)

        device_x = max(0, min(device_x, session.screen_width - 1))
        device_y = max(0, min(device_y, session.screen_height - 1))

        if self._can_use_scrcpy_control(session):
            v_scroll = -1.0 if delta_y > 0 else 1.0
            if _scrcpy_control_debug:
                logger.debug(
                    "[SCRCPY-CTRL] scroll enqueue: "
                    f"device={device_id} ctrl=({ctrl_x},{ctrl_y}) frame={ctrl_w}x{ctrl_h} "
                    f"src={src_w}x{src_h} adb_map=({device_x},{device_y}) "
                    f"video_meta={session.video_width}x{session.video_height} delta_y={delta_y}"
                )
            payload = self._pack_scrcpy_scroll_message(
                x=ctrl_x,
                y=ctrl_y,
                screen_width=ctrl_w,
                screen_height=ctrl_h,
                h_scroll=0.0,
                v_scroll=v_scroll,
                buttons=0,
            )
            if self._send_scrcpy_control_packet(session, device_id, payload, "scroll"):
                if _scrcpy_control_debug:
                    logger.debug(f"[SCRCPY-CTRL] scroll sent: device={device_id}")
                return
            logger.warning(f"[SCRCPY-CTRL] scroll control send failed, fallback adb: device={device_id}")
            self._schedule_stream_recovery(device_id, "scroll_control_send_failed")

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
        session = self._sessions.get(device_id)
        if self._can_use_scrcpy_control(session):
            if _scrcpy_control_debug:
                logger.debug(f"[SCRCPY-CTRL] key enqueue: device={device_id} keycode={keycode}")
            down = self._pack_scrcpy_key_message(action=0, keycode=keycode, repeat=0, meta_state=0)
            up = self._pack_scrcpy_key_message(action=1, keycode=keycode, repeat=0, meta_state=0)
            if self._send_scrcpy_control_packet(session, device_id, down, "key-down"):
                if self._send_scrcpy_control_packet(session, device_id, up, "key-up"):
                    if _scrcpy_control_debug:
                        logger.debug(f"[SCRCPY-CTRL] key sent: device={device_id} keycode={keycode}")
                    return
            logger.warning(f"[SCRCPY-CTRL] key control send failed, fallback adb: device={device_id} keycode={keycode}")
            self._schedule_stream_recovery(device_id, "key_control_send_failed")
        elif _scrcpy_control_debug and session and session.is_scrcpy:
            logger.debug(
                "[SCRCPY-CTRL] key control inactive, use adb: "
                f"device={device_id} keycode={keycode} control_enabled={session.control_enabled} "
                f"has_socket={bool(session._control_socket)}"
            )

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

    async def _broadcast_audio(self, session: ScrcpySession, audio_bytes: bytes):
        """Broadcast PCM audio packets to audio WebSockets."""
        if not session.connected_audio_websockets:
            return
        dead = set()
        for ws in list(session.connected_audio_websockets):
            try:
                await ws.send_bytes(audio_bytes)
            except Exception:
                dead.add(ws)
        for ws in dead:
            session.connected_audio_websockets.discard(ws)

    async def _broadcast_control(self, session: ScrcpySession, message: dict):
        """Broadcast JSON control message to video WebSockets."""
        if not session.connected_websockets:
            return
        payload = json.dumps(message, ensure_ascii=False)
        dead = set()
        for ws in list(session.connected_websockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            session.connected_websockets.discard(ws)

    @staticmethod
    def _has_any_viewers(session: ScrcpySession) -> bool:
        return bool(session.connected_websockets or session.connected_audio_websockets)

    def _schedule_auto_stop_if_needed(self, device_id: str, session: ScrcpySession):
        if self._has_any_viewers(session) or not session.is_streaming:
            return
        if _scrcpy_auto_stop_delay <= 0:
            logger.info(
                f"No-viewer auto-stop disabled for {device_id}; stream kept alive"
            )
            return
        if _main_loop and not _main_loop.is_closed():
            session._auto_stop_task = asyncio.ensure_future(
                self._auto_stop_after_delay(device_id, _scrcpy_auto_stop_delay)
            )

    def add_viewer(self, device_id: str, websocket) -> ScrcpySession:
        """Add a WebSocket viewer to a session."""
        session = self.get_or_create_session(device_id)
        session.connected_websockets.add(websocket)
        if session._auto_stop_task and not session._auto_stop_task.done():
            session._auto_stop_task.cancel()
            session._auto_stop_task = None
        return session

    def add_audio_viewer(self, device_id: str, websocket) -> ScrcpySession:
        """Add an audio WebSocket viewer to a session."""
        session = self.get_or_create_session(device_id)
        session.connected_audio_websockets.add(websocket)
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
        self._schedule_auto_stop_if_needed(device_id, session)

    def remove_audio_viewer(self, device_id: str, websocket):
        """Remove an audio WebSocket viewer and schedule optional auto-stop."""
        session = self._sessions.get(device_id)
        if not session:
            return
        session.connected_audio_websockets.discard(websocket)
        self._schedule_auto_stop_if_needed(device_id, session)

    async def _auto_stop_after_delay(self, device_id: str, delay: int):
        try:
            await asyncio.sleep(delay)
            session = self._sessions.get(device_id)
            if session and not self._has_any_viewers(session) and session.is_streaming:
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
