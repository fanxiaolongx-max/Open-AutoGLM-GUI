# -*- coding: utf-8 -*-
"""
Devices API router.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from web_app.auth import verify_token
from web_app.services.device_service import device_service

router = APIRouter(prefix="/api/devices", tags=["devices"])


class DeviceResponse(BaseModel):
    id: str
    name: str
    platform: str
    status: str
    model: str = ""
    sdk_version: str = ""
    screen_size: str = ""
    connection_type: str = ""


class UnlockRequest(BaseModel):
    pin: Optional[str] = None


class SetPinRequest(BaseModel):
    pin: str


@router.get("", response_model=list[DeviceResponse])
async def get_devices(_: bool = Depends(verify_token)):
    """Get all connected devices."""
    devices = device_service.get_all_devices()
    return [DeviceResponse(**d.to_dict()) for d in devices]


@router.post("/refresh", response_model=list[DeviceResponse])
async def refresh_devices(_: bool = Depends(verify_token)):
    """Refresh and return the list of connected devices."""
    devices = await device_service.refresh_devices()
    return [DeviceResponse(**d.to_dict()) for d in devices]


@router.get("/pins", response_model=None)
async def get_all_device_pins(_: bool = Depends(verify_token)):
    """Get all stored device PINs (masked)."""
    pins = device_service.get_all_pins()
    # Return masked pins (just indicate if set or not)
    masked = {k: True for k in pins.keys()}
    return {"pins": masked}


@router.get("/{device_id}")
async def get_device(device_id: str, _: bool = Depends(verify_token)):
    """Get a specific device by ID."""
    device = device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceResponse(**device.to_dict())


@router.get("/{device_id}/screenshot")
async def get_screenshot(device_id: str, _: bool = Depends(verify_token)):
    """Get a screenshot from the device."""
    screenshot = await device_service.get_screenshot(device_id)
    if not screenshot:
        raise HTTPException(status_code=404, detail="Cannot get screenshot")
    return Response(content=screenshot, media_type="image/png")


@router.get("/{device_id}/screenshot/base64")
async def get_screenshot_base64(device_id: str, _: bool = Depends(verify_token)):
    """Get a screenshot as base64 encoded string."""
    screenshot = await device_service.get_screenshot_base64(device_id)
    if not screenshot:
        raise HTTPException(status_code=404, detail="Cannot get screenshot")
    return {"image": screenshot}


@router.post("/{device_id}/unlock")
async def unlock_device(
    device_id: str,
    request: UnlockRequest = None,
    _: bool = Depends(verify_token)
):
    """Unlock a device."""
    pin = request.pin if request else None
    success = await device_service.unlock_device(device_id, pin)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to unlock device")
    return {"success": True, "message": "Device unlocked"}


@router.post("/{device_id}/pin")
async def set_device_pin(
    device_id: str,
    request: SetPinRequest,
    _: bool = Depends(verify_token)
):
    """Set the PIN for a device."""
    device_service.set_device_pin(device_id, request.pin)
    return {"success": True, "message": "PIN saved"}


@router.put("/{device_id}/pin")
async def update_device_pin(
    device_id: str,
    request: SetPinRequest,
    _: bool = Depends(verify_token)
):
    """Update the PIN for a device."""
    device_service.set_device_pin(device_id, request.pin)
    return {"success": True, "message": "PIN saved"}


@router.get("/{device_id}/pin")
async def get_device_pin(device_id: str, _: bool = Depends(verify_token)):
    """Get the stored PIN for a device."""
    pin = device_service.get_device_pin(device_id)
    return {"pin": pin}
