# -*- coding: utf-8 -*-
"""应用安装页面 Mixin - 处理APK安装的所有功能"""

from PySide6 import QtCore, QtGui, QtWidgets

from gui_app.components import DropZoneWidget, ApkInstallWorker


class ApkInstallerMixin:
    """应用安装页面的 Mixin 类，包含所有APK安装相关的方法"""

    def _build_apk_installer(self):
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

        header = QtWidgets.QLabel("应用安装")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("拖拽APK文件自动安装到已连接的设备")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Device Selection Card
        device_card = QtWidgets.QFrame()
        device_card.setObjectName("card")
        device_layout = QtWidgets.QVBoxLayout(device_card)
        device_layout.setContentsMargins(20, 20, 20, 20)

        device_title = QtWidgets.QLabel("目标设备选择（可多选）")
        device_title.setObjectName("cardTitle")

        # Device selection list (multi-select)
        self.apk_device_list = QtWidgets.QListWidget()
        self.apk_device_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.apk_device_list.setMinimumHeight(100)
        self.apk_device_list.setMaximumHeight(150)
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

        # Refresh button
        refresh_apk_devices_btn = QtWidgets.QPushButton("刷新设备列表")
        refresh_apk_devices_btn.setObjectName("secondary")
        refresh_apk_devices_btn.setCursor(QtCore.Qt.PointingHandCursor)
        refresh_apk_devices_btn.clicked.connect(self._refresh_apk_devices)

        device_layout.addWidget(device_title)
        device_layout.addWidget(self.apk_device_list)
        device_layout.addWidget(refresh_apk_devices_btn)

        # Drop Zone Card
        drop_card = QtWidgets.QFrame()
        drop_card.setObjectName("card")
        drop_layout = QtWidgets.QVBoxLayout(drop_card)
        drop_layout.setContentsMargins(20, 20, 20, 20)

        self.apk_drop_zone = DropZoneWidget()
        self.apk_drop_zone.setText("📱 拖拽APK文件到此处安装\n\n支持 .apk 格式")
        self.apk_drop_zone.setMinimumHeight(180)
        self.apk_drop_zone.fileDropped.connect(self._install_apk)

        drop_layout.addWidget(self.apk_drop_zone)

        # Status layout
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.setSpacing(12)

        self.apk_install_status = QtWidgets.QLabel("就绪 - 拖拽APK文件到上方区域安装")
        self.apk_install_status.setStyleSheet(
            "font-size: 13px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 8px 16px; border-radius: 8px;"
        )

        status_layout.addWidget(self.apk_install_status)
        status_layout.addStretch()

        # Progress Bar
        self.apk_progress = QtWidgets.QProgressBar()
        self.apk_progress.setRange(0, 100)
        self.apk_progress.setValue(0)
        self.apk_progress.setVisible(False)
        self.apk_progress.setStyleSheet(
            """
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
            """
        )

        # Install Log Card
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("card")
        log_layout = QtWidgets.QVBoxLayout(log_card)

        log_title = QtWidgets.QLabel("安装日志")
        log_title.setObjectName("cardTitle")

        self.apk_install_log = QtWidgets.QPlainTextEdit()
        self.apk_install_log.setReadOnly(True)
        self.apk_install_log.setPlaceholderText("安装日志将显示在这里...")
        self.apk_install_log.setMaximumHeight(200)

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.apk_install_log)

        # Install History Card
        history_card = QtWidgets.QFrame()
        history_card.setObjectName("card")
        history_layout = QtWidgets.QVBoxLayout(history_card)

        history_title = QtWidgets.QLabel("安装历史")
        history_title.setObjectName("cardTitle")

        self.apk_history_list = QtWidgets.QListWidget()
        self.apk_history_list.setMaximumHeight(150)

        history_layout.addWidget(history_title)
        history_layout.addWidget(self.apk_history_list)

        layout.addWidget(header_widget)
        layout.addWidget(device_card)
        layout.addWidget(drop_card)
        layout.addLayout(status_layout)
        layout.addWidget(self.apk_progress)
        layout.addWidget(log_card)
        layout.addWidget(history_card)
        layout.addStretch()

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)
        return page

    def _install_apk(self, file_path):
        """安装APK文件到选中的设备（支持多设备）"""
        try:
            self._append_apk_log("🔧 开始APK安装流程...\n")

            if hasattr(self, 'apk_install_workers') and self.apk_install_workers:
                # Check if any worker is still running
                running = [d for d, w in self.apk_install_workers.items() if w.isRunning()]
                if running:
                    self._append_apk_log(f"⏳ 正在安装中（{len(running)}个设备），请等待...\n")
                    return

            device_type = self._current_device_type()
            self._append_apk_log(f"📱 设备类型: {device_type}\n")

            # Get selected devices (supports multi-select)
            device_ids = self._get_apk_selected_device_ids()

            if not device_ids:
                self._append_apk_log("❌ 未选择设备，请先在上方选择目标设备\n")
                return

            self._append_apk_log(f"🎯 目标设备 ({len(device_ids)}个): {', '.join(device_ids)}\n")
            self._append_apk_log("─" * 40 + "\n")

            self.apk_install_log.clear()
            self.apk_progress.setValue(0)
            self.apk_progress.setVisible(True)
            self.apk_install_status.setText(f"安装中... (0/{len(device_ids)})")
            self.apk_drop_zone.setEnabled(False)

            # Track installation progress
            self.apk_install_workers = {}
            self.apk_install_results = {}
            self.apk_install_total = len(device_ids)
            self.apk_install_completed = 0

            # Start installation for each selected device
            for device_id in device_ids:
                self._append_apk_log(f"🔨 正在为设备 {device_id} 创建安装任务...\n")
                worker = ApkInstallWorker(file_path, device_type, device_id)
                worker.log.connect(lambda msg, dev=device_id: self._append_apk_log(f"[{dev}] {msg}"))
                worker.progress.connect(lambda p: self._update_apk_multi_progress())
                worker.finished.connect(lambda ok, msg, dev=device_id: self._apk_install_device_finished(dev, ok, msg))
                self.apk_install_workers[device_id] = worker
                worker.start()

            self._append_apk_log(f"🚀 已启动 {len(device_ids)} 个设备的安装任务\n")

        except Exception as e:
            self._append_apk_log(f"💥 APK安装流程发生错误: {type(e).__name__}: {str(e)}\n")
            import traceback
            self._append_apk_log(f"📋 错误详情:\n{traceback.format_exc()}\n")

            # 恢复界面状态
            try:
                self.apk_install_status.setText("安装失败")
                self.apk_drop_zone.setEnabled(True)
                self.apk_progress.setVisible(False)
            except:
                pass

    def _update_apk_multi_progress(self):
        """Update progress bar for multi-device installation."""
        if not hasattr(self, 'apk_install_total') or self.apk_install_total == 0:
            return
        progress = int((self.apk_install_completed / self.apk_install_total) * 100)
        self.apk_progress.setValue(progress)

    def _apk_install_device_finished(self, device_id, success, message):
        """Handle completion of APK installation on a single device."""
        self.apk_install_completed += 1
        self.apk_install_results[device_id] = {'success': success, 'message': message}

        status_icon = "✅" if success else "❌"
        self._append_apk_log(f"{status_icon} [{device_id}] {'安装成功' if success else '安装失败'}: {message}\n")

        # Update status
        self.apk_install_status.setText(f"安装中... ({self.apk_install_completed}/{self.apk_install_total})")
        self._update_apk_multi_progress()

        # Check if all installations are complete
        if self.apk_install_completed >= self.apk_install_total:
            self._apk_install_all_finished()

    def _get_apk_selected_device_ids(self):
        """Get the selected device IDs from APK page device list (supports multi-select)."""
        device_ids = []
        try:
            if hasattr(self, 'apk_device_list') and self.apk_device_list is not None:
                selected_items = self.apk_device_list.selectedItems()
                for item in selected_items:
                    device_id = item.data(QtCore.Qt.UserRole)
                    if device_id:
                        device_ids.append(device_id)
        except Exception as e:
            self._append_apk_log(f"⚠️ APK设备选择获取失败: {str(e)}\n")

        # Fallback to main device list selection if no devices selected
        if not device_ids:
            fallback_id = self._get_selected_device_id()
            if fallback_id:
                device_ids.append(fallback_id)

        return device_ids

    def _refresh_apk_devices(self):
        """Refresh the APK device selection list."""
        if not hasattr(self, 'apk_device_list') or self.apk_device_list is None:
            return

        try:
            self.apk_device_list.clear()

            # Get current devices
            devices = self._get_connected_devices()

            if not devices:
                item = QtWidgets.QListWidgetItem("未检测到设备")
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.apk_device_list.addItem(item)
                return

            # Add devices to list
            for device in devices:
                device_id = device.get('id', '')
                device_name = device.get('name', device_id)
                device_type = device.get('type', 'Unknown')

                display_text = f"{device_id} | {device_name} ({device_type})"
                item = QtWidgets.QListWidgetItem(display_text)
                item.setData(QtCore.Qt.UserRole, device_id)
                self.apk_device_list.addItem(item)

            # Auto-select first device if any exist
            if self.apk_device_list.count() > 0:
                self.apk_device_list.item(0).setSelected(True)

        except Exception as e:
            print(f"Error refreshing APK devices: {e}")
            try:
                if hasattr(self, 'apk_device_list') and self.apk_device_list is not None:
                    self.apk_device_list.clear()
                    item = QtWidgets.QListWidgetItem("设备刷新失败")
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
                    self.apk_device_list.addItem(item)
            except:
                pass

    def _append_apk_log(self, text):
        self.apk_install_log.moveCursor(QtGui.QTextCursor.End)
        self.apk_install_log.insertPlainText(text)
        self.apk_install_log.moveCursor(QtGui.QTextCursor.End)

        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(text)
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _apk_install_all_finished(self):
        """Handle completion of all APK installations."""
        self.apk_drop_zone.setEnabled(True)
        self.apk_progress.setValue(100)
        self.apk_progress.setVisible(False)

        # Count successes and failures
        successes = sum(1 for r in self.apk_install_results.values() if r['success'])
        failures = len(self.apk_install_results) - successes

        self._append_apk_log("\n" + "═" * 40 + "\n")
        self._append_apk_log(f"📊 安装完成统计:\n")
        self._append_apk_log(f"   ✅ 成功: {successes} 个设备\n")
        self._append_apk_log(f"   ❌ 失败: {failures} 个设备\n")
        self._append_apk_log("═" * 40 + "\n")

        # Update status display
        if failures == 0:
            status_msg = f"全部成功 ({successes}个设备)"
            self.apk_install_status.setText("✓ " + status_msg)
            self.apk_install_status.setStyleSheet(
                "font-size: 13px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 8px 16px; border-radius: 8px;"
            )
        elif successes == 0:
            status_msg = f"全部失败 ({failures}个设备)"
            self.apk_install_status.setText("✗ " + status_msg)
            self.apk_install_status.setStyleSheet(
                "font-size: 13px; color: #ef4444; background: rgba(239, 68, 68, 0.15); "
                "padding: 8px 16px; border-radius: 8px;"
            )
        else:
            status_msg = f"部分成功 (成功{successes}/失败{failures})"
            self.apk_install_status.setText("⚠ " + status_msg)
            self.apk_install_status.setStyleSheet(
                "font-size: 13px; color: #f59e0b; background: rgba(245, 158, 11, 0.15); "
                "padding: 8px 16px; border-radius: 8px;"
            )

        # Add to history
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        history_entry = f"{timestamp} - {status_msg}"
        self.apk_history_list.insertItem(0, history_entry)

        # Clear workers
        self.apk_install_workers = {}

    def _apk_install_finished(self, success, message):
        self.apk_drop_zone.setEnabled(True)
        self.apk_progress.setVisible(False)

        if success:
            self.apk_install_status.setText("✓ " + message)
            self.apk_install_status.setStyleSheet(
                "font-size: 13px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 8px 16px; border-radius: 8px;"
            )
        else:
            self.apk_install_status.setText("✗ " + message)
            self.apk_install_status.setStyleSheet(
                "font-size: 13px; color: #ef4444; background: rgba(239, 68, 68, 0.15); "
                "padding: 8px 16px; border-radius: 8px;"
            )

        # Add to history
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        status_text = "成功" if success else "失败"
        self.apk_history_list.insertItem(0, f"{timestamp} - {status_text}: {message}")

        self._append_apk_log(f"\n{message}\n")
