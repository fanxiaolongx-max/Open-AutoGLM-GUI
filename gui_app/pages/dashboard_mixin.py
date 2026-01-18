# -*- coding: utf-8 -*-
"""控制台页面 Mixin - 处理控制台/仪表板的所有功能"""

import shutil

from PySide6 import QtCore, QtWidgets


class DashboardMixin:
    """控制台页面的 Mixin 类，包含所有控制台相关的方法"""

    def _build_dashboard(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(18)

        # Header with welcome message
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title = QtWidgets.QLabel("欢迎回来")
        title.setObjectName("title")

        subtitle = QtWidgets.QLabel("这是您的自动化工作区概览")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        # Metrics Grid with enhanced cards
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(16)

        self.metric_device = self._create_enhanced_metric_card(
            "当前设备", "0 台", "已连接设备", "device"
        )
        self.metric_model = self._create_metric_card(
            "AI模型", "-", "使用中的语言模型", "model"
        )
        self.metric_tasks = self._create_enhanced_metric_card(
            "已完成任务", "0", "任务执行统计", "tasks"
        )
        self.metric_status = self._create_enhanced_metric_card(
            "系统状态", "检测中", "系统诊断结果", "status"
        )

        grid.addWidget(self.metric_device, 0, 0)
        grid.addWidget(self.metric_model, 0, 1)
        grid.addWidget(self.metric_tasks, 0, 2)
        grid.addWidget(self.metric_status, 0, 3)

        # Quick Actions Section
        actions_card = QtWidgets.QFrame()
        actions_card.setObjectName("card")
        actions_layout = QtWidgets.QVBoxLayout(actions_card)
        actions_layout.setContentsMargins(20, 16, 20, 16)

        actions_title = QtWidgets.QLabel("快捷操作")
        actions_title.setObjectName("cardTitle")
        actions_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #fafafa; margin-bottom: 12px;")

        # Create a grid layout for better button arrangement
        actions_grid = QtWidgets.QGridLayout()
        actions_grid.setSpacing(12)
        actions_grid.setContentsMargins(0, 8, 0, 0)

        # Define quick actions with correct page indices
        quick_actions = [
            ("新建任务", 3, "primary"),      # 任务执行 (index 3)
            ("设备中心", 1, "primary"),    # 设备中心 (index 1)
            ("模型服务", 2, "primary"),    # 模型服务 (index 2)
            ("定时任务", 4, "primary"),    # 定时任务 (index 4)
            ("系统诊断", 8, "primary"),    # 系统诊断 (index 9)
            ("系统设置", 10, "primary"),   # 系统设置 (index 10)
        ]

        buttons = []
        for i, (text, page_index, btn_type) in enumerate(quick_actions):
            btn = QtWidgets.QPushButton(text)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)

            # Set button style based on type
            if btn_type == "primary":
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #6366f1, stop:1 #4f46e5);
                        color: white;
                        border: none;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #7c3aed, stop:1 #6d28d9);
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #4f46e5, stop:1 #4338ca);
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(63, 63, 70, 0.6);
                        color: #fafafa;
                        border: 1px solid rgba(82, 82, 91, 0.8);
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background: rgba(82, 82, 91, 0.8);
                        border: 1px solid rgba(99, 102, 241, 0.5);
                    }
                    QPushButton:pressed {
                        background: rgba(63, 63, 70, 0.9);
                    }
                """)

            btn.clicked.connect(lambda checked, idx=page_index: self._go_to_page(idx))
            buttons.append(btn)

            # Arrange in 3x2 grid
            row = i // 3
            col = i % 3
            actions_grid.addWidget(btn, row, col)

        actions_layout.addWidget(actions_title)
        actions_layout.addLayout(actions_grid)

        layout.addWidget(header_widget)
        layout.addLayout(grid)
        layout.addWidget(actions_card)
        layout.addStretch()
        return page

    def _go_to_page(self, index):
        self.nav.setCurrentRow(index)

    def _create_metric_card(
        self, label: str, value: str, description: str = "", card_type: str = ""
    ) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setCursor(QtCore.Qt.PointingHandCursor)
        card.setMinimumHeight(120)
        card.setMinimumWidth(200)

        # 卡片整体样式 - 圆角背景
        icon_colors = {
            "device": ("#10b981", "rgba(16, 185, 129, 0.1)"),
            "model": ("#6366f1", "rgba(99, 102, 241, 0.1)"),
            "tasks": ("#f59e0b", "rgba(245, 158, 11, 0.1)"),
            "status": ("#22c55e", "rgba(34, 197, 94, 0.1)"),
        }
        accent_color, bg_tint = icon_colors.get(card_type, ("#6366f1", "rgba(99, 102, 241, 0.1)"))

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

        vbox = QtWidgets.QVBoxLayout(card)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(10)

        # Header row with title and colored icon badge
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(8)

        title = QtWidgets.QLabel(label)
        title.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #d4d4d8; "
            "letter-spacing: 0.3px; background: transparent; border: none;"
        )

        # Colored badge indicator
        badge = QtWidgets.QLabel("●")
        badge.setStyleSheet(
            f"""
            font-size: 12px;
            color: {accent_color};
            background: {bg_tint};
            border-radius: 12px;
            padding: 4px 8px;
            border: none;
            """
        )

        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(badge)

        # Value with accent underline effect
        val = QtWidgets.QLabel(value)
        val.setObjectName("metricValue")
        val.setStyleSheet(
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

        # Description
        desc = QtWidgets.QLabel(description)
        desc.setObjectName("metricLabel")
        desc.setStyleSheet(
            "font-size: 12px; color: #71717a; background: transparent; border: none;"
        )
        desc.setWordWrap(True)

        vbox.addLayout(header_row)
        vbox.addWidget(val)
        vbox.addWidget(desc)
        vbox.addStretch()

        return card

    def _create_enhanced_metric_card(
        self, label: str, value: str, description: str = "", card_type: str = ""
    ) -> QtWidgets.QFrame:
        """Create an enhanced metric card with support for detailed info display."""
        card = QtWidgets.QFrame()
        card.setCursor(QtCore.Qt.PointingHandCursor)
        card.setMinimumHeight(140)
        card.setMinimumWidth(200)

        # 卡片整体样式
        icon_colors = {
            "device": ("#10b981", "rgba(16, 185, 129, 0.1)"),
            "model": ("#6366f1", "rgba(99, 102, 241, 0.1)"),
            "tasks": ("#f59e0b", "rgba(245, 158, 11, 0.1)"),
            "status": ("#22c55e", "rgba(34, 197, 94, 0.1)"),
        }
        accent_color, bg_tint = icon_colors.get(card_type, ("#6366f1", "rgba(99, 102, 241, 0.1)"))

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

        vbox = QtWidgets.QVBoxLayout(card)
        vbox.setContentsMargins(20, 14, 20, 14)
        vbox.setSpacing(6)

        # Header row with title and colored icon badge
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(8)

        title = QtWidgets.QLabel(label)
        title.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #d4d4d8; "
            "letter-spacing: 0.3px; background: transparent; border: none;"
        )

        # Colored badge indicator
        badge = QtWidgets.QLabel("●")
        badge.setObjectName("statusBadge")
        badge.setStyleSheet(
            f"""
            font-size: 12px;
            color: {accent_color};
            background: {bg_tint};
            border-radius: 12px;
            padding: 4px 8px;
            border: none;
            """
        )

        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(badge)

        # Value
        val = QtWidgets.QLabel(value)
        val.setObjectName("metricValue")
        val.setStyleSheet(
            """
            font-size: 24px;
            font-weight: 700;
            color: #fafafa;
            letter-spacing: -0.5px;
            background: transparent;
            border: none;
            padding-left: 2px;
            """
        )

        # Description / subtitle
        desc = QtWidgets.QLabel(description)
        desc.setObjectName("metricLabel")
        desc.setStyleSheet(
            "font-size: 11px; color: #71717a; background: transparent; border: none;"
        )
        desc.setWordWrap(True)

        # Detail info area (for showing device list, task breakdown, etc.)
        detail = QtWidgets.QLabel("")
        detail.setObjectName("metricDetail")
        detail.setStyleSheet(
            "font-size: 11px; color: #a1a1aa; background: transparent; border: none; padding-top: 4px;"
        )
        detail.setWordWrap(True)

        vbox.addLayout(header_row)
        vbox.addWidget(val)
        vbox.addWidget(desc)
        vbox.addWidget(detail)
        vbox.addStretch()

        return card

    def _refresh_dashboard(self):
        """Refresh all dashboard cards with real-time information."""
        # === Update Device Card ===
        try:
            devices = self._get_connected_devices()
            device_count = len(devices)
            device_type = self.device_type_combo.currentText().upper()

            # Update device card value
            for child in self.metric_device.findChildren(QtWidgets.QLabel):
                if child.objectName() == "metricValue":
                    child.setText(f"{device_count} 台")
                    break

            # Update device card detail with device list
            device_detail = ""
            if device_count > 0:
                device_names = [d.get('id', '')[:12] for d in devices[:3]]  # Show first 3 devices
                device_detail = f"{device_type}: " + ", ".join(device_names)
                if device_count > 3:
                    device_detail += f" (+{device_count - 3})"
            else:
                device_detail = f"{device_type}: 无设备连接"

            for child in self.metric_device.findChildren(QtWidgets.QLabel):
                if child.objectName() == "metricDetail":
                    child.setText(device_detail)
                    break

            # Update device card badge color based on connection status
            badge_color = "#10b981" if device_count > 0 else "#71717a"
            for child in self.metric_device.findChildren(QtWidgets.QLabel):
                if child.objectName() == "statusBadge":
                    child.setStyleSheet(f"""
                        font-size: 12px;
                        color: {badge_color};
                        background: rgba(16, 185, 129, 0.1);
                        border-radius: 12px;
                        padding: 4px 8px;
                        border: none;
                    """)
                    break
        except Exception:
            pass

        # === Update Model Card ===
        active_service = self.model_services_manager.get_active_service()
        model_name = active_service.model_name if active_service else "-"
        for child in self.metric_model.findChildren(QtWidgets.QLabel):
            if child.objectName() == "metricValue":
                child.setText(model_name or "-")
                break

        # === Update Tasks Card ===
        total_tasks = self.manual_tasks_count + self.scheduled_tasks_count
        for child in self.metric_tasks.findChildren(QtWidgets.QLabel):
            if child.objectName() == "metricValue":
                child.setText(str(total_tasks))
                break

        # Update tasks detail with breakdown
        tasks_detail = f"手动: {self.manual_tasks_count} | 定时: {self.scheduled_tasks_count}"
        for child in self.metric_tasks.findChildren(QtWidgets.QLabel):
            if child.objectName() == "metricDetail":
                child.setText(tasks_detail)
                break

        # === Update System Status Card ===
        if self.system_diagnosis_result:
            status_text = self.system_diagnosis_result.get("status", "未知")
            status_detail = self.system_diagnosis_result.get("detail", "")
            status_color = self.system_diagnosis_result.get("color", "#71717a")

            for child in self.metric_status.findChildren(QtWidgets.QLabel):
                if child.objectName() == "metricValue":
                    child.setText(status_text)
                    break

            for child in self.metric_status.findChildren(QtWidgets.QLabel):
                if child.objectName() == "metricDetail":
                    child.setText(status_detail)
                    break

            for child in self.metric_status.findChildren(QtWidgets.QLabel):
                if child.objectName() == "statusBadge":
                    child.setStyleSheet(f"""
                        font-size: 12px;
                        color: {status_color};
                        background: rgba(34, 197, 94, 0.1);
                        border-radius: 12px;
                        padding: 4px 8px;
                        border: none;
                    """)
                    break

    def _run_quick_diagnosis(self):
        """Run a quick system diagnosis and update the dashboard status card."""
        issues = []
        checks_passed = 0
        total_checks = 0

        # Check 1: ADB/HDC availability
        total_checks += 1
        device_type = self.device_type_combo.currentText().lower()
        if device_type == "adb":
            adb_path = shutil.which("adb")
            if adb_path:
                checks_passed += 1
            else:
                issues.append("ADB未安装")
        elif device_type == "hdc":
            hdc_path = shutil.which("hdc")
            if hdc_path:
                checks_passed += 1
            else:
                issues.append("HDC未安装")
        else:
            checks_passed += 1  # iOS doesn't need command line tools

        # Check 2: Connected devices
        total_checks += 1
        try:
            devices = self._get_connected_devices()
            if len(devices) > 0:
                checks_passed += 1
            else:
                issues.append("无设备连接")
        except Exception:
            issues.append("设备检测失败")

        # Check 3: Model service configuration
        total_checks += 1
        active_service = self.model_services_manager.get_active_service()
        if active_service and active_service.base_url and active_service.model_name:
            checks_passed += 1
        else:
            issues.append("模型未配置")

        # Determine overall status
        if checks_passed == total_checks:
            status = "正常"
            color = "#22c55e"  # Green
            detail = "所有系统运行正常"
        elif checks_passed >= total_checks - 1:
            status = "警告"
            color = "#f59e0b"  # Yellow
            detail = "; ".join(issues[:2])
        else:
            status = "异常"
            color = "#ef4444"  # Red
            detail = "; ".join(issues[:2])

        self.system_diagnosis_result = {
            "status": status,
            "detail": detail,
            "color": color,
            "checks_passed": checks_passed,
            "total_checks": total_checks
        }

        # Update the dashboard
        self._refresh_dashboard()

    def _increment_tasks_counter(self, is_scheduled: bool = False):
        """Increment the completed tasks counter on the dashboard.

        Args:
            is_scheduled: If True, increment scheduled tasks counter; otherwise manual tasks.
        """
        if is_scheduled:
            self.scheduled_tasks_count += 1
        else:
            self.manual_tasks_count += 1

        # Update the dashboard display
        self._refresh_dashboard()
