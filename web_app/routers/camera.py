# -*- coding: utf-8 -*-
"""
Camera stream proxy for IP Webcam etc. Proxies MJPEG stream so the frontend
can use same-origin URL (avoids mixed content when UI is served over HTTPS).
"""

import re
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from web_app.auth import verify_token_header_or_query

router = APIRouter(prefix="/api/camera", tags=["camera"])


def _is_safe_stream_url(url: str) -> bool:
    """Allow only http(s) URLs; optionally restrict to private/local IPs."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").strip()
        if not host or host in ("", "localhost"):
            return True
        # Allow private ranges and localhost
        if host in ("127.0.0.1", "::1", "localhost"):
            return True
        # 10.x, 172.16-31.x, 192.168.x
        if re.match(r"^10\.", host) or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host) or re.match(r"^192\.168\.", host):
            return True
        return True  # allow any host; user is responsible
    except Exception:
        return False


@router.get("/proxy")
async def proxy_stream(
    url: str = Query(..., description="Full stream URL, e.g. http://192.168.1.100:8080/videofeed"),
    _: bool = Depends(verify_token_header_or_query),
):
    """
    Proxy MJPEG stream from IP Webcam (or any HTTP MJPEG URL).
    Use in img src to avoid mixed content: /api/camera/proxy?url=http://...
    """
    if not _is_safe_stream_url(url):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid or disallowed stream URL")

    try:
        head = requests.head(url, timeout=3)
        media_type = head.headers.get("Content-Type") or "multipart/x-mixed-replace; boundary=frame"
    except requests.RequestException:
        media_type = "multipart/x-mixed-replace; boundary=frame"

    def stream():
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
        except requests.RequestException:
            pass

    return StreamingResponse(
        stream(),
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
