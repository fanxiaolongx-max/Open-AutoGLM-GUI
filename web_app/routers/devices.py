# -*- coding: utf-8 -*-
"""
Devices API router.
"""

import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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


class WirelessPairRequest(BaseModel):
    pair_address: str
    pair_code: str


class TcpConnectRequest(BaseModel):
    connect_address: str


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


@router.post("/{device_id}/lock")
async def lock_device(
    device_id: str,
    _: bool = Depends(verify_token)
):
    """Lock a device screen."""
    success = await device_service.lock_device(device_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to lock device")
    return {"success": True, "message": "Device locked"}


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


@router.post("/pair")
async def wireless_pair_device(
    request: WirelessPairRequest,
    _: bool = Depends(verify_token)
):
    """Perform ADB wireless pairing."""
    success, message, logs = await device_service.wireless_pair(
        request.pair_address,
        request.pair_code
    )
    return {
        "success": success,
        "message": message,
        "logs": logs
    }


@router.post("/connect")
async def tcp_connect_device(
    request: TcpConnectRequest,
    _: bool = Depends(verify_token)
):
    """Connect to a device via TCP/IP (adb connect)."""
    success, message, logs = await device_service.tcp_connect(
        request.connect_address
    )
    if success:
        # Refresh devices after successful connection
        await device_service.refresh_devices()
    return {
        "success": success,
        "message": message,
        "logs": logs
    }


@router.post("/disconnect/{device_id}")
async def disconnect_device(device_id: str, _: bool = Depends(verify_token)):
    """Disconnect a device."""
    success, message = await device_service.disconnect_device(device_id)
    if success:
        await device_service.refresh_devices()
    return {"success": success, "message": message}


@router.post("/{device_id}/install-apk")
async def install_apk(
    device_id: str,
    file: UploadFile = File(...),
    _: bool = Depends(verify_token)
):
    """Install an APK file on the device."""
    # Validate file extension
    if not file.filename.lower().endswith('.apk'):
        raise HTTPException(status_code=400, detail="只支持 APK 文件")

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    try:
        # Write uploaded file
        content = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(content)

        # Install APK
        success, message, logs = await device_service.install_apk(device_id, temp_path)

        return {
            "success": success,
            "message": message,
            "logs": logs
        }
    finally:
        # Cleanup temp file
        try:
            os.remove(temp_path)
            os.rmdir(temp_dir)
        except Exception:
            pass


# File management endpoints
@router.get("/{device_id}/files")
async def list_files(
    device_id: str,
    path: str = "/sdcard",
    _: bool = Depends(verify_token)
):
    """List files in a directory on the device."""
    success, files, message = await device_service.list_files(device_id, path)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "path": path, "files": files}


@router.get("/{device_id}/files/download")
async def download_file(
    device_id: str,
    path: str,
    _: bool = Depends(verify_token)
):
    """Download a file from the device."""
    success, content, filename, message = await device_service.pull_file(device_id, path)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/{device_id}/files/upload")
async def upload_file(
    device_id: str,
    path: str = Form(...),
    file: UploadFile = File(...),
    _: bool = Depends(verify_token)
):
    """Upload a file to the device."""
    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    try:
        content = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(content)

        # Push file to device
        remote_path = f"{path}/{file.filename}" if not path.endswith('/') else f"{path}{file.filename}"
        success, message = await device_service.push_file(device_id, temp_path, remote_path)

        return {"success": success, "message": message, "remote_path": remote_path}
    finally:
        try:
            os.remove(temp_path)
            os.rmdir(temp_dir)
        except Exception:
            pass


@router.delete("/{device_id}/files")
async def delete_file(
    device_id: str,
    path: str,
    _: bool = Depends(verify_token)
):
    """Delete a file on the device."""
    success, message = await device_service.delete_file(device_id, path)
    return {"success": success, "message": message}
