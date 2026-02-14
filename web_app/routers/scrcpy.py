# -*- coding: utf-8 -*-
"""
Scrcpy streaming router - REST + WebSocket endpoints for real-time device screen
mirroring and touch interaction.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from web_app.auth import verify_token
from web_app.config import config_manager
from web_app.services.scrcpy_service import scrcpy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scrcpy", tags=["scrcpy"])


@router.post("/{device_id}/start")
async def start_stream(
    device_id: str,
    max_size: int = Query(960, ge=240, le=2160),
    bit_rate: int = Query(4_000_000, ge=500_000, le=20_000_000),
    frame_rate: int = Query(24, ge=5, le=60),
    restart: bool = Query(False),
    control: bool = Query(False),
    _: bool = Depends(verify_token),
):
    """Start scrcpy stream for a device."""
    result = await scrcpy_service.start_stream(
        device_id,
        max_size=max_size,
        bit_rate=bit_rate,
        frame_rate=frame_rate,
        restart=restart,
        control_enabled=control,
    )
    return result


@router.post("/{device_id}/stop")
async def stop_stream(device_id: str, _: bool = Depends(verify_token)):
    """Stop scrcpy stream for a device."""
    result = await scrcpy_service.stop_stream(device_id)
    return result


@router.get("/{device_id}/status")
async def stream_status(device_id: str, _: bool = Depends(verify_token)):
    """Get stream status for a device."""
    return scrcpy_service.get_stream_status(device_id)


@router.websocket("/ws/{device_id}")
async def scrcpy_websocket(websocket: WebSocket, device_id: str):
    """
    WebSocket endpoint for scrcpy video streaming and touch control.

    Binary messages (server -> client): JPEG frames
    JSON messages (server -> client): stream_info, ping
    JSON messages (client -> server): touch, key, pong
    """
    # Authentication check
    config = config_manager.get_config()
    if config.auth_enabled:
        token = websocket.query_params.get("token", "")
        if not config_manager.validate_token(token):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    await websocket.accept()
    logger.info(f"Scrcpy WebSocket connected for device {device_id} ✅ ✅ ✅")
    qs = websocket.query_params
    try:
        req_max_size = int(qs.get("max_size", "960"))
    except ValueError:
        req_max_size = 960
    try:
        req_bit_rate = int(qs.get("bit_rate", "4000000"))
    except ValueError:
        req_bit_rate = 4_000_000
    try:
        req_frame_rate = int(qs.get("frame_rate", "24"))
    except ValueError:
        req_frame_rate = 24
    req_max_size = max(240, min(2160, req_max_size))
    req_bit_rate = max(500_000, min(20_000_000, req_bit_rate))
    req_frame_rate = max(5, min(60, req_frame_rate))
    req_control = str(qs.get("control", "0")).lower() in ("1", "true", "yes", "on")

    # Add viewer to session
    session = scrcpy_service.add_viewer(device_id, websocket)

    try:
        # Auto-start stream if not running. If requested control mode differs,
        # restart stream to apply the new input path.
        if session.is_streaming and session.is_scrcpy and session.control_enabled != req_control:
            logger.info(
                f"[SCRCPY-CTRL] mode switch requested: device={device_id} "
                f"current_control={session.control_enabled} requested_control={req_control}"
            )
            await scrcpy_service.stop_stream(device_id)
            session = scrcpy_service.get_or_create_session(device_id)

        if not session.is_streaming:
            result = await scrcpy_service.start_stream(
                device_id,
                max_size=req_max_size,
                bit_rate=req_bit_rate,
                frame_rate=req_frame_rate,
                control_enabled=req_control,
            )
            # Refresh session reference after start
            session = scrcpy_service.get_session(device_id)

        # Send stream info
        if session:
            logger.info(
                f"[SCRCPY-CTRL] ws session ready: device={device_id} "
                f"requested_control={req_control} active_control={session.control_enabled} "
                f"mode={session.stream_mode}"
            )
            await websocket.send_text(json.dumps({
                "type": "stream_info",
                "width": session.screen_width,
                "height": session.screen_height,
                "fps": session.frame_rate,
                "mode": "scrcpy" if session.is_scrcpy else "fallback",
                "control": session.control_enabled,
                "video_width": session.video_width,
                "video_height": session.video_height,
            }))

            # Send last frame if available (immediate display)
            if session.last_frame:
                try:
                    await websocket.send_bytes(session.last_frame)
                except Exception:
                    pass

        # Main message loop
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )

                try:
                    message = json.loads(data)
                    msg_type = message.get("type", "")

                    if msg_type == "touch":
                        await scrcpy_service.send_touch(
                            device_id,
                            action=message.get("action", "down"),
                            x=message.get("x", 0),
                            y=message.get("y", 0),
                            width=message.get("width", 0),
                            height=message.get("height", 0),
                        )

                    elif msg_type == "key":
                        await scrcpy_service.send_key(
                            device_id,
                            keycode=message.get("keycode", 0),
                        )

                    elif msg_type == "scroll":
                        await scrcpy_service.send_scroll(
                            device_id,
                            x=message.get("x", 0),
                            y=message.get("y", 0),
                            width=message.get("width", 0),
                            height=message.get("height", 0),
                            delta_y=message.get("deltaY", 0),
                        )

                    elif msg_type == "pong":
                        pass

                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send ping
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Scrcpy WebSocket error for {device_id}: {e}")
    finally:
        scrcpy_service.remove_viewer(device_id, websocket)
        logger.info(f"Scrcpy WebSocket disconnected for device {device_id}")
