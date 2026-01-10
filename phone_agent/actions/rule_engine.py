# -*- coding: utf-8 -*-
"""规则引擎 - 在动作执行时应用用户配置的规则"""

import logging
import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RuleResult(Enum):
    """规则执行结果"""
    CONTINUE = "continue"  # 继续执行原有逻辑
    SKIP = "skip"  # 跳过执行，返回成功
    ABORT = "abort"  # 中止执行，返回失败
    MODIFIED = "modified"  # 参数已修改，使用修改后的参数继续


@dataclass
class RuleCheckResult:
    """规则检查结果"""
    result: RuleResult
    message: str | None = None
    modified_params: dict | None = None  # 修改后的参数


class RuleEngine:
    """
    规则引擎 - 在动作执行前检查并应用规则

    规则定义格式：
    {
        "id": "launch_001",
        "condition": "应用未安装",
        "action": "返回错误提示，不执行启动",
        "priority": 10,
        "enabled": True
    }

    条件和动作通过ID映射到具体的检查函数和执行函数
    """

    def __init__(self):
        self._rules_manager = None
        self._condition_checkers: dict[str, Callable] = {}
        self._action_executors: dict[str, Callable] = {}
        self._custom_condition_funcs: dict[str, Callable] = {}  # 自定义条件函数
        self._register_default_conditions()
        self._register_default_actions()

    def _get_rules_manager(self):
        """懒加载规则管理器"""
        if self._rules_manager is None:
            try:
                from gui_app.rules_manager import get_rules_manager
                self._rules_manager = get_rules_manager()
            except ImportError:
                logger.warning("无法加载规则管理器，使用默认规则")
                self._rules_manager = None
        return self._rules_manager

    def _register_default_conditions(self):
        """注册默认的条件检查器"""
        # Launch 动作条件
        self._condition_checkers["launch_app_not_installed"] = self._check_app_not_installed
        self._condition_checkers["launch_app_in_foreground"] = self._check_app_in_foreground
        self._condition_checkers["launch_app_not_mapped"] = self._check_app_not_mapped

        # Tap 动作条件
        self._condition_checkers["tap_out_of_bounds"] = self._check_coordinates_out_of_bounds
        self._condition_checkers["tap_rapid_click"] = self._check_rapid_click
        self._condition_checkers["tap_sensitive_area"] = self._check_sensitive_area

        # Type 动作条件
        self._condition_checkers["type_contains_chinese"] = self._check_contains_chinese
        self._condition_checkers["type_no_focus"] = self._check_no_focus
        self._condition_checkers["type_long_text"] = self._check_long_text

        # Swipe 动作条件
        self._condition_checkers["swipe_same_point"] = self._check_swipe_same_point
        self._condition_checkers["swipe_short_distance"] = self._check_swipe_short_distance

        # Wait 动作条件
        self._condition_checkers["wait_no_duration"] = self._check_wait_no_duration
        self._condition_checkers["wait_long_duration"] = self._check_wait_long_duration

    def _register_default_actions(self):
        """注册默认的动作执行器"""
        self._action_executors["abort_with_error"] = self._action_abort_with_error
        self._action_executors["skip_success"] = self._action_skip_success
        self._action_executors["clip_coordinates"] = self._action_clip_coordinates
        self._action_executors["show_confirmation"] = self._action_show_confirmation
        self._action_executors["merge_clicks"] = self._action_merge_clicks
        self._action_executors["use_broadcast_input"] = self._action_use_broadcast_input
        self._action_executors["split_text"] = self._action_split_text
        self._action_executors["convert_to_tap"] = self._action_convert_to_tap
        self._action_executors["extend_swipe"] = self._action_extend_swipe
        self._action_executors["default_wait"] = self._action_default_wait

    def get_predefined_condition_source(self, condition_key: str) -> str | None:
        """
        获取预定义条件检查函数的源代码

        Args:
            condition_key: 条件检查器的key，如 "launch_app_not_installed"

        Returns:
            函数源代码字符串，如果找不到返回 None
        """
        if condition_key in self._condition_checkers:
            func = self._condition_checkers[condition_key]
            try:
                return inspect.getsource(func)
            except Exception:
                return None
        return None

    def get_all_predefined_conditions(self) -> dict[str, str]:
        """
        获取所有预定义条件检查器的信息

        Returns:
            字典 {condition_key: 函数描述}
        """
        result = {}
        for key, func in self._condition_checkers.items():
            doc = func.__doc__ or "无说明"
            result[key] = doc.strip()
        return result

    def get_condition_key_for_rule(self, action_name: str, condition: str, rule_id: str) -> str | None:
        """
        获取规则对应的条件检查器key

        Args:
            action_name: 动作名称
            condition: 条件描述
            rule_id: 规则ID

        Returns:
            条件检查器key，如果没有匹配返回 None
        """
        return self._map_condition_to_key(action_name, condition, rule_id)

    def register_custom_condition(self, rule_id: str, func_code: str) -> tuple[bool, str]:
        """
        注册自定义条件检查函数

        Args:
            rule_id: 规则ID，用于标识这个自定义函数
            func_code: 函数代码字符串

        Returns:
            (成功, 消息)
        """
        try:
            # 创建执行环境
            exec_globals = {
                "__builtins__": __builtins__,
                "re": __import__("re"),
                "time": __import__("time"),
                "RuleResult": RuleResult,
                "RuleCheckResult": RuleCheckResult,
            }

            # 执行代码
            exec(func_code, exec_globals)

            # 查找定义的函数（名为 check_condition 的函数）
            if "check_condition" not in exec_globals:
                return False, "函数必须命名为 'check_condition'"

            func = exec_globals["check_condition"]
            if not callable(func):
                return False, "'check_condition' 必须是可调用的函数"

            # 验证函数签名
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if len(params) < 2:
                return False, "函数必须接受至少两个参数: (params, context)"

            # 注册函数
            custom_key = f"custom_{rule_id}"
            self._custom_condition_funcs[custom_key] = func
            self._condition_checkers[custom_key] = func

            return True, f"自定义条件函数已注册: {custom_key}"
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        except Exception as e:
            return False, f"注册失败: {e}"

    def unregister_custom_condition(self, rule_id: str) -> bool:
        """
        注销自定义条件检查函数

        Args:
            rule_id: 规则ID

        Returns:
            是否成功注销
        """
        custom_key = f"custom_{rule_id}"
        if custom_key in self._custom_condition_funcs:
            del self._custom_condition_funcs[custom_key]
            if custom_key in self._condition_checkers:
                del self._condition_checkers[custom_key]
            return True
        return False

    def get_custom_condition_template(self) -> str:
        """
        获取自定义条件函数的模板代码

        Returns:
            带有详细注释的模板代码
        """
        return '''def check_condition(params: dict, context: dict) -> bool:
    """
    自定义条件检查函数

    这个函数用于检查是否满足规则触发条件。
    当此函数返回 True 时，将执行对应的规则动作。

    参数说明:
    ----------
    params : dict
        动作参数字典，包含用户传入的参数。
        常见参数:
        - "app": 应用名称 (Launch动作)
        - "element": 坐标 [x, y] (Tap/Double Tap/Long Press动作)
        - "text": 文本内容 (Type动作)
        - "start": 起始坐标 [x, y] (Swipe动作)
        - "end": 结束坐标 [x, y] (Swipe动作)
        - "duration": 等待时长 (Wait动作)
        - "message": 提示消息 (Take_over动作)

    context : dict
        执行上下文字典，包含运行时信息。
        常见内容:
        - "device_id": 设备ID
        - "screen_width": 屏幕宽度
        - "screen_height": 屏幕高度
        - "last_tap_position": 上次点击位置 (x, y)
        - "last_tap_time": 上次点击时间戳

    返回值:
    -------
    bool
        True: 条件满足，触发规则动作
        False: 条件不满足，跳过此规则

    示例 - 检查文本是否包含敏感词:
    -----------------------------
    def check_condition(params: dict, context: dict) -> bool:
        text = params.get("text", "")
        sensitive_words = ["密码", "password", "token", "secret"]
        for word in sensitive_words:
            if word.lower() in text.lower():
                return True
        return False

    示例 - 检查点击是否在特定区域:
    -----------------------------
    def check_condition(params: dict, context: dict) -> bool:
        element = params.get("element", [])
        if len(element) < 2:
            return False
        x, y = element[0], element[1]
        # 检查是否在屏幕底部导航栏区域 (y > 900)
        return y > 900

    注意事项:
    ---------
    1. 函数必须命名为 check_condition
    2. 函数必须返回布尔值 (True/False)
    3. 可以使用 re 模块进行正则匹配
    4. 可以使用 time 模块获取时间信息
    5. 避免执行耗时操作，保持函数快速返回
    """
    # 在这里编写您的条件检查逻辑
    # 示例：检查参数中是否包含某个值

    # 获取参数示例
    # text = params.get("text", "")
    # element = params.get("element", [])

    # 返回条件是否满足
    return False
'''

    # ========== 动作执行器相关方法 ==========

    def get_predefined_action_source(self, action_key: str) -> str | None:
        """
        获取预定义动作执行函数的源代码

        Args:
            action_key: 动作执行器的key，如 "abort_with_error"

        Returns:
            函数源代码字符串，如果找不到返回 None
        """
        if action_key in self._action_executors:
            func = self._action_executors[action_key]
            try:
                return inspect.getsource(func)
            except Exception:
                return None
        return None

    def get_all_predefined_actions(self) -> dict[str, str]:
        """
        获取所有预定义动作执行器的信息

        Returns:
            字典 {action_key: 函数描述}
        """
        result = {}
        for key, func in self._action_executors.items():
            if not key.startswith("custom_"):  # 排除自定义函数
                doc = func.__doc__ or "无说明"
                result[key] = doc.strip()
        return result

    def get_action_key_for_rule(self, action_name: str, action: str, rule_id: str) -> str | None:
        """
        获取规则对应的动作执行器key

        Args:
            action_name: 动作类型名称
            action: 动作描述
            rule_id: 规则ID

        Returns:
            动作执行器key，如果没有匹配返回 None
        """
        return self._map_action_to_key(action_name, action, rule_id)

    def register_custom_action(self, rule_id: str, func_code: str) -> tuple[bool, str]:
        """
        注册自定义动作执行函数

        Args:
            rule_id: 规则ID，用于标识这个自定义函数
            func_code: 函数代码字符串

        Returns:
            (成功, 消息)
        """
        try:
            # 创建执行环境
            exec_globals = {
                "__builtins__": __builtins__,
                "re": __import__("re"),
                "time": __import__("time"),
                "RuleResult": RuleResult,
                "RuleCheckResult": RuleCheckResult,
            }

            # 执行代码
            exec(func_code, exec_globals)

            # 查找定义的函数（名为 execute_action 的函数）
            if "execute_action" not in exec_globals:
                return False, "函数必须命名为 'execute_action'"

            func = exec_globals["execute_action"]
            if not callable(func):
                return False, "'execute_action' 必须是可调用的函数"

            # 验证函数签名
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if len(params) < 3:
                return False, "函数必须接受至少三个参数: (params, context, rule)"

            # 注册函数
            custom_key = f"custom_action_{rule_id}"
            self._action_executors[custom_key] = func

            return True, f"自定义动作函数已注册: {custom_key}"
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        except Exception as e:
            return False, f"注册失败: {e}"

    def unregister_custom_action(self, rule_id: str) -> bool:
        """
        注销自定义动作执行函数

        Args:
            rule_id: 规则ID

        Returns:
            是否成功注销
        """
        custom_key = f"custom_action_{rule_id}"
        if custom_key in self._action_executors:
            del self._action_executors[custom_key]
            return True
        return False

    def get_custom_action_template(self) -> str:
        """
        获取自定义动作执行函数的模板代码

        Returns:
            带有详细注释的模板代码
        """
        return '''def execute_action(params: dict, context: dict, rule: dict) -> RuleCheckResult:
    """
    自定义动作执行函数

    当规则的条件满足时，此函数将被调用来执行相应的动作。
    函数可以修改参数、跳过执行、或中止执行。

    参数说明:
    ----------
    params : dict
        动作参数字典（可修改）。
        常见参数:
        - "app": 应用名称 (Launch动作)
        - "element": 坐标 [x, y] (Tap/Double Tap/Long Press动作)
        - "text": 文本内容 (Type动作)
        - "start": 起始坐标 [x, y] (Swipe动作)
        - "end": 结束坐标 [x, y] (Swipe动作)
        - "duration": 等待时长 (Wait动作)

    context : dict
        执行上下文字典，包含运行时信息。
        常见内容:
        - "device_id": 设备ID
        - "screen_width": 屏幕宽度
        - "screen_height": 屏幕高度

    rule : dict
        当前规则信息，包含:
        - "id": 规则ID
        - "condition": 条件描述
        - "action": 动作描述
        - "priority": 优先级
        - "enabled": 是否启用

    返回值:
    -------
    RuleCheckResult
        必须返回 RuleCheckResult 对象，可选类型:

        1. RuleCheckResult(RuleResult.CONTINUE)
           继续执行原有逻辑，不做修改

        2. RuleCheckResult(RuleResult.SKIP, message="跳过原因")
           跳过原动作执行，直接返回成功

        3. RuleCheckResult(RuleResult.ABORT, message="中止原因")
           中止执行，返回失败

        4. RuleCheckResult(RuleResult.MODIFIED, modified_params={...})
           使用修改后的参数继续执行

    示例 - 裁剪坐标到有效范围:
    --------------------------
    def execute_action(params: dict, context: dict, rule: dict) -> RuleCheckResult:
        modified = params.copy()
        if "element" in modified:
            element = modified["element"]
            if len(element) >= 2:
                modified["element"] = [
                    max(0, min(1000, element[0])),
                    max(0, min(1000, element[1]))
                ]
        return RuleCheckResult(
            RuleResult.MODIFIED,
            message="坐标已裁剪",
            modified_params=modified
        )

    示例 - 条件性跳过执行:
    ----------------------
    def execute_action(params: dict, context: dict, rule: dict) -> RuleCheckResult:
        app = params.get("app", "")
        if app == "当前应用":
            return RuleCheckResult(
                RuleResult.SKIP,
                message="应用已在前台，跳过启动"
            )
        return RuleCheckResult(RuleResult.CONTINUE)

    注意事项:
    ---------
    1. 函数必须命名为 execute_action
    2. 函数必须返回 RuleCheckResult 对象
    3. 可以使用 RuleResult 枚举: CONTINUE, SKIP, ABORT, MODIFIED
    4. 修改参数时，应复制 params 后再修改
    5. 避免执行耗时操作
    """
    # 在这里编写您的动作执行逻辑

    # 示例：继续执行原有逻辑
    return RuleCheckResult(RuleResult.CONTINUE)
'''

    def get_rules_for_action(self, action_name: str) -> list[dict]:
        """获取指定动作的所有启用规则，按优先级排序"""
        rm = self._get_rules_manager()
        if rm is None:
            return []

        try:
            rules = rm.get_action_rule_items(action_name)
            # 只返回启用的规则，按优先级降序排序
            enabled_rules = [r for r in rules if r.get("enabled", True)]
            enabled_rules.sort(key=lambda r: r.get("priority", 0), reverse=True)
            return enabled_rules
        except Exception as e:
            logger.warning(f"获取动作规则失败: {e}")
            return []

    def apply_rules(
        self,
        action_name: str,
        action_params: dict,
        context: dict
    ) -> RuleCheckResult:
        """
        应用规则到动作

        Args:
            action_name: 动作名称 (如 "Launch", "Tap")
            action_params: 动作参数
            context: 执行上下文 (包含 device_id, screen_width, screen_height 等)

        Returns:
            RuleCheckResult 包含规则应用结果
        """
        rules = self.get_rules_for_action(action_name)

        if not rules:
            return RuleCheckResult(RuleResult.CONTINUE)

        modified_params = action_params.copy()

        for rule in rules:
            rule_id = rule.get("id", "")
            condition = rule.get("condition", "")
            action = rule.get("action", "")
            custom_func_code = rule.get("condition_func")

            # 检查自定义条件函数
            custom_key = f"custom_{rule_id}"
            if custom_func_code and custom_key not in self._condition_checkers:
                # 尝试注册自定义函数
                success, _ = self.register_custom_condition(rule_id, custom_func_code)
                if not success:
                    logger.warning(f"规则 {rule_id} 的自定义条件函数注册失败")

            # 尝试匹配条件 - 优先使用自定义函数
            condition_key = custom_key if custom_key in self._condition_checkers else self._map_condition_to_key(action_name, condition, rule_id)
            if condition_key and condition_key in self._condition_checkers:
                checker = self._condition_checkers[condition_key]
                try:
                    condition_met = checker(modified_params, context)
                    if condition_met:
                        logger.info(f"规则 {rule_id} 条件满足: {condition}")

                        # 执行规则动作
                        action_key = self._map_action_to_key(action_name, action, rule_id)
                        if action_key and action_key in self._action_executors:
                            executor = self._action_executors[action_key]
                            result = executor(modified_params, context, rule)

                            if result.result in (RuleResult.SKIP, RuleResult.ABORT):
                                return result
                            elif result.result == RuleResult.MODIFIED and result.modified_params:
                                modified_params = result.modified_params
                except Exception as e:
                    logger.warning(f"规则 {rule_id} 执行失败: {e}")

        # 如果参数被修改，返回修改后的参数
        if modified_params != action_params:
            return RuleCheckResult(
                RuleResult.MODIFIED,
                modified_params=modified_params
            )

        return RuleCheckResult(RuleResult.CONTINUE)

    def _map_condition_to_key(self, action_name: str, condition: str, rule_id: str) -> str | None:
        """将条件描述映射到条件检查器的key"""
        # 根据规则ID前缀和条件文本进行映射
        condition_mappings = {
            # Launch 动作
            ("Launch", "应用未安装"): "launch_app_not_installed",
            ("Launch", "应用已在前台"): "launch_app_in_foreground",
            ("Launch", "应用名称未在映射表中"): "launch_app_not_mapped",

            # Tap 动作
            ("Tap", "坐标超出屏幕范围"): "tap_out_of_bounds",
            ("Tap", "连续快速点击同一位置"): "tap_rapid_click",
            ("Tap", "点击系统敏感区域"): "tap_sensitive_area",

            # Type 动作
            ("Type", "文本包含中文字符"): "type_contains_chinese",
            ("Type", "输入框无焦点"): "type_no_focus",
            ("Type", "文本长度超过100字符"): "type_long_text",

            # Swipe 动作
            ("Swipe", "起点和终点相同"): "swipe_same_point",
            ("Swipe", "滑动距离过短"): "swipe_short_distance",

            # Wait 动作
            ("Wait", "未指定时长"): "wait_no_duration",
            ("Wait", "等待时间超过10秒"): "wait_long_duration",

            # Double Tap 动作
            ("Double Tap", "坐标超出范围"): "tap_out_of_bounds",

            # Long Press 动作
            ("Long Press", "坐标超出范围"): "tap_out_of_bounds",
        }

        # 精确匹配
        key = (action_name, condition)
        if key in condition_mappings:
            return condition_mappings[key]

        # 模糊匹配（条件文本包含关键词）
        for (act, cond), checker_key in condition_mappings.items():
            if act == action_name and cond in condition:
                return checker_key

        return None

    def _map_action_to_key(self, action_name: str, action: str, rule_id: str) -> str | None:
        """将动作描述映射到动作执行器的key"""
        action_mappings = {
            # 通用动作
            "返回错误提示": "abort_with_error",
            "跳过": "skip_success",
            "直接返回成功": "skip_success",

            # 坐标相关
            "自动裁剪": "clip_coordinates",
            "裁剪到有效范围": "clip_coordinates",

            # 点击相关
            "显示确认对话框": "show_confirmation",
            "合并为单次点击": "merge_clicks",

            # 输入相关
            "使用ADB广播方式输入": "use_broadcast_input",
            "分段输入": "split_text",

            # 滑动相关
            "转换为Tap动作": "convert_to_tap",
            "增加滑动距离": "extend_swipe",

            # 等待相关
            "默认等待1秒": "default_wait",
        }

        # 模糊匹配
        for pattern, executor_key in action_mappings.items():
            if pattern in action:
                return executor_key

        return None

    # ========== 条件检查器 ==========

    def _check_app_not_installed(self, params: dict, context: dict) -> bool:
        """检查应用是否未安装"""
        app_name = params.get("app", "")
        if not app_name:
            return False

        try:
            from phone_agent.config.apps import APP_PACKAGES
            # 如果应用不在映射表中，可能未安装
            return app_name not in APP_PACKAGES
        except Exception:
            return False

    def _check_app_in_foreground(self, params: dict, context: dict) -> bool:
        """检查应用是否已在前台"""
        # 需要实际检查当前前台应用
        # 这需要额外的设备查询，暂时返回 False
        return False

    def _check_app_not_mapped(self, params: dict, context: dict) -> bool:
        """检查应用名称是否在映射表中"""
        app_name = params.get("app", "")
        if not app_name:
            return False

        try:
            from phone_agent.config.apps import APP_PACKAGES
            return app_name not in APP_PACKAGES
        except Exception:
            return False

    def _check_coordinates_out_of_bounds(self, params: dict, context: dict) -> bool:
        """检查坐标是否超出屏幕范围 (0-1000)"""
        element = params.get("element", [])
        if not element or len(element) < 2:
            return False

        x, y = element[0], element[1]
        return x < 0 or x > 1000 or y < 0 or y > 1000

    def _check_rapid_click(self, params: dict, context: dict) -> bool:
        """检查是否连续快速点击同一位置"""
        import time

        last_pos = context.get("last_tap_position")
        last_time = context.get("last_tap_time", 0)

        if not last_pos or not last_time:
            return False

        element = params.get("element", [])
        if not element or len(element) < 2:
            return False

        # 检查位置是否相近（允许20像素误差）
        current_pos = (element[0], element[1])
        distance = ((current_pos[0] - last_pos[0]) ** 2 + (current_pos[1] - last_pos[1]) ** 2) ** 0.5

        # 检查时间间隔是否过短（小于300ms）
        time_diff = time.time() - last_time

        return distance < 20 and time_diff < 0.3

    def _check_sensitive_area(self, params: dict, context: dict) -> bool:
        """检查是否点击敏感区域"""
        # 检查是否有 message 参数（表示敏感操作）
        return "message" in params

    def _check_contains_chinese(self, params: dict, context: dict) -> bool:
        """检查文本是否包含中文字符"""
        text = params.get("text", "")
        import re
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    def _check_no_focus(self, params: dict, context: dict) -> bool:
        """检查输入框是否无焦点"""
        # 需要实际检查 UI 状态，暂时返回 False
        return False

    def _check_long_text(self, params: dict, context: dict) -> bool:
        """检查文本长度是否超过100字符"""
        text = params.get("text", "")
        return len(text) > 100

    def _check_swipe_same_point(self, params: dict, context: dict) -> bool:
        """检查滑动起点和终点是否相同"""
        start = params.get("start", [])
        end = params.get("end", [])

        if not start or not end or len(start) < 2 or len(end) < 2:
            return False

        return start[0] == end[0] and start[1] == end[1]

    def _check_swipe_short_distance(self, params: dict, context: dict) -> bool:
        """检查滑动距离是否过短"""
        start = params.get("start", [])
        end = params.get("end", [])

        if not start or not end or len(start) < 2 or len(end) < 2:
            return False

        dx = abs(end[0] - start[0])
        dy = abs(end[1] - start[1])
        distance = (dx ** 2 + dy ** 2) ** 0.5

        # 距离小于50像素（相对坐标）认为过短
        return distance < 50

    def _check_wait_no_duration(self, params: dict, context: dict) -> bool:
        """检查是否未指定等待时长"""
        return "duration" not in params or not params.get("duration")

    def _check_wait_long_duration(self, params: dict, context: dict) -> bool:
        """检查等待时间是否超过10秒"""
        duration_str = params.get("duration", "")
        if not duration_str:
            return False

        try:
            duration = float(str(duration_str).replace("seconds", "").replace("second", "").strip())
            return duration > 10
        except ValueError:
            return False

    # ========== 动作执行器 ==========

    def _action_abort_with_error(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """中止执行并返回错误"""
        condition = rule.get("condition", "规则条件满足")
        return RuleCheckResult(
            RuleResult.ABORT,
            message=f"规则阻止执行: {condition}"
        )

    def _action_skip_success(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """跳过执行，返回成功"""
        condition = rule.get("condition", "规则条件满足")
        return RuleCheckResult(
            RuleResult.SKIP,
            message=f"规则跳过: {condition}"
        )

    def _action_clip_coordinates(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """裁剪坐标到有效范围"""
        modified = params.copy()

        if "element" in modified:
            element = modified["element"]
            if len(element) >= 2:
                modified["element"] = [
                    max(0, min(1000, element[0])),
                    max(0, min(1000, element[1]))
                ]

        if "start" in modified:
            start = modified["start"]
            if len(start) >= 2:
                modified["start"] = [
                    max(0, min(1000, start[0])),
                    max(0, min(1000, start[1]))
                ]

        if "end" in modified:
            end = modified["end"]
            if len(end) >= 2:
                modified["end"] = [
                    max(0, min(1000, end[0])),
                    max(0, min(1000, end[1]))
                ]

        return RuleCheckResult(
            RuleResult.MODIFIED,
            message="坐标已裁剪到有效范围",
            modified_params=modified
        )

    def _action_show_confirmation(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """显示确认对话框"""
        # 确认对话框由 handler 中的 confirmation_callback 处理
        # 这里只是确保 message 参数存在
        if "message" not in params:
            modified = params.copy()
            modified["message"] = "敏感操作，请确认"
            return RuleCheckResult(
                RuleResult.MODIFIED,
                modified_params=modified
            )
        return RuleCheckResult(RuleResult.CONTINUE)

    def _action_merge_clicks(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """合并连续点击"""
        # 需要记录点击历史，暂时跳过
        return RuleCheckResult(RuleResult.CONTINUE)

    def _action_use_broadcast_input(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """使用ADB广播方式输入"""
        # ADB 广播输入已经是默认行为
        return RuleCheckResult(RuleResult.CONTINUE)

    def _action_split_text(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """分段输入长文本"""
        # 分段逻辑需要在 handler 中实现
        # 这里标记需要分段
        modified = params.copy()
        modified["_split_text"] = True
        return RuleCheckResult(
            RuleResult.MODIFIED,
            modified_params=modified
        )

    def _action_convert_to_tap(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """将滑动转换为点击"""
        start = params.get("start", [500, 500])
        modified = {
            "action": "Tap",
            "element": start,
            "_converted_from_swipe": True
        }
        return RuleCheckResult(
            RuleResult.MODIFIED,
            message="滑动距离为0，已转换为点击",
            modified_params=modified
        )

    def _action_extend_swipe(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """增加滑动距离"""
        modified = params.copy()
        start = modified.get("start", [500, 500])
        end = modified.get("end", [500, 500])

        if len(start) >= 2 and len(end) >= 2:
            # 计算方向并延长距离
            dx = end[0] - start[0]
            dy = end[1] - start[1]

            # 如果距离太短，延长到至少100
            distance = (dx ** 2 + dy ** 2) ** 0.5
            if distance < 100 and distance > 0:
                scale = 100 / distance
                modified["end"] = [
                    int(start[0] + dx * scale),
                    int(start[1] + dy * scale)
                ]

        return RuleCheckResult(
            RuleResult.MODIFIED,
            message="滑动距离已增加",
            modified_params=modified
        )

    def _action_default_wait(self, params: dict, context: dict, rule: dict) -> RuleCheckResult:
        """设置默认等待时间"""
        modified = params.copy()
        modified["duration"] = "1 seconds"
        return RuleCheckResult(
            RuleResult.MODIFIED,
            message="使用默认等待时间1秒",
            modified_params=modified
        )


# 全局规则引擎实例
_rule_engine: RuleEngine | None = None


def get_rule_engine() -> RuleEngine:
    """获取规则引擎单例"""
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine
