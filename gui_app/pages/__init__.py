# -*- coding: utf-8 -*-
"""页面模块 - 包含各页面的 Mixin 类"""

from .scheduled_tasks_mixin import ScheduledTasksMixin
from .dashboard_mixin import DashboardMixin
from .device_hub_mixin import DeviceHubMixin
from .model_service_mixin import ModelServiceMixin
from .task_runner_mixin import TaskRunnerMixin
from .apk_installer_mixin import ApkInstallerMixin
from .file_manager_mixin import FileManagerMixin

__all__ = [
    "ScheduledTasksMixin",
    "DashboardMixin",
    "DeviceHubMixin",
    "ModelServiceMixin",
    "TaskRunnerMixin",
    "ApkInstallerMixin",
    "FileManagerMixin",
]
