# -*- coding: utf-8 -*-
"""
Model service for managing AI model configurations.
Wraps the existing ModelServicesManager for web use.
"""

import sys
from pathlib import Path
from typing import Optional
from dataclasses import asdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gui_app.model_services import ModelServicesManager, ModelServiceConfig, PRESET_SERVICES


class ModelService:
    """Service for managing model configurations."""

    def __init__(self):
        self._manager = ModelServicesManager()

    def get_all_services(self) -> list[dict]:
        """Get all model services as dictionaries."""
        return [asdict(s) for s in self._manager.get_all_services()]

    def get_active_service(self) -> Optional[ModelServiceConfig]:
        """Get the currently active service."""
        return self._manager.get_active_service()

    def get_active_service_dict(self) -> Optional[dict]:
        """Get the currently active service as a dictionary."""
        service = self._manager.get_active_service()
        return asdict(service) if service else None

    def get_service_by_id(self, service_id: str) -> Optional[dict]:
        """Get a service by ID."""
        service = self._manager.get_service_by_id(service_id)
        return asdict(service) if service else None

    def add_service(self, data: dict) -> bool:
        """Add a new service from dictionary data."""
        try:
            service = ModelServiceConfig(**data)
            return self._manager.add_service(service)
        except Exception:
            return False

    def update_service(self, data: dict) -> bool:
        """Update an existing service from dictionary data."""
        try:
            service = ModelServiceConfig(**data)
            return self._manager.update_service(service)
        except Exception:
            return False

    def delete_service(self, service_id: str) -> bool:
        """Delete a service."""
        return self._manager.delete_service(service_id)

    def activate_service(self, service_id: str) -> bool:
        """Activate a service."""
        return self._manager.activate_service(service_id)

    def test_service(self, service_id: str) -> tuple[bool, str]:
        """Test a service connection."""
        service = self._manager.get_service_by_id(service_id)
        if not service:
            return False, "Service not found"
        return self._manager.test_service(service)

    def test_service_config(self, data: dict) -> tuple[bool, str]:
        """Test a service configuration without saving."""
        try:
            service = ModelServiceConfig(**data)
            return self._manager.test_service(service)
        except Exception as e:
            return False, str(e)

    def get_preset_templates(self) -> list[dict]:
        """Get preset service templates."""
        return [asdict(s) for s in PRESET_SERVICES]


# Global service instance
model_service = ModelService()
