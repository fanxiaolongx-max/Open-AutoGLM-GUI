"""Screenshot configuration for Phone Agent.

This module defines configurable screenshot compression settings.
Users can customize these values by modifying this file or by setting environment variables.
"""

import os
from dataclasses import dataclass


@dataclass
class ScreenshotConfig:
    """Configuration for screenshot compression settings."""

    # Image compression settings
    max_image_dimension: int = 1920  # Max width or height before resizing
    jpeg_quality: int = 70  # JPEG quality (0-100, higher = better quality, larger size)

    def __post_init__(self):
        """Load values from config file, then environment variables if present."""
        # Try loading from JSON file first
        config_file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config",
            "screenshot_settings.json"
        )
        
        if os.path.exists(config_file_path):
            try:
                import json
                with open(config_file_path, "r") as f:
                    file_config = json.load(f)
                    self.max_image_dimension = file_config.get("max_image_dimension", self.max_image_dimension)
                    self.jpeg_quality = file_config.get("jpeg_quality", self.jpeg_quality)
            except Exception:
                pass  # Fall back to defaults if file can't be loaded
        
        # Environment variables override file config
        self.max_image_dimension = int(
            os.getenv("PHONE_AGENT_MAX_IMAGE_DIMENSION", self.max_image_dimension)
        )
        self.jpeg_quality = int(
            os.getenv("PHONE_AGENT_JPEG_QUALITY", self.jpeg_quality)
        )
        
        # Validate values
        if self.max_image_dimension < 480:
            raise ValueError("max_image_dimension must be at least 480")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")


# Global screenshot configuration instance
# Users can modify these values at runtime or through environment variables
SCREENSHOT_CONFIG = ScreenshotConfig()


def get_screenshot_config() -> ScreenshotConfig:
    """
    Get the global screenshot configuration.

    Returns:
        The global ScreenshotConfig instance.
    """
    return SCREENSHOT_CONFIG


def update_screenshot_config(config: ScreenshotConfig) -> None:
    """
    Update the global screenshot configuration.

    Args:
        config: New screenshot configuration.

    Example:
        >>> from phone_agent.config.screenshot import update_screenshot_config, ScreenshotConfig
        >>> custom_config = ScreenshotConfig(
        ...     max_image_dimension=1080,
        ...     jpeg_quality=80
        ... )
        >>> update_screenshot_config(custom_config)
    """
    global SCREENSHOT_CONFIG
    SCREENSHOT_CONFIG = config


__all__ = [
    "ScreenshotConfig",
    "SCREENSHOT_CONFIG",
    "get_screenshot_config",
    "update_screenshot_config",
]
