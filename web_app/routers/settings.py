# -*- coding: utf-8 -*-
"""
Settings API router.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from web_app.auth import verify_token
from web_app.config import config_manager
from web_app.services.email_service import email_service
from phone_agent.config import SCREENSHOT_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class EmailConfigRequest(BaseModel):
    smtp_server: str = ""
    smtp_port: int = 465
    use_ssl: bool = True
    use_tls: bool = False
    sender_email: str = ""
    sender_password: str = ""
    recipient_emails: str = ""
    enabled: bool = False


class WebConfigRequest(BaseModel):
    auth_enabled: bool = False
    cors_origins: list[str] = ["*"]


# Email settings
@router.get("/email")
async def get_email_config(_: bool = Depends(verify_token)):
    """Get email configuration."""
    config = email_service.get_config()
    # Don't expose password
    config["sender_password"] = "***" if config.get("sender_password") else ""
    return config


@router.put("/email")
async def update_email_config(
    request: EmailConfigRequest,
    _: bool = Depends(verify_token)
):
    """Update email configuration."""
    data = request.model_dump()

    # If password is masked, keep existing
    if data["sender_password"] == "***":
        existing = email_service.get_config()
        data["sender_password"] = existing.get("sender_password", "")

    success = email_service.update_config(data)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update config")
    return {"success": True, "message": "Email configuration updated"}


@router.post("/email/test")
async def test_email(_: bool = Depends(verify_token)):
    """Send a test email."""
    success, message = email_service.send_test_email()
    return {"success": success, "message": message}


# Web server settings
@router.get("/web")
async def get_web_config(_: bool = Depends(verify_token)):
    """Get web server configuration."""
    config = config_manager.get_config()
    return {
        "host": config.host,
        "port": config.port,
        "auth_enabled": config.auth_enabled,
        "cors_origins": config.cors_origins,
    }


@router.put("/web")
async def update_web_config(
    request: WebConfigRequest,
    _: bool = Depends(verify_token)
):
    """Update web server configuration."""
    config_manager.update_config(
        auth_enabled=request.auth_enabled,
        cors_origins=request.cors_origins,
    )
    return {"success": True, "message": "Web configuration updated"}


@router.post("/web/generate-token")
async def generate_auth_token(_: bool = Depends(verify_token)):
    """Generate a new authentication token."""
    token = config_manager.generate_auth_token()
    return {"success": True, "token": token}


# Screenshot settings
CONFIG_FILE = Path(__file__).parent.parent.parent / "config" / "screenshot_settings.json"


class ScreenshotSettings(BaseModel):
    """Screenshot configuration settings."""
    max_image_dimension: int = Field(ge=100, le=4000, description="Maximum image dimension")
    jpeg_quality: int = Field(ge=1, le=100, description="JPEG quality (1-100)")


def load_config_from_file() -> Dict[str, Any]:
    """Load screenshot config from file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
    return {}


def save_config_to_file(config: Dict[str, Any]) -> None:
    """Save screenshot config to file."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved screenshot config to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save config file: {e}")
        raise


@router.get("/screenshot")
async def get_screenshot_settings(_: bool = Depends(verify_token)) -> ScreenshotSettings:
    """Get current screenshot settings."""
    return ScreenshotSettings(
        max_image_dimension=SCREENSHOT_CONFIG.max_image_dimension,
        jpeg_quality=SCREENSHOT_CONFIG.jpeg_quality
    )


@router.put("/screenshot")
async def update_screenshot_settings(
    settings: ScreenshotSettings,
    _: bool = Depends(verify_token)
) -> Dict[str, str]:
    """Update screenshot settings."""
    try:
        # Update runtime config
        SCREENSHOT_CONFIG.max_image_dimension = settings.max_image_dimension
        SCREENSHOT_CONFIG.jpeg_quality = settings.jpeg_quality
        
        # Persist to file
        save_config_to_file({
            "max_image_dimension": settings.max_image_dimension,
            "jpeg_quality": settings.jpeg_quality
        })
        
        logger.info(f"Updated screenshot config: dimension={settings.max_image_dimension}, quality={settings.jpeg_quality}")
        return {"status": "success", "message": "Screenshot settings updated"}
    except Exception as e:
        logger.error(f"Failed to update screenshot settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

