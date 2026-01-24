# -*- coding: utf-8 -*-
"""Routers package for web application."""

from web_app.routers.devices import router as devices_router
from web_app.routers.tasks import router as tasks_router
from web_app.routers.scheduler import router as scheduler_router
from web_app.routers.models import router as models_router
from web_app.routers.settings import router as settings_router
from web_app.routers.websocket import router as websocket_router
from web_app.routers.chat import router as chat_router
from web_app.routers.rules import router as rules_router

__all__ = [
    "devices_router",
    "tasks_router",
    "scheduler_router",
    "models_router",
    "settings_router",
    "websocket_router",
    "chat_router",
    "rules_router",
]
