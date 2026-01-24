# -*- coding: utf-8 -*-
"""
Chat service for managing chat sessions and executing chat tasks.
Uses SQLite for persistent storage.
"""

import asyncio
import json
import logging
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from web_app.services.chat_storage import chat_storage, ChatSession, ChatMessage

logger = logging.getLogger(__name__)


class ChatService:
    """Service for managing chat sessions and execution."""

    def __init__(self):
        self._current_session_id: Optional[str] = None
        self._current_message_id: Optional[str] = None

    # ========== Session Management ==========

    def create_session(self, device_id: str, title: str = "") -> Dict:
        """Create a new chat session."""
        session = chat_storage.create_session(device_id, title)
        self._current_session_id = session.id
        return session.to_dict()

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get a session by ID."""
        session = chat_storage.get_session(session_id)
        return session.to_dict() if session else None

    def get_sessions(self, limit: int = 50, device_id: Optional[str] = None) -> List[Dict]:
        """Get recent sessions."""
        sessions = chat_storage.get_sessions(limit, device_id)
        return [s.to_dict() for s in sessions]

    def get_session_detail(self, session_id: str) -> Optional[Dict]:
        """Get full session detail including messages, logs, and screenshots."""
        return chat_storage.get_session_detail(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        return chat_storage.delete_session(session_id)

    def update_session_status(self, session_id: str, status: str) -> bool:
        """Update session status."""
        return chat_storage.update_session(session_id, status=status)

    def update_session_tokens(self, session_id: str, tokens: int) -> bool:
        """Update session total tokens."""
        session = chat_storage.get_session(session_id)
        if session:
            new_total = session.total_tokens + tokens
            return chat_storage.update_session(session_id, total_tokens=new_total)
        return False

    # ========== Message Management ==========

    def add_message(self, session_id: str, role: str, content: str, image_data: Optional[bytes] = None) -> Dict:
        """Add a message to a session, optionally with an image."""
        image_id = None

        # If there's image data, save it as a screenshot first
        if image_data:
            # We'll link it after creating the message
            pass

        message = chat_storage.add_message(session_id, role, content, image_id)
        self._current_message_id = message.id

        # Now save the image if provided
        if image_data:
            screenshot = chat_storage.add_screenshot(
                session_id=session_id,
                message_id=message.id,
                image_data=image_data,
                description="User provided image"
            )
            # Update message with image reference (optional, screenshot is already linked by message_id)

        return message.to_dict()

    def get_messages(self, session_id: str, limit: int = 100) -> List[Dict]:
        """Get messages for a session."""
        messages = chat_storage.get_messages(session_id, limit)
        return [m.to_dict() for m in messages]

    def update_message(self, message_id: str, content: Optional[str] = None,
                       status: Optional[str] = None, todo_list: Optional[list] = None) -> bool:
        """Update message fields (content, status, todo_list)."""
        return chat_storage.update_message(message_id, content, status, todo_list)

    # ========== Log Management ==========

    def add_log(self, session_id: str, message_id: str, content: str, log_type: str = "info") -> Dict:
        """Add a log entry."""
        log = chat_storage.add_log(session_id, message_id, content, log_type)
        return log.to_dict()

    def add_log_to_current(self, content: str, log_type: str = "info") -> Optional[Dict]:
        """Add a log to the current session/message."""
        if self._current_session_id and self._current_message_id:
            return self.add_log(self._current_session_id, self._current_message_id, content, log_type)
        return None

    def get_logs(self, session_id: str, message_id: Optional[str] = None, limit: int = 500) -> List[Dict]:
        """Get logs for a session or message."""
        logs = chat_storage.get_logs(session_id, message_id, limit)
        return [l.to_dict() for l in logs]

    # ========== Screenshot Management ==========

    def add_screenshot(self, session_id: str, message_id: str, image_data: bytes, description: str = "") -> Dict:
        """Add a screenshot."""
        screenshot = chat_storage.add_screenshot(session_id, message_id, image_data, description)
        return screenshot.to_dict(include_data=False)

    def add_screenshot_to_current(self, image_data: bytes, description: str = "") -> Optional[Dict]:
        """Add a screenshot to the current session/message."""
        if self._current_session_id and self._current_message_id:
            return self.add_screenshot(
                self._current_session_id,
                self._current_message_id,
                image_data,
                description
            )
        return None

    def get_screenshot(self, screenshot_id: str) -> Optional[bytes]:
        """Get screenshot image data by ID."""
        screenshot = chat_storage.get_screenshot(screenshot_id)
        return screenshot.image_data if screenshot else None

    def get_screenshots(self, session_id: str, message_id: Optional[str] = None) -> List[Dict]:
        """Get screenshot metadata for a session."""
        return chat_storage.get_screenshots(session_id, message_id)

    # ========== Current Session Context ==========

    def set_current_context(self, session_id: str, message_id: str):
        """Set the current session and message context for logging."""
        self._current_session_id = session_id
        self._current_message_id = message_id

    def get_current_context(self) -> tuple[Optional[str], Optional[str]]:
        """Get the current session and message context."""
        return self._current_session_id, self._current_message_id

    def clear_current_context(self):
        """Clear the current context."""
        self._current_session_id = None
        self._current_message_id = None

    # ========== Cleanup ==========

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Delete sessions older than specified days."""
        return chat_storage.cleanup_old_sessions(days)

    # ========== Legacy Compatibility ==========
    # These methods maintain backward compatibility with the old file-based system

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Legacy: Get recent messages across all sessions."""
        sessions = chat_storage.get_sessions(limit=10)
        all_messages = []
        for session in sessions:
            messages = chat_storage.get_messages(session.id, limit=limit)
            for msg in messages:
                all_messages.append({
                    "id": msg.id,
                    "session_id": msg.session_id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at,
                    "image": None,  # Legacy format
                })
        # Sort by timestamp and limit
        all_messages.sort(key=lambda x: x["timestamp"], reverse=True)
        return all_messages[:limit]

    def clear_history(self):
        """Legacy: This would clear all sessions - use with caution."""
        logger.warning("clear_history called - this is a legacy method")
        # Don't actually clear everything - just log a warning


# Global instance
chat_service = ChatService()
