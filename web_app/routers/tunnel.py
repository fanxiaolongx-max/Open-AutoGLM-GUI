# -*- coding: utf-8 -*-
"""
Cloudflare Quick Tunnel router.
Manages a `cloudflared tunnel --url` subprocess to expose the local server
via a temporary *.trycloudflare.com URL. No account required.
"""

import asyncio
import logging
import os
import re
import secrets
import shutil
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends
from web_app.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tunnel", tags=["tunnel"])

# ── Global state ──────────────────────────────────────────────────────────────
_process: asyncio.subprocess.Process | None = None
_tunnel_url: str = ""
_status: str = "stopped"  # stopped | starting | running | error
_error_msg: str = ""
_access_token: str = ""

TUNNEL_TOKEN_PARAM = "tunnel_token"
TUNNEL_TOKEN_COOKIE = "autoglm_tunnel_token"


def _build_tunnel_url_with_token(base_url: str, token: str) -> str:
    """Append tunnel token as query parameter to the public URL."""
    if not base_url or not token:
        return base_url
    parsed = urlparse(base_url)
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != TUNNEL_TOKEN_PARAM]
    query_items.append((TUNNEL_TOKEN_PARAM, token))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def get_public_tunnel_url() -> str:
    """Get tunnel URL with access token included."""
    return _build_tunnel_url_with_token(_tunnel_url, _access_token)


def should_require_tunnel_token(request_host: str) -> bool:
    """
    Require tunnel token only when request host equals current public tunnel host.
    Local/LAN direct access will not be affected.
    """
    if not _tunnel_url or not _access_token or not request_host:
        return False
    tunnel_host = (urlparse(_tunnel_url).hostname or "").lower()
    return request_host.lower() == tunnel_host


def validate_tunnel_access_token(token: str) -> bool:
    """Validate tunnel access token."""
    return bool(token) and bool(_access_token) and token == _access_token


async def _stop_process():
    """Terminate the cloudflared subprocess if running."""
    global _process, _status, _tunnel_url, _error_msg, _access_token
    if _process and _process.returncode is None:
        try:
            _process.terminate()
            try:
                await asyncio.wait_for(_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                _process.kill()
                await _process.wait()
        except ProcessLookupError:
            pass
    _process = None
    _tunnel_url = ""
    _status = "stopped"
    _error_msg = ""
    _access_token = ""


async def shutdown_tunnel():
    """Called during app shutdown to clean up."""
    await _stop_process()


async def _read_tunnel_url(proc: asyncio.subprocess.Process):
    """Read stderr from cloudflared to extract the tunnel URL."""
    global _tunnel_url, _status, _error_msg, _access_token
    url_pattern = re.compile(r"(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)")

    try:
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                logger.debug(f"[cloudflared] {text}")
                m = url_pattern.search(text)
                if m:
                    _tunnel_url = m.group(1)
                    if not _access_token:
                        _access_token = secrets.token_urlsafe(24)
                    _status = "running"
                    logger.info(f"Cloudflare Tunnel URL: {_tunnel_url} (token enabled)")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error reading cloudflared output: {e}")

    # If process exited without giving us a URL
    if not _tunnel_url and _status == "starting":
        _status = "error"
        _error_msg = "cloudflared exited without providing a URL"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def tunnel_status(_: bool = Depends(verify_token)):
    """Return current tunnel status."""
    installed = shutil.which("cloudflared") is not None
    return {
        "installed": installed,
        "status": _status,
        "url": get_public_tunnel_url(),
        "base_url": _tunnel_url,
        "error": _error_msg,
    }


@router.post("/start")
async def tunnel_start(_: bool = Depends(verify_token)):
    """Start a cloudflared quick tunnel."""
    global _process, _status, _tunnel_url, _error_msg, _access_token

    # Check if cloudflared is installed
    if not shutil.which("cloudflared"):
        return {
            "success": False,
            "error": "cloudflared 未安装。请运行: brew install cloudflared",
            "status": "stopped",
        }

    # Already running
    if _status == "running" and _process and _process.returncode is None:
        return {"success": True, "url": get_public_tunnel_url(), "status": "running"}

    # Clean up any previous process
    await _stop_process()

    _status = "starting"
    _error_msg = ""
    _tunnel_url = ""
    _access_token = ""

    # Determine port from config
    try:
        from web_app.config import config_manager
        port = config_manager.get_config().port
    except Exception:
        port = 8080

    try:
        null_config = os.devnull
        logger.info(
            f"[TUNNEL-CONFIG] start cloudflared with explicit null config: {null_config}"
        )
        _process = await asyncio.create_subprocess_exec(
            # Keep --config as a global flag (before subcommand) so cloudflared
            # won't auto-load ~/.cloudflared/config.yaml|config.yml.
            "cloudflared",
            "--config", null_config,
            "tunnel",
            "--url", f"http://127.0.0.1:{port}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        # Start background reader
        asyncio.create_task(_read_tunnel_url(_process))

        # Wait up to 15s for the URL to appear
        for _ in range(30):
            await asyncio.sleep(0.5)
            if _tunnel_url:
                return {"success": True, "url": get_public_tunnel_url(), "status": "running"}
            if _process.returncode is not None:
                _status = "error"
                _error_msg = f"cloudflared exited with code {_process.returncode}"
                return {"success": False, "error": _error_msg, "status": "error"}

        # Timeout
        _status = "error"
        _error_msg = "Timeout waiting for tunnel URL"
        await _stop_process()
        return {"success": False, "error": _error_msg, "status": "error"}

    except FileNotFoundError:
        _status = "error"
        _error_msg = "cloudflared 未找到"
        return {"success": False, "error": _error_msg, "status": "error"}
    except Exception as e:
        _status = "error"
        _error_msg = str(e)
        logger.error(f"Failed to start tunnel: {e}")
        return {"success": False, "error": _error_msg, "status": "error"}


@router.post("/stop")
async def tunnel_stop(_: bool = Depends(verify_token)):
    """Stop the running cloudflared tunnel."""
    await _stop_process()
    return {"success": True, "status": "stopped"}
