# -*- coding: utf-8 -*-
"""规则配置管理器 - 管理应用映射、时间延迟等规则的持久化存储"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RuleItem:
    """单条规则项"""
    id: str  # 规则ID
    condition: str  # 条件描述
    action: str  # 执行动作
    priority: int = 0  # 优先级，数值越大优先级越高
    enabled: bool = True  # 是否启用

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RuleItem":
        return cls(**data)


@dataclass
class ActionRule:
    """动作规则定义"""
    name: str  # 动作名称
    description: str  # 动作说明
    parameters: list[dict]  # 参数列表 [{"name": "xxx", "type": "xxx", "required": bool, "description": "xxx"}]
    example: str  # 示例调用
    adb_command: str = ""  # 对应的 ADB 命令（如果有）
    rules: list[dict] = field(default_factory=list)  # 具体规则内容列表
    is_custom: bool = False  # 是否为自定义动作

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActionRule":
        return cls(**data)


# 默认动作规则定义
DEFAULT_ACTION_RULES: list[dict] = [
    {
        "name": "Launch",
        "description": "启动指定应用程序",
        "parameters": [
            {"name": "app", "type": "string", "required": True, "description": "应用名称，如'微信'、'Chrome'"}
        ],
        "example": 'do(action="Launch", app="微信")',
        "adb_command": "adb shell am start -n <package>/<activity>",
        "rules": [
            {"id": "launch_001", "condition": "应用未安装", "action": "返回错误提示，不执行启动", "priority": 10, "enabled": True},
            {"id": "launch_002", "condition": "应用已在前台", "action": "跳过启动，直接返回成功", "priority": 5, "enabled": True},
            {"id": "launch_003", "condition": "应用名称未在映射表中", "action": "尝试模糊匹配或提示用户添加映射", "priority": 3, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Tap",
        "description": "点击屏幕指定坐标位置",
        "parameters": [
            {"name": "element", "type": "list[int]", "required": True, "description": "坐标 [x, y]，范围 0-1000"},
            {"name": "message", "type": "string", "required": False, "description": "敏感操作提示信息"}
        ],
        "example": 'do(action="Tap", element=[500, 300])',
        "adb_command": "adb shell input tap <x> <y>",
        "rules": [
            {"id": "tap_001", "condition": "坐标超出屏幕范围", "action": "自动裁剪到有效范围 [0-1000]", "priority": 10, "enabled": True},
            {"id": "tap_002", "condition": "连续快速点击同一位置", "action": "合并为单次点击，防止误操作", "priority": 5, "enabled": True},
            {"id": "tap_003", "condition": "点击系统敏感区域（如删除按钮）", "action": "显示确认对话框", "priority": 8, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Type",
        "description": "在当前焦点输入文本",
        "parameters": [
            {"name": "text", "type": "string", "required": True, "description": "要输入的文本内容"},
            {"name": "press_enter", "type": "bool", "required": False, "description": "输入后是否按回车键"}
        ],
        "example": 'do(action="Type", text="Hello World", press_enter=True)',
        "adb_command": "adb shell input text <text>",
        "rules": [
            {"id": "type_001", "condition": "文本包含中文字符", "action": "使用ADB广播方式输入，确保中文正确", "priority": 10, "enabled": True},
            {"id": "type_002", "condition": "输入框无焦点", "action": "先尝试点击输入框获取焦点", "priority": 8, "enabled": True},
            {"id": "type_003", "condition": "文本长度超过100字符", "action": "分段输入，每段50字符", "priority": 5, "enabled": True},
            {"id": "type_004", "condition": "输入前有旧内容", "action": "先清空输入框再输入新内容", "priority": 7, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Type_Name",
        "description": "输入用户名等特殊文本（与Type相同处理）",
        "parameters": [
            {"name": "text", "type": "string", "required": True, "description": "要输入的文本内容"}
        ],
        "example": 'do(action="Type_Name", text="username")',
        "adb_command": "adb shell input text <text>",
        "rules": [
            {"id": "typename_001", "condition": "等同于Type动作", "action": "使用Type动作的所有规则", "priority": 10, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Swipe",
        "description": "从起点滑动到终点",
        "parameters": [
            {"name": "start", "type": "list[int]", "required": True, "description": "起点坐标 [x, y]，范围 0-1000"},
            {"name": "end", "type": "list[int]", "required": True, "description": "终点坐标 [x, y]，范围 0-1000"}
        ],
        "example": 'do(action="Swipe", start=[500, 800], end=[500, 200])',
        "adb_command": "adb shell input swipe <x1> <y1> <x2> <y2>",
        "rules": [
            {"id": "swipe_001", "condition": "起点和终点相同", "action": "转换为Tap动作", "priority": 10, "enabled": True},
            {"id": "swipe_002", "condition": "滑动距离过短（<50像素）", "action": "增加滑动距离以确保触发", "priority": 5, "enabled": True},
            {"id": "swipe_003", "condition": "滑动方向为垂直", "action": "用于页面滚动场景", "priority": 3, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Back",
        "description": "按下返回键",
        "parameters": [],
        "example": 'do(action="Back")',
        "adb_command": "adb shell input keyevent KEYCODE_BACK",
        "rules": [
            {"id": "back_001", "condition": "当前在应用首页", "action": "可能退出应用，需确认", "priority": 5, "enabled": True},
            {"id": "back_002", "condition": "存在弹窗或对话框", "action": "优先关闭弹窗", "priority": 8, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Home",
        "description": "按下Home键回到桌面",
        "parameters": [],
        "example": 'do(action="Home")',
        "adb_command": "adb shell input keyevent KEYCODE_HOME",
        "rules": [
            {"id": "home_001", "condition": "任意场景", "action": "返回桌面，应用进入后台", "priority": 10, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Double Tap",
        "description": "双击屏幕指定位置",
        "parameters": [
            {"name": "element", "type": "list[int]", "required": True, "description": "坐标 [x, y]，范围 0-1000"}
        ],
        "example": 'do(action="Double Tap", element=[500, 500])',
        "adb_command": "adb shell input tap <x> <y> && adb shell input tap <x> <y>",
        "rules": [
            {"id": "dtap_001", "condition": "两次点击间隔", "action": "间隔100ms，确保识别为双击", "priority": 10, "enabled": True},
            {"id": "dtap_002", "condition": "坐标超出范围", "action": "自动裁剪到有效范围", "priority": 8, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Long Press",
        "description": "长按屏幕指定位置",
        "parameters": [
            {"name": "element", "type": "list[int]", "required": True, "description": "坐标 [x, y]，范围 0-1000"}
        ],
        "example": 'do(action="Long Press", element=[500, 500])',
        "adb_command": "adb shell input swipe <x> <y> <x> <y> 1000",
        "rules": [
            {"id": "lpress_001", "condition": "默认长按时长", "action": "持续1000ms（1秒）", "priority": 10, "enabled": True},
            {"id": "lpress_002", "condition": "长按菜单项", "action": "可能触发上下文菜单", "priority": 5, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Wait",
        "description": "等待指定时间",
        "parameters": [
            {"name": "duration", "type": "string", "required": False, "description": "等待时间，如 '2 seconds'"}
        ],
        "example": 'do(action="Wait", duration="2 seconds")',
        "adb_command": "",
        "rules": [
            {"id": "wait_001", "condition": "未指定时长", "action": "默认等待1秒", "priority": 10, "enabled": True},
            {"id": "wait_002", "condition": "等待时间超过10秒", "action": "显示进度提示", "priority": 5, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Take_over",
        "description": "请求用户接管操作（如登录、验证码）",
        "parameters": [
            {"name": "message", "type": "string", "required": False, "description": "提示用户的消息"}
        ],
        "example": 'do(action="Take_over", message="请完成登录验证")',
        "adb_command": "",
        "rules": [
            {"id": "takeover_001", "condition": "需要人工操作", "action": "暂停自动化，等待用户完成后继续", "priority": 10, "enabled": True},
            {"id": "takeover_002", "condition": "用户完成操作", "action": "用户点击'继续'按钮后恢复自动化", "priority": 8, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Note",
        "description": "记录页面内容（占位功能）",
        "parameters": [],
        "example": 'do(action="Note")',
        "adb_command": "",
        "rules": [
            {"id": "note_001", "condition": "占位功能", "action": "当前版本不执行实际操作", "priority": 10, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Call_API",
        "description": "调用外部API进行内容处理（占位功能）",
        "parameters": [],
        "example": 'do(action="Call_API")',
        "adb_command": "",
        "rules": [
            {"id": "callapi_001", "condition": "占位功能", "action": "当前版本不执行实际操作", "priority": 10, "enabled": True},
        ],
        "is_custom": False
    },
    {
        "name": "Interact",
        "description": "请求用户交互选择",
        "parameters": [],
        "example": 'do(action="Interact")',
        "adb_command": "",
        "rules": [
            {"id": "interact_001", "condition": "需要用户选择", "action": "显示选项列表，等待用户选择后继续", "priority": 10, "enabled": True},
        ],
        "is_custom": False
    },
]


class RulesManager:
    """规则配置管理器"""

    def __init__(self):
        self.config_dir = Path.home() / ".autoglm"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.apps_file = self.config_dir / "custom_apps.json"
        self.timing_file = self.config_dir / "custom_timing.json"
        self.actions_file = self.config_dir / "action_rules.json"

        # 加载自定义配置
        self._custom_apps: dict[str, str] = {}
        self._custom_timing: dict[str, float] = {}
        self._action_rules: list[dict] = []

        self._load_all()

    def _load_all(self):
        """加载所有配置"""
        self._load_custom_apps()
        self._load_custom_timing()
        self._load_action_rules()

    def _load_custom_apps(self):
        """加载自定义应用映射"""
        if self.apps_file.exists():
            try:
                self._custom_apps = json.loads(self.apps_file.read_text(encoding="utf-8"))
            except Exception:
                self._custom_apps = {}

    def _load_custom_timing(self):
        """加载自定义时间配置"""
        if self.timing_file.exists():
            try:
                self._custom_timing = json.loads(self.timing_file.read_text(encoding="utf-8"))
            except Exception:
                self._custom_timing = {}

    def _load_action_rules(self):
        """加载动作规则"""
        if self.actions_file.exists():
            try:
                self._action_rules = json.loads(self.actions_file.read_text(encoding="utf-8"))
            except Exception:
                self._action_rules = DEFAULT_ACTION_RULES.copy()
        else:
            self._action_rules = DEFAULT_ACTION_RULES.copy()
            self._save_action_rules()

    def _save_custom_apps(self):
        """保存自定义应用映射"""
        self.apps_file.write_text(
            json.dumps(self._custom_apps, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _save_custom_timing(self):
        """保存自定义时间配置"""
        self.timing_file.write_text(
            json.dumps(self._custom_timing, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _save_action_rules(self):
        """保存动作规则"""
        self.actions_file.write_text(
            json.dumps(self._action_rules, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ========== 应用映射规则 ==========

    def get_all_apps(self) -> dict[str, str]:
        """获取所有应用映射（内置 + 自定义）"""
        from phone_agent.config.apps import APP_PACKAGES
        # 合并内置和自定义，自定义优先
        merged = dict(APP_PACKAGES)
        merged.update(self._custom_apps)
        return merged

    def get_custom_apps(self) -> dict[str, str]:
        """获取自定义应用映射"""
        return self._custom_apps.copy()

    def add_app(self, app_name: str, package_name: str) -> bool:
        """添加应用映射"""
        self._custom_apps[app_name] = package_name
        self._save_custom_apps()
        # 同步到运行时配置
        self._sync_apps_to_runtime()
        return True

    def update_app(self, old_name: str, new_name: str, package_name: str) -> bool:
        """更新应用映射"""
        if old_name in self._custom_apps:
            del self._custom_apps[old_name]
        self._custom_apps[new_name] = package_name
        self._save_custom_apps()
        self._sync_apps_to_runtime()
        return True

    def delete_app(self, app_name: str) -> bool:
        """删除自定义应用映射"""
        if app_name in self._custom_apps:
            del self._custom_apps[app_name]
            self._save_custom_apps()
            self._sync_apps_to_runtime()
            return True
        return False

    def is_custom_app(self, app_name: str) -> bool:
        """检查是否为自定义应用"""
        return app_name in self._custom_apps

    def _sync_apps_to_runtime(self):
        """同步应用映射到运行时"""
        from phone_agent.config.apps import APP_PACKAGES
        # 将自定义应用添加到运行时字典
        APP_PACKAGES.update(self._custom_apps)

    # ========== 时间延迟规则 ==========

    def get_timing_config(self) -> dict[str, Any]:
        """获取时间配置（内置值 + 自定义覆盖）"""
        from phone_agent.config.timing import TIMING_CONFIG

        config = {
            "action": {
                "keyboard_switch_delay": TIMING_CONFIG.action.keyboard_switch_delay,
                "text_clear_delay": TIMING_CONFIG.action.text_clear_delay,
                "text_input_delay": TIMING_CONFIG.action.text_input_delay,
                "keyboard_restore_delay": TIMING_CONFIG.action.keyboard_restore_delay,
            },
            "device": {
                "default_tap_delay": TIMING_CONFIG.device.default_tap_delay,
                "default_double_tap_delay": TIMING_CONFIG.device.default_double_tap_delay,
                "double_tap_interval": TIMING_CONFIG.device.double_tap_interval,
                "default_long_press_delay": TIMING_CONFIG.device.default_long_press_delay,
                "default_swipe_delay": TIMING_CONFIG.device.default_swipe_delay,
                "default_back_delay": TIMING_CONFIG.device.default_back_delay,
                "default_home_delay": TIMING_CONFIG.device.default_home_delay,
                "default_launch_delay": TIMING_CONFIG.device.default_launch_delay,
            },
            "connection": {
                "adb_restart_delay": TIMING_CONFIG.connection.adb_restart_delay,
                "server_restart_delay": TIMING_CONFIG.connection.server_restart_delay,
            }
        }
        return config

    def update_timing(self, category: str, key: str, value: float) -> bool:
        """更新时间配置"""
        config_key = f"{category}.{key}"
        self._custom_timing[config_key] = value
        self._save_custom_timing()
        self._sync_timing_to_runtime(category, key, value)
        return True

    def _sync_timing_to_runtime(self, category: str, key: str, value: float):
        """同步时间配置到运行时"""
        from phone_agent.config.timing import TIMING_CONFIG

        if category == "action":
            setattr(TIMING_CONFIG.action, key, value)
        elif category == "device":
            setattr(TIMING_CONFIG.device, key, value)
        elif category == "connection":
            setattr(TIMING_CONFIG.connection, key, value)

    # ========== 动作规则 ==========

    def get_action_rules(self) -> list[dict]:
        """获取所有动作规则"""
        return self._action_rules.copy()

    def get_action_rule(self, name: str) -> dict | None:
        """获取指定动作规则"""
        for rule in self._action_rules:
            if rule["name"] == name:
                return rule.copy()
        return None

    def update_action_rule(self, name: str, updates: dict) -> bool:
        """更新动作规则"""
        for i, rule in enumerate(self._action_rules):
            if rule["name"] == name:
                self._action_rules[i].update(updates)
                self._save_action_rules()
                return True
        return False

    def reset_action_rules(self):
        """重置动作规则为默认值"""
        self._action_rules = [dict(r) for r in DEFAULT_ACTION_RULES]
        self._save_action_rules()

    def add_action_rule(self, action_data: dict) -> bool:
        """添加新的动作规则"""
        # 检查名称是否已存在
        for rule in self._action_rules:
            if rule["name"] == action_data.get("name"):
                return False
        # 确保包含必要字段
        new_rule = {
            "name": action_data.get("name", ""),
            "description": action_data.get("description", ""),
            "parameters": action_data.get("parameters", []),
            "example": action_data.get("example", ""),
            "adb_command": action_data.get("adb_command", ""),
            "rules": action_data.get("rules", []),
            "is_custom": True
        }
        self._action_rules.append(new_rule)
        self._save_action_rules()
        return True

    def delete_action_rule(self, name: str) -> bool:
        """删除动作规则（只能删除自定义规则）"""
        for i, rule in enumerate(self._action_rules):
            if rule["name"] == name:
                if rule.get("is_custom", False):
                    del self._action_rules[i]
                    self._save_action_rules()
                    return True
                else:
                    return False  # 不能删除内置规则
        return False

    def is_custom_action(self, name: str) -> bool:
        """检查是否为自定义动作"""
        for rule in self._action_rules:
            if rule["name"] == name:
                return rule.get("is_custom", False)
        return False

    # ========== 规则内容管理（针对单个动作的rules列表）==========

    def get_action_rule_items(self, action_name: str) -> list[dict]:
        """获取指定动作的所有规则项"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                return rule.get("rules", []).copy()
        return []

    def add_rule_item(self, action_name: str, rule_item: dict) -> bool:
        """添加规则项到指定动作"""
        import uuid
        for rule in self._action_rules:
            if rule["name"] == action_name:
                if "rules" not in rule:
                    rule["rules"] = []
                # 生成唯一ID
                if "id" not in rule_item or not rule_item["id"]:
                    rule_item["id"] = f"{action_name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
                # 设置默认值
                rule_item.setdefault("condition", "")
                rule_item.setdefault("action", "")
                rule_item.setdefault("priority", 0)
                rule_item.setdefault("enabled", True)
                rule["rules"].append(rule_item)
                self._save_action_rules()
                return True
        return False

    def update_rule_item(self, action_name: str, rule_id: str, updates: dict) -> bool:
        """更新指定动作的规则项"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                rules = rule.get("rules", [])
                for i, item in enumerate(rules):
                    if item.get("id") == rule_id:
                        rules[i].update(updates)
                        self._save_action_rules()
                        return True
        return False

    def delete_rule_item(self, action_name: str, rule_id: str) -> bool:
        """删除指定动作的规则项"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                rules = rule.get("rules", [])
                for i, item in enumerate(rules):
                    if item.get("id") == rule_id:
                        del rules[i]
                        self._save_action_rules()
                        return True
        return False

    def toggle_rule_item(self, action_name: str, rule_id: str) -> bool:
        """切换规则项的启用状态"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                rules = rule.get("rules", [])
                for item in rules:
                    if item.get("id") == rule_id:
                        item["enabled"] = not item.get("enabled", True)
                        self._save_action_rules()
                        return True
        return False

    def reorder_rule_items(self, action_name: str, rule_ids: list[str]) -> bool:
        """重新排序规则项"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                rules = rule.get("rules", [])
                # 创建id到规则项的映射
                id_to_item = {item["id"]: item for item in rules}
                # 按新顺序重建列表
                new_rules = []
                for rid in rule_ids:
                    if rid in id_to_item:
                        new_rules.append(id_to_item[rid])
                        del id_to_item[rid]
                # 添加不在列表中的规则项（保持原有顺序）
                new_rules.extend(id_to_item.values())
                rule["rules"] = new_rules
                self._save_action_rules()
                return True
        return False

    # ========== 参数管理 ==========

    def get_action_parameters(self, action_name: str) -> list[dict]:
        """获取指定动作的参数列表"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                return rule.get("parameters", []).copy()
        return []

    def add_parameter(self, action_name: str, param: dict) -> bool:
        """添加参数到指定动作"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                if "parameters" not in rule:
                    rule["parameters"] = []
                # 检查参数名是否已存在
                for p in rule["parameters"]:
                    if p.get("name") == param.get("name"):
                        return False
                param.setdefault("name", "")
                param.setdefault("type", "string")
                param.setdefault("required", False)
                param.setdefault("description", "")
                rule["parameters"].append(param)
                self._save_action_rules()
                return True
        return False

    def update_parameter(self, action_name: str, param_name: str, updates: dict) -> bool:
        """更新指定动作的参数"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                params = rule.get("parameters", [])
                for i, param in enumerate(params):
                    if param.get("name") == param_name:
                        params[i].update(updates)
                        self._save_action_rules()
                        return True
        return False

    def delete_parameter(self, action_name: str, param_name: str) -> bool:
        """删除指定动作的参数"""
        for rule in self._action_rules:
            if rule["name"] == action_name:
                params = rule.get("parameters", [])
                for i, param in enumerate(params):
                    if param.get("name") == param_name:
                        del params[i]
                        self._save_action_rules()
                        return True
        return False

    # ========== 导入导出 ==========

    def export_action_rules(self, filepath: str) -> bool:
        """导出动作规则到文件"""
        try:
            import json
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._action_rules, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def import_action_rules(self, filepath: str, merge: bool = False) -> tuple[bool, str]:
        """导入动作规则从文件

        Args:
            filepath: 文件路径
            merge: True=合并（保留现有，添加新的），False=替换全部

        Returns:
            (成功, 消息)
        """
        try:
            import json
            with open(filepath, 'r', encoding='utf-8') as f:
                imported_rules = json.load(f)

            if not isinstance(imported_rules, list):
                return False, "文件格式错误：期望列表格式"

            if merge:
                # 合并模式：添加新规则，跳过同名规则
                existing_names = {r["name"] for r in self._action_rules}
                added = 0
                for rule in imported_rules:
                    if rule.get("name") and rule["name"] not in existing_names:
                        rule["is_custom"] = True
                        self._action_rules.append(rule)
                        added += 1
                self._save_action_rules()
                return True, f"成功导入 {added} 条新规则"
            else:
                # 替换模式
                self._action_rules = imported_rules
                self._save_action_rules()
                return True, f"成功导入 {len(imported_rules)} 条规则"
        except json.JSONDecodeError:
            return False, "JSON 格式错误"
        except Exception as e:
            return False, f"导入失败: {str(e)}"


# 全局实例
_rules_manager: RulesManager | None = None


def get_rules_manager() -> RulesManager:
    """获取规则管理器单例"""
    global _rules_manager
    if _rules_manager is None:
        _rules_manager = RulesManager()
    return _rules_manager
