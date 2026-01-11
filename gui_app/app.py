import base64
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from main import check_model_api, check_system_requirements
from phone_agent import IOSPhoneAgent, PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig
from phone_agent.config.apps import list_supported_apps
from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
from phone_agent.config.apps_ios import list_supported_apps as list_ios_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices
from gui_app.model_services import ModelServicesManager, ModelServiceConfig
from gui_app.scheduler import ScheduledTasksManager, ScheduledTask, ScheduleType, WeekDay
from gui_app.custom_widgets import NoWheelSpinBox, NoWheelDoubleSpinBox, NoWheelComboBox, NoWheelTimeEdit

# 导入拆分后的组件模块
from gui_app.components import (
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
    CustomTitleBar,
    HoverExpandCard,
    DragDropTextEdit,
    DropZoneWidget,
    PythonHighlighter,
    CodeEditorDialog,
)
from gui_app.styles import get_dark_stylesheet, get_light_stylesheet
from gui_app.pages import ScheduledTasksMixin, DashboardMixin, DeviceHubMixin, ModelServiceMixin, TaskRunnerMixin, ApkInstallerMixin, FileManagerMixin


def _adb_prefix(device_id):
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def _setup_ime_env():
    # fcitx5 在 Qt6 中应该使用 "fcitx" 作为 QT_IM_MODULE
    gtk_im = os.environ.get("GTK_IM_MODULE", "")
    xmod = os.environ.get("XMODIFIERS", "")

    if "fcitx" in xmod or "fcitx" in gtk_im:
        os.environ["QT_IM_MODULE"] = "fcitx"
        os.environ["GTK_IM_MODULE"] = "fcitx"
        os.environ.setdefault("XMODIFIERS", "@im=fcitx")
    elif "ibus" in xmod or "ibus" in gtk_im:
        os.environ["QT_IM_MODULE"] = "ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        os.environ.setdefault("XMODIFIERS", "@im=ibus")
    else:
        os.environ.setdefault("QT_IM_MODULE", "fcitx")
        os.environ.setdefault("GTK_IM_MODULE", "fcitx")
        os.environ.setdefault("XMODIFIERS", "@im=fcitx")


def ensure_adb_keyboard_installed(device_id):
    adb_prefix = _adb_prefix(device_id)
    try:
        result = subprocess.run(
            adb_prefix + ["shell", "ime", "list", "-s"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ime_list = (result.stdout + result.stderr).strip()
        if "com.android.adbkeyboard/.AdbIME" in ime_list:
            print("ADB Keyboard already installed.")
            return True, False

        apk_path = Path(__file__).resolve().parents[1] / "ADBKeyboard.apk"
        if not apk_path.exists():
            print(f"ADBKeyboard.apk not found at {apk_path}")
            return False, False

        print("Installing ADB Keyboard...")
        install_result = subprocess.run(
            adb_prefix + ["install", "-r", str(apk_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (install_result.stdout + install_result.stderr).strip()
        if install_result.returncode != 0 or "Failure" in output:
            print(f"ADB Keyboard install failed: {output}")
            return False, False

        subprocess.run(
            adb_prefix
            + ["shell", "ime", "enable", "com.android.adbkeyboard/.AdbIME"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print("ADB Keyboard installed and enabled.")
        return True, True
    except Exception as exc:
        print(f"ADB Keyboard install error: {exc}")
        return False, False


class MainWindow(FileManagerMixin, ApkInstallerMixin, TaskRunnerMixin, ModelServiceMixin, DeviceHubMixin, DashboardMixin, ScheduledTasksMixin, QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("鱼塘管理器")

        # 设置无边框窗口
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowSystemMenuHint |
            QtCore.Qt.WindowMinMaxButtonsHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)

        # 根据屏幕分辨率调整窗口大小
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # 计算合适的窗口尺寸（屏幕的75%宽度，70%高度）
        window_width = min(int(screen_width * 0.75), 1400)
        window_height = min(int(screen_height * 0.70), 850)

        # 确保最小尺寸
        window_width = max(window_width, 900)
        window_height = max(window_height, 600)

        self.resize(window_width, window_height)

        # 根据屏幕DPI计算字体缩放
        logical_dpi = screen.logicalDotsPerInch()
        self.font_scale = logical_dpi / 96.0  # 96 DPI 为标准
        if self.font_scale < 1.0:
            self.font_scale = 1.0
        elif self.font_scale > 1.5:
            self.font_scale = 1.5

        self.task_runner_index = 3
        self.apk_installer_index = 4

        self.settings = QtCore.QSettings("鱼塘管理器", "鱼塘管理器GUI")
        self.model_services_manager = ModelServicesManager()  # 多模型服务管理器
        self.scheduled_tasks_manager = ScheduledTasksManager(self)  # 定时任务管理器
        self.scheduled_tasks_manager.task_triggered.connect(self._on_scheduled_task_triggered)
        self.task_worker = None
        self.script_worker = None
        self.diagnostic_worker = None
        self.preview_worker = None
        self.apk_install_worker = None
        self.apk_install_workers = {}  # For multi-device APK installation
        self.apk_install_results = {}
        self.apk_install_total = 0
        self.apk_install_completed = 0
        self.multi_device_manager = MultiDeviceTaskManager(self)
        self.preview_inflight = False
        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setInterval(1500)
        self.preview_timer.timeout.connect(self._request_preview_frame)
        self.last_preview_image = None
        self.editor_process = None
        self.editor_temp_path = None
        
        # Multi-device preview support
        self.preview_devices = []  # List of available devices for preview
        self.preview_current_index = 0  # Current device index
        self.preview_multi_mode = False  # Multi-device preview mode
        self.preview_workers = {}  # Multiple preview workers
        self.preview_images = {}  # Store preview images for each device
        self.preview_multi_timer = QtCore.QTimer(self)  # Timer for multi-device cycling
        self.preview_multi_timer.setInterval(3000)  # Switch device every 3 seconds
        self.preview_multi_timer.timeout.connect(self._cycle_multi_preview)

        # Scheduled tasks countdown update timer
        self.sched_countdown_timer = QtCore.QTimer(self)
        self.sched_countdown_timer.setInterval(60000)  # Update every minute
        self.sched_countdown_timer.timeout.connect(self._refresh_scheduled_tasks)

        # Task counters for dashboard (manual vs scheduled)
        self.manual_tasks_count = 0
        self.scheduled_tasks_count = 0

        # 初始化规则管理器，确保自定义配置在启动时加载并同步到运行时
        from gui_app.rules_manager import get_rules_manager
        self._rules_manager = get_rules_manager()

        # Dashboard auto-refresh timer
        self.dashboard_refresh_timer = QtCore.QTimer(self)
        self.dashboard_refresh_timer.setInterval(5000)  # Refresh every 5 seconds
        self.dashboard_refresh_timer.timeout.connect(self._refresh_dashboard)

        # System diagnosis result cache
        self.system_diagnosis_result = None

        self.nav = QtWidgets.QListWidget()
        self.nav.setFixedWidth(180)
        self.nav.addItems(
            [
                "控制台",
                "设备中心",
                "模型服务",
                "任务执行",
                "定时任务",
                "应用安装",
                "文件管理",
                "规则管理",
                "系统诊断",
                "运行日志",
                "系统设置",
            ]
        )
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._switch_page)

        self.stack = QtWidgets.QStackedWidget()
        self.pages = {
            "控制台": self._build_dashboard(),
            "设备中心": self._build_device_hub(),
            "模型服务": self._build_model_service(),
            "任务执行": self._build_task_runner(),
            "定时任务": self._build_scheduled_tasks(),
            "应用安装": self._build_apk_installer(),
            "文件管理": self._build_file_manager(),
            "规则管理": self._build_rules_page(),
            "系统诊断": self._build_diagnostics_page(),
            "运行日志": self._build_logs_page(),
            "系统设置": self._build_settings_page(),
        }

        for name in self.pages:
            self.stack.addWidget(self.pages[name])

        # 创建主容器，包含自定义标题栏和内容区域
        root = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 自定义标题栏
        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)

        # 内容区域（导航 + 页面栈）
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.nav)
        content_layout.addWidget(self.stack, 1)
        main_layout.addWidget(content_widget, 1)

        self.setCentralWidget(root)

        self._load_settings()
        self._apply_style()
        self._refresh_devices()
        self._refresh_dashboard()
        self._refresh_scheduled_tasks()
        self._start_preview()
        self.scheduled_tasks_manager.start()  # 启动定时任务调度器
        self.sched_countdown_timer.start()  # 启动倒计时更新定时器

        # 启动控制台自动刷新定时器
        self.dashboard_refresh_timer.start()

        # 运行快速系统诊断
        QtCore.QTimer.singleShot(500, self._run_quick_diagnosis)

        # 设置 PIN 请求回调（当解锁需要 PIN 但未配置时触发）
        from phone_agent.adb.unlock import set_pin_request_callback
        set_pin_request_callback(self._request_pin_dialog)

        # 窗口缩放相关
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geometry = None
        self._edge_margin = 5  # 边缘检测区域宽度（减小以避免与导航栏重叠）
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)

    def _get_resize_edge(self, pos):
        """检测鼠标是否在窗口边缘，返回边缘方向"""
        # 最大化时不允许缩放
        if self.isMaximized():
            return None

        rect = self.rect()
        margin = self._edge_margin

        left = pos.x() < margin
        right = pos.x() > rect.width() - margin
        top = pos.y() < margin
        bottom = pos.y() > rect.height() - margin

        if left and top:
            return "top-left"
        elif right and top:
            return "top-right"
        elif left and bottom:
            return "bottom-left"
        elif right and bottom:
            return "bottom-right"
        elif left:
            return "left"
        elif right:
            return "right"
        elif top:
            return "top"
        elif bottom:
            return "bottom"
        return None

    def _update_cursor(self, edge):
        """根据边缘方向更新鼠标光标"""
        cursors = {
            "left": QtCore.Qt.SizeHorCursor,
            "right": QtCore.Qt.SizeHorCursor,
            "top": QtCore.Qt.SizeVerCursor,
            "bottom": QtCore.Qt.SizeVerCursor,
            "top-left": QtCore.Qt.SizeFDiagCursor,
            "bottom-right": QtCore.Qt.SizeFDiagCursor,
            "top-right": QtCore.Qt.SizeBDiagCursor,
            "bottom-left": QtCore.Qt.SizeBDiagCursor,
        }
        if edge and edge in cursors:
            self.setCursor(cursors[edge])
        else:
            self.unsetCursor()

    def mousePressEvent(self, event):
        """鼠标按下事件 - 开始缩放"""
        if event.button() == QtCore.Qt.LeftButton:
            edge = self._get_resize_edge(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geometry = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 执行缩放或更新光标"""
        if self._resize_edge and self._resize_start_pos:
            # 正在缩放
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QtCore.QRect(self._resize_start_geometry)
            min_w, min_h = 900, 600

            if "left" in self._resize_edge:
                new_left = geo.left() + delta.x()
                new_width = geo.width() - delta.x()
                if new_width >= min_w:
                    geo.setLeft(new_left)
            if "right" in self._resize_edge:
                new_width = geo.width() + delta.x()
                if new_width >= min_w:
                    geo.setWidth(new_width)
            if "top" in self._resize_edge:
                new_top = geo.top() + delta.y()
                new_height = geo.height() - delta.y()
                if new_height >= min_h:
                    geo.setTop(new_top)
            if "bottom" in self._resize_edge:
                new_height = geo.height() + delta.y()
                if new_height >= min_h:
                    geo.setHeight(new_height)

            self.setGeometry(geo)
            event.accept()
        else:
            # 更新光标
            edge = self._get_resize_edge(event.position().toPoint())
            self._update_cursor(edge)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 结束缩放"""
        if self._resize_edge:
            self._resize_edge = None
            self._resize_start_pos = None
            self._resize_start_geometry = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        """鼠标离开窗口时重置光标"""
        self.unsetCursor()
        super().leaveEvent(event)

    def closeEvent(self, event):
        """Handle window close event."""
        try:
            print("[App] Closing application, cleaning up...")

            # Stop all managers and timers
            self.scheduled_tasks_manager.stop()
            self.preview_timer.stop()
            self.sched_countdown_timer.stop()
            self.dashboard_refresh_timer.stop()

            # Stop all worker threads - use requestInterruption first, then wait
            if hasattr(self, 'task_worker') and self.task_worker:
                if self.task_worker.isRunning():
                    self.task_worker.requestInterruption()
                    if not self.task_worker.wait(2000):  # Wait up to 2 seconds
                        self.task_worker.terminate()
                        self.task_worker.wait(500)

            if hasattr(self, 'script_worker') and self.script_worker:
                if self.script_worker.isRunning():
                    self.script_worker.terminate()
                    self.script_worker.wait(1000)

            if hasattr(self, 'diagnostic_worker') and self.diagnostic_worker:
                if self.diagnostic_worker.isRunning():
                    self.diagnostic_worker.terminate()
                    self.diagnostic_worker.wait(1000)

            if hasattr(self, 'preview_worker') and self.preview_worker:
                if self.preview_worker.isRunning():
                    self.preview_worker.requestInterruption()
                    if not self.preview_worker.wait(1000):
                        self.preview_worker.terminate()
                        self.preview_worker.wait(500)

            if hasattr(self, 'apk_install_worker') and self.apk_install_worker:
                if self.apk_install_worker.isRunning():
                    self.apk_install_worker.terminate()
                    self.apk_install_worker.wait(1000)

            if hasattr(self, 'gemini_task_worker') and self.gemini_task_worker:
                if self.gemini_task_worker.isRunning():
                    self.gemini_task_worker.requestInterruption()
                    if not self.gemini_task_worker.wait(2000):
                        self.gemini_task_worker.terminate()
                        self.gemini_task_worker.wait(500)

            # Clean up multi-device manager
            if hasattr(self, 'multi_device_manager'):
                self.multi_device_manager.stop_all()

            print("[App] Cleanup complete")

        except Exception as e:
            print(f"[App] Error during cleanup: {e}")

        super().closeEvent(event)

    def _apply_style(self):
        # 根据字体缩放计算实际字体大小
        base_font = int(12 * self.font_scale)
        title_font = int(20 * self.font_scale)
        card_title_font = int(14 * self.font_scale)
        metric_font = int(24 * self.font_scale)
        small_font = int(11 * self.font_scale)

        # 检查是否为亮色主题
        is_light = getattr(self, 'current_theme', 'dark') == 'light'

        if is_light:
            self.setStyleSheet(get_light_stylesheet(base_font, title_font, card_title_font, metric_font, small_font))
        else:
            self.setStyleSheet(get_dark_stylesheet(base_font, title_font, card_title_font, metric_font, small_font))

    # 保留旧方法作为备用（后续可删除）
    def _apply_dark_style(self, base_font, title_font, card_title_font, metric_font, small_font):
        self.setStyleSheet(get_dark_stylesheet(base_font, title_font, card_title_font, metric_font, small_font))

    def _apply_light_style(self, base_font, title_font, card_title_font, metric_font, small_font):
        self.setStyleSheet(get_light_stylesheet(base_font, title_font, card_title_font, metric_font, small_font))

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == self.task_runner_index:
            # Auto refresh devices when switching to task runner page
            QtCore.QTimer.singleShot(500, self._refresh_task_devices)
            QtCore.QTimer.singleShot(600, self._refresh_preview_devices)  # Refresh preview devices too
            self._start_preview()
        elif index == self.apk_installer_index:
            # Auto refresh devices when switching to APK installer page
            QtCore.QTimer.singleShot(500, self._refresh_apk_devices)
        elif index == 4:  # Scheduled tasks page (定时任务)
            # Auto refresh devices when switching to scheduled tasks page
            QtCore.QTimer.singleShot(500, self._refresh_sched_devices)
        elif index == 1:  # Device hub page
            # Auto detect devices when switching to device hub
            QtCore.QTimer.singleShot(500, self._auto_detect_and_clean)

    def _build_rules_page(self):
        """构建规则管理页面，展示系统中的固化规则"""
        # rules_manager 已在 MainWindow.__init__ 中初始化

        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("规则管理")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("管理应用映射、时间延迟和动作类型规则")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Tab widget for different rule categories
        self.rules_tab = QtWidgets.QTabWidget()

        # Tab 1: 应用映射规则
        apps_tab = self._build_rules_apps_tab()
        self.rules_tab.addTab(apps_tab, "应用映射")

        # Tab 2: 时间延迟规则
        timing_tab = self._build_rules_timing_tab()
        self.rules_tab.addTab(timing_tab, "时间延迟")

        # Tab 3: 动作类型规则
        actions_tab = self._build_rules_actions_tab()
        self.rules_tab.addTab(actions_tab, "动作类型")

        # Tab 4: 提示词管理
        prompts_tab = self._build_rules_prompts_tab()
        self.rules_tab.addTab(prompts_tab, "提示词")

        layout.addWidget(header_widget)
        layout.addWidget(self.rules_tab, 1)
        return page

    def _build_rules_apps_tab(self):
        """构建应用映射规则标签页 - 支持增删改查"""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)

        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()

        self.rules_apps_search = QtWidgets.QLineEdit()
        self.rules_apps_search.setPlaceholderText("搜索应用名或包名...")
        self.rules_apps_search.textChanged.connect(self._filter_rules_apps)
        toolbar.addWidget(self.rules_apps_search, 1)

        self.rules_apps_count = QtWidgets.QLabel()
        self.rules_apps_count.setStyleSheet("color: #71717a; font-size: 12px;")
        toolbar.addWidget(self.rules_apps_count)

        # Action buttons
        add_btn = QtWidgets.QPushButton("添加")
        add_btn.setObjectName("success")
        add_btn.setCursor(QtCore.Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_app_rule)
        toolbar.addWidget(add_btn)

        edit_btn = QtWidgets.QPushButton("编辑")
        edit_btn.setObjectName("secondary")
        edit_btn.setCursor(QtCore.Qt.PointingHandCursor)
        edit_btn.clicked.connect(self._edit_app_rule)
        toolbar.addWidget(edit_btn)

        delete_btn = QtWidgets.QPushButton("删除")
        delete_btn.setObjectName("danger")
        delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        delete_btn.clicked.connect(self._delete_app_rule)
        toolbar.addWidget(delete_btn)

        # Table
        self.rules_apps_table = QtWidgets.QTableWidget()
        self.rules_apps_table.setColumnCount(3)
        self.rules_apps_table.setHorizontalHeaderLabels(["应用名称", "包名", "来源"])
        self.rules_apps_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.rules_apps_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.rules_apps_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.rules_apps_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.rules_apps_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.rules_apps_table.setAlternatingRowColors(True)
        self.rules_apps_table.doubleClicked.connect(self._edit_app_rule)

        layout.addLayout(toolbar)
        layout.addWidget(self.rules_apps_table)

        self._load_rules_apps()
        return tab

    def _build_rules_timing_tab(self):
        """构建时间延迟规则标签页 - 支持编辑"""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)

        # Description and buttons
        header_layout = QtWidgets.QHBoxLayout()
        desc = QtWidgets.QLabel("各种操作后的等待时间配置（双击编辑，单位：秒）")
        desc.setStyleSheet("color: #71717a; font-size: 12px;")
        header_layout.addWidget(desc, 1)

        save_btn = QtWidgets.QPushButton("保存修改")
        save_btn.setObjectName("success")
        save_btn.setCursor(QtCore.Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_timing_rules)
        header_layout.addWidget(save_btn)

        reset_btn = QtWidgets.QPushButton("恢复默认")
        reset_btn.setObjectName("secondary")
        reset_btn.setCursor(QtCore.Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_timing_rules)
        header_layout.addWidget(reset_btn)

        # Table
        self.rules_timing_table = QtWidgets.QTableWidget()
        self.rules_timing_table.setColumnCount(4)
        self.rules_timing_table.setHorizontalHeaderLabels(["类别", "配置项", "配置键", "当前值(秒)"])
        self.rules_timing_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.rules_timing_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.rules_timing_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.rules_timing_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.rules_timing_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.rules_timing_table.setAlternatingRowColors(True)

        layout.addLayout(header_layout)
        layout.addWidget(self.rules_timing_table)

        self._load_rules_timing()
        return tab

    def _build_rules_actions_tab(self):
        """构建动作类型规则标签页 - 支持查看和编辑规则内容"""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)

        # Description
        desc = QtWidgets.QLabel("管理动作类型及其规则内容（选中动作查看/编辑规则）")
        desc.setStyleSheet("color: #71717a; font-size: 12px; margin-bottom: 8px;")

        # 动作列表工具栏
        action_toolbar = QtWidgets.QHBoxLayout()
        add_action_btn = QtWidgets.QPushButton("+ 添加动作")
        add_action_btn.clicked.connect(self._add_action_rule)
        edit_action_btn = QtWidgets.QPushButton("编辑动作")
        edit_action_btn.clicked.connect(self._edit_action_rule)
        delete_action_btn = QtWidgets.QPushButton("删除动作")
        delete_action_btn.clicked.connect(self._delete_action_rule)
        reset_actions_btn = QtWidgets.QPushButton("重置为默认")
        reset_actions_btn.clicked.connect(self._reset_action_rules)
        action_toolbar.addWidget(add_action_btn)
        action_toolbar.addWidget(edit_action_btn)
        action_toolbar.addWidget(delete_action_btn)
        action_toolbar.addStretch()
        action_toolbar.addWidget(reset_actions_btn)

        # Splitter for list and details
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left: Action list with search
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 搜索框
        self.action_search_input = QtWidgets.QLineEdit()
        self.action_search_input.setPlaceholderText("搜索动作...")
        self.action_search_input.textChanged.connect(self._filter_actions)
        left_layout.addWidget(self.action_search_input)

        self.rules_actions_list = QtWidgets.QListWidget()
        self.rules_actions_list.currentRowChanged.connect(self._show_action_details)
        left_layout.addWidget(self.rules_actions_list)

        # Right: Action details with rules
        right_widget = QtWidgets.QFrame()
        right_widget.setObjectName("card")
        right_layout = QtWidgets.QVBoxLayout(right_widget)

        # 动作基本信息
        self.action_detail_name = QtWidgets.QLabel("选择一个动作查看详情")
        self.action_detail_name.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.action_detail_desc = QtWidgets.QLabel("")
        self.action_detail_desc.setStyleSheet("color: #71717a;")
        self.action_detail_desc.setWordWrap(True)

        # 参数表格标题和工具栏
        params_header = QtWidgets.QHBoxLayout()
        params_label = QtWidgets.QLabel("参数:")
        params_label.setStyleSheet("font-weight: bold; margin-top: 11px;")
        add_param_btn = QtWidgets.QPushButton("+ 添加")
        add_param_btn.clicked.connect(self._add_parameter)
        edit_param_btn = QtWidgets.QPushButton("编辑")
        edit_param_btn.clicked.connect(self._edit_parameter)
        del_param_btn = QtWidgets.QPushButton("删除")
        del_param_btn.clicked.connect(self._delete_parameter)
        params_header.addWidget(params_label)
        params_header.addStretch()
        params_header.addWidget(add_param_btn)
        params_header.addWidget(edit_param_btn)
        params_header.addWidget(del_param_btn)

        self.action_detail_params = QtWidgets.QTableWidget()
        self.action_detail_params.setColumnCount(4)
        self.action_detail_params.setHorizontalHeaderLabels(["参数名", "类型", "必填", "说明"])
        self.action_detail_params.horizontalHeader().setStretchLastSection(True)
        self.action_detail_params.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.action_detail_params.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.action_detail_params.setMaximumHeight(120)
        self.action_detail_params.doubleClicked.connect(self._edit_parameter)
        # 改善暗黑主题下表格线条可见性
        self.action_detail_params.setStyleSheet("""
            QTableWidget {
                gridline-color: rgba(128, 128, 128, 0.5);
                border: 1px solid rgba(128, 128, 128, 0.3);
            }
            QTableWidget::item {
                border-bottom: 1px solid rgba(128, 128, 128, 0.3);
            }
            QHeaderView::section {
                border: 1px solid rgba(128, 128, 128, 0.3);
                padding: 4px;
            }
        """)

        # 示例和ADB命令（折叠显示）
        example_adb_layout = QtWidgets.QHBoxLayout()

        example_group = QtWidgets.QGroupBox("调用示例")
        example_group_layout = QtWidgets.QVBoxLayout(example_group)
        self.action_detail_example = QtWidgets.QTextEdit()
        self.action_detail_example.setReadOnly(True)
        self.action_detail_example.setMaximumHeight(50)
        self.action_detail_example.setStyleSheet("font-family: 'Menlo', 'Monaco', 'Courier New'; background: rgba(0,0,0,0.1);")
        example_group_layout.addWidget(self.action_detail_example)

        adb_group = QtWidgets.QGroupBox("ADB命令")
        adb_group_layout = QtWidgets.QVBoxLayout(adb_group)
        self.action_detail_adb = QtWidgets.QTextEdit()
        self.action_detail_adb.setReadOnly(True)
        self.action_detail_adb.setMaximumHeight(50)
        self.action_detail_adb.setStyleSheet("font-family: 'Menlo', 'Monaco', 'Courier New'; background: rgba(0,0,0,0.1);")
        adb_group_layout.addWidget(self.action_detail_adb)

        example_adb_layout.addWidget(example_group)
        example_adb_layout.addWidget(adb_group)

        # 规则内容区域（新增）
        rules_label = QtWidgets.QLabel("规则内容:")
        rules_label.setStyleSheet("font-weight: bold; margin-top: 12px; font-size: 14px;")

        # 规则内容工具栏
        rules_toolbar = QtWidgets.QHBoxLayout()
        add_rule_btn = QtWidgets.QPushButton("+ 添加规则")
        add_rule_btn.clicked.connect(self._add_rule_item)
        edit_rule_btn = QtWidgets.QPushButton("编辑规则")
        edit_rule_btn.clicked.connect(self._edit_rule_item)
        delete_rule_btn = QtWidgets.QPushButton("删除规则")
        delete_rule_btn.clicked.connect(self._delete_rule_item)
        toggle_rule_btn = QtWidgets.QPushButton("启用/禁用")
        toggle_rule_btn.clicked.connect(self._toggle_rule_item)
        view_func_btn = QtWidgets.QPushButton("查看/编辑函数")
        view_func_btn.setToolTip("双击条件列也可查看绑定的函数")
        view_func_btn.clicked.connect(self._view_or_edit_condition_func)
        rules_toolbar.addWidget(add_rule_btn)
        rules_toolbar.addWidget(edit_rule_btn)
        rules_toolbar.addWidget(delete_rule_btn)
        rules_toolbar.addWidget(toggle_rule_btn)
        rules_toolbar.addWidget(view_func_btn)
        rules_toolbar.addStretch()

        # 规则内容表格
        self.action_rules_table = QtWidgets.QTableWidget()
        self.action_rules_table.setColumnCount(7)
        self.action_rules_table.setHorizontalHeaderLabels(["ID", "条件", "执行动作", "优先级", "条件函数", "动作函数", "状态"])
        self.action_rules_table.horizontalHeader().setStretchLastSection(True)
        self.action_rules_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.action_rules_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.action_rules_table.setColumnWidth(0, 90)
        self.action_rules_table.setColumnWidth(1, 140)
        self.action_rules_table.setColumnWidth(2, 160)
        self.action_rules_table.setColumnWidth(3, 45)
        self.action_rules_table.setColumnWidth(4, 60)
        self.action_rules_table.setColumnWidth(5, 60)
        self.action_rules_table.setColumnWidth(6, 45)
        self.action_rules_table.doubleClicked.connect(self._on_rule_table_double_click)
        # 改善暗黑主题下表格线条可见性
        self.action_rules_table.setStyleSheet("""
            QTableWidget {
                gridline-color: rgba(128, 128, 128, 0.5);
                border: 1px solid rgba(128, 128, 128, 0.3);
            }
            QTableWidget::item {
                border-bottom: 1px solid rgba(128, 128, 128, 0.3);
            }
            QHeaderView::section {
                border: 1px solid rgba(128, 128, 128, 0.3);
                padding: 4px;
            }
        """)

        # 导入导出工具栏
        import_export_layout = QtWidgets.QHBoxLayout()
        export_btn = QtWidgets.QPushButton("导出规则")
        export_btn.clicked.connect(self._export_rules)
        import_btn = QtWidgets.QPushButton("导入规则")
        import_btn.clicked.connect(self._import_rules)
        import_export_layout.addStretch()
        import_export_layout.addWidget(export_btn)
        import_export_layout.addWidget(import_btn)

        right_layout.addWidget(self.action_detail_name)
        right_layout.addWidget(self.action_detail_desc)
        right_layout.addLayout(params_header)
        right_layout.addWidget(self.action_detail_params)
        right_layout.addLayout(example_adb_layout)
        right_layout.addWidget(rules_label)
        right_layout.addLayout(rules_toolbar)
        right_layout.addWidget(self.action_rules_table)
        right_layout.addLayout(import_export_layout)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 500])

        layout.addWidget(desc)
        layout.addLayout(action_toolbar)
        layout.addWidget(splitter)

        self._load_rules_actions()
        return tab

    def _build_rules_prompts_tab(self):
        """构建提示词管理标签页"""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)

        # Description
        desc = QtWidgets.QLabel("管理发送给AI模型的系统提示词（选中提示词进行编辑）")
        desc.setStyleSheet("color: #71717a; font-size: 12px; margin-bottom: 8px;")

        # Splitter for list and editor
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left: Prompt list
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.prompts_list = QtWidgets.QListWidget()
        self.prompts_list.currentRowChanged.connect(self._show_prompt_details)
        left_layout.addWidget(self.prompts_list)

        # Right: Prompt editor
        right_widget = QtWidgets.QFrame()
        right_widget.setObjectName("card")
        right_layout = QtWidgets.QVBoxLayout(right_widget)

        # 提示词名称和状态
        self.prompt_name_label = QtWidgets.QLabel("选择一个提示词进行编辑")
        self.prompt_name_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.prompt_desc_label = QtWidgets.QLabel("")
        self.prompt_desc_label.setStyleSheet("color: #71717a;")
        self.prompt_desc_label.setWordWrap(True)

        self.prompt_status_label = QtWidgets.QLabel("")
        self.prompt_status_label.setStyleSheet("font-size: 12px;")

        # 提示词编辑器
        editor_label = QtWidgets.QLabel("提示词内容:")
        editor_label.setStyleSheet("font-weight: bold; margin-top: 12px;")

        self.prompt_editor = QtWidgets.QPlainTextEdit()
        self.prompt_editor.setStyleSheet("font-family: 'Menlo', 'Monaco', 'Courier New'; font-size: 13px;")
        self.prompt_editor.setPlaceholderText("在此编辑提示词内容...")

        # 字数统计
        self.prompt_char_count = QtWidgets.QLabel("字符数: 0")
        self.prompt_char_count.setStyleSheet("color: #71717a; font-size: 12px;")
        self.prompt_editor.textChanged.connect(self._update_prompt_char_count)

        # 操作按钮
        buttons_layout = QtWidgets.QHBoxLayout()
        save_prompt_btn = QtWidgets.QPushButton("保存修改")
        save_prompt_btn.clicked.connect(self._save_prompt)
        reset_prompt_btn = QtWidgets.QPushButton("恢复默认")
        reset_prompt_btn.clicked.connect(self._reset_prompt)
        reset_all_prompts_btn = QtWidgets.QPushButton("全部恢复默认")
        reset_all_prompts_btn.clicked.connect(self._reset_all_prompts)

        buttons_layout.addWidget(save_prompt_btn)
        buttons_layout.addWidget(reset_prompt_btn)
        buttons_layout.addStretch()
        buttons_layout.addWidget(reset_all_prompts_btn)

        right_layout.addWidget(self.prompt_name_label)
        right_layout.addWidget(self.prompt_desc_label)
        right_layout.addWidget(self.prompt_status_label)
        right_layout.addWidget(editor_label)
        right_layout.addWidget(self.prompt_editor, 1)
        right_layout.addWidget(self.prompt_char_count)
        right_layout.addLayout(buttons_layout)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 500])

        layout.addWidget(desc)
        layout.addWidget(splitter, 1)

        self._load_prompts_list()
        return tab

    def _load_prompts_list(self):
        """加载提示词列表"""
        prompts = self._rules_manager.get_all_prompts()

        self.prompts_list.clear()
        for key, prompt_info in prompts.items():
            name = prompt_info.get("name", key)
            is_customized = prompt_info.get("is_customized", False)
            is_custom = prompt_info.get("is_custom", False)

            if is_customized:
                display = f"[已修改] {name}"
            elif is_custom:
                display = f"[自定义] {name}"
            else:
                display = name

            item = QtWidgets.QListWidgetItem(display)
            item.setData(QtCore.Qt.UserRole, key)
            if is_customized:
                item.setForeground(QtGui.QColor("#f59e0b"))
            elif is_custom:
                item.setForeground(QtGui.QColor("#22c55e"))
            self.prompts_list.addItem(item)

        if self.prompts_list.count() > 0:
            self.prompts_list.setCurrentRow(0)

    def _show_prompt_details(self, row):
        """显示提示词详情"""
        if row < 0:
            return

        item = self.prompts_list.item(row)
        key = item.data(QtCore.Qt.UserRole)

        prompts = self._rules_manager.get_all_prompts()
        if key not in prompts:
            return

        prompt_info = prompts[key]
        self._current_prompt_key = key

        # 更新显示
        self.prompt_name_label.setText(prompt_info.get("name", key))
        self.prompt_desc_label.setText(prompt_info.get("description", ""))

        is_customized = prompt_info.get("is_customized", False)
        if is_customized:
            self.prompt_status_label.setText("状态: 已修改（与默认值不同）")
            self.prompt_status_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
        else:
            self.prompt_status_label.setText("状态: 使用默认值")
            self.prompt_status_label.setStyleSheet("color: #22c55e; font-size: 12px;")

        # 加载内容到编辑器
        self.prompt_editor.setPlainText(prompt_info.get("content", ""))

    def _update_prompt_char_count(self):
        """更新字符数统计"""
        text = self.prompt_editor.toPlainText()
        self.prompt_char_count.setText(f"字符数: {len(text)}")

    def _save_prompt(self):
        """保存提示词修改"""
        if not hasattr(self, '_current_prompt_key'):
            return

        key = self._current_prompt_key
        content = self.prompt_editor.toPlainText()

        if self._rules_manager.update_prompt(key, content):
            self._load_prompts_list()
            # 重新选中当前项
            for i in range(self.prompts_list.count()):
                item = self.prompts_list.item(i)
                if item.data(QtCore.Qt.UserRole) == key:
                    self.prompts_list.setCurrentRow(i)
                    break
            QtWidgets.QMessageBox.information(self, "成功", "提示词已保存。\n\n注意：修改将在下次启动任务时生效。")

    def _reset_prompt(self):
        """恢复当前提示词为默认值"""
        if not hasattr(self, '_current_prompt_key'):
            return

        key = self._current_prompt_key

        reply = QtWidgets.QMessageBox.question(
            self, "确认恢复",
            "确定要将此提示词恢复为默认值吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self._rules_manager.reset_prompt(key):
                self._load_prompts_list()
                for i in range(self.prompts_list.count()):
                    item = self.prompts_list.item(i)
                    if item.data(QtCore.Qt.UserRole) == key:
                        self.prompts_list.setCurrentRow(i)
                        break
                QtWidgets.QMessageBox.information(self, "成功", "已恢复为默认值。")

    def _reset_all_prompts(self):
        """恢复所有提示词为默认值"""
        reply = QtWidgets.QMessageBox.question(
            self, "确认恢复",
            "确定要将所有提示词恢复为默认值吗？\n这将清除所有自定义修改。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self._rules_manager.reset_all_prompts()
            self._load_prompts_list()
            QtWidgets.QMessageBox.information(self, "成功", "所有提示词已恢复为默认值。")

    def _load_rules_apps(self):
        """加载应用映射规则数据"""
        all_apps = self._rules_manager.get_all_apps()
        custom_apps = self._rules_manager.get_custom_apps()

        self.rules_apps_table.setRowCount(len(all_apps))
        for row, (app_name, package_name) in enumerate(sorted(all_apps.items())):
            self.rules_apps_table.setItem(row, 0, QtWidgets.QTableWidgetItem(app_name))
            self.rules_apps_table.setItem(row, 1, QtWidgets.QTableWidgetItem(package_name))

            source = "自定义" if app_name in custom_apps else "内置"
            source_item = QtWidgets.QTableWidgetItem(source)
            if source == "自定义":
                source_item.setForeground(QtGui.QColor("#22c55e"))
            else:
                source_item.setForeground(QtGui.QColor("#71717a"))
            self.rules_apps_table.setItem(row, 2, source_item)

        custom_count = len(custom_apps)
        total_count = len(all_apps)
        self.rules_apps_count.setText(f"共 {total_count} 条 (自定义 {custom_count} 条)")

    def _load_rules_timing(self):
        """加载时间延迟规则数据"""
        from phone_agent.config.timing import TIMING_CONFIG

        # 配置项映射：(类别, 显示名, 配置键, 类别键)
        timing_data = [
            ("动作延迟", "键盘切换延迟", "keyboard_switch_delay", "action", TIMING_CONFIG.action.keyboard_switch_delay),
            ("动作延迟", "文本清除延迟", "text_clear_delay", "action", TIMING_CONFIG.action.text_clear_delay),
            ("动作延迟", "文本输入延迟", "text_input_delay", "action", TIMING_CONFIG.action.text_input_delay),
            ("动作延迟", "键盘恢复延迟", "keyboard_restore_delay", "action", TIMING_CONFIG.action.keyboard_restore_delay),
            ("设备操作", "点击后延迟", "default_tap_delay", "device", TIMING_CONFIG.device.default_tap_delay),
            ("设备操作", "双击后延迟", "default_double_tap_delay", "device", TIMING_CONFIG.device.default_double_tap_delay),
            ("设备操作", "双击间隔", "double_tap_interval", "device", TIMING_CONFIG.device.double_tap_interval),
            ("设备操作", "长按后延迟", "default_long_press_delay", "device", TIMING_CONFIG.device.default_long_press_delay),
            ("设备操作", "滑动后延迟", "default_swipe_delay", "device", TIMING_CONFIG.device.default_swipe_delay),
            ("设备操作", "返回键后延迟", "default_back_delay", "device", TIMING_CONFIG.device.default_back_delay),
            ("设备操作", "Home键后延迟", "default_home_delay", "device", TIMING_CONFIG.device.default_home_delay),
            ("设备操作", "启动应用后延迟", "default_launch_delay", "device", TIMING_CONFIG.device.default_launch_delay),
            ("连接配置", "ADB重启延迟", "adb_restart_delay", "connection", TIMING_CONFIG.connection.adb_restart_delay),
            ("连接配置", "服务重启延迟", "server_restart_delay", "connection", TIMING_CONFIG.connection.server_restart_delay),
        ]

        self.rules_timing_table.setRowCount(len(timing_data))
        for row, (category, name, key, cat_key, value) in enumerate(timing_data):
            # 类别
            cat_item = QtWidgets.QTableWidgetItem(category)
            cat_item.setFlags(cat_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.rules_timing_table.setItem(row, 0, cat_item)

            # 显示名
            name_item = QtWidgets.QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.rules_timing_table.setItem(row, 1, name_item)

            # 配置键（隐藏用于保存）
            key_item = QtWidgets.QTableWidgetItem(f"{cat_key}.{key}")
            key_item.setFlags(key_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.rules_timing_table.setItem(row, 2, key_item)

            # 当前值（可编辑）
            value_item = QtWidgets.QTableWidgetItem(str(value))
            self.rules_timing_table.setItem(row, 3, value_item)

        # 隐藏配置键列
        self.rules_timing_table.setColumnHidden(2, True)

    def _load_rules_actions(self):
        """加载动作类型规则数据"""
        action_rules = self._rules_manager.get_action_rules()

        self.rules_actions_list.clear()
        for rule in action_rules:
            is_custom = rule.get("is_custom", False)
            prefix = "[自定义] " if is_custom else ""
            desc_text = rule['description'][:18] + "..." if len(rule['description']) > 18 else rule['description']
            item = QtWidgets.QListWidgetItem(f"{prefix}{rule['name']} - {desc_text}")
            item.setData(QtCore.Qt.UserRole, rule)
            if is_custom:
                item.setForeground(QtGui.QColor("#22c55e"))
            self.rules_actions_list.addItem(item)

        if self.rules_actions_list.count() > 0:
            self.rules_actions_list.setCurrentRow(0)

    def _show_action_details(self, row):
        """显示动作详情及其规则内容"""
        if row < 0:
            return

        item = self.rules_actions_list.item(row)
        rule = item.data(QtCore.Qt.UserRole)

        # 保存当前选中的动作名称
        self._current_action_name = rule["name"]

        # 基本信息
        is_custom = rule.get("is_custom", False)
        name_text = f"{rule['name']} {'[自定义]' if is_custom else '[内置]'}"
        self.action_detail_name.setText(name_text)
        self.action_detail_desc.setText(rule["description"])
        self.action_detail_example.setPlainText(rule.get("example", ""))
        self.action_detail_adb.setPlainText(rule.get("adb_command", "") or "无")

        # 参数表格
        params = rule.get("parameters", [])
        self.action_detail_params.setRowCount(len(params))
        for i, param in enumerate(params):
            self.action_detail_params.setItem(i, 0, QtWidgets.QTableWidgetItem(param.get("name", "")))
            self.action_detail_params.setItem(i, 1, QtWidgets.QTableWidgetItem(param.get("type", "")))
            self.action_detail_params.setItem(i, 2, QtWidgets.QTableWidgetItem("是" if param.get("required") else "否"))
            self.action_detail_params.setItem(i, 3, QtWidgets.QTableWidgetItem(param.get("description", "")))

        # 规则内容表格
        rules = rule.get("rules", [])
        self.action_rules_table.setRowCount(len(rules))

        # 获取规则引擎用于检查预定义函数
        try:
            from phone_agent.actions.rule_engine import get_rule_engine
            rule_engine = get_rule_engine()
        except ImportError:
            rule_engine = None

        for i, rule_item in enumerate(rules):
            rule_id = rule_item.get("id", "")
            condition = rule_item.get("condition", "")

            # ID
            id_item = QtWidgets.QTableWidgetItem(rule_id)
            self.action_rules_table.setItem(i, 0, id_item)
            # 条件
            cond_item = QtWidgets.QTableWidgetItem(condition)
            self.action_rules_table.setItem(i, 1, cond_item)
            # 执行动作
            action_item = QtWidgets.QTableWidgetItem(rule_item.get("action", ""))
            self.action_rules_table.setItem(i, 2, action_item)
            # 优先级
            priority_item = QtWidgets.QTableWidgetItem(str(rule_item.get("priority", 0)))
            self.action_rules_table.setItem(i, 3, priority_item)

            # 函数状态
            has_custom_func = rule_item.get("condition_func") is not None
            has_predefined_func = False
            if rule_engine:
                condition_key = rule_engine.get_condition_key_for_rule(rule["name"], condition, rule_id)
                has_predefined_func = condition_key is not None

            if has_custom_func:
                func_item = QtWidgets.QTableWidgetItem("自定义")
                func_item.setForeground(QtGui.QColor("#22c55e"))  # 绿色
                func_item.setToolTip("双击查看/编辑自定义函数")
            elif has_predefined_func:
                func_item = QtWidgets.QTableWidgetItem("预定义")
                func_item.setForeground(QtGui.QColor("#3b82f6"))  # 蓝色
                func_item.setToolTip("双击查看预定义函数源码")
            else:
                func_item = QtWidgets.QTableWidgetItem("无")
                func_item.setForeground(QtGui.QColor("#71717a"))  # 灰色
                func_item.setToolTip("此条件暂无绑定的检查函数")
            self.action_rules_table.setItem(i, 4, func_item)

            # 动作函数状态
            has_custom_action_func = rule_item.get("action_func") is not None
            has_predefined_action_func = False
            if rule_engine:
                action_key = rule_engine.get_action_key_for_rule(rule["name"], rule_item.get("action", ""), rule_id)
                has_predefined_action_func = action_key is not None

            if has_custom_action_func:
                action_func_item = QtWidgets.QTableWidgetItem("自定义")
                action_func_item.setForeground(QtGui.QColor("#22c55e"))  # 绿色
                action_func_item.setToolTip("双击查看/编辑自定义动作函数")
            elif has_predefined_action_func:
                action_func_item = QtWidgets.QTableWidgetItem("预定义")
                action_func_item.setForeground(QtGui.QColor("#3b82f6"))  # 蓝色
                action_func_item.setToolTip("双击查看预定义动作函数源码")
            else:
                action_func_item = QtWidgets.QTableWidgetItem("无")
                action_func_item.setForeground(QtGui.QColor("#71717a"))  # 灰色
                action_func_item.setToolTip("此动作暂无绑定的执行函数")
            self.action_rules_table.setItem(i, 5, action_func_item)

            # 状态
            enabled = rule_item.get("enabled", True)
            status_item = QtWidgets.QTableWidgetItem("启用" if enabled else "禁用")
            if enabled:
                status_item.setForeground(QtGui.QColor("#22c55e"))
            else:
                status_item.setForeground(QtGui.QColor("#ef4444"))
            self.action_rules_table.setItem(i, 6, status_item)

    def _filter_rules_apps(self, text):
        """过滤应用映射表格"""
        for row in range(self.rules_apps_table.rowCount()):
            app_name = self.rules_apps_table.item(row, 0).text().lower()
            package_name = self.rules_apps_table.item(row, 1).text().lower()
            match = text.lower() in app_name or text.lower() in package_name
            self.rules_apps_table.setRowHidden(row, not match)

    def _add_app_rule(self):
        """添加应用映射规则"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("添加应用映射")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QFormLayout(dialog)

        name_input = QtWidgets.QLineEdit()
        name_input.setPlaceholderText("如：抖音、微信")
        package_input = QtWidgets.QLineEdit()
        package_input.setPlaceholderText("如：com.ss.android.ugc.aweme")

        layout.addRow("应用名称:", name_input)
        layout.addRow("包名:", package_input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            name = name_input.text().strip()
            package = package_input.text().strip()
            if name and package:
                self._rules_manager.add_app(name, package)
                self._load_rules_apps()

    def _edit_app_rule(self):
        """编辑应用映射规则"""
        selected = self.rules_apps_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        old_name = self.rules_apps_table.item(row, 0).text()
        old_package = self.rules_apps_table.item(row, 1).text()
        source = self.rules_apps_table.item(row, 2).text()

        if source == "内置":
            QtWidgets.QMessageBox.information(self, "提示", "内置规则不可编辑，但您可以添加同名自定义规则覆盖它。")
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("编辑应用映射")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QFormLayout(dialog)

        name_input = QtWidgets.QLineEdit(old_name)
        package_input = QtWidgets.QLineEdit(old_package)

        layout.addRow("应用名称:", name_input)
        layout.addRow("包名:", package_input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_name = name_input.text().strip()
            new_package = package_input.text().strip()
            if new_name and new_package:
                self._rules_manager.update_app(old_name, new_name, new_package)
                self._load_rules_apps()

    def _delete_app_rule(self):
        """删除应用映射规则"""
        selected = self.rules_apps_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        app_name = self.rules_apps_table.item(row, 0).text()
        source = self.rules_apps_table.item(row, 2).text()

        if source == "内置":
            QtWidgets.QMessageBox.information(self, "提示", "内置规则不可删除。")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除应用映射 '{app_name}' 吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self._rules_manager.delete_app(app_name)
            self._load_rules_apps()

    def _save_timing_rules(self):
        """保存时间延迟规则"""
        for row in range(self.rules_timing_table.rowCount()):
            key_item = self.rules_timing_table.item(row, 2)
            value_item = self.rules_timing_table.item(row, 3)

            if key_item and value_item:
                full_key = key_item.text()
                try:
                    value = float(value_item.text())
                    category, key = full_key.split(".", 1)
                    self._rules_manager.update_timing(category, key, value)
                except ValueError:
                    pass

        QtWidgets.QMessageBox.information(self, "成功", "时间延迟规则已保存。")

    def _reset_timing_rules(self):
        """重置时间延迟规则为默认值"""
        reply = QtWidgets.QMessageBox.question(
            self, "确认重置",
            "确定要将所有时间延迟恢复为默认值吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            # 重新初始化配置
            from phone_agent.config.timing import TimingConfig, TIMING_CONFIG
            import phone_agent.config.timing as timing_module
            timing_module.TIMING_CONFIG = TimingConfig()
            self._load_rules_timing()
            QtWidgets.QMessageBox.information(self, "成功", "已恢复默认值。")

    def _refresh_rules(self):
        """刷新所有规则数据"""
        self._load_rules_apps()
        self._load_rules_timing()
        self._load_rules_actions()

    # ========== 动作规则增删改查 ==========

    def _add_action_rule(self):
        """添加新的动作规则"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("添加动作规则")
        dialog.setMinimumWidth(500)

        layout = QtWidgets.QFormLayout(dialog)

        name_input = QtWidgets.QLineEdit()
        name_input.setPlaceholderText("如: Custom_Action")
        desc_input = QtWidgets.QLineEdit()
        desc_input.setPlaceholderText("动作的功能说明")
        example_input = QtWidgets.QLineEdit()
        example_input.setPlaceholderText('如: do(action="Custom_Action", param="value")')
        adb_input = QtWidgets.QLineEdit()
        adb_input.setPlaceholderText("对应的ADB命令（可选）")

        layout.addRow("动作名称:", name_input)
        layout.addRow("动作说明:", desc_input)
        layout.addRow("调用示例:", example_input)
        layout.addRow("ADB命令:", adb_input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            name = name_input.text().strip()
            if not name:
                QtWidgets.QMessageBox.warning(self, "错误", "动作名称不能为空。")
                return

            action_data = {
                "name": name,
                "description": desc_input.text().strip(),
                "parameters": [],
                "example": example_input.text().strip(),
                "adb_command": adb_input.text().strip(),
                "rules": [],
                "is_custom": True
            }

            if self._rules_manager.add_action_rule(action_data):
                self._load_rules_actions()
                QtWidgets.QMessageBox.information(self, "成功", f"动作 '{name}' 已添加。")
            else:
                QtWidgets.QMessageBox.warning(self, "错误", f"动作 '{name}' 已存在。")

    def _edit_action_rule(self):
        """编辑动作规则"""
        current_item = self.rules_actions_list.currentItem()
        if not current_item:
            return

        rule = current_item.data(QtCore.Qt.UserRole)
        is_custom = rule.get("is_custom", False)

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"编辑动作: {rule['name']}")
        dialog.setMinimumWidth(500)

        layout = QtWidgets.QFormLayout(dialog)

        name_input = QtWidgets.QLineEdit(rule["name"])
        name_input.setEnabled(is_custom)  # 内置动作不允许改名
        desc_input = QtWidgets.QLineEdit(rule.get("description", ""))
        example_input = QtWidgets.QLineEdit(rule.get("example", ""))
        adb_input = QtWidgets.QLineEdit(rule.get("adb_command", ""))

        layout.addRow("动作名称:", name_input)
        layout.addRow("动作说明:", desc_input)
        layout.addRow("调用示例:", example_input)
        layout.addRow("ADB命令:", adb_input)

        if not is_custom:
            note = QtWidgets.QLabel("注: 内置动作只能修改说明、示例和ADB命令")
            note.setStyleSheet("color: #f59e0b; font-size: 12px;")
            layout.addRow(note)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            updates = {
                "description": desc_input.text().strip(),
                "example": example_input.text().strip(),
                "adb_command": adb_input.text().strip(),
            }
            if is_custom:
                updates["name"] = name_input.text().strip()

            self._rules_manager.update_action_rule(rule["name"], updates)
            self._load_rules_actions()

    def _delete_action_rule(self):
        """删除动作规则"""
        current_item = self.rules_actions_list.currentItem()
        if not current_item:
            return

        rule = current_item.data(QtCore.Qt.UserRole)
        is_custom = rule.get("is_custom", False)

        if not is_custom:
            QtWidgets.QMessageBox.information(self, "提示", "内置动作不可删除。")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除动作 '{rule['name']}' 吗？\n此操作将同时删除该动作的所有规则内容。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self._rules_manager.delete_action_rule(rule["name"]):
                self._load_rules_actions()
                QtWidgets.QMessageBox.information(self, "成功", f"动作 '{rule['name']}' 已删除。")

    def _reset_action_rules(self):
        """重置动作规则为默认值"""
        reply = QtWidgets.QMessageBox.question(
            self, "确认重置",
            "确定要将所有动作规则恢复为默认值吗？\n这将删除所有自定义动作和规则修改。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self._rules_manager.reset_action_rules()
            self._load_rules_actions()
            QtWidgets.QMessageBox.information(self, "成功", "已恢复默认动作规则。")

    # ========== 规则内容增删改查 ==========

    def _get_current_action_name(self):
        """获取当前选中的动作名称"""
        return getattr(self, '_current_action_name', None)

    def _add_rule_item(self):
        """添加规则项"""
        action_name = self._get_current_action_name()
        if not action_name:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择一个动作。")
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"添加规则 - {action_name}")
        dialog.setMinimumWidth(450)

        layout = QtWidgets.QFormLayout(dialog)

        condition_input = QtWidgets.QLineEdit()
        condition_input.setPlaceholderText("触发此规则的条件")
        action_input = QtWidgets.QLineEdit()
        action_input.setPlaceholderText("满足条件时执行的动作")
        priority_input = QtWidgets.QSpinBox()
        priority_input.setRange(0, 100)
        priority_input.setValue(5)
        enabled_check = QtWidgets.QCheckBox("启用此规则")
        enabled_check.setChecked(True)

        layout.addRow("条件:", condition_input)
        layout.addRow("执行动作:", action_input)
        layout.addRow("优先级:", priority_input)
        layout.addRow("", enabled_check)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            rule_item = {
                "condition": condition_input.text().strip(),
                "action": action_input.text().strip(),
                "priority": priority_input.value(),
                "enabled": enabled_check.isChecked()
            }

            if self._rules_manager.add_rule_item(action_name, rule_item):
                self._load_rules_actions()
                # 重新选中当前动作
                for i in range(self.rules_actions_list.count()):
                    item = self.rules_actions_list.item(i)
                    if item.data(QtCore.Qt.UserRole)["name"] == action_name:
                        self.rules_actions_list.setCurrentRow(i)
                        break

    def _edit_rule_item(self):
        """编辑规则项"""
        action_name = self._get_current_action_name()
        if not action_name:
            return

        selected = self.action_rules_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要编辑的规则。")
            return

        row = selected[0].row()
        rule_id = self.action_rules_table.item(row, 0).text()
        condition = self.action_rules_table.item(row, 1).text()
        action = self.action_rules_table.item(row, 2).text()
        priority = int(self.action_rules_table.item(row, 3).text())
        enabled = self.action_rules_table.item(row, 6).text() == "启用"  # 状态列是第7列（索引6）

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"编辑规则 - {rule_id}")
        dialog.setMinimumWidth(450)

        layout = QtWidgets.QFormLayout(dialog)

        condition_input = QtWidgets.QLineEdit(condition)
        action_input = QtWidgets.QLineEdit(action)
        priority_input = QtWidgets.QSpinBox()
        priority_input.setRange(0, 100)
        priority_input.setValue(priority)
        enabled_check = QtWidgets.QCheckBox("启用此规则")
        enabled_check.setChecked(enabled)

        layout.addRow("条件:", condition_input)
        layout.addRow("执行动作:", action_input)
        layout.addRow("优先级:", priority_input)
        layout.addRow("", enabled_check)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            updates = {
                "condition": condition_input.text().strip(),
                "action": action_input.text().strip(),
                "priority": priority_input.value(),
                "enabled": enabled_check.isChecked()
            }

            if self._rules_manager.update_rule_item(action_name, rule_id, updates):
                self._load_rules_actions()
                for i in range(self.rules_actions_list.count()):
                    item = self.rules_actions_list.item(i)
                    if item.data(QtCore.Qt.UserRole)["name"] == action_name:
                        self.rules_actions_list.setCurrentRow(i)
                        break

    def _delete_rule_item(self):
        """删除规则项"""
        action_name = self._get_current_action_name()
        if not action_name:
            return

        selected = self.action_rules_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要删除的规则。")
            return

        row = selected[0].row()
        rule_id = self.action_rules_table.item(row, 0).text()
        condition = self.action_rules_table.item(row, 1).text()

        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除规则 '{rule_id}' 吗？\n条件: {condition}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self._rules_manager.delete_rule_item(action_name, rule_id):
                self._load_rules_actions()
                for i in range(self.rules_actions_list.count()):
                    item = self.rules_actions_list.item(i)
                    if item.data(QtCore.Qt.UserRole)["name"] == action_name:
                        self.rules_actions_list.setCurrentRow(i)
                        break

    def _toggle_rule_item(self):
        """切换规则项启用状态"""
        action_name = self._get_current_action_name()
        if not action_name:
            return

        selected = self.action_rules_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要切换的规则。")
            return

        row = selected[0].row()
        rule_id = self.action_rules_table.item(row, 0).text()

        if self._rules_manager.toggle_rule_item(action_name, rule_id):
            self._load_rules_actions()
            for i in range(self.rules_actions_list.count()):
                item = self.rules_actions_list.item(i)
                if item.data(QtCore.Qt.UserRole)["name"] == action_name:
                    self.rules_actions_list.setCurrentRow(i)
                    break

    def _on_rule_table_double_click(self, index):
        """规则表格双击处理 - 根据点击的列执行不同操作"""
        column = index.column()
        if column == 1 or column == 4:  # 条件列或条件函数列
            self._view_or_edit_condition_func()
        elif column == 2 or column == 5:  # 执行动作列或动作函数列
            self._view_or_edit_action_func()
        else:
            self._edit_rule_item()

    def _view_or_edit_condition_func(self):
        """查看或编辑条件检查函数"""
        action_name = self._get_current_action_name()
        if not action_name:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择一个动作。")
            return

        selected = self.action_rules_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一条规则。")
            return

        row = selected[0].row()
        rule_id = self.action_rules_table.item(row, 0).text()
        condition = self.action_rules_table.item(row, 1).text()
        func_status = self.action_rules_table.item(row, 4).text()

        # 获取规则引擎
        try:
            from phone_agent.actions.rule_engine import get_rule_engine
            rule_engine = get_rule_engine()
        except ImportError:
            rule_engine = None

        # 检查是否有自定义函数
        custom_func_code = self._rules_manager.get_rule_condition_func(action_name, rule_id)

        if custom_func_code:
            # 有自定义函数 - 编辑模式
            dialog = CodeEditorDialog(
                self,
                title=f"编辑自定义条件函数 - {rule_id}",
                code=custom_func_code,
                readonly=False
            )
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                new_code = dialog.get_code()
                if new_code.strip():
                    # 验证并注册函数
                    if rule_engine:
                        success, message = rule_engine.register_custom_condition(rule_id, new_code)
                        if not success:
                            QtWidgets.QMessageBox.warning(self, "函数验证失败", message)
                            return
                    # 保存到规则管理器
                    self._rules_manager.set_rule_condition_func(action_name, rule_id, new_code)
                    self._refresh_current_action()
                    QtWidgets.QMessageBox.information(self, "成功", "自定义条件函数已保存。")
                else:
                    # 删除自定义函数
                    reply = QtWidgets.QMessageBox.question(
                        self, "确认删除",
                        "代码为空，是否删除自定义条件函数？",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                    )
                    if reply == QtWidgets.QMessageBox.Yes:
                        self._rules_manager.remove_rule_condition_func(action_name, rule_id)
                        if rule_engine:
                            rule_engine.unregister_custom_condition(rule_id)
                        self._refresh_current_action()

        elif func_status == "预定义" and rule_engine:
            # 有预定义函数 - 只读查看模式
            condition_key = rule_engine.get_condition_key_for_rule(action_name, condition, rule_id)
            if condition_key:
                source_code = rule_engine.get_predefined_condition_source(condition_key)
                if source_code:
                    dialog = CodeEditorDialog(
                        self,
                        title=f"查看预定义条件函数 - {condition_key}",
                        code=source_code,
                        readonly=True
                    )
                    # 添加"复制为自定义函数"按钮
                    copy_btn = QtWidgets.QPushButton("复制为自定义函数")

                    def copy_as_custom():
                        dialog.reject()
                        self._create_custom_func_from_predefined(action_name, rule_id, source_code)

                    copy_btn.clicked.connect(copy_as_custom)
                    dialog.layout().itemAt(2).layout().insertWidget(0, copy_btn)
                    dialog.exec()
                else:
                    QtWidgets.QMessageBox.information(
                        self, "提示",
                        f"无法获取函数 '{condition_key}' 的源代码。"
                    )
            else:
                QtWidgets.QMessageBox.information(
                    self, "提示",
                    "无法找到对应的预定义函数。"
                )
        else:
            # 无函数 - 询问是否创建自定义函数
            reply = QtWidgets.QMessageBox.question(
                self, "创建自定义函数",
                f"条件 '{condition}' 当前没有绑定的检查函数。\n\n是否为此条件创建自定义检查函数？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self._create_new_custom_func(action_name, rule_id)

    def _create_custom_func_from_predefined(self, action_name: str, rule_id: str, source_code: str):
        """从预定义函数复制创建自定义函数"""
        # 修改函数名为 check_condition
        import re
        modified_code = re.sub(
            r'def\s+_check_\w+\s*\(',
            'def check_condition(',
            source_code
        )

        dialog = CodeEditorDialog(
            self,
            title=f"基于预定义函数创建自定义函数 - {rule_id}",
            code=modified_code,
            readonly=False
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_code = dialog.get_code()
            if new_code.strip():
                # 验证并注册函数
                try:
                    from phone_agent.actions.rule_engine import get_rule_engine
                    rule_engine = get_rule_engine()
                    success, message = rule_engine.register_custom_condition(rule_id, new_code)
                    if not success:
                        QtWidgets.QMessageBox.warning(self, "函数验证失败", message)
                        return
                except ImportError:
                    pass

                self._rules_manager.set_rule_condition_func(action_name, rule_id, new_code)
                self._refresh_current_action()
                QtWidgets.QMessageBox.information(self, "成功", "自定义条件函数已创建。")

    def _create_new_custom_func(self, action_name: str, rule_id: str):
        """创建新的自定义条件函数"""
        # 获取模板代码
        try:
            from phone_agent.actions.rule_engine import get_rule_engine
            rule_engine = get_rule_engine()
            template_code = rule_engine.get_custom_condition_template()
        except ImportError:
            template_code = """def check_condition(params: dict, context: dict) -> bool:
    \"\"\"
    自定义条件检查函数

    Args:
        params: 动作参数字典
        context: 执行上下文字典

    Returns:
        True: 条件满足，触发规则动作
        False: 条件不满足，跳过此规则
    \"\"\"
    # 在这里编写您的条件检查逻辑
    return False
"""

        dialog = CodeEditorDialog(
            self,
            title=f"创建自定义条件函数 - {rule_id}",
            code=template_code,
            readonly=False
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_code = dialog.get_code()
            if new_code.strip():
                # 验证并注册函数
                try:
                    from phone_agent.actions.rule_engine import get_rule_engine
                    rule_engine = get_rule_engine()
                    success, message = rule_engine.register_custom_condition(rule_id, new_code)
                    if not success:
                        QtWidgets.QMessageBox.warning(self, "函数验证失败", message)
                        return
                except ImportError:
                    pass

                self._rules_manager.set_rule_condition_func(action_name, rule_id, new_code)
                self._refresh_current_action()
                QtWidgets.QMessageBox.information(self, "成功", "自定义条件函数已创建。")

    def _refresh_current_action(self):
        """刷新当前选中的动作详情"""
        action_name = self._get_current_action_name()
        if action_name:
            self._load_rules_actions()
            for i in range(self.rules_actions_list.count()):
                item = self.rules_actions_list.item(i)
                if item.data(QtCore.Qt.UserRole)["name"] == action_name:
                    self.rules_actions_list.setCurrentRow(i)
                    break

    # ========== 动作函数管理 ==========

    def _view_or_edit_action_func(self):
        """查看或编辑动作执行函数"""
        action_name = self._get_current_action_name()
        if not action_name:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择一个动作。")
            return

        selected = self.action_rules_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一条规则。")
            return

        row = selected[0].row()
        rule_id = self.action_rules_table.item(row, 0).text()
        action_desc = self.action_rules_table.item(row, 2).text()
        func_status = self.action_rules_table.item(row, 5).text()

        # 获取规则引擎
        try:
            from phone_agent.actions.rule_engine import get_rule_engine
            rule_engine = get_rule_engine()
        except ImportError:
            rule_engine = None

        # 检查是否有自定义函数
        custom_func_code = self._rules_manager.get_rule_action_func(action_name, rule_id)

        if custom_func_code:
            # 有自定义函数 - 编辑模式
            dialog = CodeEditorDialog(
                self,
                title=f"编辑自定义动作函数 - {rule_id}",
                code=custom_func_code,
                readonly=False
            )
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                new_code = dialog.get_code()
                if new_code.strip():
                    # 验证并注册函数
                    if rule_engine:
                        success, message = rule_engine.register_custom_action(rule_id, new_code)
                        if not success:
                            QtWidgets.QMessageBox.warning(self, "函数验证失败", message)
                            return
                    # 保存到规则管理器
                    self._rules_manager.set_rule_action_func(action_name, rule_id, new_code)
                    self._refresh_current_action()
                    QtWidgets.QMessageBox.information(self, "成功", "自定义动作函数已保存。")
                else:
                    # 删除自定义函数
                    reply = QtWidgets.QMessageBox.question(
                        self, "确认删除",
                        "代码为空，是否删除自定义动作函数？",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                    )
                    if reply == QtWidgets.QMessageBox.Yes:
                        self._rules_manager.remove_rule_action_func(action_name, rule_id)
                        if rule_engine:
                            rule_engine.unregister_custom_action(rule_id)
                        self._refresh_current_action()

        elif func_status == "预定义" and rule_engine:
            # 有预定义函数 - 只读查看模式
            action_key = rule_engine.get_action_key_for_rule(action_name, action_desc, rule_id)
            if action_key:
                source_code = rule_engine.get_predefined_action_source(action_key)
                if source_code:
                    dialog = CodeEditorDialog(
                        self,
                        title=f"查看预定义动作函数 - {action_key}",
                        code=source_code,
                        readonly=True
                    )
                    # 添加"复制为自定义函数"按钮
                    copy_btn = QtWidgets.QPushButton("复制为自定义函数")

                    def copy_as_custom():
                        dialog.reject()
                        self._create_custom_action_func_from_predefined(action_name, rule_id, source_code)

                    copy_btn.clicked.connect(copy_as_custom)
                    dialog.layout().itemAt(2).layout().insertWidget(0, copy_btn)
                    dialog.exec()
                else:
                    QtWidgets.QMessageBox.information(
                        self, "提示",
                        f"无法获取函数 '{action_key}' 的源代码。"
                    )
            else:
                QtWidgets.QMessageBox.information(
                    self, "提示",
                    "无法找到对应的预定义函数。"
                )
        else:
            # 无函数 - 询问是否创建自定义函数
            reply = QtWidgets.QMessageBox.question(
                self, "创建自定义函数",
                f"动作 '{action_desc}' 当前没有绑定的执行函数。\n\n是否为此动作创建自定义执行函数？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self._create_new_custom_action_func(action_name, rule_id)

    def _create_custom_action_func_from_predefined(self, action_name: str, rule_id: str, source_code: str):
        """从预定义动作函数复制创建自定义函数"""
        import re
        modified_code = re.sub(
            r'def\s+_execute_\w+\s*\(',
            'def execute_action(',
            source_code
        )

        dialog = CodeEditorDialog(
            self,
            title=f"基于预定义函数创建自定义动作函数 - {rule_id}",
            code=modified_code,
            readonly=False
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_code = dialog.get_code()
            if new_code.strip():
                # 验证并注册函数
                try:
                    from phone_agent.actions.rule_engine import get_rule_engine
                    rule_engine = get_rule_engine()
                    success, message = rule_engine.register_custom_action(rule_id, new_code)
                    if not success:
                        QtWidgets.QMessageBox.warning(self, "函数验证失败", message)
                        return
                except ImportError:
                    pass

                self._rules_manager.set_rule_action_func(action_name, rule_id, new_code)
                self._refresh_current_action()
                QtWidgets.QMessageBox.information(self, "成功", "自定义动作函数已创建。")

    def _create_new_custom_action_func(self, action_name: str, rule_id: str):
        """创建新的自定义动作执行函数"""
        # 获取模板代码
        try:
            from phone_agent.actions.rule_engine import get_rule_engine
            rule_engine = get_rule_engine()
            template_code = rule_engine.get_custom_action_template()
        except ImportError:
            template_code = '''def execute_action(params: dict, context: dict, rule: dict) -> RuleCheckResult:
    """
    自定义动作执行函数

    当规则的条件满足时，此函数将被调用来执行相应的动作。
    函数可以修改参数、跳过执行、或中止执行。

    Args:
        params: 动作参数字典（可修改）
        context: 执行上下文字典，包含 device_id, screen_width 等
        rule: 当前规则信息，包含 id, condition, action, priority, enabled

    Returns:
        RuleCheckResult 对象，可选类型:
        - RuleCheckResult(RuleResult.CONTINUE) - 继续执行原有逻辑
        - RuleCheckResult(RuleResult.SKIP, message="...") - 跳过执行，返回成功
        - RuleCheckResult(RuleResult.ABORT, message="...") - 中止执行，返回失败
        - RuleCheckResult(RuleResult.MODIFIED, modified_params={...}) - 使用修改后的参数
    """
    # 在这里编写您的动作执行逻辑
    # 示例：继续执行原有逻辑
    return RuleCheckResult(RuleResult.CONTINUE)
'''

        dialog = CodeEditorDialog(
            self,
            title=f"创建自定义动作函数 - {rule_id}",
            code=template_code,
            readonly=False
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_code = dialog.get_code()
            if new_code.strip():
                # 验证并注册函数
                try:
                    from phone_agent.actions.rule_engine import get_rule_engine
                    rule_engine = get_rule_engine()
                    success, message = rule_engine.register_custom_action(rule_id, new_code)
                    if not success:
                        QtWidgets.QMessageBox.warning(self, "函数验证失败", message)
                        return
                except ImportError:
                    pass

                self._rules_manager.set_rule_action_func(action_name, rule_id, new_code)
                self._refresh_current_action()
                QtWidgets.QMessageBox.information(self, "成功", "自定义动作函数已创建。")

    # ========== 参数管理 ==========

    def _add_parameter(self):
        """添加动作参数"""
        action_name = self._get_current_action_name()
        if not action_name:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择一个动作。")
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"添加参数 - {action_name}")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QFormLayout(dialog)

        name_input = QtWidgets.QLineEdit()
        name_input.setPlaceholderText("参数名称，如 text, element")
        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(["string", "int", "float", "bool", "list[int]", "list[str]", "dict"])
        type_combo.setEditable(True)
        required_check = QtWidgets.QCheckBox("必填参数")
        desc_input = QtWidgets.QLineEdit()
        desc_input.setPlaceholderText("参数说明")

        layout.addRow("参数名:", name_input)
        layout.addRow("类型:", type_combo)
        layout.addRow("", required_check)
        layout.addRow("说明:", desc_input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            param_name = name_input.text().strip()
            if not param_name:
                QtWidgets.QMessageBox.warning(self, "错误", "参数名不能为空。")
                return

            param = {
                "name": param_name,
                "type": type_combo.currentText(),
                "required": required_check.isChecked(),
                "description": desc_input.text().strip()
            }

            if self._rules_manager.add_parameter(action_name, param):
                self._load_rules_actions()
                self._select_action_by_name(action_name)
            else:
                QtWidgets.QMessageBox.warning(self, "错误", f"参数 '{param_name}' 已存在。")

    def _edit_parameter(self):
        """编辑动作参数"""
        action_name = self._get_current_action_name()
        if not action_name:
            return

        selected = self.action_detail_params.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要编辑的参数。")
            return

        row = selected[0].row()
        old_name = self.action_detail_params.item(row, 0).text()
        old_type = self.action_detail_params.item(row, 1).text()
        old_required = self.action_detail_params.item(row, 2).text() == "是"
        old_desc = self.action_detail_params.item(row, 3).text()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"编辑参数 - {old_name}")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QFormLayout(dialog)

        name_input = QtWidgets.QLineEdit(old_name)
        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(["string", "int", "float", "bool", "list[int]", "list[str]", "dict"])
        type_combo.setEditable(True)
        type_combo.setCurrentText(old_type)
        required_check = QtWidgets.QCheckBox("必填参数")
        required_check.setChecked(old_required)
        desc_input = QtWidgets.QLineEdit(old_desc)

        layout.addRow("参数名:", name_input)
        layout.addRow("类型:", type_combo)
        layout.addRow("", required_check)
        layout.addRow("说明:", desc_input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            updates = {
                "name": name_input.text().strip(),
                "type": type_combo.currentText(),
                "required": required_check.isChecked(),
                "description": desc_input.text().strip()
            }

            if self._rules_manager.update_parameter(action_name, old_name, updates):
                self._load_rules_actions()
                self._select_action_by_name(action_name)

    def _delete_parameter(self):
        """删除动作参数"""
        action_name = self._get_current_action_name()
        if not action_name:
            return

        selected = self.action_detail_params.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要删除的参数。")
            return

        row = selected[0].row()
        param_name = self.action_detail_params.item(row, 0).text()

        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除参数 '{param_name}' 吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self._rules_manager.delete_parameter(action_name, param_name):
                self._load_rules_actions()
                self._select_action_by_name(action_name)

    def _select_action_by_name(self, action_name: str):
        """根据名称选中动作"""
        for i in range(self.rules_actions_list.count()):
            item = self.rules_actions_list.item(i)
            if item.data(QtCore.Qt.UserRole)["name"] == action_name:
                self.rules_actions_list.setCurrentRow(i)
                break

    # ========== 导入导出 ==========

    def _export_rules(self):
        """导出动作规则"""
        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出动作规则",
            "action_rules.json",
            "JSON 文件 (*.json)"
        )
        if filepath:
            if self._rules_manager.export_action_rules(filepath):
                QtWidgets.QMessageBox.information(self, "成功", f"规则已导出到:\n{filepath}")
            else:
                QtWidgets.QMessageBox.warning(self, "错误", "导出失败。")

    def _import_rules(self):
        """导入动作规则"""
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "导入动作规则",
            "",
            "JSON 文件 (*.json)"
        )
        if not filepath:
            return

        # 询问导入模式
        reply = QtWidgets.QMessageBox.question(
            self, "导入模式",
            "选择导入模式:\n\n点击'是'：合并模式（保留现有规则，添加新规则）\n点击'否'：替换模式（替换所有规则）",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )

        if reply == QtWidgets.QMessageBox.Cancel:
            return

        merge = (reply == QtWidgets.QMessageBox.Yes)
        success, message = self._rules_manager.import_action_rules(filepath, merge)

        if success:
            self._load_rules_actions()
            QtWidgets.QMessageBox.information(self, "成功", message)
        else:
            QtWidgets.QMessageBox.warning(self, "错误", message)

    # ========== 搜索过滤 ==========

    def _filter_actions(self, text: str):
        """过滤动作列表"""
        search_text = text.lower().strip()
        for i in range(self.rules_actions_list.count()):
            item = self.rules_actions_list.item(i)
            rule = item.data(QtCore.Qt.UserRole)
            # 搜索动作名称、描述
            match = (
                search_text in rule["name"].lower() or
                search_text in rule.get("description", "").lower()
            )
            item.setHidden(not match)

    def _build_diagnostics_page(self):
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Create scroll area for the entire content
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(scroll_content)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("系统诊断")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("运行系统检查和故障排除")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Status Badge
        self.diagnostics_status = QtWidgets.QLabel("准备运行诊断")
        self.diagnostics_status.setStyleSheet(
            "font-size: 13px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 8px 16px; border-radius: 8px;"
        )

        # Action Buttons
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(10)

        self.diag_all_btn = QtWidgets.QPushButton("运行全部检查")
        self.diag_all_btn.setObjectName("success")
        self.diag_all_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.diag_all_btn.clicked.connect(lambda: self._run_diagnostics("all"))

        self.diag_system_btn = QtWidgets.QPushButton("系统检查")
        self.diag_system_btn.setObjectName("secondary")
        self.diag_system_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.diag_system_btn.clicked.connect(lambda: self._run_diagnostics("system"))

        self.diag_model_btn = QtWidgets.QPushButton("模型检查")
        self.diag_model_btn.setObjectName("secondary")
        self.diag_model_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.diag_model_btn.clicked.connect(lambda: self._run_diagnostics("model"))

        self.diag_clear_btn = QtWidgets.QPushButton("清空")
        self.diag_clear_btn.setObjectName("secondary")
        self.diag_clear_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.diag_clear_btn.clicked.connect(self._clear_diagnostics)

        actions.addWidget(self.diag_all_btn)
        actions.addWidget(self.diag_system_btn)
        actions.addWidget(self.diag_model_btn)
        actions.addWidget(self.diag_clear_btn)
        actions.addStretch()

        # Summary Card
        summary_card = QtWidgets.QFrame()
        summary_card.setObjectName("card")
        summary_layout = QtWidgets.QVBoxLayout(summary_card)

        summary_title = QtWidgets.QLabel("检查结果")
        summary_title.setObjectName("cardTitle")

        self.diagnostics_summary = QtWidgets.QListWidget()
        self.diagnostics_summary.setMaximumHeight(120)

        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.diagnostics_summary)

        # Log Card
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("card")
        log_layout = QtWidgets.QVBoxLayout(log_card)

        log_title = QtWidgets.QLabel("诊断日志")
        log_title.setObjectName("cardTitle")

        self.diagnostics_log = QtWidgets.QPlainTextEdit()
        self.diagnostics_log.setReadOnly(True)
        self.diagnostics_log.setPlaceholderText("诊断输出将显示在这里...")

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.diagnostics_log)

        layout.addWidget(header_widget)
        layout.addWidget(self.diagnostics_status)
        layout.addLayout(actions)
        layout.addWidget(summary_card)
        layout.addWidget(log_card, 1)

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)
        return page

    def _build_logs_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("运行日志")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("查看所有应用日志和活动历史")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Log Card
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("card")
        log_layout = QtWidgets.QVBoxLayout(log_card)

        log_title = QtWidgets.QLabel("应用日志")
        log_title.setObjectName("cardTitle")

        self.logs_view = QtWidgets.QPlainTextEdit()
        self.logs_view.setReadOnly(True)
        self.logs_view.setPlaceholderText("应用日志将随着您使用应用而显示在这里...")

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.logs_view)

        layout.addWidget(header_widget)
        layout.addWidget(log_card, 1)
        return page

    def _build_settings_page(self):
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Create scroll area for the entire content
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(scroll_content)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("系统设置")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("配置应用程序首选项和默认值")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Settings Card
        settings_card = QtWidgets.QFrame()
        settings_card.setObjectName("card")
        settings_layout = QtWidgets.QVBoxLayout(settings_card)
        settings_layout.setSpacing(16)

        settings_title = QtWidgets.QLabel("常规设置")
        settings_title.setObjectName("cardTitle")

        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        self.theme_combo = NoWheelComboBox()
        self.theme_combo.addItems(["暗色", "亮色"])
        self.theme_combo.currentTextChanged.connect(self._apply_theme)

        form.addRow("程序主题", self.theme_combo)

        settings_layout.addWidget(settings_title)
        settings_layout.addLayout(form)

        # Debian Virtualization Switch Card
        virt_card = QtWidgets.QFrame()
        virt_card.setObjectName("card")
        virt_layout = QtWidgets.QVBoxLayout(virt_card)
        virt_layout.setSpacing(12)

        virt_header_layout = QtWidgets.QHBoxLayout()

        virt_title = QtWidgets.QLabel("Debian 虚拟化切换")
        virt_title.setObjectName("cardTitle")

        virt_badge = QtWidgets.QLabel("仅限 Debian")
        virt_badge.setStyleSheet(
            "font-size: 10px; color: #f59e0b; background: rgba(245, 158, 11, 0.15); "
            "padding: 3px 8px; border-radius: 4px; font-weight: 600;"
        )

        virt_header_layout.addWidget(virt_title)
        virt_header_layout.addWidget(virt_badge)
        virt_header_layout.addStretch()

        virt_desc = QtWidgets.QLabel(
            "适用于 Debian 系统 + 虚拟机运行安卓的场景。\n"
            "一键切换 KVM 和 VirtualBox 虚拟化内核，无需手动执行脚本。\n"
            "注意：切换操作需要 sudo 权限。"
        )
        virt_desc.setStyleSheet("color: #71717a; font-size: 12px; line-height: 1.5;")
        virt_desc.setWordWrap(True)

        # Status display
        self.virt_status_label = QtWidgets.QLabel("点击「检测状态」查看当前虚拟化环境")
        self.virt_status_label.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 10px 14px; border-radius: 8px;"
        )

        # Buttons
        virt_btn_layout = QtWidgets.QHBoxLayout()
        virt_btn_layout.setSpacing(10)

        self.virt_detect_btn = QtWidgets.QPushButton("检测状态")
        self.virt_detect_btn.setObjectName("secondary")
        self.virt_detect_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.virt_detect_btn.clicked.connect(self._detect_virtualization)

        self.virt_kvm_btn = QtWidgets.QPushButton("切换到 KVM")
        self.virt_kvm_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.virt_kvm_btn.clicked.connect(lambda: self._switch_virtualization("kvm"))

        self.virt_vbox_btn = QtWidgets.QPushButton("切换到 VirtualBox")
        self.virt_vbox_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.virt_vbox_btn.clicked.connect(lambda: self._switch_virtualization("vbox"))

        virt_btn_layout.addWidget(self.virt_detect_btn)
        virt_btn_layout.addWidget(self.virt_kvm_btn)
        virt_btn_layout.addWidget(self.virt_vbox_btn)
        virt_btn_layout.addStretch()

        # Log display
        virt_log_label = QtWidgets.QLabel("切换日志")
        virt_log_label.setStyleSheet("color: #71717a; font-size: 11px; margin-top: 8px;")

        self.virt_log = QtWidgets.QPlainTextEdit()
        self.virt_log.setReadOnly(True)
        self.virt_log.setPlaceholderText("虚拟化切换操作日志将显示在这里...")
        self.virt_log.setMaximumHeight(120)

        virt_layout.addLayout(virt_header_layout)
        virt_layout.addWidget(virt_desc)
        virt_layout.addWidget(self.virt_status_label)
        virt_layout.addLayout(virt_btn_layout)
        virt_layout.addWidget(virt_log_label)
        virt_layout.addWidget(self.virt_log)

        # About Section
        about_card = QtWidgets.QFrame()
        about_card.setObjectName("card")
        about_layout = QtWidgets.QVBoxLayout(about_card)

        about_title = QtWidgets.QLabel("关于")
        about_title.setObjectName("cardTitle")

        about_text = QtWidgets.QLabel(
            "鱼塘管理器\n"
            "AI驱动的手机自动化工具\n\n"
            "仅支持安卓(ADB)"
        )
        about_text.setStyleSheet("color: #71717a; line-height: 1.6;")

        about_layout.addWidget(about_title)
        about_layout.addWidget(about_text)

        layout.addWidget(header_widget)
        layout.addWidget(settings_card)
        layout.addWidget(virt_card)
        layout.addWidget(about_card)
        layout.addStretch()

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)
        return page

    def _apply_theme(self, value):
        """应用主题设置"""
        self.current_theme = "light" if value == "亮色" else "dark"
        self.settings.setValue("theme", self.current_theme)
        self._apply_style()
        # 更新自定义标题栏样式
        if hasattr(self, 'title_bar'):
            self.title_bar.update_theme()
        # 更新硬编码样式的组件
        self._update_component_themes()

    def _update_component_themes(self):
        """根据当前主题更新所有硬编码样式的组件"""
        is_light = getattr(self, 'current_theme', 'dark') == 'light'

        # ===== 应用安装页面 =====
        # 设备列表样式
        if hasattr(self, 'apk_device_list') and self.apk_device_list:
            if is_light:
                self.apk_device_list.setStyleSheet("""
                    QListWidget {
                        background: rgba(255, 255, 255, 0.95);
                        border: 2px solid rgba(212, 212, 216, 0.8);
                        border-radius: 8px;
                        padding: 4px;
                        color: #18181b;
                        font-size: 13px;
                    }
                    QListWidget::item {
                        padding: 8px 12px;
                        border-radius: 4px;
                        margin: 2px;
                    }
                    QListWidget::item:selected {
                        background: rgba(99, 102, 241, 0.3);
                        color: #18181b;
                    }
                    QListWidget::item:hover {
                        background: rgba(228, 228, 231, 0.6);
                    }
                """)
            else:
                self.apk_device_list.setStyleSheet("""
                    QListWidget {
                        background: #18181b;
                        border: 2px solid #27272a;
                        border-radius: 8px;
                        padding: 4px;
                        color: #fafafa;
                        font-size: 13px;
                    }
                    QListWidget::item {
                        padding: 8px 12px;
                        border-radius: 4px;
                        margin: 2px;
                    }
                    QListWidget::item:selected {
                        background: #3f3f46;
                        color: #fafafa;
                    }
                    QListWidget::item:hover {
                        background: #27272a;
                    }
                """)

        # APK 拖动区域样式
        if hasattr(self, 'apk_drop_zone') and self.apk_drop_zone:
            self.apk_drop_zone._is_light_theme = is_light
            self.apk_drop_zone._update_style(False)

        # APK 安装状态样式
        if hasattr(self, 'apk_install_status') and self.apk_install_status:
            if is_light:
                self.apk_install_status.setStyleSheet(
                    "font-size: 13px; color: #52525b; background: rgba(228, 228, 231, 0.6); "
                    "padding: 8px 16px; border-radius: 8px;"
                )
            else:
                self.apk_install_status.setStyleSheet(
                    "font-size: 13px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
                    "padding: 8px 16px; border-radius: 8px;"
                )

        # APK 进度条样式
        if hasattr(self, 'apk_progress') and self.apk_progress:
            if is_light:
                self.apk_progress.setStyleSheet("""
                    QProgressBar {
                        background: rgba(228, 228, 231, 0.6);
                        border: 1px solid rgba(212, 212, 216, 0.5);
                        border-radius: 8px;
                        height: 20px;
                        text-align: center;
                        color: #18181b;
                    }
                    QProgressBar::chunk {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #6366f1, stop:1 #8b5cf6);
                        border-radius: 7px;
                    }
                """)
            else:
                self.apk_progress.setStyleSheet("""
                    QProgressBar {
                        background: rgba(39, 39, 42, 0.6);
                        border: 1px solid rgba(63, 63, 70, 0.5);
                        border-radius: 8px;
                        height: 20px;
                        text-align: center;
                        color: #fafafa;
                    }
                    QProgressBar::chunk {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #6366f1, stop:1 #8b5cf6);
                        border-radius: 7px;
                    }
                """)

        # ===== 定时任务页面 =====
        # 任务列表样式
        if hasattr(self, 'scheduled_task_list') and self.scheduled_task_list:
            if is_light:
                self.scheduled_task_list.setStyleSheet("""
                    QTableWidget {
                        gridline-color: rgba(212, 212, 216, 0.8);
                        border: 1px solid rgba(212, 212, 216, 0.5);
                        background: rgba(255, 255, 255, 0.95);
                        color: #18181b;
                    }
                    QTableWidget::item {
                        padding: 4px 8px;
                        border-bottom: 1px solid rgba(212, 212, 216, 0.5);
                    }
                    QHeaderView::section {
                        background: rgba(244, 244, 245, 0.95);
                        border: 1px solid rgba(212, 212, 216, 0.5);
                        padding: 6px;
                        color: #52525b;
                    }
                """)
            else:
                self.scheduled_task_list.setStyleSheet("""
                    QTableWidget {
                        gridline-color: rgba(63, 63, 70, 0.8);
                        border: 1px solid rgba(63, 63, 70, 0.5);
                    }
                    QTableWidget::item {
                        padding: 4px 8px;
                        border-bottom: 1px solid rgba(63, 63, 70, 0.5);
                    }
                    QHeaderView::section {
                        background: rgba(39, 39, 42, 0.8);
                        border: 1px solid rgba(63, 63, 70, 0.5);
                        padding: 6px;
                    }
                """)

        # 日期时间选择器样式
        datetime_style_light = """
            QDateTimeEdit {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid rgba(212, 212, 216, 0.8);
                border-radius: 6px;
                padding: 4px 8px;
                color: #18181b;
            }
            QDateTimeEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border-left: 1px solid rgba(212, 212, 216, 0.8);
                background: rgba(244, 244, 245, 0.5);
            }
            QDateTimeEdit::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #71717a;
            }
        """
        datetime_style_dark = """
            QDateTimeEdit {
                background: rgba(39, 39, 42, 0.8);
                border: 1px solid rgba(63, 63, 70, 0.8);
                border-radius: 6px;
                padding: 4px 8px;
                color: #fafafa;
            }
            QDateTimeEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border-left: 1px solid rgba(63, 63, 70, 0.8);
                background: rgba(63, 63, 70, 0.5);
            }
            QDateTimeEdit::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #a1a1aa;
            }
        """
        if hasattr(self, 'sched_once_datetime') and self.sched_once_datetime:
            self.sched_once_datetime.setStyleSheet(datetime_style_light if is_light else datetime_style_dark)

        # ===== 任务执行页面 =====
        # 设备执行状态提示框
        if hasattr(self, 'multi_status_label') and self.multi_status_label:
            if is_light:
                self.multi_status_label.setStyleSheet(
                    "font-size: 12px; color: #52525b; background: rgba(228, 228, 231, 0.6); "
                    "padding: 8px 12px; border-radius: 8px;"
                )
            else:
                self.multi_status_label.setStyleSheet(
                    "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
                    "padding: 8px 12px; border-radius: 8px;"
                )

        # 实时预览状态
        if hasattr(self, 'preview_status') and self.preview_status:
            if is_light:
                self.preview_status.setStyleSheet(
                    "font-size: 10px; color: #52525b; background: rgba(228, 228, 231, 0.6); "
                    "padding: 3px 8px; border-radius: 4px;"
                )
            else:
                self.preview_status.setStyleSheet(
                    "font-size: 10px; color: #71717a; background: rgba(39, 39, 42, 0.6); "
                    "padding: 3px 8px; border-radius: 4px;"
                )

        # 预览设备选择框
        if hasattr(self, 'preview_device_combo') and self.preview_device_combo:
            if is_light:
                self.preview_device_combo.setStyleSheet("""
                    QComboBox {
                        padding: 4px 8px;
                        border: 1px solid rgba(212, 212, 216, 0.8);
                        border-radius: 6px;
                        background: rgba(255, 255, 255, 0.95);
                        color: #18181b;
                        font-size: 12px;
                        min-width: 100px;
                    }
                    QComboBox::drop-down {
                        border: none;
                        width: 20px;
                    }
                    QComboBox QAbstractItemView {
                        background: rgba(255, 255, 255, 0.98);
                        border: 1px solid rgba(212, 212, 216, 0.8);
                        border-radius: 6px;
                        selection-background-color: rgba(99, 102, 241, 0.3);
                        selection-color: #18181b;
                        padding: 2px;
                    }
                """)
            else:
                self.preview_device_combo.setStyleSheet("""
                    QComboBox {
                        padding: 4px 8px;
                        border: 1px solid #27272a;
                        border-radius: 6px;
                        background: #18181b;
                        color: #fafafa;
                        font-size: 12px;
                        min-width: 100px;
                    }
                    QComboBox::drop-down {
                        border: none;
                        width: 20px;
                    }
                    QComboBox QAbstractItemView {
                        background: #18181b;
                        border: 1px solid #27272a;
                        border-radius: 6px;
                        selection-background-color: #3f3f46;
                        selection-color: #fafafa;
                        padding: 2px;
                    }
                """)

        # 预览区域样式
        if hasattr(self, 'preview_label') and self.preview_label:
            if is_light:
                self.preview_label.setStyleSheet("""
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #e4e4e7, stop:1 #d4d4d8);
                    border: 2px solid rgba(161, 161, 170, 0.5);
                    border-radius: 12px;
                    color: #52525b;
                    font-size: 12px;
                """)
            else:
                self.preview_label.setStyleSheet("""
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #18181b, stop:1 #09090b);
                    border: 2px solid #27272a;
                    border-radius: 12px;
                    color: #71717a;
                    font-size: 12px;
                """)

        # ===== 控制台/仪表盘页面 =====
        # 更新 metric cards 需要重新构建，这里更新快捷操作标题和按钮
        self._update_dashboard_theme(is_light)

    def _update_dashboard_theme(self, is_light):
        """更新控制台/仪表盘页面的主题"""
        # 更新欢迎标题
        dashboard_page = self.stack.widget(0)
        if dashboard_page:
            title_label = dashboard_page.findChild(QtWidgets.QLabel, "title")
            if title_label:
                if is_light:
                    title_label.setStyleSheet("""
                        font-size: 28px;
                        font-weight: 700;
                        color: #18181b;
                        letter-spacing: -0.5px;
                        margin-bottom: 4px;
                    """)
                else:
                    title_label.setStyleSheet("""
                        font-size: 28px;
                        font-weight: 700;
                        color: #fafafa;
                        letter-spacing: -0.5px;
                        margin-bottom: 4px;
                    """)

        # 更新快捷操作卡片
        actions_card = dashboard_page.findChild(QtWidgets.QFrame, "card") if dashboard_page else None
        if actions_card:
            card_title = actions_card.findChild(QtWidgets.QLabel, "cardTitle")
            if card_title:
                if is_light:
                    card_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #18181b; margin-bottom: 12px;")
                else:
                    card_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #fafafa; margin-bottom: 12px;")

        # 更新 metric cards
        metric_cards = [
            (self.metric_device, "device"),
            (self.metric_model, "model"),
            (self.metric_tasks, "tasks"),
            (self.metric_status, "status"),
        ]

        icon_colors = {
            "device": ("#10b981", "rgba(16, 185, 129, 0.1)"),
            "model": ("#6366f1", "rgba(99, 102, 241, 0.1)"),
            "tasks": ("#f59e0b", "rgba(245, 158, 11, 0.1)"),
            "status": ("#22c55e", "rgba(34, 197, 94, 0.1)"),
        }

        for card, card_type in metric_cards:
            if not card:
                continue
            accent_color, bg_tint = icon_colors.get(card_type, ("#6366f1", "rgba(99, 102, 241, 0.1)"))

            if is_light:
                card.setStyleSheet(
                    f"""
                    QFrame {{
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.98), stop:1 rgba(250, 250, 250, 0.95));
                        border: 1px solid rgba(212, 212, 216, 0.6);
                        border-radius: 16px;
                    }}
                    QFrame:hover {{
                        border: 1px solid {accent_color};
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 1), stop:1 rgba(252, 252, 253, 0.98));
                    }}
                    """
                )
            else:
                card.setStyleSheet(
                    f"""
                    QFrame {{
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(24, 24, 27, 0.95), stop:1 rgba(17, 17, 19, 0.95));
                        border: 1px solid rgba(63, 63, 70, 0.4);
                        border-radius: 16px;
                    }}
                    QFrame:hover {{
                        border: 1px solid {accent_color};
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(30, 30, 34, 0.98), stop:1 rgba(20, 20, 23, 0.98));
                    }}
                    """
                )

            # 更新卡片内的标签颜色
            for child in card.findChildren(QtWidgets.QLabel):
                obj_name = child.objectName()
                current_style = child.styleSheet()

                if obj_name == "metricValue":
                    if is_light:
                        child.setStyleSheet(
                            f"""
                            font-size: 28px;
                            font-weight: 700;
                            color: #18181b;
                            letter-spacing: -0.5px;
                            background: transparent;
                            border: none;
                            padding-left: 2px;
                            """
                        )
                    else:
                        child.setStyleSheet(
                            f"""
                            font-size: 28px;
                            font-weight: 700;
                            color: #fafafa;
                            letter-spacing: -0.5px;
                            background: transparent;
                            border: none;
                            padding-left: 2px;
                            """
                        )
                elif obj_name == "metricLabel":
                    if is_light:
                        child.setStyleSheet("font-size: 12px; color: #52525b; background: transparent; border: none;")
                    else:
                        child.setStyleSheet("font-size: 12px; color: #71717a; background: transparent; border: none;")
                elif "font-size: 14px" in current_style and "font-weight: 600" in current_style:
                    # 这是标题标签
                    if is_light:
                        child.setStyleSheet(
                            "font-size: 14px; font-weight: 600; color: #52525b; "
                            "letter-spacing: 0.3px; background: transparent; border: none;"
                        )
                    else:
                        child.setStyleSheet(
                            "font-size: 14px; font-weight: 600; color: #d4d4d8; "
                            "letter-spacing: 0.3px; background: transparent; border: none;"
                        )

    def _detect_virtualization(self):
        """检测当前虚拟化环境状态"""
        kvm_active, vbox_active, message = detect_virtualization_status()

        # 更新状态显示
        if kvm_active and vbox_active:
            status_text = "⚠️ KVM 和 VirtualBox 同时活动（可能存在冲突）"
            style = "font-size: 12px; color: #f59e0b; background: rgba(245, 158, 11, 0.15); padding: 10px 14px; border-radius: 8px;"
        elif kvm_active:
            status_text = "✅ 当前环境: KVM 已激活"
            style = "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); padding: 10px 14px; border-radius: 8px;"
        elif vbox_active:
            status_text = "✅ 当前环境: VirtualBox 已激活"
            style = "font-size: 12px; color: #6366f1; background: rgba(99, 102, 241, 0.15); padding: 10px 14px; border-radius: 8px;"
        else:
            status_text = "⚪ 未检测到活动的虚拟化环境"
            style = "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); padding: 10px 14px; border-radius: 8px;"

        self.virt_status_label.setText(status_text)
        self.virt_status_label.setStyleSheet(style)

        # 添加详细信息到日志
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.virt_log.appendPlainText(f"[{timestamp}] 检测结果: {message}")

    def _switch_virtualization(self, target):
        """切换虚拟化环境"""
        if hasattr(self, 'virt_switch_worker') and self.virt_switch_worker and self.virt_switch_worker.isRunning():
            QtWidgets.QMessageBox.warning(self, "切换中", "虚拟化切换正在进行中，请稍候...")
            return

        # 确认对话框
        target_name = "KVM" if target == "kvm" else "VirtualBox"
        reply = QtWidgets.QMessageBox.question(
            self,
            "确认切换",
            f"确定要切换到 {target_name} 吗？\n\n"
            f"此操作需要 sudo 权限，可能会要求输入密码。\n"
            f"切换过程中请勿关闭应用程序。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        # 禁用按钮
        self.virt_kvm_btn.setEnabled(False)
        self.virt_vbox_btn.setEnabled(False)
        self.virt_detect_btn.setEnabled(False)

        # 更新状态
        self.virt_status_label.setText(f"⏳ 正在切换到 {target_name}...")
        self.virt_status_label.setStyleSheet(
            "font-size: 12px; color: #6366f1; background: rgba(99, 102, 241, 0.15); "
            "padding: 10px 14px; border-radius: 8px;"
        )

        # 启动Worker
        self.virt_switch_worker = VirtualizationSwitchWorker(target)
        self.virt_switch_worker.log.connect(self._append_virt_log)
        self.virt_switch_worker.finished.connect(self._virtualization_switch_finished)
        self.virt_switch_worker.start()

    def _append_virt_log(self, text):
        """添加虚拟化切换日志"""
        self.virt_log.moveCursor(QtGui.QTextCursor.End)
        self.virt_log.insertPlainText(text)
        self.virt_log.moveCursor(QtGui.QTextCursor.End)

        # 同时添加到主日志
        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(f"[虚拟化] {text}")
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _virtualization_switch_finished(self, success, message):
        """虚拟化切换完成回调"""
        # 重新启用按钮
        self.virt_kvm_btn.setEnabled(True)
        self.virt_vbox_btn.setEnabled(True)
        self.virt_detect_btn.setEnabled(True)

        if success:
            self.virt_status_label.setText(f"✅ {message}")
            self.virt_status_label.setStyleSheet(
                "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 10px 14px; border-radius: 8px;"
            )
            # 自动刷新检测状态
            QtCore.QTimer.singleShot(500, self._detect_virtualization)
        else:
            self.virt_status_label.setText(f"❌ 切换失败: {message}")
            self.virt_status_label.setStyleSheet(
                "font-size: 12px; color: #ef4444; background: rgba(239, 68, 68, 0.15); "
                "padding: 10px 14px; border-radius: 8px;"
            )

    def _append_log(self, text):
        self.task_log.moveCursor(QtGui.QTextCursor.End)
        self.task_log.insertPlainText(text)
        self.task_log.moveCursor(QtGui.QTextCursor.End)

        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(text)
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _timestamp(self):
        """Return current timestamp string."""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def _append_device_log(self, text):
        """Append text to device connection log."""
        self.device_log.moveCursor(QtGui.QTextCursor.End)
        self.device_log.insertPlainText(text)
        self.device_log.moveCursor(QtGui.QTextCursor.End)

        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(text)
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _update_device_status(self, message, status_type="info"):
        """Update device connection status label."""
        status_styles = {
            "info": "color: #60a5fa; background: rgba(96, 165, 250, 0.15);",
            "success": "color: #34d399; background: rgba(52, 211, 153, 0.15);",
            "warning": "color: #fbbf24; background: rgba(251, 191, 36, 0.15);",
            "error": "color: #f87171; background: rgba(248, 113, 113, 0.15);",
        }
        style = status_styles.get(status_type, status_styles["info"])
        self.device_connection_status.setText(message)
        self.device_connection_status.setStyleSheet(
            f"font-size: 12px; {style} padding: 8px 12px; border-radius: 8px;"
        )

    def _load_connection_history(self):
        """Load connection history from settings."""
        import json
        history_json = self.settings.value("connection_history", "[]")
        try:
            history = json.loads(history_json)
        except:
            history = []

        self.connection_history_list.clear()
        for item in history[-20:]:  # Keep last 20 items
            display_text = f"[{item.get('type', 'connect')}] {item.get('address', '')} - {item.get('time', '')}"
            list_item = QtWidgets.QListWidgetItem(display_text)
            list_item.setData(QtCore.Qt.UserRole, item)
            self.connection_history_list.addItem(list_item)

    def _add_connection_history(self, conn_type, address):
        """Add a connection to history."""
        import json
        from datetime import datetime

        history_json = self.settings.value("connection_history", "[]")
        try:
            history = json.loads(history_json)
        except:
            history = []

        # Add new entry
        new_entry = {
            "type": conn_type,
            "address": address,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "device_type": self.device_type_combo.currentText()
        }

        # Remove duplicate addresses
        history = [h for h in history if h.get("address") != address]
        history.append(new_entry)

        # Keep only last 20
        history = history[-20:]

        self.settings.setValue("connection_history", json.dumps(history))
        self._load_connection_history()

    def _clear_connection_history(self):
        """Clear all connection history."""
        self.settings.setValue("connection_history", "[]")
        self.connection_history_list.clear()
        self._append_device_log(f"[{self._timestamp()}] 连接历史已清空\n")

    def _use_history_connection(self, item):
        """Use a connection from history."""
        data = item.data(QtCore.Qt.UserRole)
        if data:
            address = data.get("address", "")
            conn_type = data.get("type", "connect")
            device_type = data.get("device_type", "adb")

            self.device_type_combo.setCurrentText(device_type)

            if conn_type == "pair":
                self.pair_address_input.setText(address)
                self._append_device_log(f"[{self._timestamp()}] 已填入配对地址: {address}\n")
            else:
                self.connect_input.setText(address)
                self._append_device_log(f"[{self._timestamp()}] 已填入连接地址: {address}\n")

    def _append_diag_log(self, text):
        self.diagnostics_log.moveCursor(QtGui.QTextCursor.End)
        self.diagnostics_log.insertPlainText(text)
        self.diagnostics_log.moveCursor(QtGui.QTextCursor.End)

        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(text)
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _load_settings(self):
        # Load global settings (device, max_steps, lang)
        self.max_steps_input.setValue(int(self.settings.value("max_steps", 100)))
        self.lang_combo.setCurrentText(self.settings.value("lang", "cn"))
        self.device_type_combo.setCurrentText(
            self.settings.value("device_type", "adb")
        )
        # Load theme setting
        self.current_theme = self.settings.value("theme", "dark")
        self.theme_combo.setCurrentText("亮色" if self.current_theme == "light" else "暗色")
        self.device_id_input.setText(self.settings.value("device_id", ""))

        # Load active service config to legacy inputs for compatibility
        active_service = self.model_services_manager.get_active_service()
        if active_service:
            self.base_url_input.setText(active_service.base_url)
            self.model_input.setText(active_service.model_name)
            self.api_key_input.setText(active_service.api_key)

        # Load connection history
        self._load_connection_history()

    def _save_settings(self):
        # Save global settings only
        self.settings.setValue("max_steps", self.max_steps_input.value())
        self.settings.setValue("lang", self.lang_combo.currentText())
        self.settings.setValue("device_type", self.device_type_combo.currentText())
        self.settings.setValue("device_id", self.device_id_input.text().strip())
        self._append_log("全局设置已保存。\n")
        self._refresh_dashboard()

    def _test_model(self):
        # Use active service for testing
        active_service = self.model_services_manager.get_active_service()
        if active_service:
            success, message = self.model_services_manager.test_service(active_service)
            self._append_log(f"测试模型连接: {message}\n")
        else:
            self._append_log("没有激活的模型服务。\n")

    def _current_device_type(self):
        return DeviceType(self.device_type_combo.currentText())

    def _toggle_advanced(self, checked):
        """Toggle advanced configuration visibility."""
        self.advanced_widget.setVisible(checked)
        if checked:
            self.advanced_btn.setText("⚙️ 隐藏高级配置")
        else:
            self.advanced_btn.setText("⚙️ 高级配置")

    def _auto_detect_and_clean(self):
        """Auto detect devices and clean existing connections if needed."""
        device_type = self._current_device_type()
        
        try:
            self._append_device_log(f"[{self._timestamp()}] 开始自动检测设备...\n")
            self._update_device_status("正在检测设备", "info")
            
            # First, check if there are already connected devices
            has_connected_devices = self._check_connected_devices(device_type)
            
            if has_connected_devices:
                self._append_device_log(f"[{self._timestamp()}] 发现已有连接设备，跳过清理步骤\n")
                self._update_device_status("检测完成", "success")
            else:
                self._append_device_log(f"[{self._timestamp()}] 未发现连接设备，开始清理现有连接...\n")
                # Clean existing connections only if no devices are connected
                self._clean_existing_connections(device_type)
            
            # Then refresh devices
            self._refresh_devices()
            
            # Check if any devices found
            if self.device_list.count() > 0:
                self._append_device_log(f"[{self._timestamp()}] ✅ 检测到 {self.device_list.count()} 个设备\n")
                self._update_device_status("检测完成", "success")
            else:
                self._append_device_log(f"[{self._timestamp()}] ⚠️ 未检测到设备\n")
                self._update_device_status("未检测到设备", "warning")
                
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ❌ 自动检测失败: {str(e)}\n")
            self._update_device_status("检测失败", "error")

    def _check_connected_devices(self, device_type) -> bool:
        """Check if there are already connected devices (ADB only)."""
        try:
            # Only check ADB devices since interface is ADB-only
            result = subprocess.run(
                ['adb', 'devices'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                for line in lines:
                    if '\t' in line:
                        device_id, status = line.split('\t')
                        if status == 'device':
                            self._append_device_log(f"[{self._timestamp()}] 发现已连接的ADB设备: {device_id}\n")
                            return True
            
            return False
            
        except subprocess.TimeoutExpired:
            self._append_device_log(f"[{self._timestamp()}] ⚠️ 设备检查超时\n")
            return False
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ⚠️ 检查连接设备时出错: {str(e)}\n")
            return False

    def _clean_existing_connections(self, device_type):
        """Clean existing pairings and connections (ADB only)."""
        try:
            self._append_device_log(f"[{self._timestamp()}] 清理现有连接...\n")
            
            # Only handle ADB since interface is ADB-only
            # Kill existing ADB server
            subprocess.run(['adb', 'kill-server'], capture_output=True, check=False)
            subprocess.run(['adb', 'start-server'], capture_output=True, check=False)
            self._append_device_log(f"[{self._timestamp()}] ADB服务已重启\n")
                
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ⚠️ 清理连接时出错: {str(e)}\n")

    def _refresh_devices(self):
        device_type = self._current_device_type()
        self.device_list.clear()

        # Show refresh status
        self.refresh_devices_btn.setEnabled(False)
        self.refresh_devices_btn.setText("刷新中...")
        self._update_device_status("正在刷新设备列表...", "info")
        QtWidgets.QApplication.processEvents()

        try:
            if device_type == DeviceType.IOS:
                devices = list_ios_devices()
                if not devices:
                    self.device_list.addItem("没有iOS设备连接。")
                    self._update_device_status("未发现iOS设备", "warning")
                else:
                    for device in devices:
                        name = device.device_name or device.device_id
                        line = f"{name} | {device.device_id} | {device.connection_type.value}"
                        self.device_list.addItem(line)
                    self._update_device_status(f"发现 {len(devices)} 个iOS设备", "success")
            else:
                set_device_type(device_type)
                factory = get_device_factory()
                
                # 检查工具是否已安装
                tool_name = "adb" if device_type == DeviceType.ADB else "hdc"
                if not self._is_tool_installed(tool_name):
                    install_hint = self._get_tool_install_hint(tool_name)
                    self.device_list.addItem(f"⚠️ {tool_name} 未安装")
                    self.device_list.addItem(install_hint)
                    self._update_device_status(f"{tool_name} 未安装，请先安装", "warning")
                    self._refresh_dashboard()
                    self.refresh_devices_btn.setEnabled(True)
                    self.refresh_devices_btn.setText("🔍 自动检测")
                    return
                
                devices = factory.list_devices()
                if not devices:
                    self.device_list.addItem("没有设备连接。")
                    self._update_device_status("未发现设备", "warning")
                else:
                    for device in devices:
                        status = "OK" if device.status == "device" else device.status
                        line = f"{device.device_id} | {status} | {device.connection_type.value}"
                        if device.model:
                            line += f" | {device.model}"
                        item = QtWidgets.QListWidgetItem(line)
                        item.setData(QtCore.Qt.UserRole, device.device_id)  # Store device ID
                        self.device_list.addItem(item)
                    self._update_device_status(f"发现 {len(devices)} 个设备", "success")

            self._refresh_dashboard()
            # 同步更新 PIN 配置的设备下拉框
            self._refresh_pin_device_combo()
        except Exception as e:
            self._update_device_status(f"刷新失败: {str(e)}", "error")
        finally:
            self.refresh_devices_btn.setEnabled(True)
            self.refresh_devices_btn.setText("🔍 自动检测")

    def _is_tool_installed(self, tool_name: str) -> bool:
        """检查工具是否已安装"""
        import shutil
        return shutil.which(tool_name) is not None
    
    def _get_tool_install_hint(self, tool_name: str) -> str:
        """获取工具安装提示"""
        import platform
        system = platform.system()
        
        if tool_name == "adb":
            if system == "Darwin":  # macOS
                return "💡 安装方法: brew install android-platform-tools"
            elif system == "Windows":
                return "💡 安装方法: 下载 Android SDK Platform Tools"
            else:  # Linux
                return "💡 安装方法: sudo apt install adb 或 sudo pacman -S android-tools"
        elif tool_name == "hdc":
            return "💡 安装方法: 请安装 HarmonyOS DevEco Studio"
        else:
            return f"💡 请安装 {tool_name}"

    def _on_device_selected(self, item):
        """Handle device selection in device list."""
        # Get device ID from user data
        device_id = item.data(QtCore.Qt.UserRole)
        if not device_id:
            # Fallback to parsing text
            text = item.text()
            if "|" in text:
                device_id = text.split("|")[0].strip()
        
        if device_id:
            # Update device_id_input to reflect selection
            self.device_id_input.setText(device_id)
            # Update preview status
            self.preview_status.setText(f"已选择设备: {device_id}")
            # If preview is running, restart it with new device
            if self.preview_timer.isActive():
                self._stop_preview()
                self._start_preview()

    def _on_device_double_clicked(self, item):
        """Handle device double click - start preview for this device."""
        # Get device ID from user data
        device_id = item.data(QtCore.Qt.UserRole)
        if not device_id:
            # Fallback to parsing text
            text = item.text()
            if "|" in text:
                device_id = text.split("|")[0].strip()
        
        if device_id:
            # Update device_id_input
            self.device_id_input.setText(device_id)
            # Start preview immediately
            self._start_preview()
            # Switch to task runner page to see preview
            self.stack.setCurrentIndex(self.task_runner_index)

    def _get_selected_device_id(self):
        """Get the currently selected device ID from device list."""
        selected_items = self.device_list.selectedItems()
        if selected_items:
            # Use the first selected device
            item = selected_items[0]
            device_id = item.data(QtCore.Qt.UserRole)
            if device_id:
                return device_id
            # Fallback to parsing text if user data not available
            text = item.text()
            if "|" in text:
                return text.split("|")[0].strip()
        
        # Fallback to device_id_input
        return self.device_id_input.text().strip() or None

    def _connect_device(self):
        device_type = self._current_device_type()
        address = self.connect_input.text().strip()
        if not address:
            self._append_device_log(f"[{self._timestamp()}] 需要填写连接地址\n")
            self._update_device_status("请输入连接地址", "warning")
            return
        if device_type == DeviceType.IOS:
            self._append_device_log(f"[{self._timestamp()}] iOS配对请使用配对按钮\n")
            self._update_device_status("iOS请使用配对按钮", "warning")
            return

        # Disable button and show progress
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("连接中...")
        self._update_device_status("正在连接...", "info")
        self._append_device_log(f"[{self._timestamp()}] 开始连接设备\n")
        self._append_device_log(f"  设备类型: {device_type.value}\n")
        self._append_device_log(f"  连接地址: {address}\n")
        QtWidgets.QApplication.processEvents()

        try:
            set_device_type(device_type)
            factory = get_device_factory()
            conn = factory.get_connection_class()()
            success, message = conn.connect(address)

            self._append_device_log(f"[{self._timestamp()}] 连接结果: {message}\n")

            if success:
                self._append_device_log(f"[{self._timestamp()}] ✅ 连接成功\n")
                self._update_device_status("连接成功", "success")
                self._add_connection_history("connect", address)
            else:
                self._append_device_log(f"[{self._timestamp()}] ❌ 连接失败\n")
                self._update_device_status("连接失败", "error")

            self._refresh_devices()
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ❌ 错误: {str(e)}\n")
            self._update_device_status(f"错误: {str(e)}", "error")
        finally:
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("连接")

    def _disconnect_device(self):
        device_type = self._current_device_type()
        target = self.connect_input.text().strip()
        if device_type == DeviceType.IOS:
            self._append_device_log(f"[{self._timestamp()}] iOS断开连接由系统工具处理\n")
            return

        # Disable button and show progress
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setText("断开中...")
        self._update_device_status("正在断开...", "info")
        self._append_device_log(f"[{self._timestamp()}] 开始断开设备\n")
        QtWidgets.QApplication.processEvents()

        try:
            set_device_type(device_type)
            factory = get_device_factory()
            conn = factory.get_connection_class()()
            if target:
                success, message = conn.disconnect(target)
            else:
                success, message = conn.disconnect()

            self._append_device_log(f"[{self._timestamp()}] 断开结果: {message}\n")

            if success:
                self._update_device_status("已断开", "success")
            else:
                self._update_device_status("断开失败", "error")

            self._refresh_devices()
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ❌ 错误: {str(e)}\n")
            self._update_device_status(f"错误: {str(e)}", "error")
        finally:
            self.disconnect_btn.setEnabled(True)
            self.disconnect_btn.setText("断开")

    def _enable_tcpip(self):
        device_type = self._current_device_type()
        if device_type == DeviceType.IOS:
            self._append_device_log(f"[{self._timestamp()}] TCP/IP不适用于iOS\n")
            self._update_device_status("TCP/IP不适用于iOS", "warning")
            return

        # Disable button and show progress
        self.tcpip_btn.setEnabled(False)
        self.tcpip_btn.setText("启用中...")
        self._update_device_status("正在启用TCP/IP...", "info")
        QtWidgets.QApplication.processEvents()

        try:
            set_device_type(device_type)
            factory = get_device_factory()
            conn = factory.get_connection_class()()
            port = self.tcpip_port_input.value()
            device_id = self.device_id_input.text().strip() or None

            self._append_device_log(f"[{self._timestamp()}] 启用TCP/IP模式\n")
            self._append_device_log(f"  端口: {port}\n")
            if device_id:
                self._append_device_log(f"  设备ID: {device_id}\n")

            success, message = conn.enable_tcpip(port, device_id)
            self._append_device_log(f"[{self._timestamp()}] 结果: {message}\n")

            if success:
                self._update_device_status("TCP/IP已启用", "success")
            else:
                self._update_device_status("启用失败", "error")
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ❌ 错误: {str(e)}\n")
            self._update_device_status(f"错误: {str(e)}", "error")
        finally:
            self.tcpip_btn.setEnabled(True)
            self.tcpip_btn.setText("启用TCP/IP")

    def _pair_ios(self):
        device_id = self.device_id_input.text().strip() or None
        wda_url = None  # ADB-only interface doesn't use WDA
        conn = XCTestConnection(wda_url=wda_url)
        success, message = conn.pair_device(device_id=device_id)
        self._append_log(f"{'成功' if success else '失败'}: {message}\n")

    def _wireless_pair_device(self):
        """Perform ADB wireless pairing and connect."""
        device_type = self._current_device_type()
        if device_type != DeviceType.ADB:
            self._append_device_log("无线配对仅适用于Android设备(ADB)。\n")
            self._update_device_status("无线配对仅适用于ADB", "warning")
            return

        pair_address = self.pair_address_input.text().strip()
        pair_code = self.pair_code_input.text().strip()

        if not pair_address:
            self._append_device_log("请输入配对地址（在手机的开发者选项 > 无线调试中查看）。\n")
            self._update_device_status("请输入配对地址", "warning")
            return

        if not pair_code:
            self._append_device_log("请输入6位配对码。\n")
            self._update_device_status("请输入配对码", "warning")
            return

        if len(pair_code) != 6 or not pair_code.isdigit():
            self._append_device_log("配对码必须是6位数字。\n")
            self._update_device_status("配对码格式错误", "error")
            return

        # Disable button and show progress
        self.wireless_pair_btn.setEnabled(False)
        self.wireless_pair_btn.setText("配对中...")
        self._update_device_status("正在配对...", "info")
        self._append_device_log(f"[{self._timestamp()}] 开始无线配对\n")
        self._append_device_log(f"  配对地址: {pair_address}\n")
        self._append_device_log(f"  配对码: {'*' * 6}\n")
        QtWidgets.QApplication.processEvents()

        # Run adb pair command
        try:
            import subprocess
            self._append_device_log(f"[{self._timestamp()}] 执行 adb pair {pair_address}\n")
            QtWidgets.QApplication.processEvents()

            # adb pair requires the pairing code to be passed via stdin or as part of the command
            pair_result = subprocess.run(
                ["adb", "pair", pair_address],
                input=pair_code + "\n",
                capture_output=True,
                text=True,
                timeout=30
            )

            pair_output = (pair_result.stdout + pair_result.stderr).strip()
            self._append_device_log(f"[{self._timestamp()}] 配对输出:\n  {pair_output}\n")

            if "Successfully paired" in pair_output or "成功" in pair_output:
                self._append_device_log(f"[{self._timestamp()}] ✅ 配对成功！\n")
                self._update_device_status("配对成功", "success")

                # Save to connection history
                self._add_connection_history("pair", pair_address)

                # Extract the connect address (usually same IP but different port)
                # The pairing port is different from the connection port
                connect_address = self.connect_input.text().strip()

                if connect_address:
                    self._append_device_log(f"[{self._timestamp()}] 正在连接设备 {connect_address}...\n")
                    self._update_device_status("正在连接...", "info")
                    QtWidgets.QApplication.processEvents()

                    connect_result = subprocess.run(
                        ["adb", "connect", connect_address],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    connect_output = (connect_result.stdout + connect_result.stderr).strip()
                    self._append_device_log(f"[{self._timestamp()}] 连接输出:\n  {connect_output}\n")

                    if "connected" in connect_output.lower():
                        self._append_device_log(f"[{self._timestamp()}] ✅ 连接成功！\n")
                        self._update_device_status("连接成功", "success")
                        self._add_connection_history("connect", connect_address)
                        self._refresh_devices()
                    else:
                        self._append_device_log(f"[{self._timestamp()}] ⚠️ 连接失败\n")
                        self._update_device_status("连接失败", "error")
                else:
                    self._append_device_log(
                        f"[{self._timestamp()}] 提示：配对成功后，请在「连接地址」中输入设备的无线调试地址，然后点击「连接」。\n"
                    )
                    self._update_device_status("配对成功，请输入连接地址", "success")
                    self._refresh_devices()
            else:
                self._append_device_log(f"[{self._timestamp()}] ❌ 配对失败\n")
                self._update_device_status("配对失败", "error")

        except subprocess.TimeoutExpired:
            self._append_device_log(f"[{self._timestamp()}] ❌ 配对超时\n")
            self._update_device_status("配对超时", "error")
        except FileNotFoundError:
            self._append_device_log(f"[{self._timestamp()}] ❌ 未找到adb命令\n")
            self._update_device_status("未找到adb", "error")
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ❌ 错误: {str(e)}\n")
            self._update_device_status(f"错误: {str(e)}", "error")
        finally:
            # Re-enable button
            self.wireless_pair_btn.setEnabled(True)
            self.wireless_pair_btn.setText("无线配对")

    def _qr_pair_device(self):
        """Perform ADB QR code pairing for Android devices using direct connection."""
        device_type = self._current_device_type()
        if device_type != DeviceType.ADB:
            self._append_device_log("二维码配对仅适用于Android设备(ADB)。\n")
            self._update_device_status("二维码配对仅适用于ADB", "warning")
            return
        
        try:
            from phone_agent.direct_qr_pairing import DirectQRCodeDialog
            
            # Show QR code dialog
            dialog = DirectQRCodeDialog(self)
            self._append_device_log(f"[{self._timestamp()}] 启动直接二维码配对对话框\n")
            
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                # Get paired device
                device_id = dialog.get_paired_device()
                if device_id:
                    self._append_device_log(f"[{self._timestamp()}] ✅ 直接二维码配对成功，设备: {device_id}\n")
                    self._update_device_status("二维码配对成功", "success")
                    
                    # Update device ID input
                    self.device_id_input.setText(device_id)
                    
                    # Refresh device list
                    self._refresh_devices()
                    
                    # Add to connection history
                    self._add_connection_history("qr_pair", device_id)
                else:
                    self._append_device_log(f"[{self._timestamp()}] ⚠️ 配对完成但未找到设备\n")
                    self._update_device_status("配对完成但未找到设备", "warning")
            else:
                self._append_device_log(f"[{self._timestamp()}] 直接二维码配对已取消\n")
                self._update_device_status("二维码配对已取消", "info")
                
        except ImportError:
            self._append_device_log(f"[{self._timestamp()}] ❌ 直接二维码配对模块不可用，请安装qrcode库\n")
            self._update_device_status("缺少qrcode库", "error")
        except Exception as e:
            self._append_device_log(f"[{self._timestamp()}] ❌ 直接二维码配对错误: {str(e)}\n")
            self._update_device_status(f"二维码配对错误: {str(e)}", "error")

    def _check_wda(self):
        wda_url = None  # ADB-only interface doesn't use WDA
        conn = XCTestConnection(wda_url=wda_url)
        status = conn.get_wda_status()
        if status is None:
            self._append_log("WDA无法连接。\n")
        else:
            self._append_log("WDA连接正常。\n")

    def _run_task(self):
        task = self.task_input.toPlainText().strip()
        if not task:
            self._append_log("任务输入为空。\n")
            return

        # Check for task conflicts
        if self._check_task_conflicts():
            return

        # Get active model service config
        active_service = self.model_services_manager.get_active_service()
        if not active_service:
            self._append_log("没有激活的模型服务，请先在「模型服务」页面配置并激活一个服务。\n")
            return

        self._save_settings()
        self.run_task_btn.setEnabled(False)
        self.stop_task_btn.setEnabled(True)
        self.task_log.clear()
        self.timeline_list.clear()

        wda_url = None  # ADB-only interface doesn't use WDA
        self.task_worker = TaskWorker(
            device_type=self._current_device_type(),
            base_url=active_service.base_url,
            model=active_service.model_name,
            api_key=active_service.api_key,
            max_steps=self.max_steps_input.value(),
            device_id=self.device_id_input.text().strip(),
            lang=self.lang_combo.currentText(),
            wda_url=wda_url,
            task=task,
        )
        self.task_worker.log.connect(self._append_log)
        self.task_worker.timeline.connect(self._append_timeline)
        self.task_worker.adb_keyboard_notice.connect(self._show_adb_keyboard_notice)
        self.task_worker.confirmation_required.connect(self._show_confirmation_notice)
        self.task_worker.takeover_required.connect(self._show_takeover_notice)
        self.task_worker.finished.connect(self._task_finished)
        self.task_worker.failed.connect(self._task_failed)
        self.task_worker.start()

    def _stop_task(self):
        if self.task_worker and self.task_worker.isRunning():
            self._append_log("已请求停止。\n")
            self.task_worker.requestInterruption()
            self.stop_task_btn.setEnabled(False)

    def _task_finished(self, result):
        self._append_log(f"\n结果: {result}\n")
        self._append_timeline(f"任务完成: {result}")
        self._increment_tasks_counter()
        self.run_task_btn.setEnabled(True)
        self.stop_task_btn.setEnabled(False)

        # Wait for worker thread to fully finish before showing dialog
        if self.task_worker and self.task_worker.isRunning():
            self.task_worker.wait(500)

        # Show completion dialog
        self._show_task_completion_dialog(result, success=True)

    def _task_failed(self, message):
        self._append_log(f"\n错误: {message}\n")
        self._append_timeline(f"任务失败: {message}")
        self.run_task_btn.setEnabled(True)
        self.stop_task_btn.setEnabled(False)
        
        # Show completion dialog for failure
        self._show_task_completion_dialog(message, success=False)

    def _show_task_completion_dialog(self, result, success=True):
        """Show task completion dialog to user."""
        try:
            # Create dialog
            dialog = QtWidgets.QMessageBox(self)
            dialog.setWindowTitle("任务完成" if success else "任务失败")
            
            # Set icon and title based on success
            if success:
                dialog.setIcon(QtWidgets.QMessageBox.Information)
                dialog.setText("任务执行完成！")
                dialog.setDetailedText(f"执行结果:\n{result}")
            else:
                dialog.setIcon(QtWidgets.QMessageBox.Warning)
                dialog.setText("任务执行失败！")
                dialog.setDetailedText(f"错误信息:\n{result}")
            
            # Add standard buttons
            dialog.setStandardButtons(QtWidgets.QMessageBox.Ok)
            dialog.setDefaultButton(QtWidgets.QMessageBox.Ok)
            
            # Show dialog (non-blocking)
            dialog.show()
            
        except Exception as e:
            # Fallback to simple logging if dialog fails
            self._append_log(f"对话框显示失败: {e}\n")

    def _append_timeline(self, text):
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.timeline_list.addItem(f"{timestamp} {text}")
        self.timeline_list.scrollToBottom()

    def _show_adb_keyboard_notice(self, message):
        self._append_log(f"{message}\n")
        QtWidgets.QMessageBox.information(self, "ADB键盘", message)

    def _show_confirmation_notice(self, message):
        """Display a notice when a sensitive operation is being auto-confirmed."""
        self._append_timeline(f"⚠️ 敏感操作: {message}")
        # Show a brief notification in the status bar or timeline
        # The operation is auto-confirmed, so just notify the user

    def _show_takeover_notice(self, message):
        """Display a notice when manual operation is needed."""
        self._append_timeline(f"👋 需要手动操作: {message}")
        # Show a message box to alert the user
        QtWidgets.QMessageBox.warning(
            self,
            "需要手动操作",
            f"{message}\n\n任务将在3秒后自动继续。\n如需更多时间，请暂停任务。"
        )

    def _find_editor(self):
        editor = os.environ.get("EDITOR")
        if editor and shutil.which(editor):
            return editor
        for candidate in ["xed", "gedit", "code", "nano", "vim", "vi"]:
            if shutil.which(candidate):
                return candidate
        return None

    def _open_external_editor(self):
        if self.editor_process and self.editor_process.state() != QtCore.QProcess.NotRunning:
            return

        editor = self._find_editor()
        if not editor:
            QtWidgets.QMessageBox.information(
                self,
                "外部编辑器",
                "未找到编辑器。请设置EDITOR环境变量或安装gedit/xed/vim/nano。",
            )
            return

        fd, path = tempfile.mkstemp(prefix="autoglm_task_", suffix=".txt")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.task_input.toPlainText())

        self.editor_temp_path = path
        self.editor_process = QtCore.QProcess(self)
        self.editor_process.finished.connect(self._external_editor_finished)
        self.editor_process.start(editor, [path])

    def _external_editor_finished(self):
        if not self.editor_temp_path:
            return
        try:
            with open(self.editor_temp_path, "r", encoding="utf-8") as handle:
                self.task_input.setPlainText(handle.read())
        finally:
            with contextlib.suppress(Exception):
                os.remove(self.editor_temp_path)
            self.editor_temp_path = None

    def _get_connected_devices(self):
        """Get list of connected devices as dictionaries with id, name, type."""
        devices = []
        device_type = self._current_device_type()

        try:
            if device_type == DeviceType.IOS:
                ios_devices = list_ios_devices()
                for device in ios_devices:
                    devices.append({
                        'id': device.device_id,
                        'name': device.device_name or device.device_id,
                        'type': 'iOS'
                    })
            else:
                set_device_type(device_type)
                factory = get_device_factory()
                device_list = factory.list_devices()
                for device in device_list:
                    status = "OK" if device.status == "device" else device.status
                    type_name = "Android" if device_type == DeviceType.ADB else "HarmonyOS"
                    devices.append({
                        'id': device.device_id,
                        'name': f"{device.device_id} ({status})",
                        'type': type_name
                    })
        except Exception as e:
            print(f"Error getting connected devices: {e}")

        return devices

    def _refresh_preview_devices(self):
        """Refresh the preview device selection combo box."""
        if not hasattr(self, 'preview_device_combo'):
            return

        try:
            self.preview_device_combo.clear()

            # Get current devices
            devices = self._get_connected_devices()
            self.preview_devices = devices
            
            if not devices:
                self.preview_device_combo.addItem("未检测到设备", None)
                self.preview_prev_btn.setEnabled(False)
                self.preview_next_btn.setEnabled(False)
                self.preview_multi_btn.setEnabled(False)
                return
            
            # Add devices to combo box
            for i, device in enumerate(devices):
                device_id = device.get('id', '')
                device_name = device.get('name', device_id)
                device_type = device.get('type', 'Unknown')
                
                display_text = f"{device_id} | {device_name}"
                self.preview_device_combo.addItem(display_text, i)
            
            # Enable navigation buttons
            self.preview_prev_btn.setEnabled(len(devices) > 1)
            self.preview_next_btn.setEnabled(len(devices) > 1)
            self.preview_multi_btn.setEnabled(len(devices) > 1)
            
            # Auto-select first device if none selected
            if devices and self.preview_device_combo.count() > 0:
                self.preview_device_combo.setCurrentIndex(0)
                
        except Exception as e:
            print(f"Error refreshing preview devices: {e}")

    def _preview_device_changed(self, index):
        """Handle preview device selection change."""
        if index >= 0 and index < len(self.preview_devices):
            self.preview_current_index = index
            device = self.preview_devices[index]
            device_id = device.get('id', '')
            
            # Update device_id_input to match selection
            self.device_id_input.setText(device_id)
            
            # Restart preview if running
            if self.preview_timer.isActive():
                self._stop_preview()
                self._start_preview()

    def _preview_prev_device(self):
        """Switch to previous device in preview."""
        if len(self.preview_devices) > 1:
            self.preview_current_index = (self.preview_current_index - 1) % len(self.preview_devices)
            self.preview_device_combo.setCurrentIndex(self.preview_current_index)

    def _preview_next_device(self):
        """Switch to next device in preview."""
        if len(self.preview_devices) > 1:
            self.preview_current_index = (self.preview_current_index + 1) % len(self.preview_devices)
            self.preview_device_combo.setCurrentIndex(self.preview_current_index)

    def _toggle_multi_preview(self):
        """Toggle multi-device preview mode."""
        self.preview_multi_mode = self.preview_multi_btn.isChecked()

        if self.preview_multi_mode:
            # Start multi-device preview
            self.preview_multi_btn.setText("停止轮播")
            self.preview_device_combo.setEnabled(False)
            self.preview_prev_btn.setEnabled(False)
            self.preview_next_btn.setEnabled(False)

            # Start multi-device cycling
            if self.preview_timer.isActive():
                self._start_multi_preview()
        else:
            # Stop multi-device preview
            self.preview_multi_btn.setText("设备轮播")
            self.preview_device_combo.setEnabled(True)
            if len(self.preview_devices) > 1:
                self.preview_prev_btn.setEnabled(True)
                self.preview_next_btn.setEnabled(True)

            # Stop multi-device cycling
            self._stop_multi_preview()

    def _start_multi_preview(self):
        """Start multi-device preview cycling."""
        if not self.preview_devices:
            return
            
        # Start preview workers for all devices
        for device in self.preview_devices:
            device_id = device.get('id', '')
            if device_id and device_id not in self.preview_workers:
                self._start_device_preview_worker(device_id)
        
        # Start cycling timer
        self.preview_multi_timer.start()
        self.preview_status.setText(f"多设备预览 ({len(self.preview_devices)} 设备)")

    def _stop_multi_preview(self):
        """Stop multi-device preview cycling."""
        # Stop cycling timer
        self.preview_multi_timer.stop()
        
        # Stop all preview workers
        for device_id, worker in list(self.preview_workers.items()):
            if worker and worker.isRunning():
                worker.terminate()
                worker.wait(1000)
        self.preview_workers.clear()
        self.preview_images.clear()

    def _start_device_preview_worker(self, device_id):
        """Start preview worker for a specific device."""
        try:
            device_type = self._current_device_type()
            
            worker = ScreenshotWorker(
                device_type=device_type,
                device_id=device_id,
                wda_url=None,
            )
            worker.frame.connect(lambda data, is_sensitive, dev_id=device_id: self._handle_multi_preview_frame(dev_id, data, is_sensitive))
            worker.failed.connect(lambda msg: self._handle_multi_preview_error(device_id, msg))
            worker.finished.connect(lambda: self._handle_multi_preview_done(device_id))
            
            self.preview_workers[device_id] = worker
            worker.start()
            
        except Exception as e:
            print(f"Error starting preview worker for {device_id}: {e}")

    def _cycle_multi_preview(self):
        """Cycle through multi-device preview images."""
        if not self.preview_multi_mode or not self.preview_images:
            return
        
        # Get current device image
        if self.preview_current_index < len(self.preview_devices):
            current_device = self.preview_devices[self.preview_current_index]
            device_id = current_device.get('id', '')
            
            if device_id in self.preview_images:
                image = self.preview_images[device_id]
                if image:
                    pixmap = QtGui.QPixmap.fromImage(image).scaled(
                        self.preview_label.size(),
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                    self.preview_label.setPixmap(pixmap)
                    
                    # Update status
                    device_name = current_device.get('name', device_id)
                    self.preview_status.setText(f"多设备预览: {device_name}")
        
        # Move to next device
        self.preview_current_index = (self.preview_current_index + 1) % len(self.preview_devices)

    def _handle_multi_preview_frame(self, device_id, data, is_sensitive):
        """Handle preview frame for multi-device mode."""
        # Convert bytes to QImage
        image = QtGui.QImage.fromData(data)
        if not image.isNull():
            self.preview_images[device_id] = image

    def _handle_multi_preview_error(self, device_id, message):
        """Handle preview error for multi-device mode."""
        print(f"Preview error for {device_id}: {message}")

    def _handle_multi_preview_done(self, device_id):
        """Handle preview worker completion for multi-device mode."""
        if device_id in self.preview_workers:
            del self.preview_workers[device_id]

    def _start_preview(self):
        """Start device preview using embedded screenshot display."""
        device_id = self._get_preview_device_id()

        if not device_id:
            self.preview_status.setText("未选择设备")
            print("[Preview] No device selected")
            return

        print(f"[Preview] Starting preview for device: {device_id}")

        if not self.preview_timer.isActive():
            self.preview_timer.start()

        self.preview_status.setText(f"预览中: {device_id}")
        self.preview_start_btn.setEnabled(False)
        self.preview_stop_btn.setEnabled(True)
        self._request_preview_frame()

    def _stop_preview(self):
        """Stop device preview."""
        print("[Preview] Stopping preview")
        self.preview_timer.stop()
        self.preview_status.setText("预览已停止")
        self.preview_label.setText("📱\n\n预览区域\n\n选择设备后开始预览")
        self.preview_start_btn.setEnabled(True)
        self.preview_stop_btn.setEnabled(False)

    def _get_preview_device_id(self) -> str | None:
        """Get the current preview device ID."""
        device_id = None
        if hasattr(self, 'preview_devices') and self.preview_devices:
            if self.preview_current_index < len(self.preview_devices):
                device = self.preview_devices[self.preview_current_index]
                device_id = device.get('id', '')

        if not device_id:
            device_id = self._get_selected_device_id()

        return device_id

    def _snapshot_preview(self):
        self._request_preview_frame()

    def _request_preview_frame(self):
        if self.preview_inflight:
            # print("[Preview] Request skipped - already in flight")
            return
        self.preview_inflight = True
        device_type = self._current_device_type()

        device_id = self._get_preview_device_id()

        if not device_id:
            self.preview_status.setText("未选择设备")
            self.preview_inflight = False
            return

        # print(f"[Preview] Requesting frame from device: {device_id}")

        # WDA URL is not needed for ADB-only interface
        self.preview_worker = ScreenshotWorker(
            device_type=device_type,
            device_id=device_id,
            wda_url=None,  # ADB-only interface doesn't use WDA
        )
        self.preview_worker.frame.connect(self._handle_preview_frame)
        self.preview_worker.failed.connect(self._handle_preview_error)
        self.preview_worker.finished.connect(self._preview_done)
        self.preview_worker.start()

    def _preview_done(self):
        self.preview_inflight = False

    def _handle_preview_frame(self, data, is_sensitive):
        image = QtGui.QImage.fromData(data)
        if image.isNull():
            print("[Preview] Failed to decode image")
            self.preview_status.setText("预览解码失败")
            return

        # print(f"[Preview] Frame received: {image.width()}x{image.height()}, sensitive={is_sensitive}")
        self.last_preview_image = image
        pixmap = QtGui.QPixmap.fromImage(image).scaled(
            self.preview_label.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)
        
        # Update status only if there's an error or initial state
        current_status = self.preview_status.text()
        if current_status.startswith("预览设备:") or current_status == "预览运行中。":
            # Keep current status showing device info, don't update with timestamp
            pass
        elif is_sensitive:
            self.preview_status.setText("预览已更新(敏感内容)")
        else:
            self.preview_status.setText("预览已更新")

    def _handle_preview_error(self, message):
        self.preview_status.setText(f"预览错误: {message}")
        self.preview_inflight = False

    def _clear_diagnostics(self):
        self.diagnostics_log.clear()
        self.diagnostics_summary.clear()
        self.diagnostics_status.setText("就绪。")

    def _run_diagnostics(self, mode):
        if self.diagnostic_worker and self.diagnostic_worker.isRunning():
            return
        self.diagnostics_status.setText("运行中...")

        # Get active model service config
        active_service = self.model_services_manager.get_active_service()
        base_url = active_service.base_url if active_service else ""
        model = active_service.model_name if active_service else ""
        api_key = active_service.api_key if active_service else ""

        self.diagnostic_worker = DiagnosticWorker(
            mode=mode,
            device_type=self._current_device_type(),
            device_id=self.device_id_input.text().strip() or None,
            base_url=base_url,
            model=model,
            api_key=api_key,
            wda_url=None,  # ADB-only interface doesn't use WDA
        )
        self.diag_system_btn.setEnabled(False)
        self.diag_model_btn.setEnabled(False)
        self.diag_all_btn.setEnabled(False)
        self.diagnostic_worker.log.connect(self._append_diag_log)
        self.diagnostic_worker.summary.connect(self._update_diagnostics_summary)
        self.diagnostic_worker.adb_keyboard_notice.connect(
            self._show_adb_keyboard_notice
        )
        self.diagnostic_worker.finished.connect(self._diagnostics_finished)
        self.diagnostic_worker.start()

    def _diagnostics_finished(self, ok, message):
        status = "OK" if ok else "FAIL"
        self.diagnostics_status.setText(f"{status}: {message}")
        self.diag_system_btn.setEnabled(True)
        self.diag_model_btn.setEnabled(True)
        self.diag_all_btn.setEnabled(True)

    def _update_diagnostics_summary(self, items):
        self.diagnostics_summary.clear()
        for item in items:
            status = item.get("status", "unknown")
            label = item.get("label", "Check")
            detail = item.get("detail", "")
            text = f"{label}: {status.upper()}"
            if detail:
                text = f"{text} ({detail})"
            list_item = QtWidgets.QListWidgetItem(text)
            if status == "ok":
                list_item.setForeground(QtGui.QColor("#22c55e"))
            elif status == "fail":
                list_item.setForeground(QtGui.QColor("#ef4444"))
            elif status == "skip":
                list_item.setForeground(QtGui.QColor("#f59e0b"))
            else:
                list_item.setForeground(QtGui.QColor("#e5e7eb"))
            self.diagnostics_summary.addItem(list_item)


def run():
    _setup_ime_env()
    if hasattr(QtCore.Qt, "AA_InputMethodEnabled"):
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_InputMethodEnabled, True)
    elif hasattr(QtCore.Qt, "ApplicationAttribute"):
        attr = QtCore.Qt.ApplicationAttribute
        if hasattr(attr, "AA_InputMethodEnabled"):
            QtCore.QCoreApplication.setAttribute(attr.AA_InputMethodEnabled, True)
    
    # 使用已存在的 QApplication 实例，如果不存在则创建新的
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
