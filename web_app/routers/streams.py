# -*- coding: utf-8 -*-
"""
RTSP streams API: config and MJPEG endpoints for 4-grid monitor.
Streams are pulled and transcoded on the server so they work via Cloudflare tunnel.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web_app.auth import verify_token, verify_token_header_or_query
from web_app.services.stream_service import (
    get_stream_config,
    set_stream_config,
    stream_rtsp_as_mjpeg,
)

router = APIRouter(prefix="/api/streams", tags=["streams"])


class StreamItem(BaseModel):
    url: str = ""
    name: str = ""


class StreamConfigBody(BaseModel):
    streams: list = []  # list of { url, name }, up to 4


@router.get("/config")
async def streams_get_config(_: bool = Depends(verify_token)):
    """Get RTSP stream list (4 slots)."""
    return {"streams": get_stream_config()}


@router.post("/config")
async def streams_set_config(
    body: StreamConfigBody,
    _: bool = Depends(verify_token),
):
    """Set RTSP stream list (up to 4 items)."""
    normalized = set_stream_config(body.streams or [])
    return {"streams": normalized}


@router.get("/{index:int}/mjpeg")
async def stream_mjpeg(
    index: int,
    _: bool = Depends(verify_token_header_or_query),
):
    """
    Stream camera at index (0..3) as MJPEG.
    Server pulls RTSP and transcodes with ffmpeg; works through Cloudflare tunnel.
    """
    if index < 0 or index >= 4:
        raise HTTPException(status_code=404, detail="Invalid stream index")
    config = get_stream_config()
    url = (config[index].get("url") or "").strip()
    if not url or not url.startswith("rtsp://"):
        raise HTTPException(status_code=404, detail="No RTSP URL configured for this slot")

    gen = stream_rtsp_as_mjpeg(index)
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        raise HTTPException(status_code=502, detail="Stream failed to start (check ffmpeg and RTSP URL)")

    if not first or not isinstance(first, (list, tuple)) or len(first) != 2:
        raise HTTPException(status_code=502, detail="Stream error")

    first_chunk, media_type = first

    async def body():
        yield first_chunk
        async for item in gen:
            chunk, _ = item if isinstance(item, (list, tuple)) else (item, None)
            if chunk:
                yield chunk

    return StreamingResponse(
        body(),
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
