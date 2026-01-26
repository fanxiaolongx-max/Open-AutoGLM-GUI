"""Action handler for processing AI model outputs."""

import ast
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions.rule_engine import RuleResult, get_rule_engine
from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import get_device_factory

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of an action execution."""

    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False


class ActionHandler:
    """
    Handles execution of actions from AI model output.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        confirmation_callback: Optional callback for sensitive action confirmation.
            Should return True to proceed, False to cancel.
        takeover_callback: Optional callback for takeover requests (login, captcha).
    """

    def __init__(
        self,
        device_id: str | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        tap_preview_callback: Callable[[int, int, int, int, str], tuple[bool, int, int]] | None = None,
    ):
        self.device_id = device_id
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover
        self.tap_preview_callback = tap_preview_callback  # (x, y, width, height, screenshot_b64) -> (proceed, new_x, new_y)
        self._original_ime: str | None = None
        self._keyboard_set: bool = False
        self._rule_engine = get_rule_engine()
        self._last_tap_position: tuple[int, int] | None = None
        self._last_tap_time: float = 0

    def setup_keyboard(self) -> None:
        """
        Set up ADB keyboard at task start to avoid repeated switching.
        Call this before executing any task steps.
        """
        device_factory = get_device_factory()
        try:
            self._original_ime = device_factory.detect_and_set_adb_keyboard(self.device_id)
            self._keyboard_set = True
            time.sleep(TIMING_CONFIG.action.keyboard_switch_delay)
        except Exception:
            self._keyboard_set = False

    def restore_keyboard(self) -> None:
        """
        Restore original keyboard after task completion.
        Call this after all task steps are done.
        """
        if self._keyboard_set and self._original_ime:
            device_factory = get_device_factory()
            try:
                device_factory.restore_keyboard(self._original_ime, self.device_id)
                time.sleep(TIMING_CONFIG.action.keyboard_restore_delay)
            except Exception:
                pass
            finally:
                self._keyboard_set = False
                self._original_ime = None

    def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        """
        Execute an action from the AI model.

        Args:
            action: The action dictionary from the model.
            screen_width: Current screen width in pixels.
            screen_height: Current screen height in pixels.

        Returns:
            ActionResult indicating success and whether to finish.
        """
        action_type = action.get("_metadata")

        if action_type == "finish":
            return ActionResult(
                success=True, should_finish=True, message=action.get("message")
            )

        if action_type != "do":
            return ActionResult(
                success=False,
                should_finish=True,
                message=f"Unknown action type: {action_type}",
            )

        action_name = action.get("action")
        handler_method = self._get_handler(action_name)

        if handler_method is None:
            return ActionResult(
                success=False,
                should_finish=False,
                message=f"Unknown action: {action_name}",
            )

        # 应用规则引擎
        try:
            context = {
                "device_id": self.device_id,
                "screen_width": screen_width,
                "screen_height": screen_height,
                "last_tap_position": self._last_tap_position,
                "last_tap_time": self._last_tap_time,
            }
            rule_result = self._rule_engine.apply_rules(action_name, action, context)

            if rule_result.result == RuleResult.ABORT:
                logger.info(f"规则阻止执行动作 {action_name}: {rule_result.message}")
                return ActionResult(
                    success=False,
                    should_finish=False,
                    message=rule_result.message or f"规则阻止执行: {action_name}"
                )

            if rule_result.result == RuleResult.SKIP:
                logger.info(f"规则跳过动作 {action_name}: {rule_result.message}")
                return ActionResult(
                    success=True,
                    should_finish=False,
                    message=rule_result.message or f"规则跳过: {action_name}"
                )

            if rule_result.result == RuleResult.MODIFIED and rule_result.modified_params:
                # 使用修改后的参数
                action = rule_result.modified_params
                logger.info(f"规则修改了动作 {action_name} 的参数")

                # 检查是否转换为其他动作
                if action.get("_converted_from_swipe"):
                    action_name = "Tap"
                    handler_method = self._get_handler(action_name)

        except Exception as e:
            logger.warning(f"规则引擎执行失败，继续使用原有逻辑: {e}")

        try:
            return handler_method(action, screen_width, screen_height)
        except Exception as e:
            return ActionResult(
                success=False, should_finish=False, message=f"Action failed: {e}"
            )

    def _get_handler(self, action_name: str) -> Callable | None:
        """Get the handler method for an action."""
        handlers = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Type_Name": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
            "Interact": self._handle_interact,
        }
        return handlers.get(action_name)

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        """Convert relative coordinates (0-999) to absolute pixels."""
        x = int(element[0] / 999 * screen_width)
        y = int(element[1] / 999 * screen_height)
        return x, y

    def _handle_launch(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle app launch action."""
        app_name = action.get("app")
        if not app_name:
            return ActionResult(False, False, "No app name specified")

        device_factory = get_device_factory()
        success = device_factory.launch_app(app_name, self.device_id)
        if success:
            return ActionResult(True, False)
        return ActionResult(False, False, f"App not found: {app_name}")

    def _handle_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)

        # Check for sensitive operation
        if "message" in action:
            if not self.confirmation_callback(action["message"]):
                return ActionResult(
                    success=False,
                    should_finish=True,
                    message="User cancelled sensitive operation",
                )

        # Debug mode: call tap preview callback if available
        if self.tap_preview_callback:
            logger.info(f"Debug mode enabled, calling tap preview callback for ({x}, {y})")
            try:
                # Get current screenshot for preview
                device_factory = get_device_factory()
                screenshot = device_factory.get_screenshot(self.device_id)
                screenshot_b64 = screenshot.base64_data if screenshot else ""
                
                proceed, new_x, new_y = self.tap_preview_callback(x, y, width, height, screenshot_b64)
                logger.info(f"Tap preview callback returned: proceed={proceed}, new_x={new_x}, new_y={new_y}")
                if not proceed:
                    logger.info("User cancelled tap action in debug mode")
                    return ActionResult(
                        success=False,
                        should_finish=False,
                        message="User cancelled tap action in debug mode",
                    )
                # Use adjusted coordinates
                x, y = new_x, new_y
                logger.info(f"Using adjusted coordinates: ({x}, {y})")
            except Exception as e:
                logger.warning(f"Tap preview callback failed: {e}")

        logger.info(f"Executing tap at ({x}, {y}) on device {self.device_id}")
        device_factory = get_device_factory()
        device_factory.tap(x, y, self.device_id)

        # 记录点击位置和时间，用于规则引擎检测连续快速点击
        self._last_tap_position = (x, y)
        self._last_tap_time = time.time()

        return ActionResult(True, False)

    def _handle_type(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle text input action."""
        text = action.get("text", "")
        press_enter = action.get("press_enter", False)

        device_factory = get_device_factory()

        # Ensure ADB keyboard is set up (in case setup_keyboard wasn't called)
        if not self._keyboard_set:
            self.setup_keyboard()

        # Clear existing text and type new text
        device_factory.clear_text(self.device_id)
        time.sleep(TIMING_CONFIG.action.text_clear_delay)

        # Handle multiline text by splitting on newlines
        device_factory.type_text(text, self.device_id)
        time.sleep(TIMING_CONFIG.action.text_input_delay)

        # Press Enter key if requested
        if press_enter:
            device_factory.press_enter(self.device_id)
            time.sleep(TIMING_CONFIG.action.text_input_delay)

        return ActionResult(True, False)

    def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle swipe action."""
        start = action.get("start")
        end = action.get("end")

        if not start or not end:
            return ActionResult(False, False, "Missing swipe coordinates")

        start_x, start_y = self._convert_relative_to_absolute(start, width, height)
        end_x, end_y = self._convert_relative_to_absolute(end, width, height)

        device_factory = get_device_factory()
        device_factory.swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_back(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle back button action."""
        device_factory = get_device_factory()
        device_factory.back(self.device_id)
        return ActionResult(True, False)

    def _handle_home(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle home button action."""
        device_factory = get_device_factory()
        device_factory.home(self.device_id)
        return ActionResult(True, False)

    def _handle_double_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle double tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = get_device_factory()
        device_factory.double_tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_long_press(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle long press action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = get_device_factory()
        device_factory.long_press(x, y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_wait(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle wait action."""
        duration_str = action.get("duration", "1 seconds")
        try:
            duration = float(duration_str.replace("seconds", "").strip())
        except ValueError:
            duration = 1.0

        time.sleep(duration)
        return ActionResult(True, False)

    def _handle_takeover(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle takeover request (login, captcha, etc.)."""
        message = action.get("message", "User intervention required")
        self.takeover_callback(message)
        return ActionResult(True, False)

    def _handle_note(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle note action (placeholder for content recording)."""
        # This action is typically used for recording page content
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    def _handle_call_api(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle API call action (placeholder for summarization)."""
        # This action is typically used for content summarization
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    def _handle_interact(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle interaction request (user choice needed)."""
        # This action signals that user input is needed
        return ActionResult(True, False, message="User interaction required")

    def _send_keyevent(self, keycode: str) -> None:
        """Send a keyevent to the device."""
        from phone_agent.device_factory import DeviceType, get_device_factory
        from phone_agent.hdc.connection import _run_hdc_command

        device_factory = get_device_factory()

        # Handle HDC devices with HarmonyOS-specific keyEvent command
        if device_factory.device_type == DeviceType.HDC:
            hdc_prefix = ["hdc", "-t", self.device_id] if self.device_id else ["hdc"]
            
            # Map common keycodes to HarmonyOS keyEvent codes
            # KEYCODE_ENTER (66) -> 2054 (HarmonyOS Enter key code)
            if keycode == "KEYCODE_ENTER" or keycode == "66":
                _run_hdc_command(
                    hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                    capture_output=True,
                    text=True,
                )
            else:
                # For other keys, try to use the numeric code directly
                # If keycode is a string like "KEYCODE_ENTER", convert it
                try:
                    # Try to extract numeric code from string or use as-is
                    if keycode.startswith("KEYCODE_"):
                        # For now, only handle ENTER, other keys may need mapping
                        if "ENTER" in keycode:
                            _run_hdc_command(
                                hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                                capture_output=True,
                                text=True,
                            )
                        else:
                            # Fallback to ADB-style command for unsupported keys
                            subprocess.run(
                                hdc_prefix + ["shell", "input", "keyevent", keycode],
                                capture_output=True,
                                text=True,
                            )
                    else:
                        # Assume it's a numeric code
                        _run_hdc_command(
                            hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", str(keycode)],
                            capture_output=True,
                            text=True,
                        )
                except Exception:
                    # Fallback to ADB-style command
                    subprocess.run(
                        hdc_prefix + ["shell", "input", "keyevent", keycode],
                        capture_output=True,
                        text=True,
                    )
        else:
            # ADB devices use standard input keyevent command
            cmd_prefix = ["adb", "-s", self.device_id] if self.device_id else ["adb"]
            subprocess.run(
                cmd_prefix + ["shell", "input", "keyevent", keycode],
                capture_output=True,
                text=True,
            )

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation callback using console input."""
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        """Default takeover callback using console input."""
        input(f"{message}\nPress Enter after completing manual operation...")


def parse_action(response: str) -> dict[str, Any]:
    """
    Parse action from model response.

    Args:
        response: Raw response string from the model.

    Returns:
        Parsed action dictionary.

    Raises:
        ValueError: If the response cannot be parsed.
    """
    import re
    print(f"Parsing action: {response}")

    # Handle empty or whitespace-only responses early
    if not response or not response.strip():
        raise ValueError("Empty response from model")
    try:
        response = response.strip()

        # Check again after stripping
        if not response:
            raise ValueError("Empty response after stripping")

        # 1. 首先尝试从 <answer> 标签中提取动作
        answer_match = re.search(r'<answer>(.*?)</answer>', response, re.DOTALL)
        if answer_match:
            response = answer_match.group(1).strip()
        
        # 2. 尝试匹配 do(...) 或 finish(...) 模式
        # 使用正则表达式匹配完整的函数调用
        do_match = re.search(r'(do\s*\([^)]+\))', response)
        if do_match:
            response = do_match.group(1).strip()
        else:
            finish_match = re.search(r'(finish\s*\([^)]+\))', response)
            if finish_match:
                response = finish_match.group(1).strip()
        
        # 3. 清理 markdown 格式（反引号等）
        response = response.strip('`').strip()
        
        # 4. 移除常见的响应杂质
        response = response.replace("</answer>", "").strip()
        response = response.replace("<answer>", "").strip()
        
        if response.startswith('do(action="Type"') or response.startswith(
            'do(action="Type_Name"'
        ):
            text = response.split("text=", 1)[1][1:-2]
            action = {"_metadata": "do", "action": "Type", "text": text}
            return action
        elif response.startswith("do"):
            # Use regex parsing to handle Chinese characters and special chars
            # AST parser fails on full-width chars like ？ (U+FF1F)
            try:
                import re
                action = {"_metadata": "do"}

                # Extract action type: do(action="XXX", ...)
                action_match = re.search(r'do\s*\(\s*action\s*=\s*"([^"]*)"', response)
                if action_match:
                    action["action"] = action_match.group(1)

                # Extract message parameter if present
                # Handle both simple and multiline messages
                message_match = re.search(r',\s*message\s*=\s*"((?:[^"\\]|\\.|"(?=[^,\)]*(?:,|\))))*)"', response, re.DOTALL)
                if message_match:
                    msg = message_match.group(1)
                    # Unescape common escape sequences
                    msg = msg.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t').replace('\\"', '"')
                    action["message"] = msg

                # Extract other common parameters
                for param in ["text", "index", "direction", "x", "y", "package", "app"]:
                    param_match = re.search(rf',\s*{param}\s*=\s*"([^"]*)"', response)
                    if param_match:
                        action[param] = param_match.group(1)
                    else:
                        # Try numeric value
                        param_match = re.search(rf',\s*{param}\s*=\s*(\d+)', response)
                        if param_match:
                            action[param] = int(param_match.group(1))

                # Extract array parameters (element, start, end for Tap/Swipe)
                for param in ["element", "start", "end"]:
                    param_match = re.search(rf',\s*{param}\s*=\s*\[([^\]]+)\]', response)
                    if param_match:
                        # Parse array like [268, 149]
                        try:
                            values = [int(v.strip()) for v in param_match.group(1).split(',')]
                            action[param] = values
                        except ValueError:
                            pass

                if "action" not in action:
                    raise ValueError("Could not extract action type from do()")

                return action
            except Exception as e:
                raise ValueError(f"Failed to parse do() action: {e}")

        elif response.startswith("finish"):
            action = {
                "_metadata": "finish",
                "message": response.replace("finish(message=", "")[1:-2],
            }
        else:
            raise ValueError(f"Failed to parse action: {response}")
        return action
    except Exception as e:
        raise ValueError(f"Failed to parse action: {e}")


def do(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'do' actions."""
    kwargs["_metadata"] = "do"
    return kwargs


def finish(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'finish' actions."""
    kwargs["_metadata"] = "finish"
    return kwargs
