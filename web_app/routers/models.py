# -*- coding: utf-8 -*-
"""
Models API router.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from web_app.auth import verify_token
from web_app.services.model_service import model_service

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelServiceCreate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    model_name: str = ""
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    description: str = ""
    protocol: str = "openai"
    category: str = ""


class ModelServiceUpdate(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str = ""
    model_name: str = ""
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    description: str = ""
    is_active: bool = False
    protocol: str = "openai"
    category: str = ""


class TestConfigRequest(BaseModel):
    base_url: str
    api_key: str = ""
    model_name: str = ""
    protocol: str = "openai"


@router.get("")
async def get_models(_: bool = Depends(verify_token)):
    """Get all model services."""
    services = model_service.get_all_services()
    return {"services": services}


@router.get("/active")
async def get_active_model(_: bool = Depends(verify_token)):
    """Get the currently active model service."""
    service = model_service.get_active_service_dict()
    if not service:
        raise HTTPException(status_code=404, detail="No active model service")
    return service


@router.get("/presets")
async def get_preset_templates(_: bool = Depends(verify_token)):
    """Get preset model service templates."""
    presets = model_service.get_preset_templates()
    return {"presets": presets}


@router.get("/{service_id}")
async def get_model(service_id: str, _: bool = Depends(verify_token)):
    """Get a specific model service."""
    service = model_service.get_service_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.post("")
async def create_model(
    request: ModelServiceCreate,
    _: bool = Depends(verify_token)
):
    """Create a new model service."""
    data = request.model_dump()
    success = model_service.add_service(data)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to create service")
    return {"success": True, "message": "Service created"}


@router.put("/{service_id}")
async def update_model(
    service_id: str,
    request: ModelServiceUpdate,
    _: bool = Depends(verify_token)
):
    """Update an existing model service."""
    if request.id != service_id:
        raise HTTPException(status_code=400, detail="Service ID mismatch")

    data = request.model_dump()
    success = model_service.update_service(data)
    if not success:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"success": True, "message": "Service updated"}


@router.delete("/{service_id}")
async def delete_model(service_id: str, _: bool = Depends(verify_token)):
    """Delete a model service."""
    success = model_service.delete_service(service_id)
    if not success:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"success": True, "message": "Service deleted"}


@router.post("/{service_id}/activate")
async def activate_model(service_id: str, _: bool = Depends(verify_token)):
    """Activate a model service."""
    success = model_service.activate_service(service_id)
    if not success:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"success": True, "message": "Service activated"}


@router.post("/{service_id}/test")
async def test_model(service_id: str, _: bool = Depends(verify_token)):
    """Test a model service connection."""
    success, message = model_service.test_service(service_id)
    return {"success": success, "message": message}


@router.post("/test")
async def test_model_config(
    request: TestConfigRequest,
    _: bool = Depends(verify_token)
):
    """Test a model configuration without saving."""
    data = request.model_dump()
    success, message = model_service.test_service_config(data)
    return {"success": success, "message": message}
