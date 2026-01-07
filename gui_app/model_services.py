# -*- coding: utf-8 -*-
"""
模型服务配置管理模块
支持多个第三方模型服务的配置、测试和激活
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    OpenAI = None


@dataclass
class ModelServiceConfig:
    """单个模型服务配置"""
    id: str = ""  # 唯一标识
    name: str = ""  # 服务名称（用于显示）
    base_url: str = ""  # API 基础地址
    api_key: str = ""  # API 密钥
    model_name: str = ""  # 模型名称
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    is_active: bool = False  # 是否为当前激活的服务
    description: str = ""  # 服务描述

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]


# 预置的服务模板
PRESET_SERVICES = [
    ModelServiceConfig(
        id="bigmodel",
        name="智谱BigModel",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="",
        model_name="autoglm-phone",
        description="智谱AI官方API，支持AutoGLM-Phone模型",
        is_active=True,
    ),
    ModelServiceConfig(
        id="gemini_antigravity",
        name="Gemini (Antigravity代理)",
        base_url="http://127.0.0.1:8045/v1",
        api_key="sk-985786ae787d43e6b8d42688f39ed83a",
        model_name="gemini-3-pro-high",
        description="使用Antigravity代理的Gemini API服务",
        temperature=0.7,
        max_tokens=4000,
    ),
    ModelServiceConfig(
        id="modelscope",
        name="ModelScope (魔搭社区)",
        base_url="https://api-inference.modelscope.cn/v1",
        api_key="",
        model_name="autoglm-phone-9b",
        description="阿里云魔搭社区模型推理服务",
    ),
    ModelServiceConfig(
        id="local_vllm",
        name="本地部署 (vLLM)",
        base_url="http://localhost:8000/v1",
        api_key="EMPTY",
        model_name="autoglm-phone-9b",
        description="使用vLLM本地部署的模型服务",
    ),
    ModelServiceConfig(
        id="local_lmdeploy",
        name="本地部署 (LMDeploy)",
        base_url="http://localhost:23333/v1",
        api_key="EMPTY",
        model_name="autoglm-phone-9b",
        description="使用LMDeploy本地部署的模型服务",
    ),
    ModelServiceConfig(
        id="openai_compat",
        name="OpenAI兼容服务",
        base_url="http://localhost:8000/v1",
        api_key="",
        model_name="",
        description="任何OpenAI API兼容的模型服务",
    ),
]


class ModelServicesManager:
    """模型服务管理器"""

    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化管理器

        Args:
            config_dir: 配置文件目录，默认为用户配置目录
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 默认使用 ~/.config/autoglm-gui/ 或应用目录
            config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            self.config_dir = Path(config_home) / "autoglm-gui"

        self.config_file = self.config_dir / "model_services.json"
        self.services: list[ModelServiceConfig] = []
        self._load()

    def _load(self):
        """从配置文件加载服务配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.services = []
                for item in data.get("services", []):
                    service = ModelServiceConfig(**item)
                    self.services.append(service)
                # 确保至少有一个激活的服务
                if self.services and not any(s.is_active for s in self.services):
                    self.services[0].is_active = True
            except Exception as e:
                print(f"加载模型服务配置失败: {e}")
                self._init_default()
        else:
            self._init_default()

    def _init_default(self):
        """初始化默认配置"""
        # 复制预置服务作为初始配置
        self.services = []
        for preset in PRESET_SERVICES:
            service = ModelServiceConfig(
                id=preset.id,
                name=preset.name,
                base_url=preset.base_url,
                api_key=preset.api_key,
                model_name=preset.model_name,
                max_tokens=preset.max_tokens,
                temperature=preset.temperature,
                top_p=preset.top_p,
                frequency_penalty=preset.frequency_penalty,
                is_active=preset.is_active,
                description=preset.description,
            )
            self.services.append(service)
        self._save()

    def _save(self):
        """保存服务配置到文件"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "services": [asdict(s) for s in self.services]
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all_services(self) -> list[ModelServiceConfig]:
        """获取所有服务配置"""
        return self.services.copy()

    def get_active_service(self) -> Optional[ModelServiceConfig]:
        """获取当前激活的服务"""
        for service in self.services:
            if service.is_active:
                return service
        return self.services[0] if self.services else None

    def get_service_by_id(self, service_id: str) -> Optional[ModelServiceConfig]:
        """根据ID获取服务"""
        for service in self.services:
            if service.id == service_id:
                return service
        return None

    def add_service(self, service: ModelServiceConfig) -> bool:
        """添加新服务"""
        # 检查ID是否重复
        if self.get_service_by_id(service.id):
            # 生成新ID
            service.id = str(uuid.uuid4())[:8]

        # 如果是第一个服务，自动激活
        if not self.services:
            service.is_active = True

        self.services.append(service)
        self._save()
        return True

    def update_service(self, service: ModelServiceConfig) -> bool:
        """更新服务配置"""
        for i, s in enumerate(self.services):
            if s.id == service.id:
                self.services[i] = service
                self._save()
                return True
        return False

    def delete_service(self, service_id: str) -> bool:
        """删除服务"""
        for i, service in enumerate(self.services):
            if service.id == service_id:
                was_active = service.is_active
                del self.services[i]
                # 如果删除的是激活服务，激活第一个
                if was_active and self.services:
                    self.services[0].is_active = True
                self._save()
                return True
        return False

    def activate_service(self, service_id: str) -> bool:
        """激活指定服务"""
        found = False
        for service in self.services:
            if service.id == service_id:
                service.is_active = True
                found = True
            else:
                service.is_active = False
        if found:
            self._save()
        return found

    def test_service(self, service: ModelServiceConfig) -> tuple[bool, str]:
        """
        测试服务连接

        Returns:
            (success, message)
        """
        if not HAS_OPENAI:
            return False, "OpenAI 模块未安装，无法测试连接"

        try:
            if not service.base_url:
                return False, "服务地址不能为空"
            if not service.model_name:
                return False, "模型名称不能为空"

            client = OpenAI(
                base_url=service.base_url,
                api_key=service.api_key or "EMPTY",
                timeout=30,  # 增加超时时间到30秒
            )

            # 尝试调用 models 接口
            try:
                models = client.models.list()
                model_ids = [m.id for m in models.data]
                if service.model_name in model_ids:
                    return True, f"连接成功，模型 {service.model_name} 可用"
                else:
                    return True, f"连接成功，但未找到模型 {service.model_name}，可用模型: {', '.join(model_ids[:5])}"
            except Exception as models_error:
                # 有些服务不支持 models 接口，尝试简单的补全请求
                try:
                    response = client.chat.completions.create(
                        model=service.model_name,
                        messages=[{"role": "user", "content": "hi"}],
                        max_tokens=5,
                        timeout=30,  # 明确设置超时
                    )
                    if response and response.choices and len(response.choices) > 0:
                        return True, "连接成功"
                    else:
                        return False, "连接成功但响应为空"
                except Exception as chat_error:
                    return False, f"连接测试失败: models接口错误({str(models_error)[:50]})，聊天接口错误({str(chat_error)[:50]})"
        except Exception as e:
            return False, f"连接错误: {str(e)[:100]}"

    def create_from_preset(self, preset_id: str) -> Optional[ModelServiceConfig]:
        """从预置模板创建新服务"""
        for preset in PRESET_SERVICES:
            if preset.id == preset_id:
                # 创建副本
                new_service = ModelServiceConfig(
                    id=str(uuid.uuid4())[:8],
                    name=f"{preset.name} (副本)",
                    base_url=preset.base_url,
                    api_key=preset.api_key,
                    model_name=preset.model_name,
                    max_tokens=preset.max_tokens,
                    temperature=preset.temperature,
                    top_p=preset.top_p,
                    frequency_penalty=preset.frequency_penalty,
                    is_active=False,
                    description=preset.description,
                )
                return new_service
        return None

    def get_preset_templates(self) -> list[ModelServiceConfig]:
        """获取预置模板列表"""
        return PRESET_SERVICES.copy()
