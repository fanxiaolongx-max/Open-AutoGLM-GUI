"""
设备 PIN 管理器
使用数据库存储替代 JSON 文件
"""

from typing import Dict, Optional


class DevicePinManager:
    """设备 PIN 配置管理器（数据库存储）"""
    
    def __init__(self):
        # 延迟导入避免循环依赖
        self._storage = None
    
    @property
    def storage(self):
        if self._storage is None:
            from web_app.services.config_storage import config_storage
            self._storage = config_storage
        return self._storage
    
    def get_pin(self, device_id: str) -> Optional[str]:
        """获取设备的 PIN"""
        pins = self.storage.get_device_pins()
        return pins.get(device_id)
    
    def set_pin(self, device_id: str, pin: str):
        """设置设备的 PIN"""
        if pin:
            self.storage.set_device_pin(device_id, pin)
        else:
            self.storage.delete_device_pin(device_id)
    
    def remove_pin(self, device_id: str):
        """移除设备的 PIN"""
        self.storage.delete_device_pin(device_id)
    
    def has_pin(self, device_id: str) -> bool:
        """检查设备是否配置了 PIN"""
        pins = self.storage.get_device_pins()
        return device_id in pins and bool(pins[device_id])
    
    def get_all_pins(self) -> Dict[str, str]:
        """获取所有设备的 PIN 配置"""
        return self.storage.get_device_pins()


# 全局单例
_device_pin_manager: Optional[DevicePinManager] = None


def get_device_pin_manager() -> DevicePinManager:
    """获取设备 PIN 管理器单例"""
    global _device_pin_manager
    if _device_pin_manager is None:
        _device_pin_manager = DevicePinManager()
    return _device_pin_manager
