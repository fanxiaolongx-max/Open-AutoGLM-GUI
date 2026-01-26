"""Configuration module for Phone Agent."""

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.apps_ios import APP_PACKAGES_IOS
from phone_agent.config.i18n import get_message, get_messages
from phone_agent.config.prompts_en import SYSTEM_PROMPT as SYSTEM_PROMPT_EN
from phone_agent.config.prompts_zh import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH
from phone_agent.config.timing import (
    TIMING_CONFIG,
    ActionTimingConfig,
    ConnectionTimingConfig,
    DeviceTimingConfig,
    TimingConfig,
    get_timing_config,
    update_timing_config,
)
from phone_agent.config.screenshot import (
    SCREENSHOT_CONFIG,
    ScreenshotConfig,
    get_screenshot_config,
    update_screenshot_config,
)


def get_system_prompt(lang: str = "cn") -> str:
    """
    Get system prompt by language.

    优先使用 rules_manager 中的自定义提示词，如果没有自定义则使用默认值。

    Args:
        lang: Language code, 'cn' for Chinese, 'en' for English.

    Returns:
        System prompt string.
    """
    # 尝试从 rules_manager 获取自定义提示词
    try:
        from gui_app.rules_manager import get_rules_manager
        rm = get_rules_manager()

        if lang == "en":
            prompt_key = "system_prompt_en"
        else:
            prompt_key = "system_prompt_zh"

        # 检查是否有自定义提示词
        if rm.is_prompt_customized(prompt_key):
            custom_prompt = rm.get_prompt(prompt_key)
            if custom_prompt:
                return custom_prompt
    except Exception:
        # 如果 rules_manager 不可用，使用默认值
        pass

    # 使用默认提示词
    if lang == "en":
        return SYSTEM_PROMPT_EN
    return SYSTEM_PROMPT_ZH


# Default to Chinese for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "APP_PACKAGES",
    "APP_PACKAGES_IOS",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "SYSTEM_PROMPT_EN",
    "get_system_prompt",
    "get_messages",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
    "SCREENSHOT_CONFIG",
    "ScreenshotConfig",
    "get_screenshot_config",
    "update_screenshot_config",
]
