# -*- coding: utf-8 -*-
"""GUI 组件模块"""

from .workers import (
    StreamEmitter,
    TaskWorker,
    ScriptWorker,
    VirtualizationSwitchWorker,
    DiagnosticWorker,
    ScreenshotWorker,
    ApkInstallWorker,
    MultiDeviceTaskWorker,
    MultiDeviceTaskManager,
    detect_virtualization_status,
    ensure_adb_keyboard_installed,
)

from .widgets import (
    CustomTitleBar,
    HoverExpandCard,
    DragDropTextEdit,
    DropZoneWidget,
    PythonHighlighter,
    CodeEditorDialog,
)

from .chat_worker import ChatTaskWorker

from .chat_widgets import (
    SessionListWidget,
    MessageBubble,
    MessageListWidget,
    ChatInputWidget,
    ScreenshotDialog,
)

__all__ = [
    # Workers
    "StreamEmitter",
    "TaskWorker",
    "ScriptWorker",
    "VirtualizationSwitchWorker",
    "DiagnosticWorker",
    "ScreenshotWorker",
    "ApkInstallWorker",
    "MultiDeviceTaskWorker",
    "MultiDeviceTaskManager",
    "detect_virtualization_status",
    "ensure_adb_keyboard_installed",
    # Widgets
    "CustomTitleBar",
    "HoverExpandCard",
    "DragDropTextEdit",
    "DropZoneWidget",
    "PythonHighlighter",
    "CodeEditorDialog",
    # Chat components
    "ChatTaskWorker",
    "SessionListWidget",
    "MessageBubble",
    "MessageListWidget",
    "ChatInputWidget",
    "ScreenshotDialog",
]
