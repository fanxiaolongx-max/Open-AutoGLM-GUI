# -*- coding: utf-8 -*-
"""
FastAPI main application for Open-AutoGLM-GUI Web Server.

This module provides a web-based interface as an alternative to the GUI,
supporting headless systems and multi-user web access.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_app.config import config_manager
from web_app.routers import (
    devices_router,
    tasks_router,
    scheduler_router,
    models_router,
    settings_router,
    websocket_router,
    chat_router,
    rules_router,
    telegram_router,
)
from web_app.services.scheduler_service import scheduler_service
from web_app.services.device_service import device_service

logger = logging.getLogger(__name__)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    import asyncio

    # Startup
    logger.info("Starting AutoGLM Web Server...")

    # Set the main event loop for thread-safe WebSocket callbacks
    from web_app.routers.websocket import set_main_loop
    set_main_loop(asyncio.get_event_loop())
    logger.info("Main event loop registered for WebSocket callbacks")

    # Start the scheduler
    await scheduler_service.start()
    logger.info("Scheduler started")

    # Register scheduler callback to execute tasks
    def on_scheduled_task(task_id: str, task_content: str):
        """Callback when a scheduled task should run."""
        import asyncio
        from web_app.services.task_service import task_service
        from web_app.services.device_service import device_service

        # Get task to find devices
        task = scheduler_service.get_task(task_id)
        if not task:
            logger.error(f"Scheduled task {task_id} not found")
            return

        device_ids = task.devices if task.devices else []
        if not device_ids:
            # Use all connected devices if none specified
            devices = device_service.get_all_devices()
            device_ids = [d.id for d in devices]

        if not device_ids:
            logger.warning(f"No devices available for scheduled task {task_id}")
            scheduler_service.mark_task_finished(task_id)
            return

        logger.info(f"Running scheduled task {task_id}: {task_content[:50]}...")

        # Run task in background
        async def run_scheduled():
            try:
                result = await task_service.run_task(task_content, device_ids, is_scheduled=True, task_type="scheduled")
                # Record log
                success_count = sum(1 for r in result.results if r.get("success", False))
                failed_count = len(result.results) - success_count
                success = result.status == "completed" and failed_count == 0
                message = f"完成: {success_count} 成功, {failed_count} 失败"
                details = "\n".join(result.logs) if result.logs else ""
                scheduler_service.add_task_log(task_id, success, message, details)
            except Exception as e:
                logger.error(f"Scheduled task {task_id} failed: {e}")
                scheduler_service.add_task_log(task_id, False, f"执行失败: {str(e)}", "")
            finally:
                scheduler_service.mark_task_finished(task_id)

        asyncio.create_task(run_scheduled())

    scheduler_service.add_task_callback(on_scheduled_task)
    logger.info("Scheduler callback registered")

    # Refresh devices on startup
    from web_app.services.device_service import device_service
    await device_service.refresh_devices()
    logger.info("Devices refreshed")

    # Start Telegram bot if enabled
    telegram_bot_started = False
    try:
        from web_app.services.telegram_bot import telegram_bot_service
        from web_app.routers.telegram import load_telegram_config
        from datetime import datetime
        
        telegram_config = load_telegram_config()
        
        if telegram_config.get("enabled") and telegram_config.get("bot_token"):
            await telegram_bot_service.start(telegram_config)
            logger.info("Telegram bot started")
            telegram_bot_started = True
            
            # Wire up device service with telegram bot for notifications
            device_service.set_telegram_bot(telegram_bot_service)
            
            # Wire up scheduler service with telegram bot for task notifications
            scheduler_service.set_telegram_bot(telegram_bot_service)
            
            # Start device monitoring
            await device_service.start_device_monitoring()
            logger.info("Device monitoring started")
            
            # Send startup notification to groups
            device_count = len(device_service.get_all_devices())
            startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            startup_msg = (
                f"✅ *AutoGLM 系统已启动*\n\n"
                f"⏰ 时间: `{startup_time}`\n"
                f"📱 设备: {device_count} 台已连接\n"
                f"🤖 状态: 已就绪"
            )
            await telegram_bot_service.send_system_notification(startup_msg)
            logger.info("Startup notification sent")
    except Exception as e:
        logger.warning(f"Failed to start Telegram bot: {e}")


    yield

    # Shutdown
    logger.info("Shutting down AutoGLM Web Server...")
    
    # Stop device monitoring
    try:
        from web_app.services.device_service import device_service
        if device_service._monitoring_task and not device_service._monitoring_task.done():
            device_service._monitoring_task.cancel()
            try:
                await device_service._monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("Device monitoring stopped")
    except Exception as e:
        logger.warning(f"Error stopping device monitoring: {e}")
    
    # Stop Telegram bot
    try:
        from web_app.services.telegram_bot import telegram_bot_service
        await telegram_bot_service.stop()
        logger.info("Telegram bot stopped")
    except Exception as e:
        logger.warning(f"Error stopping Telegram bot: {e}")
    
    await scheduler_service.stop()
    logger.info("Scheduler stopped")



# Create FastAPI app
app = FastAPI(
    title="AutoGLM Web Server",
    description="Web interface for Open-AutoGLM-GUI - AI-powered phone automation",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
config = config_manager.get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(devices_router)
app.include_router(tasks_router)
app.include_router(scheduler_router)
app.include_router(models_router)
app.include_router(settings_router)
app.include_router(websocket_router)
app.include_router(chat_router)
app.include_router(rules_router)
app.include_router(telegram_router)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """Serve the main page."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        # Add no-cache headers to prevent browser caching
        # This ensures users always get the latest HTML/JavaScript code
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {
        "message": "AutoGLM Web Server",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "name": "AutoGLM Web API",
        "version": "0.1.0",
        "endpoints": {
            "devices": "/api/devices",
            "tasks": "/api/tasks",
            "scheduler": "/api/scheduler",
            "models": "/api/models",
            "settings": "/api/settings",
            "websocket": "/ws",
        },
        "docs": "/docs",
    }
