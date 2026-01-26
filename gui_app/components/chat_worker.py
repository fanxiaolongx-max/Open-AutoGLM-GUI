# -*- coding: utf-8 -*-
"""Chat 任务执行 Worker - 处理 Chat 消息的后台任务"""

import contextlib
from typing import Optional

from PySide6 import QtCore

from phone_agent import PhoneAgent, IOSPhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig

from .workers import StreamEmitter, ensure_adb_keyboard_installed


class ChatTaskWorker(QtCore.QThread):
    """Chat 任务执行 Worker，处理单个消息的任务执行"""

    # 信号定义
    log_emitted = QtCore.Signal(str, str, str, str)  # session_id, message_id, content, log_type
    screenshot_captured = QtCore.Signal(str, str, bytes, str)  # session_id, message_id, image_data, desc
    step_completed = QtCore.Signal(str, int, str, list)  # message_id, step_num, action, todo_list
    message_updated = QtCore.Signal(str, str, str)  # message_id, content, status
    task_finished = QtCore.Signal(str, str)  # message_id, result
    task_failed = QtCore.Signal(str, str)  # message_id, error

    def __init__(
        self,
        session_id: str,
        message_id: str,
        task: str,
        device_id: str,
        device_type: DeviceType,
        config: dict,
        parent=None,
    ):
        super().__init__(parent)
        self.session_id = session_id
        self.message_id = message_id
        self.task = task
        self.device_id = device_id
        self.device_type = device_type
        self.config = config
        self._stop_requested = False
        self._agent: Optional[PhoneAgent] = None

    def request_stop(self):
        """请求停止任务"""
        self._stop_requested = True
        if self._agent:
            try:
                self._agent.request_stop()
            except Exception:
                pass

    def _emit_log(self, content: str, log_type: str = "info"):
        """发射日志信号"""
        self.log_emitted.emit(self.session_id, self.message_id, content, log_type)

    def _capture_screenshot(self, description: str = ""):
        """捕获并发射截图"""
        try:
            if self.device_type == DeviceType.IOS:
                from phone_agent.xctest import get_screenshot as ios_get_screenshot
                screenshot = ios_get_screenshot(
                    wda_url=self.config.get("wda_url", "http://localhost:8100"),
                    device_id=self.device_id,
                )
            else:
                set_device_type(self.device_type)
                screenshot = get_device_factory().get_screenshot(self.device_id)

            import base64
            image_data = base64.b64decode(screenshot.base64_data)
            self.screenshot_captured.emit(
                self.session_id, self.message_id, image_data, description
            )
        except Exception as e:
            self._emit_log(f"截图失败: {str(e)}", "error")

    def _get_action_desc(self, result) -> str:
        """从步骤结果获取动作描述"""
        if result.action:
            meta = result.action.get("_metadata")
            if meta == "finish":
                return "finish"
            if meta == "do":
                return result.action.get("action", "Unknown")
        return "思考中"

    def run(self):
        """执行任务"""
        # 创建日志重定向器
        class LogEmitter:
            def __init__(self, worker):
                self.worker = worker
                self.buffer = ""

            def write(self, text):
                if text:
                    self.buffer += text
                    # 按行分割并发送
                    while "\n" in self.buffer:
                        line, self.buffer = self.buffer.split("\n", 1)
                        if line.strip():
                            self.worker._emit_log(line, "info")

            def flush(self):
                if self.buffer.strip():
                    self.worker._emit_log(self.buffer, "info")
                    self.buffer = ""

        log_emitter = LogEmitter(self)

        with contextlib.redirect_stdout(log_emitter), contextlib.redirect_stderr(log_emitter):
            try:
                self._emit_log(f"开始执行任务: {self.task[:50]}...", "info")

                # 设置设备类型
                if self.device_type != DeviceType.IOS:
                    set_device_type(self.device_type)
                    if self.device_type == DeviceType.ADB:
                        ok, installed_now = ensure_adb_keyboard_installed(self.device_id)
                        if not ok:
                            self.task_failed.emit(self.message_id, "ADB Keyboard 安装失败")
                            return
                        if installed_now:
                            self._emit_log("ADB Keyboard 已安装", "info")

                # 创建模型配置
                model_config = ModelConfig(
                    base_url=self.config.get("base_url", ""),
                    api_key=self.config.get("api_key", ""),
                    model_name=self.config.get("model", ""),
                    lang=self.config.get("lang", "cn"),
                )

                # 创建 Agent
                if self.device_type == DeviceType.IOS:
                    agent_config = IOSAgentConfig(
                        max_steps=self.config.get("max_steps", 50),
                        wda_url=self.config.get("wda_url", "http://localhost:8100"),
                        device_id=self.device_id,
                        verbose=True,
                        lang=self.config.get("lang", "cn"),
                    )
                    self._agent = IOSPhoneAgent(
                        model_config=model_config,
                        agent_config=agent_config,
                    )
                else:
                    agent_config = AgentConfig(
                        max_steps=self.config.get("max_steps", 50),
                        device_id=self.device_id,
                        verbose=True,
                        lang=self.config.get("lang", "cn"),
                    )
                    self._agent = PhoneAgent(
                        model_config=model_config,
                        agent_config=agent_config,
                    )

                # 捕获初始截图
                self._capture_screenshot("初始状态")

                # 执行任务循环
                step_count = 0
                max_steps = self.config.get("max_steps", 50)
                todo_list = []

                try:
                    # 第一步
                    if self._stop_requested:
                        self._agent.cleanup()
                        self.task_failed.emit(self.message_id, "用户停止")
                        return

                    result = self._agent.step(self.task)
                    step_count += 1

                    action_desc = self._get_action_desc(result)
                    todo_list.append({"step": step_count, "action": action_desc, "status": "completed"})
                    self.step_completed.emit(self.message_id, step_count, action_desc, todo_list.copy())

                    if result.thinking:
                        self._emit_log(f"思考: {result.thinking[:200]}...", "thinking")

                    # 每步捕获截图
                    self._capture_screenshot(f"步骤 {step_count}: {action_desc}")

                    # 继续执行直到完成或达到最大步数
                    while not result.finished and step_count < max_steps:
                        if self._stop_requested:
                            self._agent.cleanup()
                            self.task_failed.emit(self.message_id, "用户停止")
                            return

                        result = self._agent.step()
                        step_count += 1

                        action_desc = self._get_action_desc(result)
                        todo_list.append({"step": step_count, "action": action_desc, "status": "completed"})
                        self.step_completed.emit(self.message_id, step_count, action_desc, todo_list.copy())

                        if result.thinking:
                            self._emit_log(f"思考: {result.thinking[:200]}...", "thinking")

                        # 每步捕获截图
                        self._capture_screenshot(f"步骤 {step_count}: {action_desc}")

                    # 任务完成
                    if result.finished:
                        final_message = result.message or f"任务完成，共执行 {step_count} 步"
                        self.message_updated.emit(self.message_id, final_message, "success")
                        self.task_finished.emit(self.message_id, final_message)
                    else:
                        self._agent.cleanup()
                        final_message = f"达到最大步数 {max_steps}"
                        self.message_updated.emit(self.message_id, final_message, "success")
                        self.task_finished.emit(self.message_id, final_message)

                except Exception as e:
                    if self._agent:
                        self._agent.cleanup()
                    raise e

            except Exception as e:
                error_msg = str(e)
                # 过滤掉一些常见的非致命错误信息，不覆盖任务执行的最终结果
                if "Model error" in error_msg or "404" in error_msg:
                    # 模型返回的错误可能是中间状态，记录日志但不覆盖消息
                    self._emit_log(f"模型响应异常: {error_msg}", "error")
                    # 如果任务已经在执行中，不更新消息内容，只标记失败
                    self.message_updated.emit(self.message_id, f"任务执行中遇到错误", "error")
                    self.task_failed.emit(self.message_id, error_msg)
                else:
                    self._emit_log(f"任务执行失败: {error_msg}", "error")
                    self.message_updated.emit(self.message_id, f"任务失败: {error_msg}", "error")
                    self.task_failed.emit(self.message_id, error_msg)
