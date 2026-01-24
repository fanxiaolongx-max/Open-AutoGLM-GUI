# -*- coding: utf-8 -*-
"""
Chat router for managing chat sessions and messages.
Provides REST API for the chat interface with persistent SQLite storage.
"""

import base64
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel

from web_app.services.chat_service import chat_service
from web_app.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ========== Request/Response Models ==========

class CreateSessionRequest(BaseModel):
    device_id: str
    title: Optional[str] = ""


class AddMessageRequest(BaseModel):
    role: str
    content: str
    image: Optional[str] = None  # Base64 encoded image


class AddLogRequest(BaseModel):
    content: str
    log_type: Optional[str] = "info"


class AddScreenshotRequest(BaseModel):
    image: str  # Base64 encoded
    description: Optional[str] = ""


# ========== Session Endpoints ==========

@router.get("/sessions")
async def get_sessions(
    limit: int = Query(50, ge=1, le=200),
    device_id: Optional[str] = None,
    _: bool = Depends(verify_token)
):
    """Get list of chat sessions."""
    return chat_service.get_sessions(limit, device_id)


@router.post("/sessions")
async def create_session(
    request: CreateSessionRequest,
    _: bool = Depends(verify_token)
):
    """Create a new chat session."""
    return chat_service.create_session(request.device_id, request.title)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, _: bool = Depends(verify_token)):
    """Get a session by ID."""
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/detail")
async def get_session_detail(session_id: str, _: bool = Depends(verify_token)):
    """Get full session detail including messages, logs, and screenshots."""
    detail = chat_service.get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, _: bool = Depends(verify_token)):
    """Delete a session and all related data."""
    success = chat_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@router.patch("/sessions/{session_id}/status")
async def update_session_status(
    session_id: str,
    status: str = Query(..., regex="^(active|completed|failed)$"),
    _: bool = Depends(verify_token)
):
    """Update session status."""
    success = chat_service.update_session_status(session_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


# ========== Message Endpoints ==========

@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    _: bool = Depends(verify_token)
):
    """Get messages for a session."""
    return chat_service.get_messages(session_id, limit)


@router.post("/sessions/{session_id}/messages")
async def add_message(
    session_id: str,
    request: AddMessageRequest,
    _: bool = Depends(verify_token)
):
    """Add a message to a session."""
    # Check session exists
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Decode image if provided
    image_data = None
    if request.image:
        try:
            # Handle data URL format
            if "," in request.image:
                _, encoded = request.image.split(",", 1)
            else:
                encoded = request.image
            image_data = base64.b64decode(encoded)
        except Exception as e:
            logger.error(f"Failed to decode image: {e}")

    return chat_service.add_message(session_id, request.role, request.content, image_data)


class UpdateMessageRequest(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None
    todo_list: Optional[list] = None


@router.patch("/sessions/{session_id}/messages/{message_id}")
async def update_message(
    session_id: str,
    message_id: str,
    request: UpdateMessageRequest,
    _: bool = Depends(verify_token)
):
    """Update message fields (content, status, todo_list)."""
    success = chat_service.update_message(
        message_id,
        content=request.content,
        status=request.status,
        todo_list=request.todo_list
    )
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or no updates")
    return {"success": True}


# ========== Log Endpoints ==========

@router.get("/sessions/{session_id}/logs")
async def get_logs(
    session_id: str,
    message_id: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    _: bool = Depends(verify_token)
):
    """Get logs for a session or specific message."""
    return chat_service.get_logs(session_id, message_id, limit)


@router.post("/sessions/{session_id}/messages/{message_id}/logs")
async def add_log(
    session_id: str,
    message_id: str,
    request: AddLogRequest,
    _: bool = Depends(verify_token)
):
    """Add a log entry for a message."""
    return chat_service.add_log(session_id, message_id, request.content, request.log_type)


# ========== Screenshot Endpoints ==========

@router.get("/sessions/{session_id}/screenshots")
async def get_screenshots(
    session_id: str,
    message_id: Optional[str] = None,
    _: bool = Depends(verify_token)
):
    """Get screenshot metadata for a session."""
    return chat_service.get_screenshots(session_id, message_id)


@router.post("/sessions/{session_id}/messages/{message_id}/screenshots")
async def add_screenshot(
    session_id: str,
    message_id: str,
    request: AddScreenshotRequest,
    _: bool = Depends(verify_token)
):
    """Add a screenshot for a message."""
    try:
        # Handle data URL format
        if "," in request.image:
            _, encoded = request.image.split(",", 1)
        else:
            encoded = request.image
        image_data = base64.b64decode(encoded)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image data: {e}")

    return chat_service.add_screenshot(session_id, message_id, image_data, request.description)


@router.get("/screenshots/{screenshot_id}")
async def get_screenshot_image(screenshot_id: str):
    """Get screenshot image by ID (returns PNG image)."""
    image_data = chat_service.get_screenshot(screenshot_id)
    if not image_data:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return Response(content=image_data, media_type="image/png")


# ========== Legacy Endpoints (backward compatibility) ==========

@router.get("/history")
async def get_history(limit: int = 50, _: bool = Depends(verify_token)):
    """Legacy: Get recent messages across all sessions."""
    return chat_service.get_history(limit)


@router.post("/messages")
async def add_legacy_message(request: AddMessageRequest, _: bool = Depends(verify_token)):
    """Legacy: Add a message (creates session if needed)."""
    # Get or create a default session
    sessions = chat_service.get_sessions(limit=1)
    if sessions and sessions[0].get("status") == "active":
        session_id = sessions[0]["id"]
    else:
        # Create a new session with a default device
        session = chat_service.create_session("default", "Legacy Chat")
        session_id = session["id"]

    # Decode image if provided
    image_data = None
    if request.image:
        try:
            if "," in request.image:
                _, encoded = request.image.split(",", 1)
            else:
                encoded = request.image
            image_data = base64.b64decode(encoded)
        except Exception:
            pass

    return chat_service.add_message(session_id, request.role, request.content, image_data)


@router.delete("/history")
async def clear_history(_: bool = Depends(verify_token)):
    """Legacy: Clear history (deprecated - does nothing)."""
    chat_service.clear_history()
    return {"success": True, "message": "This endpoint is deprecated. Use DELETE /sessions/{id} instead."}


# ========== Cleanup Endpoint ==========

@router.post("/cleanup")
async def cleanup_old_sessions(
    days: int = Query(30, ge=1, le=365),
    _: bool = Depends(verify_token)
):
    """Clean up sessions older than specified days."""
    count = chat_service.cleanup_old_sessions(days)
    return {"success": True, "deleted_sessions": count}
