# -*- coding: utf-8 -*-
"""
API Key management service.
Handles generating, storing, listing, and validating API keys for Open API and Agent SKILLs.
"""

import json
import logging
import secrets
import time
from datetime import datetime
from typing import Optional

from web_app.services.config_storage import config_storage

logger = logging.getLogger(__name__)

API_KEYS_STORAGE_KEY = "open_api_keys"


class APIKeyService:
    """Service for managing persistent API keys."""

    def __init__(self):
        self._keys_cache: Optional[list[dict]] = None

    def _load_keys(self) -> list[dict]:
        """Load API keys from persistent SQLite storage."""
        data = config_storage.get(API_KEYS_STORAGE_KEY)
        if isinstance(data, list):
            self._keys_cache = data
            return self._keys_cache
        elif isinstance(data, dict) and "keys" in data:
            self._keys_cache = data["keys"]
            return self._keys_cache

        # First run: initialize with a primary default key
        initial_key = self._create_key_record(name="Default API Key")
        self._keys_cache = [initial_key]
        self._save_keys(self._keys_cache)
        return self._keys_cache

    def _save_keys(self, keys: list[dict]) -> None:
        """Save API keys to SQLite storage."""
        self._keys_cache = keys
        config_storage.set(API_KEYS_STORAGE_KEY, keys, "api_auth")

    def _create_key_record(self, name: str = "Default API Key") -> dict:
        """Create a new key record."""
        # Key format: ak_autoglm_<32 urlsafe chars>
        raw_token = secrets.token_urlsafe(32)
        key_str = f"ak_autoglm_{raw_token}"
        now_iso = datetime.now().isoformat()
        return {
            "key": key_str,
            "name": name,
            "created_at": now_iso,
            "last_used_at": None,
            "is_active": True,
        }

    def get_all_keys(self, mask: bool = True) -> list[dict]:
        """
        Get all API keys.
        If mask is True, masks the secret portion of each key.
        """
        keys = self._load_keys()
        if not mask:
            return keys

        result = []
        for item in keys:
            k = item.get("key", "")
            if len(k) > 16:
                masked = f"{k[:11]}...{k[-4:]}"
            else:
                masked = "***"
            result.append({
                "key": masked,
                "full_key": None,
                "name": item.get("name", ""),
                "created_at": item.get("created_at"),
                "last_used_at": item.get("last_used_at"),
                "is_active": item.get("is_active", True),
            })
        return result

    def get_primary_key(self, unmasked: bool = False) -> dict:
        """Get or create the active primary API key."""
        keys = self._load_keys()
        active_keys = [k for k in keys if k.get("is_active", True)]
        if not active_keys:
            new_key = self.generate_key(name="Primary Key")
            return new_key if unmasked else self._mask_key_record(new_key)

        primary = active_keys[0]
        return primary if unmasked else self._mask_key_record(primary)

    def _mask_key_record(self, item: dict) -> dict:
        k = item.get("key", "")
        masked = f"{k[:11]}...{k[-4:]}" if len(k) > 16 else "***"
        return {
            "key": masked,
            "name": item.get("name", ""),
            "created_at": item.get("created_at"),
            "last_used_at": item.get("last_used_at"),
            "is_active": item.get("is_active", True),
        }

    def generate_key(self, name: str = "New API Key") -> dict:
        """Generate and save a new API key."""
        keys = self._load_keys()
        new_record = self._create_key_record(name=name)
        keys.insert(0, new_record)
        self._save_keys(keys)
        logger.info(f"Generated new API key: {name}")
        return new_record

    def revoke_key(self, key_str: str) -> bool:
        """Revoke / deactivate an API key."""
        keys = self._load_keys()
        found = False
        for item in keys:
            if item.get("key") == key_str:
                item["is_active"] = False
                found = True
                break
        if found:
            self._save_keys(keys)
            logger.info(f"Revoked API key: {key_str[:12]}...")
        return found

    def validate_key(self, token: str) -> bool:
        """
        Validate an API token.
        Returns True if the token exists, is active, and records usage timestamp.
        """
        if not token:
            return False

        clean_token = token.strip()
        # Support Bearer prefix removal
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        keys = self._load_keys()
        for item in keys:
            if item.get("is_active", True) and item.get("key") == clean_token:
                # Update last used timestamp
                item["last_used_at"] = datetime.now().isoformat()
                self._save_keys(keys)
                return True

        # Fallback to config_manager legacy auth_token if configured and enabled
        try:
            from web_app.config import config_manager
            cfg = config_manager.get_config()
            if cfg.auth_enabled and cfg.auth_token and cfg.auth_token == clean_token:
                return True
        except Exception:
            pass

        return False


# Global singleton instance
api_key_service = APIKeyService()
