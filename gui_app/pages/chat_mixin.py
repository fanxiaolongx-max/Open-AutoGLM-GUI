# -*- coding: utf-8 -*-
"""Chat 页面 Mixin - 实现 AI 对话功能"""

from typing import Optional, Dict, List
import base64

from PySide6 import QtCore, QtWidgets

from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.xctest import list_devices as list_ios_devices

from web_app.services.chat_service import chat_service
from web_app.services.chat_storage import chat_storage


class ChatMixin:
    """Chat 页面的 Mixin 类，包含所有 AI 对话相关的方法"""

    def _build_chat(self):
        """构建 Chat 页面"""
        from gui_app.components.chat_widgets import (
            SessionListWidget,
            MessageListWidget,
            ChatInputWidget,
        )

        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧：会话列表侧边栏
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("chatSidebar")
        sidebar.setFixedWidth(220)

        sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # 侧边栏标题
        sidebar_header = QtWidgets.QLabel("对话历史")
        sidebar_header.setObjectName("chatSidebarHeader")
        sidebar_layout.addWidget(sidebar_header)

        # 会话列表
        self.chat_session_list = SessionListWidget()
        self.chat_session_list.new_session_requested.connect(self._create_new_chat_session)
        self.chat_session_list.session_selected.connect(self._on_chat_session_selected)
        self.chat_session_list.session_deleted.connect(self._on_chat_session_deleted)
        sidebar_layout.addWidget(self.chat_session_list, 1)

        layout.addWidget(sidebar)

        # 右侧：主内容区
        main_area = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 消息列表
        self.chat_message_list = MessageListWidget()
        self.chat_message_list.screenshot_clicked.connect(self._show_chat_screenshot)
        main_layout.addWidget(self.chat_message_list, 1)

        # 输入区域
        input_container = QtWidgets.QFrame()
        input_container.setObjectName("chatInputContainer")
        input_layout = QtWidgets.QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_input = ChatInputWidget()
        self.chat_input.message_submitted.connect(self._send_chat_message)
        self.chat_input.stop_requested.connect(self._stop_chat_task)
        self.chat_input.refresh_btn.clicked.connect(self._refresh_chat_devices)
        input_layout.addWidget(self.chat_input)

        main_layout.addWidget(input_container)
        layout.addWidget(main_area, 1)

        # 初始化状态
        self._chat_worker = None
        self._current_chat_session_id: Optional[str] = None
        self._current_chat_message_id: Optional[str] = None
        self._chat_settings = {
            "complex_task_mode": False,
            "subtask_timeout": 180,
            "auto_email": False,
        }

        # 加载会话列表
        self._refresh_chat_sessions()
        self._refresh_chat_devices()

        return page

    def _refresh_chat_sessions(self):
        """刷新会话列表"""
        try:
            sessions = chat_service.get_sessions(limit=50)
            self.chat_session_list.set_sessions(sessions)
        except Exception as e:
            print(f"刷新会话列表失败: {e}")

    def _refresh_chat_devices(self):
        """刷新设备列表"""
        devices = []
        device_type = self._current_device_type()

        try:
            if device_type == DeviceType.IOS:
                ios_devices = list_ios_devices()
                for d in ios_devices:
                    name = d.device_name or d.device_id
                    devices.append((d.device_id, device_type, f"iOS: {name[:20]}"))
            else:
                set_device_type(device_type)
                factory = get_device_factory()
                for d in factory.list_devices():
                    if d.status == "device":
                        type_name = "ADB" if device_type == DeviceType.ADB else "HDC"
                        devices.append((d.device_id, device_type, f"{type_name}: {d.device_id[:20]}"))
        except Exception as e:
            print(f"刷新设备列表失败: {e}")

        self.chat_input.set_devices(devices)

    def _create_new_chat_session(self):
        """创建新会话"""
        device = self.chat_input.get_selected_device()
        device_id = device[0] if device else "unknown"

        try:
            session = chat_service.create_session(device_id, "")
            self._current_chat_session_id = session.get("id")
            self._refresh_chat_sessions()
            self.chat_session_list.select_session(self._current_chat_session_id)
            self.chat_message_list.clear_messages()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "错误", f"创建会话失败: {e}")

    def _on_chat_session_selected(self, session_id: str):
        """选择会话"""
        self._current_chat_session_id = session_id
        self._load_chat_session_messages(session_id)

    def _on_chat_session_deleted(self, session_id: str):
        """删除会话"""
        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            "确定要删除这个会话吗？所有消息和截图都将被删除。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            try:
                chat_service.delete_session(session_id)
                if self._current_chat_session_id == session_id:
                    self._current_chat_session_id = None
                    self.chat_message_list.clear_messages()
                self._refresh_chat_sessions()
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "错误", f"删除会话失败: {e}")

    def _load_chat_session_messages(self, session_id: str):
        """加载会话消息"""
        self.chat_message_list.clear_messages()

        try:
            detail = chat_service.get_session_detail(session_id)
            if detail:
                for msg in detail.get("messages", []):
                    self.chat_message_list.add_message(msg)
        except Exception as e:
            print(f"加载消息失败: {e}")

    def _send_chat_message(self, message: str, device_id: str):
        """发送消息"""
        from gui_app.components.chat_worker import ChatTaskWorker

        # 确保有会话
        if not self._current_chat_session_id:
            self._create_new_chat_session()

        if not self._current_chat_session_id:
            return

        # 添加用户消息
        try:
            user_msg = chat_storage.add_message(
                self._current_chat_session_id,
                "user",
                message
            )
            self.chat_message_list.add_message(user_msg.to_dict())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "错误", f"保存消息失败: {e}")
            return

        # 添加助手消息（执行中状态）
        try:
            assistant_msg = chat_storage.add_message(
                self._current_chat_session_id,
                "assistant",
                "正在执行任务...",
                status="running"
            )
            self._current_chat_message_id = assistant_msg.id
            self.chat_message_list.add_message(assistant_msg.to_dict())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "错误", f"创建响应失败: {e}")
            return

        # 获取设备类型
        device = self.chat_input.get_selected_device()
        if not device:
            return
        device_id, device_type = device

        # 获取模型配置
        active_service = self.model_services_manager.get_active_service()
        if not active_service:
            self._on_chat_task_failed(self._current_chat_message_id, "没有激活的模型服务")
            return

        # 获取 chat 设置
        chat_settings = self.chat_input.get_settings()

        config = {
            "base_url": active_service.base_url,
            "model": active_service.model_name,
            "api_key": active_service.api_key,
            "max_steps": 50,
            "lang": "cn",
            "complex_task_mode": chat_settings.get("complex_task_mode", False),
            "subtask_timeout": chat_settings.get("subtask_timeout", 180),
            "auto_email": chat_settings.get("auto_email", False),
        }

        # 创建并启动 Worker
        self._chat_worker = ChatTaskWorker(
            session_id=self._current_chat_session_id,
            message_id=self._current_chat_message_id,
            task=message,
            device_id=device_id,
            device_type=device_type,
            config=config,
        )

        # 连接信号
        self._chat_worker.log_emitted.connect(self._on_chat_log)
        self._chat_worker.screenshot_captured.connect(self._on_chat_screenshot)
        self._chat_worker.step_completed.connect(self._on_chat_step)
        self._chat_worker.message_updated.connect(self._on_chat_message_updated)
        self._chat_worker.task_finished.connect(self._on_chat_task_finished)
        self._chat_worker.task_failed.connect(self._on_chat_task_failed)

        # 更新 UI 状态
        self.chat_input.set_running(True)

        # 启动 Worker
        self._chat_worker.start()

    def _stop_chat_task(self):
        """停止当前任务"""
        if self._chat_worker and self._chat_worker.isRunning():
            self._chat_worker.request_stop()
            self._chat_worker.wait(2000)
            if self._chat_worker.isRunning():
                self._chat_worker.terminate()
                self._chat_worker.wait(500)

        self.chat_input.set_running(False)

        # 更新消息状态
        if self._current_chat_message_id:
            try:
                chat_storage.update_message(
                    self._current_chat_message_id,
                    content="任务已停止",
                    status="error"
                )
                self.chat_message_list.update_message(
                    self._current_chat_message_id,
                    "任务已停止",
                    "error"
                )
            except Exception:
                pass

    def _on_chat_log(self, session_id: str, message_id: str, content: str, log_type: str):
        """处理日志信号"""
        # 保存到存储
        try:
            chat_storage.add_log(session_id, message_id, content, log_type)
        except Exception:
            pass

        # 更新 UI
        self.chat_message_list.append_log(message_id, content, log_type)

    def _on_chat_screenshot(self, session_id: str, message_id: str, image_data: bytes, description: str):
        """处理截图信号"""
        # 保存到存储
        screenshot_id = None
        try:
            screenshot = chat_storage.add_screenshot(session_id, message_id, image_data, description)
            screenshot_id = screenshot.id
        except Exception:
            pass

        # 实时更新 UI - 添加截图到消息气泡
        if screenshot_id:
            screenshot_dict = {
                "id": screenshot_id,
                "description": description,
                "image_data": image_data,  # 直接传递二进制数据
            }
            self.chat_message_list.add_screenshot(message_id, screenshot_dict)

    def _on_chat_step(self, message_id: str, step_num: int, action: str, todo_list: list):
        """处理步骤完成信号"""
        # 更新消息的 todo_list
        try:
            chat_storage.update_message(message_id, todo_list=todo_list)
        except Exception:
            pass

    def _on_chat_message_updated(self, message_id: str, content: str, status: str):
        """处理消息更新信号"""
        # 更新存储
        try:
            chat_storage.update_message(message_id, content=content, status=status)
        except Exception:
            pass

        # 更新 UI
        self.chat_message_list.update_message(message_id, content, status)

    def _on_chat_task_finished(self, message_id: str, result: str):
        """处理任务完成信号"""
        self.chat_input.set_running(False)
        self._chat_worker = None

        # 刷新会话列表（更新标题等）
        self._refresh_chat_sessions()

        # 发送邮件（如果开启）
        chat_settings = self.chat_input.get_settings()
        if chat_settings.get("auto_email", False):
            self._send_chat_task_email(message_id, result, success=True)

    def _on_chat_task_failed(self, message_id: str, error: str):
        """处理任务失败信号"""
        self.chat_input.set_running(False)
        self._chat_worker = None

        # 更新消息状态
        try:
            chat_storage.update_message(message_id, content=f"任务失败: {error}", status="error")
        except Exception:
            pass

        self.chat_message_list.update_message(message_id, f"任务失败: {error}", "error")

        # 发送邮件（如果开启）
        chat_settings = self.chat_input.get_settings()
        if chat_settings.get("auto_email", False):
            self._send_chat_task_email(message_id, error, success=False)

    def _send_chat_task_email(self, message_id: str, result: str, success: bool):
        """发送任务完成邮件"""
        try:
            if hasattr(self, 'email_service') and self.email_service:
                # 获取会话信息
                session = chat_storage.get_session(self._current_chat_session_id)
                task_name = session.title if session else "AI 对话任务"

                # 发送邮件
                self._send_task_report_email(
                    task_name=task_name,
                    success_count=1 if success else 0,
                    failed_count=0 if success else 1,
                    total_count=1,
                    details=result,
                    is_scheduled=False
                )
        except Exception as e:
            print(f"发送邮件失败: {e}")

    def _show_chat_screenshot(self, screenshot_id: str, cached_data: bytes):
        """显示截图对话框"""
        from gui_app.components.chat_widgets import ScreenshotDialog

        try:
            # 优先使用缓存的数据
            if cached_data:
                image_data = cached_data
            else:
                # 从存储加载
                image_data = chat_service.get_screenshot(screenshot_id)

            if image_data:
                dialog = ScreenshotDialog(image_data, "", self)
                dialog.exec_()
            else:
                QtWidgets.QMessageBox.warning(self, "错误", "无法加载截图数据")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "错误", f"加载截图失败: {e}")
