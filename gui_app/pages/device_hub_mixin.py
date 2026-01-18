# -*- coding: utf-8 -*-
"""设备中心页面 Mixin - 处理设备管理的所有功能"""

import subprocess

from PySide6 import QtCore, QtGui, QtWidgets

from gui_app.custom_widgets import NoWheelSpinBox
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices


class DeviceHubMixin:
    """设备中心页面的 Mixin 类，包含所有设备管理相关的方法"""

    def _build_device_hub(self):
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
        header_layout.setSpacing(8)

        header = QtWidgets.QLabel("设备中心")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("连接和管理您的安卓设备")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Connection Settings Card
        settings_card = QtWidgets.QFrame()
        settings_card.setObjectName("card")
        settings_layout = QtWidgets.QVBoxLayout(settings_card)
        settings_layout.setSpacing(16)

        settings_title = QtWidgets.QLabel("连接设置")
        settings_title.setObjectName("cardTitle")

        # Basic settings (always visible)
        basic_form = QtWidgets.QFormLayout()
        basic_form.setSpacing(12)
        basic_form.setLabelAlignment(QtCore.Qt.AlignLeft)
        basic_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        from gui_app.custom_widgets import NoWheelComboBox
        self.device_type_combo = NoWheelComboBox()
        self.device_type_combo.addItems(["adb"])
        self.device_type_combo.currentTextChanged.connect(self._refresh_devices)
        self.device_type_combo.currentTextChanged.connect(self._refresh_dashboard)
        self.device_type_combo.currentTextChanged.connect(self._run_quick_diagnosis)

        self.connect_input = QtWidgets.QLineEdit()
        self.connect_input.setPlaceholderText("例如: 192.168.1.100:5555")

        # Wireless pairing inputs (always visible)
        self.pair_address_input = QtWidgets.QLineEdit()
        self.pair_address_input.setPlaceholderText("例如: 192.168.1.100:37000")

        self.pair_code_input = QtWidgets.QLineEdit()
        self.pair_code_input.setPlaceholderText("6位配对码")
        self.pair_code_input.setMaxLength(6)

        basic_form.addRow("设备类型", self.device_type_combo)
        basic_form.addRow("连接地址", self.connect_input)
        basic_form.addRow("配对地址", self.pair_address_input)
        basic_form.addRow("配对码", self.pair_code_input)

        # Advanced settings (hidden by default)
        self.advanced_widget = QtWidgets.QWidget()
        self.advanced_widget.setVisible(False)
        advanced_layout = QtWidgets.QVBoxLayout(self.advanced_widget)
        advanced_layout.setContentsMargins(0, 10, 0, 0)

        advanced_form = QtWidgets.QFormLayout()
        advanced_form.setSpacing(12)
        advanced_form.setLabelAlignment(QtCore.Qt.AlignLeft)
        advanced_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        self.device_id_input = QtWidgets.QLineEdit()
        self.device_id_input.setPlaceholderText("自动检测或指定设备ID")

        self.tcpip_port_input = NoWheelSpinBox()
        self.tcpip_port_input.setRange(1000, 65535)
        self.tcpip_port_input.setValue(5555)

        advanced_form.addRow("设备ID", self.device_id_input)
        advanced_form.addRow("TCP/IP端口", self.tcpip_port_input)

        advanced_layout.addLayout(advanced_form)

        # Advanced toggle button
        self.advanced_btn = QtWidgets.QPushButton("⚙️ 高级配置")
        self.advanced_btn.setObjectName("secondary")
        self.advanced_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.advanced_btn.setCheckable(True)
        self.advanced_btn.toggled.connect(self._toggle_advanced)

        settings_layout.addWidget(settings_title)
        settings_layout.addLayout(basic_form)
        settings_layout.addWidget(self.advanced_btn)
        settings_layout.addWidget(self.advanced_widget)

        # Action Buttons
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(10)

        self.refresh_devices_btn = QtWidgets.QPushButton("🔍 自动检测")
        self.refresh_devices_btn.setObjectName("primary")
        self.refresh_devices_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.refresh_devices_btn.clicked.connect(self._auto_detect_and_clean)

        self.connect_btn = QtWidgets.QPushButton("连接")
        self.connect_btn.setObjectName("success")
        self.connect_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self._connect_device)

        self.disconnect_btn = QtWidgets.QPushButton("断开")
        self.disconnect_btn.setObjectName("danger")
        self.disconnect_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.disconnect_btn.clicked.connect(self._disconnect_device)

        self.tcpip_btn = QtWidgets.QPushButton("启用TCP/IP")
        self.tcpip_btn.setObjectName("secondary")
        self.tcpip_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.tcpip_btn.clicked.connect(self._enable_tcpip)

        self.wireless_pair_btn = QtWidgets.QPushButton("无线配对")
        self.wireless_pair_btn.setObjectName("secondary")
        self.wireless_pair_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.wireless_pair_btn.clicked.connect(self._wireless_pair_device)

        self.qr_pair_btn = QtWidgets.QPushButton("二维码配对")
        self.qr_pair_btn.setObjectName("primary")
        self.qr_pair_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.qr_pair_btn.clicked.connect(self._qr_pair_device)

        buttons.addWidget(self.refresh_devices_btn)
        buttons.addWidget(self.connect_btn)
        buttons.addWidget(self.disconnect_btn)
        buttons.addWidget(self.tcpip_btn)
        buttons.addWidget(self.wireless_pair_btn)
        buttons.addWidget(self.qr_pair_btn)
        buttons.addStretch()

        # Connected Devices List Card
        devices_card = QtWidgets.QFrame()
        devices_card.setObjectName("card")
        devices_layout = QtWidgets.QVBoxLayout(devices_card)

        devices_title = QtWidgets.QLabel("已连接设备（可多选）")
        devices_title.setObjectName("cardTitle")

        self.device_list = QtWidgets.QListWidget()
        self.device_list.setMinimumHeight(150)
        self.device_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.device_list.itemClicked.connect(self._on_device_selected)
        self.device_list.itemDoubleClicked.connect(self._on_device_double_clicked)

        devices_layout.addWidget(devices_title)
        devices_layout.addWidget(self.device_list)

        # PIN Configuration Card
        pin_card = QtWidgets.QFrame()
        pin_card.setObjectName("card")
        pin_layout = QtWidgets.QVBoxLayout(pin_card)

        pin_header = QtWidgets.QHBoxLayout()
        pin_title = QtWidgets.QLabel("设备 PIN 配置")
        pin_title.setObjectName("cardTitle")

        pin_header.addWidget(pin_title)
        pin_header.addStretch()

        pin_desc = QtWidgets.QLabel("为需要 PIN 解锁的设备配置解锁密码（任务执行时自动使用）")
        pin_desc.setStyleSheet("font-size: 12px; color: #71717a;")

        # PIN 配置表单
        pin_form = QtWidgets.QHBoxLayout()
        pin_form.setSpacing(8)

        self.pin_device_combo = QtWidgets.QComboBox()
        self.pin_device_combo.setMinimumWidth(200)
        self.pin_device_combo.setPlaceholderText("选择设备...")

        self.pin_input = QtWidgets.QLineEdit()
        self.pin_input.setPlaceholderText("输入 PIN 码（留空表示无 PIN）")
        self.pin_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.pin_input.setMinimumWidth(150)

        self.pin_show_cb = QtWidgets.QCheckBox("显示")
        self.pin_show_cb.toggled.connect(
            lambda checked: self.pin_input.setEchoMode(
                QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
            )
        )

        self.pin_save_btn = QtWidgets.QPushButton("保存 PIN")
        self.pin_save_btn.setObjectName("secondary")
        self.pin_save_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.pin_save_btn.clicked.connect(self._save_device_pin)

        self.pin_clear_btn = QtWidgets.QPushButton("清除")
        self.pin_clear_btn.setObjectName("secondary")
        self.pin_clear_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.pin_clear_btn.clicked.connect(self._clear_device_pin)

        pin_form.addWidget(QtWidgets.QLabel("设备:"))
        pin_form.addWidget(self.pin_device_combo)
        pin_form.addWidget(QtWidgets.QLabel("PIN:"))
        pin_form.addWidget(self.pin_input)
        pin_form.addWidget(self.pin_show_cb)
        pin_form.addWidget(self.pin_save_btn)
        pin_form.addWidget(self.pin_clear_btn)
        pin_form.addStretch()

        # PIN 状态显示
        self.pin_status = QtWidgets.QLabel("")
        self.pin_status.setStyleSheet("font-size: 11px; color: #71717a;")

        # 加载选中设备的 PIN
        self.pin_device_combo.currentTextChanged.connect(self._load_device_pin)

        pin_layout.addLayout(pin_header)
        pin_layout.addWidget(pin_desc)
        pin_layout.addLayout(pin_form)
        pin_layout.addWidget(self.pin_status)

        # Connection History Card
        history_card = QtWidgets.QFrame()
        history_card.setObjectName("card")
        history_layout = QtWidgets.QVBoxLayout(history_card)

        history_header = QtWidgets.QHBoxLayout()
        history_title = QtWidgets.QLabel("连接历史")
        history_title.setObjectName("cardTitle")

        self.clear_history_btn = QtWidgets.QPushButton("清空")
        self.clear_history_btn.setObjectName("secondary")
        self.clear_history_btn.setFixedWidth(60)
        self.clear_history_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.clear_history_btn.clicked.connect(self._clear_connection_history)

        history_header.addWidget(history_title)
        history_header.addStretch()
        history_header.addWidget(self.clear_history_btn)

        self.connection_history_list = QtWidgets.QListWidget()
        self.connection_history_list.setMinimumHeight(80)
        self.connection_history_list.setMaximumHeight(120)
        self.connection_history_list.itemDoubleClicked.connect(self._use_history_connection)

        history_layout.addLayout(history_header)
        history_layout.addWidget(self.connection_history_list)

        # Connection Status/Log Card
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("card")
        log_layout_v = QtWidgets.QVBoxLayout(log_card)

        log_title = QtWidgets.QLabel("连接日志")
        log_title.setObjectName("cardTitle")

        self.device_connection_status = QtWidgets.QLabel("就绪")
        self.device_connection_status.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 8px 12px; border-radius: 8px;"
        )

        self.device_log = QtWidgets.QPlainTextEdit()
        self.device_log.setReadOnly(True)
        self.device_log.setPlaceholderText("连接操作日志将显示在这里...")
        self.device_log.setMaximumHeight(150)

        log_layout_v.addWidget(log_title)
        log_layout_v.addWidget(self.device_connection_status)
        log_layout_v.addWidget(self.device_log)

        layout.addWidget(header_widget)
        layout.addWidget(settings_card)
        layout.addLayout(buttons)
        layout.addWidget(devices_card)
        layout.addWidget(pin_card)
        layout.addWidget(history_card)
        layout.addWidget(log_card)

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)
        return page

    def _save_device_pin(self):
        """保存设备 PIN"""
        from gui_app.device_pin_manager import get_device_pin_manager

        device_id = self.pin_device_combo.currentText()
        if not device_id:
            self.pin_status.setText("请先选择设备")
            self.pin_status.setStyleSheet("font-size: 11px; color: #ef4444;")
            return

        pin = self.pin_input.text().strip()
        get_device_pin_manager().set_pin(device_id, pin)

        if pin:
            self.pin_status.setText(f"✓ 设备 {device_id[:20]}... 的 PIN 已保存")
            self.pin_status.setStyleSheet("font-size: 11px; color: #10b981;")
        else:
            self.pin_status.setText(f"✓ 设备 {device_id[:20]}... 的 PIN 已清除")
            self.pin_status.setStyleSheet("font-size: 11px; color: #71717a;")

    def _clear_device_pin(self):
        """清除设备 PIN"""
        from gui_app.device_pin_manager import get_device_pin_manager

        device_id = self.pin_device_combo.currentText()
        if not device_id:
            return

        get_device_pin_manager().remove_pin(device_id)
        self.pin_input.clear()
        self.pin_status.setText(f"✓ 设备 {device_id[:20]}... 的 PIN 已清除")
        self.pin_status.setStyleSheet("font-size: 11px; color: #71717a;")

    def _load_device_pin(self, device_id: str):
        """加载设备已配置的 PIN"""
        if not device_id:
            self.pin_input.clear()
            self.pin_status.setText("")
            return

        from gui_app.device_pin_manager import get_device_pin_manager
        pin = get_device_pin_manager().get_pin(device_id)

        if pin:
            self.pin_input.setText(pin)
            self.pin_status.setText("此设备已配置 PIN")
            self.pin_status.setStyleSheet("font-size: 11px; color: #6366f1;")
        else:
            self.pin_input.clear()
            self.pin_status.setText("此设备未配置 PIN（无需 PIN 或滑动解锁）")
            self.pin_status.setStyleSheet("font-size: 11px; color: #71717a;")

    def _refresh_pin_device_combo(self):
        """刷新 PIN 配置的设备下拉框"""
        current = self.pin_device_combo.currentText()
        self.pin_device_combo.clear()

        # 从设备列表获取设备
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            data = item.data(QtCore.Qt.UserRole)
            if data:
                device_id = data[0] if isinstance(data, tuple) else data
                self.pin_device_combo.addItem(device_id)

        # 恢复之前的选择
        if current:
            index = self.pin_device_combo.findText(current)
            if index >= 0:
                self.pin_device_combo.setCurrentIndex(index)

    def _request_pin_dialog(self, device_id: str) -> str:
        """弹出对话框请求用户输入 PIN"""
        from gui_app.device_pin_manager import get_device_pin_manager

        pin, ok = QtWidgets.QInputDialog.getText(
            self,
            "需要 PIN 解锁",
            f"设备 {device_id[:30]}... 需要 PIN 解锁\n请输入 PIN 码：",
            QtWidgets.QLineEdit.Password
        )

        if ok and pin:
            # 询问是否保存 PIN
            save = QtWidgets.QMessageBox.question(
                self,
                "保存 PIN",
                "是否保存此 PIN 到设备配置？\n下次将自动使用此 PIN 解锁。",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            if save == QtWidgets.QMessageBox.Yes:
                get_device_pin_manager().set_pin(device_id, pin)

            return pin

        return None

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
            device_count = self._refresh_devices()

            # Check if any devices found (use actual device count, not list item count)
            if device_count > 0:
                self._append_device_log(f"[{self._timestamp()}] ✅ 检测到 {device_count} 个设备\n")
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
        """Refresh device list and return actual device count."""
        device_type = self._current_device_type()
        self.device_list.clear()
        device_count = 0

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
                    device_count = len(devices)
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
                    return 0

                devices = factory.list_devices()
                if not devices:
                    self.device_list.addItem("没有设备连接。")
                    self._update_device_status("未发现设备", "warning")
                else:
                    device_count = len(devices)
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

        return device_count

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
