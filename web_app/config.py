# -*- coding: utf-8 -*-
"""
Web application configuration module.
"""

import json
import os
import secrets
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class WebConfig:
    """Web server configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # Authentication
    auth_enabled: bool = False
    auth_token: str = ""  # Will be auto-generated if auth is enabled

    # CORS
    cors_origins: list = field(default_factory=lambda: ["*"])

    # Static files
    static_dir: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WebConfig":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class WebConfigManager:
    """Manager for web configuration."""

    def __init__(self):
        self.config = self._load()

    def _load(self) -> WebConfig:
        """Load configuration from database."""
        try:
            from web_app.services.config_storage import config_storage
            data = config_storage.get("web_config")
            if data:
                return WebConfig.from_dict(data)
        except Exception:
            pass
        return WebConfig()

    def save(self):
        """Save configuration to database."""
        try:
            from web_app.services.config_storage import config_storage
            config_storage.set("web_config", self.config.to_dict(), "web")
        except Exception:
            pass

    def get_config(self) -> WebConfig:
        """Get current configuration."""
        return self.config

    def update_config(self, **kwargs):
        """Update configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.save()

    def generate_auth_token(self) -> str:
        """Generate a new authentication token."""
        token = secrets.token_urlsafe(32)
        self.config.auth_token = token
        self.save()
        return token

    def validate_token(self, token: str) -> bool:
        """Validate authentication token."""
        if not self.config.auth_enabled:
            return True
        return token == self.config.auth_token


# Global config manager instance
config_manager = WebConfigManager()
