"""
设备 PIN 管理器
管理每个设备的解锁 PIN 配置
"""

import json
import os
from typing import Dict, Optional


class DevicePinManager:
    """设备 PIN 配置管理器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            # 默认配置文件路径
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(config_dir, "..", "device_pins.json")
        
        self.config_path = os.path.abspath(config_path)
        self._pins: Dict[str, str] = {}
        self._load()
    
    def _load(self):
        """从文件加载 PIN 配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._pins = json.load(f)
        except Exception as e:
            print(f"加载设备 PIN 配置失败: {e}")
            self._pins = {}
    
    def _save(self):
        """保存 PIN 配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._pins, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存设备 PIN 配置失败: {e}")
    
    def get_pin(self, device_id: str) -> Optional[str]:
        """获取设备的 PIN"""
        return self._pins.get(device_id)
    
    def set_pin(self, device_id: str, pin: str):
        """设置设备的 PIN"""
        if pin:
            self._pins[device_id] = pin
        elif device_id in self._pins:
            del self._pins[device_id]
        self._save()
    
    def remove_pin(self, device_id: str):
        """移除设备的 PIN"""
        if device_id in self._pins:
            del self._pins[device_id]
            self._save()
    
    def has_pin(self, device_id: str) -> bool:
        """检查设备是否配置了 PIN"""
        return device_id in self._pins and bool(self._pins[device_id])
    
    def get_all_pins(self) -> Dict[str, str]:
        """获取所有设备的 PIN 配置"""
        return self._pins.copy()


# 全局单例
_device_pin_manager: Optional[DevicePinManager] = None


def get_device_pin_manager() -> DevicePinManager:
    """获取设备 PIN 管理器单例"""
    global _device_pin_manager
    if _device_pin_manager is None:
        _device_pin_manager = DevicePinManager()
    return _device_pin_manager
