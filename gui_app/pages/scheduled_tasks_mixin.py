# -*- coding: utf-8 -*-
"""定时任务页面 Mixin - 处理定时任务管理的所有功能"""

from PySide6 import QtCore, QtGui, QtWidgets

from gui_app.custom_widgets import NoWheelSpinBox, NoWheelComboBox, NoWheelTimeEdit
from gui_app.scheduler import ScheduledTask
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.xctest import list_devices as list_ios_devices
from gui_app.components import TaskWorker


class ScheduledTasksMixin:
    """定时任务页面的 Mixin 类，包含所有定时任务相关的方法"""

    def _build_scheduled_tasks(self):
        """Build the scheduled tasks management page."""
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

        header = QtWidgets.QLabel("定时任务")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("设置自动执行的定时任务，支持多种调度周期")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Task List Card
        list_card = QtWidgets.QFrame()
        list_card.setObjectName("card")
        list_layout = QtWidgets.QVBoxLayout(list_card)

        list_header = QtWidgets.QHBoxLayout()
        list_title = QtWidgets.QLabel("任务列表")
        list_title.setObjectName("cardTitle")

        add_task_btn = QtWidgets.QPushButton("+ 添加任务")
        add_task_btn.setCursor(QtCore.Qt.PointingHandCursor)
        add_task_btn.clicked.connect(self._add_scheduled_task)

        list_header.addWidget(list_title)
        list_header.addStretch()
        list_header.addWidget(add_task_btn)

        self.scheduled_task_list = QtWidgets.QTableWidget()
        self.scheduled_task_list.setColumnCount(7)
        self.scheduled_task_list.setHorizontalHeaderLabels(
            ["启用", "任务名称", "执行设备", "调度类型", "下次执行", "执行次数", "操作"]
        )
        # 设置表格样式
        self.scheduled_task_list.setShowGrid(True)  # 显示网格线
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
        # 设置列宽可交互调整
        header = self.scheduled_task_list.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)  # 启用 - 可调整
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)  # 任务名称 - 可调整
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)  # 执行设备 - 可调整
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)  # 调度类型 - 可调整
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Interactive)  # 下次执行 - 可调整
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.Interactive)  # 执行次数 - 可调整
        # 设置默认列宽
        self.scheduled_task_list.setColumnWidth(0, 50)
        self.scheduled_task_list.setColumnWidth(1, 120)
        self.scheduled_task_list.setColumnWidth(2, 100)
        self.scheduled_task_list.setColumnWidth(3, 70)
        self.scheduled_task_list.setColumnWidth(4, 120)
        self.scheduled_task_list.setColumnWidth(5, 70)
        self.scheduled_task_list.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self.scheduled_task_list.setMinimumHeight(200)
        self.scheduled_task_list.verticalHeader().setVisible(False)

        list_layout.addLayout(list_header)
        list_layout.addWidget(self.scheduled_task_list)

        # Task Editor Card
        editor_card = QtWidgets.QFrame()
        editor_card.setObjectName("card")
        editor_layout = QtWidgets.QVBoxLayout(editor_card)

        editor_title = QtWidgets.QLabel("任务配置")
        editor_title.setObjectName("cardTitle")

        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        self.sched_task_name = QtWidgets.QLineEdit()
        self.sched_task_name.setPlaceholderText("任务名称")

        self.sched_task_content = QtWidgets.QTextEdit()
        self.sched_task_content.setPlaceholderText("任务指令，例如：打开微信发送消息给张三")
        self.sched_task_content.setMaximumHeight(80)

        self.sched_type_combo = NoWheelComboBox()
        self.sched_type_combo.addItems([
            "单次执行",
            "间隔执行",
            "每日执行",
            "每周执行",
            "每月执行",
        ])
        self.sched_type_combo.currentTextChanged.connect(self._on_schedule_type_changed)

        # Schedule options stack
        self.sched_options_stack = QtWidgets.QStackedWidget()

        # 日期时间选择器样式 - 暗黑主题可见
        datetime_style = """
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

        # ONCE options
        once_widget = QtWidgets.QWidget()
        once_widget.setFixedHeight(32)  # 固定高度，防止撑大
        once_layout = QtWidgets.QHBoxLayout(once_widget)
        once_layout.setContentsMargins(0, 0, 0, 0)
        once_layout.setAlignment(QtCore.Qt.AlignVCenter)  # 垂直居中
        self.sched_once_datetime = QtWidgets.QDateTimeEdit()
        self.sched_once_datetime.setDateTime(QtCore.QDateTime.currentDateTime().addSecs(3600))
        self.sched_once_datetime.setCalendarPopup(True)
        self.sched_once_datetime.setStyleSheet(datetime_style)
        self.sched_once_datetime.setFixedHeight(28)  # 限制高度
        once_layout.addWidget(QtWidgets.QLabel("执行时间:"))
        once_layout.addWidget(self.sched_once_datetime)
        once_layout.addStretch()

        # INTERVAL options
        interval_widget = QtWidgets.QWidget()
        interval_layout = QtWidgets.QHBoxLayout(interval_widget)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        self.sched_interval_value = NoWheelSpinBox()
        self.sched_interval_value.setRange(1, 10080)  # 1 min to 1 week
        self.sched_interval_value.setValue(60)
        self.sched_interval_unit = NoWheelComboBox()
        self.sched_interval_unit.addItems(["分钟", "小时", "天"])
        interval_layout.addWidget(QtWidgets.QLabel("每隔:"))
        interval_layout.addWidget(self.sched_interval_value)
        interval_layout.addWidget(self.sched_interval_unit)
        interval_layout.addStretch()

        # DAILY options
        daily_widget = QtWidgets.QWidget()
        daily_layout = QtWidgets.QHBoxLayout(daily_widget)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        self.sched_daily_time = QtWidgets.QTimeEdit()
        self.sched_daily_time.setTime(QtCore.QTime(9, 0))
        daily_layout.addWidget(QtWidgets.QLabel("每天:"))
        daily_layout.addWidget(self.sched_daily_time)
        daily_layout.addStretch()

        # WEEKLY options
        weekly_widget = QtWidgets.QWidget()
        weekly_layout = QtWidgets.QVBoxLayout(weekly_widget)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        weekly_days_layout = QtWidgets.QHBoxLayout()
        self.sched_weekly_days = []
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i, name in enumerate(day_names):
            cb = QtWidgets.QCheckBox(name)
            if i == 0:  # Monday checked by default
                cb.setChecked(True)
            self.sched_weekly_days.append(cb)
            weekly_days_layout.addWidget(cb)
        weekly_days_layout.addStretch()
        weekly_time_layout = QtWidgets.QHBoxLayout()
        self.sched_weekly_time = QtWidgets.QTimeEdit()
        self.sched_weekly_time.setTime(QtCore.QTime(9, 0))
        weekly_time_layout.addWidget(QtWidgets.QLabel("时间:"))
        weekly_time_layout.addWidget(self.sched_weekly_time)
        weekly_time_layout.addStretch()
        weekly_layout.addLayout(weekly_days_layout)
        weekly_layout.addLayout(weekly_time_layout)

        # MONTHLY options
        monthly_widget = QtWidgets.QWidget()
        monthly_layout = QtWidgets.QHBoxLayout(monthly_widget)
        monthly_layout.setContentsMargins(0, 0, 0, 0)
        self.sched_monthly_day = NoWheelSpinBox()
        self.sched_monthly_day.setRange(1, 31)
        self.sched_monthly_day.setValue(1)
        self.sched_monthly_time = NoWheelTimeEdit()
        self.sched_monthly_time.setTime(QtCore.QTime(9, 0))
        monthly_layout.addWidget(QtWidgets.QLabel("每月:"))
        monthly_layout.addWidget(self.sched_monthly_day)
        monthly_layout.addWidget(QtWidgets.QLabel("日"))
        monthly_layout.addWidget(self.sched_monthly_time)
        monthly_layout.addStretch()

        self.sched_options_stack.addWidget(once_widget)
        self.sched_options_stack.addWidget(interval_widget)
        self.sched_options_stack.addWidget(daily_widget)
        self.sched_options_stack.addWidget(weekly_widget)
        self.sched_options_stack.addWidget(monthly_widget)

        # 设备选择
        device_widget = QtWidgets.QWidget()
        device_layout = QtWidgets.QVBoxLayout(device_widget)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(4)

        self.sched_device_list = QtWidgets.QListWidget()
        self.sched_device_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.sched_device_list.setMinimumHeight(100)
        self.sched_device_list.setMaximumHeight(150)

        sched_device_refresh_btn = QtWidgets.QPushButton("刷新设备")
        sched_device_refresh_btn.setObjectName("secondary")
        sched_device_refresh_btn.setFixedWidth(80)
        sched_device_refresh_btn.setCursor(QtCore.Qt.PointingHandCursor)
        sched_device_refresh_btn.clicked.connect(self._refresh_sched_devices)

        device_layout.addWidget(self.sched_device_list)
        device_layout.addWidget(sched_device_refresh_btn)

        form.addRow("任务名称", self.sched_task_name)
        form.addRow("任务指令", self.sched_task_content)
        form.addRow("执行设备", device_widget)
        form.addRow("调度类型", self.sched_type_combo)
        form.addRow("调度设置", self.sched_options_stack)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.sched_save_btn = QtWidgets.QPushButton("保存任务")
        self.sched_save_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.sched_save_btn.clicked.connect(self._save_scheduled_task)

        self.sched_delete_btn = QtWidgets.QPushButton("删除任务")
        self.sched_delete_btn.setObjectName("danger")
        self.sched_delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.sched_delete_btn.clicked.connect(self._delete_scheduled_task)

        self.sched_run_now_btn = QtWidgets.QPushButton("立即执行")
        self.sched_run_now_btn.setObjectName("success")
        self.sched_run_now_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.sched_run_now_btn.clicked.connect(self._run_scheduled_task_now)

        btn_layout.addWidget(self.sched_save_btn)
        btn_layout.addWidget(self.sched_delete_btn)
        btn_layout.addWidget(self.sched_run_now_btn)
        btn_layout.addStretch()

        editor_layout.addWidget(editor_title)
        editor_layout.addLayout(form)
        editor_layout.addLayout(btn_layout)

        # Log Card
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("card")
        log_layout_v = QtWidgets.QVBoxLayout(log_card)

        log_title = QtWidgets.QLabel("执行日志")
        log_title.setObjectName("cardTitle")

        self.sched_log = QtWidgets.QTextEdit()
        self.sched_log.setReadOnly(True)
        self.sched_log.setMinimumHeight(150)
        self.sched_log.setPlaceholderText("定时任务执行日志将显示在这里...")

        log_layout_v.addWidget(log_title)
        log_layout_v.addWidget(self.sched_log)

        layout.addWidget(header_widget)
        layout.addWidget(list_card)
        layout.addWidget(editor_card)
        layout.addWidget(log_card)

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)

        # Track currently editing task
        self._current_sched_task_id = None

        # Connect list selection
        self.scheduled_task_list.itemSelectionChanged.connect(
            self._on_scheduled_task_selected
        )

        return page

    def _on_schedule_type_changed(self, text):
        """Handle schedule type combo change."""
        # Map text to index
        type_to_index = {
            "单次执行": 0,
            "间隔执行": 1,
            "每日执行": 2,
            "每周执行": 3,
            "每月执行": 4,
        }
        index = type_to_index.get(text, 0)
        self.sched_options_stack.setCurrentIndex(index)

    def _refresh_scheduled_tasks(self):
        """Refresh the scheduled tasks list."""
        self.scheduled_task_list.setRowCount(0)
        tasks = self.scheduled_tasks_manager.get_all_tasks()

        for task in tasks:
            row = self.scheduled_task_list.rowCount()
            self.scheduled_task_list.insertRow(row)

            # Enabled checkbox
            enabled_widget = QtWidgets.QWidget()
            enabled_layout = QtWidgets.QHBoxLayout(enabled_widget)
            enabled_layout.setContentsMargins(5, 0, 5, 0)
            enabled_cb = QtWidgets.QCheckBox()
            enabled_cb.setChecked(task.enabled)
            # 使用 clicked 信号代替 stateChanged，避免 PySide6 的 CheckState 问题
            enabled_cb.clicked.connect(
                lambda checked, tid=task.id: self._toggle_scheduled_task(tid, checked)
            )
            enabled_layout.addWidget(enabled_cb)
            enabled_layout.setAlignment(QtCore.Qt.AlignCenter)
            self.scheduled_task_list.setCellWidget(row, 0, enabled_widget)

            # Name
            name_item = QtWidgets.QTableWidgetItem(task.name or "未命名")
            name_item.setData(QtCore.Qt.UserRole, task.id)
            self.scheduled_task_list.setItem(row, 1, name_item)

            # Devices - 执行设备
            task_devices = getattr(task, 'devices', []) or []
            if task_devices:
                if len(task_devices) == 1:
                    device_text = task_devices[0][:12] + "..." if len(task_devices[0]) > 12 else task_devices[0]
                else:
                    device_text = f"{len(task_devices)} 个设备"
            else:
                device_text = "未指定"
            device_item = QtWidgets.QTableWidgetItem(device_text)
            device_item.setToolTip("\n".join(task_devices) if task_devices else "未指定执行设备")
            self.scheduled_task_list.setItem(row, 2, device_item)

            # Schedule type
            type_names = {
                "once": "单次",
                "interval": "间隔",
                "daily": "每日",
                "weekly": "每周",
                "monthly": "每月",
            }
            type_item = QtWidgets.QTableWidgetItem(
                type_names.get(task.schedule_type, task.schedule_type)
            )
            self.scheduled_task_list.setItem(row, 3, type_item)

            # Next run with countdown
            if task.next_run and task.enabled:
                try:
                    from datetime import datetime
                    next_dt = datetime.fromisoformat(task.next_run)
                    next_str = next_dt.strftime("%m-%d %H:%M")
                    # Calculate countdown
                    now = datetime.now()
                    if next_dt > now:
                        delta = next_dt - now
                        total_seconds = int(delta.total_seconds())
                        if total_seconds < 60:
                            countdown = f"{total_seconds}秒"
                        elif total_seconds < 3600:
                            minutes = total_seconds // 60
                            countdown = f"{minutes}分钟"
                        elif total_seconds < 86400:
                            hours = total_seconds // 3600
                            minutes = (total_seconds % 3600) // 60
                            countdown = f"{hours}小时{minutes}分"
                        else:
                            days = total_seconds // 86400
                            hours = (total_seconds % 86400) // 3600
                            countdown = f"{days}天{hours}小时"
                        next_str = f"{next_str} ({countdown})"
                except Exception:
                    next_str = "-"
            else:
                next_str = "-"
            next_item = QtWidgets.QTableWidgetItem(next_str)
            self.scheduled_task_list.setItem(row, 4, next_item)

            # Run count
            count_item = QtWidgets.QTableWidgetItem(str(task.run_count))
            self.scheduled_task_list.setItem(row, 5, count_item)

            # Actions - 使用紧凑按钮样式
            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(4)

            # 按钮紧凑样式
            btn_style = """
                QPushButton {
                    padding: 2px 8px;
                    font-size: px;
                    min-height: 16px;
                    max-height: 22px;
                }
            """

            run_btn = QtWidgets.QPushButton("执行")
            run_btn.setFixedWidth(42)
            run_btn.setStyleSheet(btn_style)
            run_btn.setObjectName("secondary")
            run_btn.setToolTip("立即执行此任务")
            run_btn.setCursor(QtCore.Qt.PointingHandCursor)
            run_btn.clicked.connect(lambda _, tid=task.id: self._run_task_by_id(tid))

            edit_btn = QtWidgets.QPushButton("编辑")
            edit_btn.setFixedWidth(42)
            edit_btn.setStyleSheet(btn_style)
            edit_btn.setObjectName("secondary")
            edit_btn.setToolTip("编辑任务配置")
            edit_btn.setCursor(QtCore.Qt.PointingHandCursor)
            edit_btn.clicked.connect(lambda _, tid=task.id: self._edit_scheduled_task(tid))

            actions_layout.addWidget(run_btn)
            actions_layout.addWidget(edit_btn)
            actions_layout.addStretch()
            self.scheduled_task_list.setCellWidget(row, 6, actions_widget)

    def _add_scheduled_task(self):
        """Add a new scheduled task."""
        self._current_sched_task_id = None
        self.sched_task_name.clear()
        self.sched_task_content.clear()
        self.sched_type_combo.setCurrentIndex(2)  # Daily by default
        self.sched_daily_time.setTime(QtCore.QTime(9, 0))
        self.sched_device_list.clearSelection()  # 清除设备选择
        self._refresh_sched_devices()  # 刷新设备列表
        self._append_sched_log("新建定时任务，请填写配置后保存。\n")

    def _refresh_sched_devices(self):
        """刷新定时任务的设备列表"""
        self.sched_device_list.clear()
        device_type = self._current_device_type()

        if device_type == DeviceType.IOS:
            devices = list_ios_devices()
            for device in devices:
                name = device.device_name or device.device_id
                item = QtWidgets.QListWidgetItem(f"{name}")
                item.setData(QtCore.Qt.UserRole, (device.device_id, device_type))
                self.sched_device_list.addItem(item)
        else:
            set_device_type(device_type)
            factory = get_device_factory()
            devices = factory.list_devices()
            for device in devices:
                name = device.model or device.device_id
                item = QtWidgets.QListWidgetItem(f"{name} ({device.device_id[:15]}...)")
                item.setData(QtCore.Qt.UserRole, (device.device_id, device_type))
                self.sched_device_list.addItem(item)

        if self.sched_device_list.count() == 0:
            self.sched_device_list.addItem("没有可用设备")

    def _save_scheduled_task(self):
        """Save the current scheduled task."""
        name = self.sched_task_name.text().strip()
        content = self.sched_task_content.toPlainText().strip()

        if not name:
            self._append_sched_log("请输入任务名称。\n")
            return
        if not content:
            self._append_sched_log("请输入任务指令。\n")
            return

        schedule_types = ["once", "interval", "daily", "weekly", "monthly"]
        schedule_type = schedule_types[self.sched_type_combo.currentIndex()]

        if self._current_sched_task_id:
            task = self.scheduled_tasks_manager.get_task(self._current_sched_task_id)
            if not task:
                task = ScheduledTask()
        else:
            task = ScheduledTask()

        task.name = name
        task.task_content = content
        task.schedule_type = schedule_type

        # Set schedule-specific options
        if schedule_type == "once":
            task.run_at = self.sched_once_datetime.dateTime().toPython().isoformat()
        elif schedule_type == "interval":
            value = self.sched_interval_value.value()
            unit = self.sched_interval_unit.currentIndex()
            if unit == 1:  # hours
                value *= 60
            elif unit == 2:  # days
                value *= 60 * 24
            task.interval_minutes = value
        elif schedule_type == "daily":
            task.daily_time = self.sched_daily_time.time().toString("HH:mm")
        elif schedule_type == "weekly":
            task.weekly_days = [
                i for i, cb in enumerate(self.sched_weekly_days) if cb.isChecked()
            ]
            task.weekly_time = self.sched_weekly_time.time().toString("HH:mm")
        elif schedule_type == "monthly":
            task.monthly_day = self.sched_monthly_day.value()
            task.monthly_time = self.sched_monthly_time.time().toString("HH:mm")

        # 保存选中的设备列表
        selected_devices = []
        for item in self.sched_device_list.selectedItems():
            data = item.data(QtCore.Qt.UserRole)
            if data:
                selected_devices.append(data[0])  # 只保存 device_id
        task.devices = selected_devices if selected_devices else []

        if self._current_sched_task_id:
            self.scheduled_tasks_manager.update_task(task)
            self._append_sched_log(f"任务 [{name}] 已更新。\n")
        else:
            self.scheduled_tasks_manager.add_task(task)
            self._current_sched_task_id = task.id
            self._append_sched_log(f"任务 [{name}] 已创建。\n")

        self._refresh_scheduled_tasks()

    def _delete_scheduled_task(self):
        """Delete the selected scheduled task."""
        if not self._current_sched_task_id:
            self._append_sched_log("请先选择一个任务。\n")
            return

        task = self.scheduled_tasks_manager.get_task(self._current_sched_task_id)
        if task:
            reply = QtWidgets.QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除任务 [{task.name}] 吗？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self.scheduled_tasks_manager.delete_task(self._current_sched_task_id)
                self._current_sched_task_id = None
                self.sched_task_name.clear()
                self.sched_task_content.clear()
                self._append_sched_log(f"任务 [{task.name}] 已删除。\n")
                self._refresh_scheduled_tasks()

    def _run_scheduled_task_now(self):
        """Run the selected task immediately."""
        if self._current_sched_task_id:
            self._run_task_by_id(self._current_sched_task_id)

    def _run_task_by_id(self, task_id):
        """Run a task by its ID."""
        self.scheduled_tasks_manager.run_task_now(task_id)
        self._refresh_scheduled_tasks()

    def _toggle_scheduled_task(self, task_id, enabled):
        """Toggle a task's enabled state."""
        self.scheduled_tasks_manager.set_task_enabled(task_id, enabled)
        self._refresh_scheduled_tasks()

    def _edit_scheduled_task(self, task_id):
        """Load a task into the editor."""
        task = self.scheduled_tasks_manager.get_task(task_id)
        if not task:
            return

        self._current_sched_task_id = task_id
        self.sched_task_name.setText(task.name)
        self.sched_task_content.setText(task.task_content)

        type_index = {
            "once": 0, "interval": 1, "daily": 2, "weekly": 3, "monthly": 4
        }.get(task.schedule_type, 2)
        self.sched_type_combo.setCurrentIndex(type_index)

        if task.schedule_type == "once" and task.run_at:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(task.run_at)
                self.sched_once_datetime.setDateTime(
                    QtCore.QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute)
                )
            except Exception:
                pass
        elif task.schedule_type == "interval":
            mins = task.interval_minutes
            if mins >= 1440 and mins % 1440 == 0:
                self.sched_interval_value.setValue(mins // 1440)
                self.sched_interval_unit.setCurrentIndex(2)
            elif mins >= 60 and mins % 60 == 0:
                self.sched_interval_value.setValue(mins // 60)
                self.sched_interval_unit.setCurrentIndex(1)
            else:
                self.sched_interval_value.setValue(mins)
                self.sched_interval_unit.setCurrentIndex(0)
        elif task.schedule_type == "daily":
            h, m = map(int, task.daily_time.split(":"))
            self.sched_daily_time.setTime(QtCore.QTime(h, m))
        elif task.schedule_type == "weekly":
            for i, cb in enumerate(self.sched_weekly_days):
                cb.setChecked(i in task.weekly_days)
            h, m = map(int, task.weekly_time.split(":"))
            self.sched_weekly_time.setTime(QtCore.QTime(h, m))
        elif task.schedule_type == "monthly":
            self.sched_monthly_day.setValue(task.monthly_day)
            h, m = map(int, task.monthly_time.split(":"))
            self.sched_monthly_time.setTime(QtCore.QTime(h, m))

        # 加载设备选择
        self._refresh_sched_devices()
        task_devices = getattr(task, 'devices', []) or []
        for i in range(self.sched_device_list.count()):
            item = self.sched_device_list.item(i)
            data = item.data(QtCore.Qt.UserRole)
            if data and data[0] in task_devices:
                item.setSelected(True)

    def _on_scheduled_task_selected(self):
        """Handle task list selection."""
        selected = self.scheduled_task_list.selectedItems()
        if selected:
            for item in selected:
                task_id = item.data(QtCore.Qt.UserRole)
                if task_id:
                    self._edit_scheduled_task(task_id)
                    break

    def _on_scheduled_task_triggered(self, task_id, task_content):
        """Handle when a scheduled task is triggered."""
        task = self.scheduled_tasks_manager.get_task(task_id)
        task_name = task.name if task else task_id

        self._append_sched_log(f"⏰ 定时任务触发: [{task_name}]\n")
        self._append_log(f"⏰ 定时任务触发: [{task_name}]\n")

        # Execute the task
        self._execute_scheduled_task(task_id, task_content)
        self._refresh_scheduled_tasks()

    def _execute_scheduled_task(self, task_id, task_content):
        """Execute a scheduled task content."""
        task = self.scheduled_tasks_manager.get_task(task_id)

        # Get active model service config
        active_service = self.model_services_manager.get_active_service()
        if not active_service:
            self._append_sched_log("没有激活的模型服务，无法执行定时任务。\n")
            self.scheduled_tasks_manager.mark_task_finished(task_id)
            return

        device_type = self._current_device_type()

        # 获取任务配置的设备列表
        task_devices = getattr(task, 'devices', []) if task else []

        if task_devices and len(task_devices) > 0:
            # 多设备执行
            self._append_sched_log(f"执行设备: {len(task_devices)} 个\n")

            # 准备设备列表和解锁
            devices = []
            self._sched_devices_to_relock = []

            from phone_agent.adb.unlock import ensure_device_unlocked, is_device_locked
            for device_id in task_devices:
                devices.append((device_id, device_type))
                if device_type == DeviceType.ADB:
                    self._append_sched_log(f"检查设备 {device_id} 锁屏状态...\n")
                    was_locked = is_device_locked(device_id)
                    if was_locked:
                        self._sched_devices_to_relock.append(device_id)
                    success, message = ensure_device_unlocked(device_id)
                    self._append_sched_log(f"  {'✓' if success else '⚠'} {message}\n")

            config = {
                "base_url": active_service.base_url,
                "model": active_service.model_name,
                "api_key": active_service.api_key,
                "max_steps": self.max_steps_input.value(),
                "lang": self.lang_combo.currentText(),
                "wda_url": None,
            }

            # 保存任务 ID 用于完成回调
            self._sched_multi_task_id = task_id

            # 使用多设备管理器执行
            self.multi_device_manager.all_finished.disconnect()  # 断开之前的连接
            self.multi_device_manager.all_finished.connect(self._on_sched_multi_task_finished)
            self.multi_device_manager.device_log.connect(lambda dev, msg: self._append_sched_log(f"[{dev[:10]}] {msg}"))
            self.multi_device_manager.start_tasks(devices, task_content, config)
        else:
            # 单设备执行（使用默认设备）
            device_id = self.device_id_input.text().strip()
            if not device_id:
                self._append_sched_log("没有配置执行设备，请在任务配置中选择设备或设置默认设备。\n")
                self.scheduled_tasks_manager.mark_task_finished(task_id)
                return

            self._append_sched_log(f"执行设备: {device_id}\n")

            # 检查并解锁设备
            sched_device_was_locked = False
            if device_type == DeviceType.ADB:
                from phone_agent.adb.unlock import ensure_device_unlocked, is_device_locked
                self._append_sched_log(f"检查设备锁屏状态...\n")
                sched_device_was_locked = is_device_locked(device_id)
                success, message = ensure_device_unlocked(device_id)
                self._append_sched_log(f"  {'✓' if success else '⚠'} {message}\n")

            self._sched_device_was_locked = sched_device_was_locked
            self._sched_device_id = device_id

            self.task_worker = TaskWorker(
                device_type=device_type,
                base_url=active_service.base_url,
                model=active_service.model_name,
                api_key=active_service.api_key,
                max_steps=self.max_steps_input.value(),
                device_id=device_id,
                lang=self.lang_combo.currentText(),
                wda_url=None,
                task=task_content,
                quiet=True,
            )
            self.task_worker.log.connect(lambda msg: self._append_sched_log(msg))
            self.task_worker.finished.connect(
                lambda result: self._on_sched_task_finished(task_id, result)
            )
            self.task_worker.failed.connect(
                lambda msg: self._on_sched_task_failed(task_id, msg)
            )
            self.task_worker.start()

    def _on_sched_task_finished(self, task_id, result):
        """定时任务完成回调"""
        self._append_sched_log(f"任务完成: {result}\n")
        self.scheduled_tasks_manager.mark_task_finished(task_id)
        self._increment_tasks_counter(is_scheduled=True)
        self._restore_sched_device_lock()

        # 发送邮件报告（定时任务-单设备）
        if hasattr(self, '_send_task_report_email'):
            task = self.scheduled_tasks_manager.get_task(task_id)
            task_name = task.name if task else task_id
            log_content = self.sched_log.toPlainText()
            self._send_task_report_email(
                task_name=task_name,
                success_count=1,
                failed_count=0,
                total_count=1,
                details=log_content,
                is_scheduled=True
            )

    def _on_sched_task_failed(self, task_id, msg):
        """定时任务失败回调"""
        self._append_sched_log(f"任务失败: {msg}\n")
        self.scheduled_tasks_manager.mark_task_finished(task_id)
        self._restore_sched_device_lock()

        # 发送失败报告邮件（定时任务-单设备）
        if hasattr(self, '_send_task_report_email'):
            task = self.scheduled_tasks_manager.get_task(task_id)
            task_name = task.name if task else task_id
            log_content = self.sched_log.toPlainText()
            self._send_task_report_email(
                task_name=task_name,
                success_count=0,
                failed_count=1,
                total_count=1,
                details=log_content,
                is_scheduled=True
            )

    def _restore_sched_device_lock(self):
        """恢复定时任务设备的锁屏状态"""
        if hasattr(self, '_sched_device_was_locked') and self._sched_device_was_locked:
            device_id = getattr(self, '_sched_device_id', None)
            if device_id:
                from phone_agent.adb.unlock import lock_screen
                self._append_sched_log(f"恢复设备 {device_id} 锁屏状态...\n")
                if lock_screen(device_id):
                    self._append_sched_log(f"  ✓ 已锁屏\n")
                else:
                    self._append_sched_log(f"  ⚠ 锁屏失败\n")
            self._sched_device_was_locked = False

    def _on_sched_multi_task_finished(self):
        """多设备定时任务完成回调"""
        task_id = getattr(self, '_sched_multi_task_id', None)
        success = 0
        failed = 0
        total = 0

        if task_id:
            success, failed = self.multi_device_manager.get_results_summary()
            total = success + failed
            self._append_sched_log(f"多设备任务完成: {success} 成功, {failed} 失败\n")
            self.scheduled_tasks_manager.mark_task_finished(task_id)
            # Increment counter for each successful device
            for _ in range(success):
                self._increment_tasks_counter(is_scheduled=True)

        # 恢复锁屏
        if hasattr(self, '_sched_devices_to_relock') and self._sched_devices_to_relock:
            from phone_agent.adb.unlock import lock_screen
            for device_id in self._sched_devices_to_relock:
                self._append_sched_log(f"恢复设备 {device_id} 锁屏状态...\n")
                if lock_screen(device_id):
                    self._append_sched_log(f"  ✓ 已锁屏\n")
                else:
                    self._append_sched_log(f"  ⚠ 锁屏失败\n")
            self._sched_devices_to_relock = []

        # 发送邮件报告（定时任务-多设备）
        if task_id and hasattr(self, '_send_task_report_email'):
            task = self.scheduled_tasks_manager.get_task(task_id)
            task_name = task.name if task else task_id
            log_content = self.sched_log.toPlainText()
            self._send_task_report_email(
                task_name=task_name,
                success_count=success,
                failed_count=failed,
                total_count=total,
                details=log_content,
                is_scheduled=True
            )

        # 清理任务 ID
        if task_id:
            self._sched_multi_task_id = None

        # 恢复普通任务的 all_finished 连接
        try:
            self.multi_device_manager.all_finished.disconnect()
        except Exception:
            pass
        self.multi_device_manager.all_finished.connect(self._on_all_tasks_finished)

    def _append_sched_log(self, text):
        """Append text to scheduled tasks log."""
        self.sched_log.moveCursor(QtGui.QTextCursor.End)
        self.sched_log.insertPlainText(text)
        self.sched_log.moveCursor(QtGui.QTextCursor.End)
