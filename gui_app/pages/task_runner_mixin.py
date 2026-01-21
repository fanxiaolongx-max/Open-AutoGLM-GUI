# -*- coding: utf-8 -*-
"""任务执行页面 Mixin - 处理任务执行的所有功能"""

from PySide6 import QtCore, QtGui, QtWidgets

from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.xctest import list_devices as list_ios_devices


class TaskRunnerMixin:
    """任务执行页面的 Mixin 类，包含所有任务执行相关的方法"""

    def _build_task_runner(self):
        from gui_app.components import DragDropTextEdit

        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(12)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        header = QtWidgets.QLabel("任务执行")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("支持多设备并行执行AI驱动的自动化任务")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Main content - 3 column layout
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(12)

        # Left Panel - Task Input & Device Selection & Status
        left_card = QtWidgets.QFrame()
        left_card.setObjectName("card")
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 12, 16, 12)
        left_layout.setSpacing(10)

        # Task Templates Section
        template_header = QtWidgets.QLabel("快捷模板")
        template_header.setObjectName("cardTitle")

        template_layout = QtWidgets.QHBoxLayout()
        template_layout.setSpacing(6)

        templates = [
            ("📱 打开应用", "打开微信"),
            ("💬 发送消息", "打开微信，找到张三，发送消息：你好"),
            ("📸 截图保存", "截取当前屏幕并保存到相册"),
            ("⚙️ 系统设置", "进入设置，找到显示选项，调整亮度为50%"),
            ("🔍 搜索内容", "打开浏览器，搜索今天的天气"),
        ]

        for label, task_text in templates:
            btn = QtWidgets.QPushButton(label)
            btn.setObjectName("secondary")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setToolTip(task_text)
            btn.clicked.connect(lambda checked, t=task_text: self.task_input.setPlainText(t))
            template_layout.addWidget(btn)

        template_layout.addStretch()

        # Task Input Section
        input_header = QtWidgets.QLabel("任务描述")
        input_header.setObjectName("cardTitle")

        self.task_input = DragDropTextEdit()
        self.task_input.setPlaceholderText(
            "描述您希望AI在设备上执行的任务...\n"
            "支持拖拽 .txt/.md/.py 等文件导入\n\n"
            "示例:\n"
            "• 打开微信给张三发送消息\n"
            "• 截图并保存\n"
            "• 进入设置 > 显示 > 亮度"
        )
        # 启用输入法支持
        self.task_input.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        self.task_input.setInputMethodHints(QtCore.Qt.ImhMultiLine)
        self.task_input.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.task_input.setMinimumHeight(80)
        self.task_input.setMaximumHeight(150)
        self.task_input.fileImported.connect(
            lambda path: self._append_log(f"已导入文件: {path}\n")
        )

        # Device Selection Section
        device_header = QtWidgets.QLabel("选择设备（可多选）")
        device_header.setObjectName("cardTitle")
        device_header.setStyleSheet("margin-top: 8px;")

        self.task_device_list = QtWidgets.QListWidget()
        self.task_device_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.task_device_list.setMinimumHeight(100)
        self.task_device_list.setMaximumHeight(150)

        refresh_devices_btn = QtWidgets.QPushButton("刷新设备列表")
        refresh_devices_btn.setObjectName("secondary")
        refresh_devices_btn.setCursor(QtCore.Qt.PointingHandCursor)
        refresh_devices_btn.clicked.connect(self._refresh_task_devices)

        # Action Buttons
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)

        self.run_task_btn = QtWidgets.QPushButton("批量执行")
        self.run_task_btn.setObjectName("success")
        self.run_task_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.run_task_btn.clicked.connect(self._run_multi_task)

        self.stop_task_btn = QtWidgets.QPushButton("全部停止")
        self.stop_task_btn.setObjectName("danger")
        self.stop_task_btn.setEnabled(False)
        self.stop_task_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.stop_task_btn.clicked.connect(self._stop_multi_task)

        actions.addWidget(self.run_task_btn)
        actions.addWidget(self.stop_task_btn)
        actions.addStretch()

        left_layout.addWidget(template_header)
        left_layout.addLayout(template_layout)
        left_layout.addWidget(input_header)
        left_layout.addWidget(self.task_input)

        # 左栏上部：任务和设备选择行
        task_device_row = QtWidgets.QHBoxLayout()
        task_device_row.setSpacing(12)

        # 设备选择区
        device_section = QtWidgets.QVBoxLayout()
        device_section.setSpacing(6)
        device_section.addWidget(device_header)
        device_section.addWidget(self.task_device_list)
        device_section.addWidget(refresh_devices_btn)
        device_section.addLayout(actions)

        task_device_row.addLayout(device_section, 1)

        left_layout.addLayout(task_device_row)

        # 设备执行状态（在快捷模板下方）
        status_header = QtWidgets.QLabel("设备执行状态")
        status_header.setObjectName("cardTitle")
        status_header.setStyleSheet("margin-top: 8px;")

        self.multi_status_label = QtWidgets.QLabel("就绪 - 选择设备后点击批量执行")
        self.multi_status_label.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 8px 12px; border-radius: 8px;"
        )

        self.device_status_list = QtWidgets.QListWidget()
        self.device_status_list.setMinimumHeight(80)
        self.device_status_list.setMaximumHeight(120)

        # Log Section
        log_header = QtWidgets.QLabel("执行日志")
        log_header.setObjectName("cardTitle")
        log_header.setStyleSheet("margin-top: 8px;")

        self.task_log = QtWidgets.QPlainTextEdit()
        self.task_log.setReadOnly(True)
        self.task_log.setPlaceholderText("任务执行日志将显示在这里...")
        self.task_log.setMaximumHeight(150)

        left_layout.addWidget(status_header)
        left_layout.addWidget(self.multi_status_label)
        left_layout.addWidget(self.device_status_list)
        left_layout.addWidget(log_header)
        left_layout.addWidget(self.task_log, 1)

        # Right Panel - Preview & Timeline
        right_card = QtWidgets.QFrame()
        right_card.setObjectName("card")
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(10)

        # Preview Section
        preview_header_layout = QtWidgets.QHBoxLayout()
        preview_header = QtWidgets.QLabel("实时预览")
        preview_header.setObjectName("cardTitle")

        self.preview_status = QtWidgets.QLabel("初始化中...")
        self.preview_status.setFixedWidth(140)  # 固定宽度防止布局变化
        self.preview_status.setStyleSheet(
            "font-size: 10px; color: #71717a; background: rgba(39, 39, 42, 0.6); "
            "padding: 3px 8px; border-radius: 4px;"
        )

        preview_header_layout.addWidget(preview_header)
        preview_header_layout.addStretch()
        preview_header_layout.addWidget(self.preview_status)

        # Device Selection and Navigation
        preview_nav_layout = QtWidgets.QHBoxLayout()

        # Previous device button
        self.preview_prev_btn = QtWidgets.QPushButton("◀")
        self.preview_prev_btn.setObjectName("secondary")
        self.preview_prev_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.preview_prev_btn.setMaximumWidth(40)
        self.preview_prev_btn.setToolTip("切换到上一个设备")
        self.preview_prev_btn.clicked.connect(self._preview_prev_device)
        self.preview_prev_btn.setEnabled(False)

        # Device selector - 固定宽度防止布局变化
        self.preview_device_combo = QtWidgets.QComboBox()
        self.preview_device_combo.setObjectName("deviceSelector")
        self.preview_device_combo.setMinimumHeight(30)
        self.preview_device_combo.setFixedWidth(150)  # 固定宽度
        self.preview_device_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preview_device_combo.setToolTip("选择要预览的设备")
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
        self.preview_device_combo.currentIndexChanged.connect(self._preview_device_changed)

        # Next device button
        self.preview_next_btn = QtWidgets.QPushButton("▶")
        self.preview_next_btn.setObjectName("secondary")
        self.preview_next_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.preview_next_btn.setMaximumWidth(40)
        self.preview_next_btn.setToolTip("切换到下一个设备")
        self.preview_next_btn.clicked.connect(self._preview_next_device)
        self.preview_next_btn.setEnabled(False)

        # Multi-device toggle
        self.preview_multi_btn = QtWidgets.QPushButton("设备轮播")
        self.preview_multi_btn.setObjectName("secondary")
        self.preview_multi_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.preview_multi_btn.setMinimumWidth(80)
        self.preview_multi_btn.setCheckable(True)
        self.preview_multi_btn.setChecked(False)  # Explicitly ensure not checked by default
        self.preview_multi_btn.setToolTip("启用后自动轮流预览所有已连接设备")
        self.preview_multi_btn.clicked.connect(self._toggle_multi_preview)

        preview_nav_layout.addWidget(self.preview_prev_btn)
        preview_nav_layout.addWidget(self.preview_device_combo, 1)
        preview_nav_layout.addWidget(self.preview_next_btn)
        preview_nav_layout.addWidget(self.preview_multi_btn)

        # Device Preview Frame - 使用固定宽度容器保持稳定
        preview_container = QtWidgets.QWidget()
        preview_container_layout = QtWidgets.QVBoxLayout(preview_container)
        preview_container_layout.setContentsMargins(0, 0, 0, 0)
        preview_container_layout.setAlignment(QtCore.Qt.AlignCenter)

        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setFixedSize(220, 390)  # 固定大小，9:16 手机屏幕比例
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setObjectName("preview")
        self.preview_label.setStyleSheet(
            """
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #18181b, stop:1 #09090b);
            border: 2px solid #27272a;
            border-radius: 12px;
            color: #71717a;
            font-size: 12px;
        """)
        self.preview_label.setText("📱\n\n预览区域\n\n选择设备后开始预览")

        preview_container_layout.addWidget(self.preview_label)

        # Preview Controls
        preview_controls = QtWidgets.QHBoxLayout()
        self.preview_start_btn = QtWidgets.QPushButton("开始预览")
        self.preview_start_btn.setObjectName("secondary")
        self.preview_start_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.preview_start_btn.setToolTip("开始实时预览设备屏幕")
        self.preview_start_btn.clicked.connect(self._start_preview)

        self.preview_stop_btn = QtWidgets.QPushButton("暂停预览")
        self.preview_stop_btn.setObjectName("secondary")
        self.preview_stop_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.preview_stop_btn.setToolTip("暂停实时预览")
        self.preview_stop_btn.clicked.connect(self._stop_preview)
        self.preview_stop_btn.setEnabled(False)

        # 高清镜像按钮 (scrcpy)
        self.scrcpy_btn = QtWidgets.QPushButton("高清镜像")
        self.scrcpy_btn.setObjectName("success")
        self.scrcpy_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.scrcpy_btn.setToolTip("使用 scrcpy 启动高清实时镜像 (30fps+)")
        self.scrcpy_btn.clicked.connect(self._start_scrcpy_mirror)

        preview_controls.addStretch()
        preview_controls.addWidget(self.preview_start_btn)
        preview_controls.addWidget(self.preview_stop_btn)
        preview_controls.addWidget(self.scrcpy_btn)
        preview_controls.addStretch()

        right_layout.addLayout(preview_header_layout)
        right_layout.addLayout(preview_nav_layout)
        right_layout.addWidget(preview_container, 2)
        right_layout.addLayout(preview_controls)

        # Timeline Section
        timeline_header = QtWidgets.QLabel("活动时间线")
        timeline_header.setObjectName("cardTitle")
        timeline_header.setStyleSheet("margin-top: 6px;")

        self.timeline_list = QtWidgets.QListWidget()
        self.timeline_list.setObjectName("timeline_list")
        self.timeline_list.setMinimumHeight(60)
        self.timeline_list.setMaximumHeight(120)

        right_layout.addWidget(timeline_header)
        right_layout.addWidget(self.timeline_list, 1)

        content_layout.addWidget(left_card, 5)
        content_layout.addWidget(right_card, 3)

        layout.addWidget(header_widget)
        layout.addLayout(content_layout, 1)

        # Connect multi-device manager signals
        self.multi_device_manager.device_log.connect(self._on_multi_device_log)
        self.multi_device_manager.device_status.connect(self._on_multi_device_status)
        self.multi_device_manager.device_finished.connect(self._on_multi_device_finished)
        self.multi_device_manager.all_finished.connect(self._on_all_tasks_finished)

        return page

    def _refresh_task_devices(self):
        """刷新任务页面的设备列表"""
        self.task_device_list.clear()
        device_type = self._current_device_type()

        if device_type == DeviceType.IOS:
            devices = list_ios_devices()
            for device in devices:
                name = device.device_name or device.device_id
                item = QtWidgets.QListWidgetItem(f"{name} | {device.device_id}")
                item.setData(QtCore.Qt.UserRole, (device.device_id, device_type))
                self.task_device_list.addItem(item)
        else:
            set_device_type(device_type)
            factory = get_device_factory()
            devices = factory.list_devices()
            for device in devices:
                status = "OK" if device.status == "device" else device.status
                item = QtWidgets.QListWidgetItem(f"{device.device_id} | {status}")
                item.setData(QtCore.Qt.UserRole, (device.device_id, device_type))
                self.task_device_list.addItem(item)

        if self.task_device_list.count() == 0:
            item = QtWidgets.QListWidgetItem("没有检测到设备")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self.task_device_list.addItem(item)

    def _check_task_conflicts(self):
        """检查是否有任务冲突，如果有正在运行的任务则返回True"""
        conflicts = []

        # Check multi-device manager
        if hasattr(self, 'multi_device_manager') and self.multi_device_manager.workers:
            running_devices = []
            for device_id, worker in self.multi_device_manager.workers.items():
                if worker.isRunning():
                    running_devices.append(device_id)
            if running_devices:
                conflicts.append(f"多设备任务正在运行: {', '.join(running_devices)}")

        # Check single task worker
        if hasattr(self, 'task_worker') and self.task_worker and self.task_worker.isRunning():
            conflicts.append("单设备任务正在运行")

        # Check script worker
        if hasattr(self, 'script_worker') and self.script_worker and self.script_worker.isRunning():
            conflicts.append("脚本任务正在运行")

        # Check gemini task worker
        if hasattr(self, 'gemini_task_worker') and self.gemini_task_worker and self.gemini_task_worker.isRunning():
            conflicts.append("Gemini任务正在运行")

        # Check scheduled tasks manager
        if hasattr(self, 'scheduled_tasks_manager') and self.scheduled_tasks_manager:
            running_scheduled = self.scheduled_tasks_manager.get_running_tasks()
            if running_scheduled:
                conflicts.append(f"定时任务正在运行: {len(running_scheduled)} 个")

        if conflicts:
            self._append_log("⚠️ 检测到任务冲突:\n")
            for conflict in conflicts:
                self._append_log(f"   • {conflict}\n")
            self._append_log("请先停止正在运行的任务，或等待任务完成。\n")
            return True

        return False

    def _run_multi_task(self):
        """批量执行多设备任务"""
        task = self.task_input.toPlainText().strip()
        if not task:
            self._append_log("任务输入为空。\n")
            return

        # Check for task conflicts
        if self._check_task_conflicts():
            return

        selected_items = self.task_device_list.selectedItems()
        if not selected_items:
            self._append_log("请先选择至少一个设备。\n")
            return

        devices = []
        for item in selected_items:
            data = item.data(QtCore.Qt.UserRole)
            if data:
                devices.append(data)

        if not devices:
            self._append_log("没有有效的设备被选择。\n")
            return

        self._save_settings()
        self.run_task_btn.setEnabled(False)
        self.stop_task_btn.setEnabled(True)
        self.device_status_list.clear()
        self.task_log.clear()

        # 初始化设备状态显示
        for device_id, device_type in devices:
            item = QtWidgets.QListWidgetItem(f"📱 {device_id}: 准备中...")
            item.setData(QtCore.Qt.UserRole, device_id)
            self.device_status_list.addItem(item)

        self.multi_status_label.setText(f"正在执行 - {len(devices)} 个设备")
        self.multi_status_label.setStyleSheet(
            "font-size: 12px; color: #6366f1; background: rgba(99, 102, 241, 0.15); "
            "padding: 8px 12px; border-radius: 8px;"
        )

        # Get active model service config
        active_service = self.model_services_manager.get_active_service()
        if not active_service:
            self._append_log("没有激活的模型服务，请先在「模型服务」页面配置并激活一个服务。\n")
            self.run_task_btn.setEnabled(True)
            self.stop_task_btn.setEnabled(False)
            return

        config = {
            "base_url": active_service.base_url,
            "model": active_service.model_name,
            "api_key": active_service.api_key,
            "max_steps": self.max_steps_input.value(),
            "lang": self.lang_combo.currentText(),
            "wda_url": None,  # ADB-only interface doesn't use WDA
        }

        # 在执行任务前，检查并解锁 ADB 设备，记录之前的锁屏状态
        from phone_agent.adb.unlock import ensure_device_unlocked, is_device_locked
        self._devices_to_relock = []  # 记录需要重新锁屏的设备
        failed_devices = []  # 记录解锁失败的设备
        valid_devices = []  # 记录可以执行任务的设备

        for device_id, device_type in devices:
            if device_type == DeviceType.ADB:
                self._append_log(f"检查设备 {device_id} 锁屏状态...\n")
                QtWidgets.QApplication.processEvents()
                # 先检查是否锁屏，记录状态
                was_locked = is_device_locked(device_id)
                if was_locked:
                    self._devices_to_relock.append(device_id)
                success, message = ensure_device_unlocked(device_id)
                if success:
                    self._append_log(f"  ✓ {message}\n")
                    valid_devices.append((device_id, device_type))
                else:
                    self._append_log(f"  ✗ {message}\n")
                    self._append_log(f"  ❌ 设备 {device_id} 解锁失败，跳过此设备\n")
                    failed_devices.append((device_id, message))
                    # 更新设备状态显示为失败
                    for i in range(self.device_status_list.count()):
                        item = self.device_status_list.item(i)
                        if item.data(QtCore.Qt.UserRole) == device_id:
                            item.setText(f"❌ {device_id}: 解锁失败")
                            item.setBackground(QtGui.QColor(239, 68, 68, 30))
                            break
            else:
                valid_devices.append((device_id, device_type))

        # 如果所有设备都解锁失败，则直接返回失败
        if not valid_devices:
            self._append_log("\n❌ 所有设备解锁失败，无法执行任务\n")
            self.run_task_btn.setEnabled(True)
            self.stop_task_btn.setEnabled(False)
            self.multi_status_label.setText(f"失败 - 所有设备解锁失败")
            self.multi_status_label.setStyleSheet(
                "font-size: 12px; color: #ef4444; background: rgba(239, 68, 68, 0.15); "
                "padding: 8px 12px; border-radius: 8px;"
            )
            # 发送失败报告邮件
            if hasattr(self, '_send_task_report_email'):
                task_content = self.task_input.toPlainText().strip()
                task_name = task_content[:50] + "..." if len(task_content) > 50 else task_content
                log_content = self.task_log.toPlainText()
                self._send_task_report_email(
                    task_name=task_name,
                    success_count=0,
                    failed_count=len(devices),
                    total_count=len(devices),
                    details=log_content,
                    is_scheduled=False
                )
            return

        # 如果有部分设备解锁失败，提示用户
        if failed_devices:
            self._append_log(f"\n⚠️ {len(failed_devices)} 个设备解锁失败，将仅在 {len(valid_devices)} 个设备上执行任务\n")

        self.multi_device_manager.start_tasks(valid_devices, task, config)
        self._append_timeline(f"批量任务开始: {len(valid_devices)} 个设备")

    def _stop_multi_task(self):
        """停止所有设备的任务"""
        stopped_tasks = []

        # Stop multi-device tasks
        if hasattr(self, 'multi_device_manager') and self.multi_device_manager.workers:
            running_count = len([w for w in self.multi_device_manager.workers.values() if w.isRunning()])
            if running_count > 0:
                self.multi_device_manager.stop_all()
                # 等待所有 worker 停止
                for worker in self.multi_device_manager.workers.values():
                    if worker.isRunning():
                        worker.wait(2000)  # 等待最多2秒
                        if worker.isRunning():
                            worker.terminate()  # 强制终止
                            worker.wait(500)
                stopped_tasks.append(f"多设备任务 ({running_count} 个)")

        # Stop single task worker
        if hasattr(self, 'task_worker') and self.task_worker and self.task_worker.isRunning():
            self.task_worker.terminate()
            self.task_worker.wait(1000)
            stopped_tasks.append("单设备任务")

        # Stop script worker
        if hasattr(self, 'script_worker') and self.script_worker and self.script_worker.isRunning():
            self.script_worker.terminate()
            self.script_worker.wait(1000)
            stopped_tasks.append("脚本任务")

        # Stop gemini task worker
        if hasattr(self, 'gemini_task_worker') and self.gemini_task_worker and self.gemini_task_worker.isRunning():
            self.gemini_task_worker.terminate()
            self.gemini_task_worker.wait(1000)
            stopped_tasks.append("Gemini任务")

        # Stop scheduled tasks
        if hasattr(self, 'scheduled_tasks_manager') and self.scheduled_tasks_manager:
            running_scheduled = self.scheduled_tasks_manager.get_running_tasks()
            if running_scheduled:
                self.scheduled_tasks_manager.stop_all()
                stopped_tasks.append(f"定时任务 ({len(running_scheduled)} 个)")

        # Re-enable buttons
        self.run_task_btn.setEnabled(True)
        self.stop_task_btn.setEnabled(False)

        # Log what was stopped
        if stopped_tasks:
            self._append_log("🛑 已停止以下任务:\n")
            for task in stopped_tasks:
                self._append_log(f"   • {task}\n")
            self._append_log("所有任务已停止。\n")
        else:
            self._append_log("没有正在运行的任务。\n")

    def _on_multi_device_log(self, device_id, message):
        """处理多设备日志"""
        self._append_log(f"[{device_id}] {message}")

    def _on_multi_device_status(self, device_id, status):
        """更新设备状态显示"""
        for i in range(self.device_status_list.count()):
            item = self.device_status_list.item(i)
            if item.data(QtCore.Qt.UserRole) == device_id:
                item.setText(f"📱 {device_id}: {status}")
                break

    def _on_multi_device_finished(self, device_id, success, result):
        """单个设备任务完成"""
        icon = "✅" if success else "❌"
        for i in range(self.device_status_list.count()):
            item = self.device_status_list.item(i)
            if item.data(QtCore.Qt.UserRole) == device_id:
                item.setText(f"{icon} {device_id}: {result}")
                if success:
                    item.setBackground(QtGui.QColor(16, 185, 129, 30))
                else:
                    item.setBackground(QtGui.QColor(239, 68, 68, 30))
                break
        self._append_timeline(f"{icon} {device_id}: {result}")

        # Update completed tasks counter if successful
        if success:
            self._increment_tasks_counter()

    def _on_all_tasks_finished(self):
        """所有任务完成"""
        self.run_task_btn.setEnabled(True)
        self.stop_task_btn.setEnabled(False)

        success, failed = self.multi_device_manager.get_results_summary()
        total = success + failed

        if failed == 0:
            self.multi_status_label.setText(f"全部完成 - {success}/{total} 成功")
            self.multi_status_label.setStyleSheet(
                "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 8px 12px; border-radius: 8px;"
            )
        else:
            self.multi_status_label.setText(f"已完成 - {success} 成功, {failed} 失败")
            self.multi_status_label.setStyleSheet(
                "font-size: 12px; color: #f59e0b; background: rgba(245, 158, 11, 0.15); "
                "padding: 8px 12px; border-radius: 8px;"
            )

        self._append_timeline(f"批量任务完成: {success} 成功, {failed} 失败")

        # 重新锁屏之前已锁屏的设备
        if hasattr(self, '_devices_to_relock') and self._devices_to_relock:
            from phone_agent.adb.unlock import lock_screen
            for device_id in self._devices_to_relock:
                self._append_log(f"恢复设备 {device_id} 锁屏状态...\n")
                if lock_screen(device_id):
                    self._append_log(f"  ✓ 已锁屏\n")
                else:
                    self._append_log(f"  ⚠ 锁屏失败\n")
            self._devices_to_relock = []

        # Show multi-device task completion dialog
        self._show_multi_device_completion_dialog(success, failed, total)

        # 发送邮件报告（手动任务）
        if hasattr(self, '_send_task_report_email'):
            task_content = self.task_input.toPlainText().strip()
            task_name = task_content[:50] + "..." if len(task_content) > 50 else task_content
            log_content = self.task_log.toPlainText()
            self._send_task_report_email(
                task_name=task_name,
                success_count=success,
                failed_count=failed,
                total_count=total,
                details=log_content,
                is_scheduled=False
            )

    def _show_multi_device_completion_dialog(self, success, failed, total):
        """Show multi-device task completion dialog to user."""
        try:
            # Create dialog
            dialog = QtWidgets.QMessageBox(self)
            dialog.setWindowTitle("批量任务完成")

            # Set icon and message based on results
            if failed == 0:
                dialog.setIcon(QtWidgets.QMessageBox.Information)
                dialog.setText(f"所有设备任务执行完成！")
                dialog.setDetailedText(f"执行结果:\n成功: {success} 个设备\n失败: {failed} 个设备\n总计: {total} 个设备")
            elif success == 0:
                dialog.setIcon(QtWidgets.QMessageBox.Critical)
                dialog.setText(f"所有设备任务执行失败！")
                dialog.setDetailedText(f"执行结果:\n成功: {success} 个设备\n失败: {failed} 个设备\n总计: {total} 个设备")
            else:
                dialog.setIcon(QtWidgets.QMessageBox.Warning)
                dialog.setText(f"批量任务执行完成（部分失败）！")
                dialog.setDetailedText(f"执行结果:\n成功: {success} 个设备\n失败: {failed} 个设备\n总计: {total} 个设备")

            # Add standard buttons
            dialog.setStandardButtons(QtWidgets.QMessageBox.Ok)
            dialog.setDefaultButton(QtWidgets.QMessageBox.Ok)

            # Show dialog (non-blocking)
            dialog.show()

        except Exception as e:
            # Fallback to simple logging if dialog fails
            self._append_log(f"多设备对话框显示失败: {e}\n")
