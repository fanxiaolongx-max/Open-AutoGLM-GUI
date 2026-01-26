# -*- coding: utf-8 -*-
"""Chat UI 组件 - 会话列表、消息气泡、输入区域等"""

import base64
from typing import List, Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets


class SessionListWidget(QtWidgets.QWidget):
    """会话列表组件"""

    session_selected = QtCore.Signal(str)  # session_id
    session_deleted = QtCore.Signal(str)  # session_id
    new_session_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_session_id: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 新建会话按钮
        self.new_btn = QtWidgets.QPushButton("+ 新建对话")
        self.new_btn.setObjectName("success")
        self.new_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_session_requested.emit)
        layout.addWidget(self.new_btn)

        # 会话列表
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)

    def set_sessions(self, sessions: List[Dict]):
        """设置会话列表"""
        self.list_widget.clear()
        for session in sessions:
            item = QtWidgets.QListWidgetItem()
            title = session.get("title", "新对话")[:30] or "新对话"
            device_id = session.get("device_id", "")[:15]
            item.setText(f"{title}\n{device_id}")
            item.setData(QtCore.Qt.UserRole, session.get("id"))
            item.setToolTip(f"ID: {session.get('id')}\n设备: {device_id}\n创建: {session.get('created_at', '')[:19]}")
            self.list_widget.addItem(item)

        # 恢复选中状态
        if self._current_session_id:
            self.select_session(self._current_session_id)

    def select_session(self, session_id: str):
        """选中指定会话"""
        self._current_session_id = session_id
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(QtCore.Qt.UserRole) == session_id:
                self.list_widget.setCurrentItem(item)
                break

    def get_current_session_id(self) -> Optional[str]:
        """获取当前选中的会话 ID"""
        return self._current_session_id

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem):
        session_id = item.data(QtCore.Qt.UserRole)
        if session_id:
            self._current_session_id = session_id
            self.session_selected.emit(session_id)

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return

        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除会话")
        action = menu.exec_(self.list_widget.mapToGlobal(pos))

        if action == delete_action:
            session_id = item.data(QtCore.Qt.UserRole)
            if session_id:
                self.session_deleted.emit(session_id)


class MessageBubble(QtWidgets.QFrame):
    """消息气泡组件"""

    screenshot_clicked = QtCore.Signal(str, bytes)  # screenshot_id, image_data (for cached)

    def __init__(self, message: Dict, parent=None):
        super().__init__(parent)
        self.message = message
        self.message_id = message.get("id", "")
        self._logs_visible = False
        self._screenshot_cache: Dict[str, bytes] = {}  # 缓存截图数据
        self._setup_ui()

    def _setup_ui(self):
        role = self.message.get("role", "user")
        content = self.message.get("content", "")
        status = self.message.get("status")

        # 使用 objectName 来区分，样式由主题控制
        if role == "user":
            self.setObjectName("userBubble")
        else:
            self.setObjectName("assistantBubble")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # 头部：角色 + 状态
        header = QtWidgets.QHBoxLayout()
        role_label = QtWidgets.QLabel("你" if role == "user" else "AI 助手")
        role_label.setObjectName("chatRoleLabel")
        header.addWidget(role_label)
        header.addStretch()

        # 状态指示器
        self.status_label = None
        if role == "assistant":
            self.status_label = QtWidgets.QLabel()
            self._update_status_label(status)
            header.addWidget(self.status_label)

        layout.addLayout(header)

        # 消息内容
        self.content_label = QtWidgets.QLabel(content)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.content_label.setObjectName("chatContentLabel")
        layout.addWidget(self.content_label)

        # TodoList 显示
        todo_list = self.message.get("todo_list")
        if todo_list and isinstance(todo_list, list):
            self._add_todo_list(layout, todo_list)

        # 截图缩略图区域
        screenshots = self.message.get("screenshots", [])
        if screenshots:
            self._add_screenshots(layout, screenshots)

        # 日志展开区
        logs = self.message.get("logs", [])
        if logs:
            self._add_logs_section(layout, logs)

    def _update_status_label(self, status: str):
        """更新状态标签"""
        if not self.status_label:
            return
        if status == "running":
            self.status_label.setText("执行中...")
            self.status_label.setObjectName("status_info")
        elif status == "success":
            self.status_label.setText("已完成")
            self.status_label.setObjectName("status_ok")
        elif status == "error":
            self.status_label.setText("失败")
            self.status_label.setObjectName("status_error")
        else:
            self.status_label.setText("")

    def _add_todo_list(self, layout: QtWidgets.QVBoxLayout, todo_list: List[Dict]):
        """添加 TodoList 显示"""
        self.todo_frame = QtWidgets.QFrame()
        self.todo_frame.setObjectName("todoListFrame")
        todo_layout = QtWidgets.QVBoxLayout(self.todo_frame)
        todo_layout.setContentsMargins(8, 6, 8, 6)
        todo_layout.setSpacing(4)

        self.todo_labels = []
        for item in todo_list[-5:]:  # 只显示最后5步
            step = item.get("step", 0)
            action = item.get("action", "")
            item_status = item.get("status", "pending")

            step_label = QtWidgets.QLabel(f"{'✓' if item_status == 'completed' else '○'} 步骤 {step}: {action}")
            step_label.setObjectName("status_ok" if item_status == "completed" else "chatMutedLabel")
            todo_layout.addWidget(step_label)
            self.todo_labels.append(step_label)

        layout.addWidget(self.todo_frame)

    def _add_screenshots(self, layout: QtWidgets.QVBoxLayout, screenshots: List[Dict]):
        """添加截图缩略图"""
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(100)
        scroll.setObjectName("screenshotScroll")

        self.screenshot_container = QtWidgets.QWidget()
        self.screenshot_layout = QtWidgets.QHBoxLayout(self.screenshot_container)
        self.screenshot_layout.setContentsMargins(0, 0, 0, 0)
        self.screenshot_layout.setSpacing(6)

        for screenshot in screenshots[-6:]:  # 最多显示6张
            self._add_screenshot_thumb(screenshot)

        self.screenshot_layout.addStretch()
        scroll.setWidget(self.screenshot_container)
        layout.addWidget(scroll)

    def _add_screenshot_thumb(self, screenshot: Dict):
        """添加单个截图缩略图"""
        thumb = QtWidgets.QLabel()
        thumb.setFixedSize(60, 80)
        thumb.setObjectName("screenshotThumb")
        thumb.setAlignment(QtCore.Qt.AlignCenter)
        thumb.setCursor(QtCore.Qt.PointingHandCursor)
        thumb.setToolTip(screenshot.get("description", "点击查看大图"))
        thumb.setScaledContents(False)

        screenshot_id = screenshot.get("id", "")

        # 尝试加载图片
        image_data = screenshot.get("image_data")
        if image_data:
            # 如果有直接的图片数据
            if isinstance(image_data, str):
                image_data = base64.b64decode(image_data)
            self._set_thumb_image(thumb, image_data)
            self._screenshot_cache[screenshot_id] = image_data
        else:
            # 显示占位符，等待异步加载
            thumb.setText("📷")

        # 点击事件
        thumb.mousePressEvent = lambda e, sid=screenshot_id: self._on_thumb_clicked(sid)

        # 插入到 stretch 之前
        count = self.screenshot_layout.count()
        if count > 0:
            self.screenshot_layout.insertWidget(count - 1, thumb)
        else:
            self.screenshot_layout.addWidget(thumb)

    def _set_thumb_image(self, thumb: QtWidgets.QLabel, image_data: bytes):
        """设置缩略图图片"""
        pixmap = QtGui.QPixmap()
        if pixmap.loadFromData(image_data):
            scaled = pixmap.scaled(
                58, 78,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            thumb.setPixmap(scaled)

    def _on_thumb_clicked(self, screenshot_id: str):
        """点击缩略图"""
        image_data = self._screenshot_cache.get(screenshot_id)
        self.screenshot_clicked.emit(screenshot_id, image_data if image_data else b"")

    def _add_logs_section(self, layout: QtWidgets.QVBoxLayout, logs: List[Dict]):
        """添加日志展开区"""
        # 展开按钮
        self.logs_toggle_btn = QtWidgets.QPushButton(f"查看日志 ({len(logs)})")
        self.logs_toggle_btn.setObjectName("secondary")
        self.logs_toggle_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.logs_toggle_btn.setMaximumWidth(120)
        self.logs_toggle_btn.clicked.connect(self._toggle_logs)
        layout.addWidget(self.logs_toggle_btn)

        # 日志内容（默认隐藏）
        self.logs_widget = QtWidgets.QPlainTextEdit()
        self.logs_widget.setReadOnly(True)
        self.logs_widget.setMaximumHeight(150)
        self.logs_widget.setObjectName("chatLogsWidget")

        log_text = "\n".join([f"[{log.get('log_type', 'info')}] {log.get('content', '')}" for log in logs])
        self.logs_widget.setPlainText(log_text)
        self.logs_widget.hide()
        layout.addWidget(self.logs_widget)

    def _toggle_logs(self):
        """切换日志显示状态"""
        self._logs_visible = not self._logs_visible
        self.logs_widget.setVisible(self._logs_visible)
        self.logs_toggle_btn.setText("收起日志" if self._logs_visible else "查看日志")

    def update_content(self, content: str):
        """更新消息内容"""
        self.content_label.setText(content)

    def update_status(self, status: str):
        """更新状态"""
        self.message["status"] = status
        self._update_status_label(status)

    def append_log(self, content: str, log_type: str = "info"):
        """追加日志"""
        if not hasattr(self, "logs_widget"):
            # 动态创建日志区域
            self.logs_toggle_btn = QtWidgets.QPushButton("查看日志 (1)")
            self.logs_toggle_btn.setObjectName("secondary")
            self.logs_toggle_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.logs_toggle_btn.setMaximumWidth(120)
            self.logs_toggle_btn.clicked.connect(self._toggle_logs)
            self.layout().addWidget(self.logs_toggle_btn)

            self.logs_widget = QtWidgets.QPlainTextEdit()
            self.logs_widget.setReadOnly(True)
            self.logs_widget.setMaximumHeight(150)
            self.logs_widget.setObjectName("chatLogsWidget")
            self.logs_widget.hide()
            self.layout().addWidget(self.logs_widget)
            self._logs_visible = False

        self.logs_widget.appendPlainText(f"[{log_type}] {content}")
        # 更新按钮文本
        line_count = self.logs_widget.document().blockCount()
        if not self._logs_visible:
            self.logs_toggle_btn.setText(f"查看日志 ({line_count})")

    def add_screenshot(self, screenshot: Dict):
        """动态添加截图"""
        if not hasattr(self, "screenshot_layout"):
            # 动态创建截图区域
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scroll.setMaximumHeight(100)
            scroll.setObjectName("screenshotScroll")

            self.screenshot_container = QtWidgets.QWidget()
            self.screenshot_layout = QtWidgets.QHBoxLayout(self.screenshot_container)
            self.screenshot_layout.setContentsMargins(0, 0, 0, 0)
            self.screenshot_layout.setSpacing(6)
            self.screenshot_layout.addStretch()

            scroll.setWidget(self.screenshot_container)
            # 插入到日志区域之前
            insert_idx = self.layout().count()
            if hasattr(self, "logs_toggle_btn"):
                insert_idx = self.layout().indexOf(self.logs_toggle_btn)
            self.layout().insertWidget(insert_idx, scroll)

        self._add_screenshot_thumb(screenshot)


class MessageListWidget(QtWidgets.QScrollArea):
    """消息列表组件"""

    screenshot_clicked = QtCore.Signal(str, bytes)  # screenshot_id, cached_data

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: Dict[str, MessageBubble] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setObjectName("chatMessageList")

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("chatMessageContainer")
        self.msg_layout = QtWidgets.QVBoxLayout(self.container)
        self.msg_layout.setContentsMargins(12, 12, 12, 12)
        self.msg_layout.setSpacing(8)
        self.msg_layout.addStretch()

        self.setWidget(self.container)

    def clear_messages(self):
        """清空所有消息"""
        for bubble in self._messages.values():
            bubble.deleteLater()
        self._messages.clear()

        # 重新创建布局
        while self.msg_layout.count():
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.msg_layout.addStretch()

    def add_message(self, message: Dict) -> MessageBubble:
        """添加消息"""
        message_id = message.get("id", "")
        bubble = MessageBubble(message)
        bubble.screenshot_clicked.connect(self.screenshot_clicked.emit)

        # 插入到 stretch 之前
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
        self._messages[message_id] = bubble

        # 滚动到底部
        QtCore.QTimer.singleShot(100, self._scroll_to_bottom)

        return bubble

    def update_message(self, message_id: str, content: str = None, status: str = None):
        """更新消息"""
        if message_id in self._messages:
            bubble = self._messages[message_id]
            if content:
                bubble.update_content(content)
            if status:
                bubble.update_status(status)

    def append_log(self, message_id: str, content: str, log_type: str = "info"):
        """追加日志到指定消息"""
        if message_id in self._messages:
            self._messages[message_id].append_log(content, log_type)

    def add_screenshot(self, message_id: str, screenshot: Dict):
        """添加截图到指定消息"""
        if message_id in self._messages:
            self._messages[message_id].add_screenshot(screenshot)

    def get_bubble(self, message_id: str) -> Optional[MessageBubble]:
        """获取消息气泡"""
        return self._messages.get(message_id)

    def _scroll_to_bottom(self):
        """滚动到底部"""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class ChatInputWidget(QtWidgets.QWidget):
    """聊天输入区域组件"""

    message_submitted = QtCore.Signal(str, str)  # message, device_id
    stop_requested = QtCore.Signal()
    settings_changed = QtCore.Signal(dict)  # 设置变更信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = False
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 12)
        main_layout.setSpacing(8)

        # 顶部选项行
        options_layout = QtWidgets.QHBoxLayout()
        options_layout.setSpacing(16)

        # 设备选择器
        device_label = QtWidgets.QLabel("设备:")
        device_label.setObjectName("chatMutedLabel")
        options_layout.addWidget(device_label)

        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.setMinimumWidth(150)
        self.device_combo.setPlaceholderText("选择设备")
        options_layout.addWidget(self.device_combo)

        options_layout.addSpacing(20)

        # 复杂任务开关
        self.complex_task_check = QtWidgets.QCheckBox("复杂任务模式")
        self.complex_task_check.setToolTip("开启后会先将任务拆解成子任务列表，再逐个执行")
        self.complex_task_check.stateChanged.connect(self._on_settings_changed)
        options_layout.addWidget(self.complex_task_check)

        # 子任务超时选择
        timeout_label = QtWidgets.QLabel("子任务超时:")
        timeout_label.setObjectName("chatMutedLabel")
        options_layout.addWidget(timeout_label)

        self.timeout_combo = QtWidgets.QComboBox()
        self.timeout_combo.addItem("1 分钟", 60)
        self.timeout_combo.addItem("2 分钟", 120)
        self.timeout_combo.addItem("3 分钟", 180)
        self.timeout_combo.addItem("5 分钟", 300)
        self.timeout_combo.addItem("10 分钟", 600)
        self.timeout_combo.setCurrentIndex(2)  # 默认 3 分钟
        self.timeout_combo.currentIndexChanged.connect(self._on_settings_changed)
        options_layout.addWidget(self.timeout_combo)

        options_layout.addSpacing(20)

        # 自动发送邮件开关
        self.auto_email_check = QtWidgets.QCheckBox("自动发送邮件")
        self.auto_email_check.setToolTip("任务完成后自动发送汇总邮件")
        self.auto_email_check.stateChanged.connect(self._on_settings_changed)
        options_layout.addWidget(self.auto_email_check)

        options_layout.addStretch()

        # 刷新设备按钮
        self.refresh_btn = QtWidgets.QPushButton("刷新设备")
        self.refresh_btn.setObjectName("secondary")
        self.refresh_btn.setCursor(QtCore.Qt.PointingHandCursor)
        options_layout.addWidget(self.refresh_btn)

        main_layout.addLayout(options_layout)

        # 输入行
        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setSpacing(8)

        # 输入框
        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setPlaceholderText("输入你的指令，例如：打开微信给张三发消息...")
        self.input_edit.returnPressed.connect(self._on_submit)
        input_layout.addWidget(self.input_edit, 1)

        # 发送按钮
        self.send_btn = QtWidgets.QPushButton("发送")
        self.send_btn.setObjectName("success")
        self.send_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.send_btn.setMinimumWidth(70)
        self.send_btn.clicked.connect(self._on_submit)
        input_layout.addWidget(self.send_btn)

        # 停止按钮
        self.stop_btn = QtWidgets.QPushButton("停止")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.stop_btn.setMinimumWidth(70)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        input_layout.addWidget(self.stop_btn)

        main_layout.addLayout(input_layout)

    def _on_settings_changed(self):
        """设置变更"""
        self.settings_changed.emit(self.get_settings())

    def get_settings(self) -> dict:
        """获取当前设置"""
        return {
            "complex_task_mode": self.complex_task_check.isChecked(),
            "subtask_timeout": self.timeout_combo.currentData(),
            "auto_email": self.auto_email_check.isChecked(),
        }

    def set_devices(self, devices: List[tuple]):
        """设置设备列表 [(device_id, device_type, display_name), ...]"""
        self.device_combo.clear()
        for device_id, device_type, display_name in devices:
            self.device_combo.addItem(display_name, (device_id, device_type))

    def get_selected_device(self) -> Optional[tuple]:
        """获取选中的设备 (device_id, device_type)"""
        return self.device_combo.currentData()

    def set_running(self, running: bool):
        """设置运行状态"""
        self._is_running = running
        self.send_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.input_edit.setEnabled(not running)
        self.device_combo.setEnabled(not running)
        self.complex_task_check.setEnabled(not running)
        self.timeout_combo.setEnabled(not running)

    def _on_submit(self):
        if self._is_running:
            return

        message = self.input_edit.text().strip()
        if not message:
            return

        device = self.get_selected_device()
        if not device:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择设备")
            return

        device_id, _ = device
        self.input_edit.clear()
        self.message_submitted.emit(message, device_id)

    def _on_stop(self):
        self.stop_requested.emit()


class ScreenshotDialog(QtWidgets.QDialog):
    """截图查看对话框"""

    def __init__(self, image_data: bytes, description: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("截图查看")
        self.setMinimumSize(400, 600)
        self.resize(450, 700)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # 图片显示
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setObjectName("screenshotPreview")

        # 加载图片
        if image_data:
            pixmap = QtGui.QPixmap()
            if pixmap.loadFromData(image_data):
                scaled = pixmap.scaled(
                    420, 650,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled)
            else:
                self.image_label.setText("图片加载失败")
        else:
            self.image_label.setText("无图片数据")

        layout.addWidget(self.image_label, 1)

        # 描述
        if description:
            desc_label = QtWidgets.QLabel(description)
            desc_label.setObjectName("chatMutedLabel")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        # 关闭按钮
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


class SubtaskItemWidget(QtWidgets.QFrame):
    """子任务项组件（用于复杂任务模式）"""

    skip_requested = QtCore.Signal(int)  # subtask_index

    def __init__(self, index: int, task: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.task = task
        self._status = "pending"  # pending, running, success, error, skipped, timeout
        self._countdown = 0
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("subtaskItem")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # 状态图标
        self.status_label = QtWidgets.QLabel("○")
        self.status_label.setFixedWidth(20)
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # 任务序号
        self.index_label = QtWidgets.QLabel(f"#{self.index + 1}")
        self.index_label.setFixedWidth(30)
        self.index_label.setObjectName("chatMutedLabel")
        layout.addWidget(self.index_label)

        # 任务内容
        self.task_label = QtWidgets.QLabel(self.task[:50] + ("..." if len(self.task) > 50 else ""))
        self.task_label.setToolTip(self.task)
        layout.addWidget(self.task_label, 1)

        # 倒计时显示
        self.countdown_label = QtWidgets.QLabel("")
        self.countdown_label.setFixedWidth(50)
        self.countdown_label.setAlignment(QtCore.Qt.AlignCenter)
        self.countdown_label.setObjectName("chatMutedLabel")
        layout.addWidget(self.countdown_label)

        # 跳过按钮
        self.skip_btn = QtWidgets.QPushButton("跳过")
        self.skip_btn.setObjectName("secondary")
        self.skip_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.skip_btn.setFixedWidth(50)
        self.skip_btn.clicked.connect(lambda: self.skip_requested.emit(self.index))
        self.skip_btn.hide()  # 默认隐藏，运行时显示
        layout.addWidget(self.skip_btn)

    def set_status(self, status: str):
        """设置状态"""
        self._status = status
        icons = {
            "pending": "○",
            "running": "▶",
            "success": "✓",
            "error": "✗",
            "skipped": "⏭",
            "timeout": "⏰",
        }
        colors = {
            "pending": "#71717a",
            "running": "#6366f1",
            "success": "#10b981",
            "error": "#ef4444",
            "skipped": "#f59e0b",
            "timeout": "#f59e0b",
        }
        self.status_label.setText(icons.get(status, "○"))
        self.status_label.setStyleSheet(f"color: {colors.get(status, '#71717a')};")

        # 运行时显示跳过按钮
        self.skip_btn.setVisible(status == "running")

    def set_countdown(self, seconds: int):
        """设置倒计时"""
        self._countdown = seconds
        if seconds > 0:
            mins = seconds // 60
            secs = seconds % 60
            self.countdown_label.setText(f"{mins}:{secs:02d}")
        else:
            self.countdown_label.setText("")
