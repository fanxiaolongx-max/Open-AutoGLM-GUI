# -*- coding: utf-8 -*-
"""
Telegram Bot API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
import json
from pathlib import Path

from web_app.auth import verify_token
from web_app.services.telegram_bot import telegram_bot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

# Configuration file path
CONFIG_FILE = Path(__file__).parent.parent.parent / "config" / "telegram_settings.json"


def load_telegram_config():
    """Load Telegram config from file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load Telegram config: {e}")
    return {
        "bot_token": "",
        "enabled": False,
        "allowed_users": [],
        "send_screenshots": True,
        "send_logs": True
    }


def save_telegram_config(config: dict):
    """Save Telegram config to file."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved Telegram config to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save Telegram config: {e}")
        raise


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""
    bot_token: Optional[str] = None
    enabled: bool = False
    allowed_users: list[int] = []
    send_screenshots: bool = True
    send_logs: bool = True


class TelegramTestRequest(BaseModel):
    """Test Telegram bot connection."""
    bot_token: str


@router.get("/config")
async def get_telegram_config(_: bool = Depends(verify_token)):
    """Get Telegram bot configuration."""
    try:
        config = load_telegram_config()
        
        # Don't expose full bot token, only show if it's set
        return {
            "bot_token": "***" if config.get("bot_token") else "",
            "enabled": config.get("enabled", False),
            "allowed_users": config.get("allowed_users", []),
            "send_screenshots": config.get("send_screenshots", True),
            "send_logs": config.get("send_logs", True),
            "status": "running" if telegram_bot_service._running else "stopped"
        }
    except Exception as e:
        logger.error(f"Failed to get Telegram config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def save_telegram_config_endpoint(config: TelegramConfig, _: bool = Depends(verify_token)):
    """Save Telegram bot configuration."""
    try:
        # Load existing config
        current_config = load_telegram_config()
        
        # Update with new values
        telegram_config = {
            "bot_token": config.bot_token if config.bot_token and config.bot_token != "***" else current_config.get("bot_token", ""),
            "enabled": config.enabled,
            "allowed_users": config.allowed_users,
            "send_screenshots": config.send_screenshots,
            "send_logs": config.send_logs
        }
        
        save_telegram_config(telegram_config)
        
        # Restart bot if enabled
        if config.enabled and telegram_config["bot_token"]:
            try:
                await telegram_bot_service.stop()
                await telegram_bot_service.start(telegram_config)
            except Exception as e:
                logger.error(f"Failed to start Telegram bot: {e}")
                raise HTTPException(status_code=500, detail=f"配置已保存，但启动 Bot 失败: {str(e)}")
        elif not config.enabled:
            await telegram_bot_service.stop()
        
        return {"success": True, "message": "Telegram 配置已保存"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save Telegram config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_telegram_connection(request: TelegramTestRequest, _: bool = Depends(verify_token)):
    """Test Telegram bot connection."""
    try:
        from telegram import Bot
        
        bot = Bot(token=request.bot_token)
        me = await bot.get_me()
        
        return {
            "success": True,
            "bot_info": {
                "username": me.username,
                "first_name": me.first_name,
                "id": me.id
            }
        }
    except Exception as e:
        logger.error(f"Failed to test Telegram connection: {e}")
        raise HTTPException(status_code=400, detail=f"连接测试失败: {str(e)}")


@router.post("/start")
async def start_telegram_bot(_: bool = Depends(verify_token)):
    """Start Telegram bot."""
    try:
        config = load_telegram_config()
        
        if not config.get("bot_token"):
            raise HTTPException(status_code=400, detail="未配置 Bot Token")
        
        await telegram_bot_service.start(config)
        return {"success": True, "message": "Telegram Bot 已启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_telegram_bot(_: bool = Depends(verify_token)):
    """Stop Telegram bot."""
    try:
        await telegram_bot_service.stop()
        return {"success": True, "message": "Telegram Bot 已停止"}
    except Exception as e:
        logger.error(f"Failed to stop Telegram bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))
