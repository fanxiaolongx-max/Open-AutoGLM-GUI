# -*- coding: utf-8 -*-
"""
Rules API router - 规则配置管理 API
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from web_app.auth import verify_token
from gui_app.rules_manager import get_rules_manager

router = APIRouter(prefix="/api/rules", tags=["rules"])


# ========== Pydantic Models ==========

class AppMappingRequest(BaseModel):
    app_name: str
    package_name: str


class AppMappingUpdateRequest(BaseModel):
    new_name: Optional[str] = None
    package_name: str


class TimingUpdateRequest(BaseModel):
    category: str  # "action", "device", or "connection"
    key: str
    value: float


class PromptUpdateRequest(BaseModel):
    content: str


# ========== 应用映射 API ==========

@router.get("/apps")
async def get_app_mappings(_: bool = Depends(verify_token)):
    """获取所有应用映射"""
    manager = get_rules_manager()
    all_apps = manager.get_all_apps()
    custom_apps = manager.get_custom_apps()
    
    result = []
    for name, package in all_apps.items():
        result.append({
            "app_name": name,
            "package_name": package,
            "is_custom": name in custom_apps
        })
    
    # Sort: custom first, then alphabetically
    result.sort(key=lambda x: (not x["is_custom"], x["app_name"]))
    return {"apps": result}


@router.post("/apps")
async def add_app_mapping(
    request: AppMappingRequest,
    _: bool = Depends(verify_token)
):
    """添加应用映射"""
    manager = get_rules_manager()
    
    # Check if exists
    all_apps = manager.get_all_apps()
    if request.app_name in all_apps:
        raise HTTPException(status_code=400, detail="应用名称已存在")
    
    manager.add_app(request.app_name, request.package_name)
    return {"success": True, "message": "应用映射添加成功"}


@router.put("/apps/{app_name}")
async def update_app_mapping(
    app_name: str,
    request: AppMappingUpdateRequest,
    _: bool = Depends(verify_token)
):
    """更新应用映射"""
    manager = get_rules_manager()
    
    # Check if custom
    if not manager.is_custom_app(app_name):
        raise HTTPException(status_code=400, detail="只能编辑自定义应用")
    
    new_name = request.new_name or app_name
    manager.update_app(app_name, new_name, request.package_name)
    return {"success": True, "message": "应用映射更新成功"}


@router.delete("/apps/{app_name}")
async def delete_app_mapping(
    app_name: str,
    _: bool = Depends(verify_token)
):
    """删除应用映射"""
    manager = get_rules_manager()
    
    if not manager.is_custom_app(app_name):
        raise HTTPException(status_code=400, detail="只能删除自定义应用")
    
    success = manager.delete_app(app_name)
    if not success:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    return {"success": True, "message": "应用映射删除成功"}


# ========== 时间配置 API ==========

@router.get("/timing")
async def get_timing_config(_: bool = Depends(verify_token)):
    """获取时间配置"""
    manager = get_rules_manager()
    config = manager.get_timing_config()
    return config


@router.put("/timing")
async def update_timing_config(
    request: TimingUpdateRequest,
    _: bool = Depends(verify_token)
):
    """更新时间配置"""
    manager = get_rules_manager()
    
    if request.category not in ["action", "device", "connection"]:
        raise HTTPException(status_code=400, detail="无效的配置类别")
    
    success = manager.update_timing(request.category, request.key, request.value)
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")
    
    return {"success": True, "message": "时间配置更新成功"}


# ========== 动作规则 API ==========

@router.get("/actions")
async def get_action_rules(_: bool = Depends(verify_token)):
    """获取所有动作规则"""
    manager = get_rules_manager()
    rules = manager.get_action_rules()
    return {"actions": rules}


@router.put("/actions/{name}/rules/{rule_id}/toggle")
async def toggle_rule_item(
    name: str,
    rule_id: str,
    _: bool = Depends(verify_token)
):
    """切换规则项的启用状态"""
    manager = get_rules_manager()
    success = manager.toggle_rule_item(name, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="规则项不存在")
    return {"success": True, "message": "规则状态已切换"}


class RuleItemRequest(BaseModel):
    condition: str
    action: str
    priority: int = 0
    enabled: bool = True


@router.post("/actions/{name}/rules")
async def add_rule_item(
    name: str,
    request: RuleItemRequest,
    _: bool = Depends(verify_token)
):
    """添加规则项"""
    manager = get_rules_manager()
    rule_data = request.model_dump()
    success = manager.add_rule_item(name, rule_data)
    if not success:
        raise HTTPException(status_code=400, detail="添加失败")
    return {"success": True, "message": "规则项添加成功"}


@router.put("/actions/{name}/rules/{rule_id}")
async def update_rule_item(
    name: str,
    rule_id: str,
    request: RuleItemRequest,
    _: bool = Depends(verify_token)
):
    """更新规则项"""
    manager = get_rules_manager()
    updates = request.model_dump()
    success = manager.update_rule_item(name, rule_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="规则项不存在")
    return {"success": True, "message": "规则项更新成功"}


@router.delete("/actions/{name}/rules/{rule_id}")
async def delete_rule_item(
    name: str,
    rule_id: str,
    _: bool = Depends(verify_token)
):
    """删除规则项"""
    manager = get_rules_manager()
    success = manager.delete_rule_item(name, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="规则项不存在")
    return {"success": True, "message": "规则项删除成功"}


@router.post("/actions/reset")
async def reset_action_rules(_: bool = Depends(verify_token)):
    """重置动作规则为默认值"""
    manager = get_rules_manager()
    manager.reset_action_rules()
    return {"success": True, "message": "动作规则已重置为默认值"}


# ========== 提示词 API ==========

@router.get("/prompts")
async def get_prompts(_: bool = Depends(verify_token)):
    """获取所有提示词"""
    manager = get_rules_manager()
    prompts = manager.get_all_prompts()
    return {"prompts": prompts}


@router.put("/prompts/{key}")
async def update_prompt(
    key: str,
    request: PromptUpdateRequest,
    _: bool = Depends(verify_token)
):
    """更新提示词"""
    manager = get_rules_manager()
    success = manager.update_prompt(key, request.content)
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")
    return {"success": True, "message": "提示词更新成功"}


@router.post("/prompts/{key}/reset")
async def reset_prompt(
    key: str,
    _: bool = Depends(verify_token)
):
    """重置提示词为默认值"""
    manager = get_rules_manager()
    success = manager.reset_prompt(key)
    return {"success": True, "message": "提示词已重置为默认值"}
