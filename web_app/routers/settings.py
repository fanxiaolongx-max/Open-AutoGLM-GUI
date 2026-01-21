# -*- coding: utf-8 -*-
"""
Settings API router.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web_app.auth import verify_token
from web_app.config import config_manager
from web_app.services.email_service import email_service

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
