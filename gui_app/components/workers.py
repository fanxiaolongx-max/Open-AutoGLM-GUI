# -*- coding: utf-8 -*-
"""Worker 线程类 - 处理后台任务"""

import base64
import contextlib
import os
import subprocess
import sys
from pathlib import Path

from PySide6 import QtCore

from main import check_model_api, check_system_requirements
from phone_agent import IOSPhoneAgent, PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.xctest import XCTestConnection


def _adb_prefix(device_id):
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


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

        apk_path = Path(__file__).resolve().parents[2] / "ADBKeyboard.apk"
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


class StreamEmitter:
    def __init__(self, signal):
        self._signal = signal

    def write(self, text):
        if text:
            self._signal.emit(text)

    def flush(self):
        pass


class TaskWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)
    timeline = QtCore.Signal(str)
    adb_keyboard_notice = QtCore.Signal(str)
    confirmation_required = QtCore.Signal(str)
    takeover_required = QtCore.Signal(str)

    def __init__(
        self,
        device_type,
        base_url,
        model,
        api_key,
        max_steps,
        device_id,
        lang,
        wda_url,
        task,
        quiet=False,
        auto_confirm=True,
    ):
        super().__init__()
        self.device_type = device_type
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.max_steps = max_steps
        self.device_id = device_id or None
        self.lang = lang
        self.wda_url = wda_url
        self.task = task
        self.quiet = quiet
        self.auto_confirm = auto_confirm

    def _gui_confirmation(self, message: str) -> bool:
        """Confirmation callback for GUI mode - auto-confirms and logs."""
        self.log.emit(f"\n⚠️ 敏感操作确认: {message}\n")
        self.confirmation_required.emit(message)
        if self.auto_confirm:
            self.log.emit("✅ 自动确认执行\n")
            return True
        else:
            self.log.emit("✅ 已确认执行\n")
            return True

    def _gui_takeover(self, message: str) -> None:
        """Takeover callback for GUI mode - logs and continues."""
        self.log.emit(f"\n👋 需要手动操作: {message}\n")
        self.takeover_required.emit(message)
        self.log.emit("⏳ 等待3秒后自动继续...\n")
        import time
        time.sleep(3)
        self.log.emit("▶️ 继续执行任务\n")

    def run(self):
        emitter = StreamEmitter(self.log)
        with contextlib.redirect_stdout(emitter), contextlib.redirect_stderr(emitter):
            try:
                if self.isInterruptionRequested():
                    self.finished.emit("Stopped by user.")
                    return

                if self.device_type != DeviceType.IOS:
                    set_device_type(self.device_type)
                    if self.device_type == DeviceType.HDC:
                        from phone_agent.hdc import set_hdc_verbose
                        set_hdc_verbose(True)
                    if self.device_type == DeviceType.ADB:
                        ok, installed_now = ensure_adb_keyboard_installed(self.device_id)
                        if not ok:
                            self.failed.emit("ADB Keyboard install failed.")
                            return
                        if installed_now:
                            self.adb_keyboard_notice.emit(
                                "ADB Keyboard installed. If input fails, enable it in "
                                "Settings > System > Languages & Input > Virtual Keyboard."
                            )

                self.timeline.emit("System check started")
                ok = check_system_requirements(
                    self.device_type,
                    wda_url=self.wda_url if self.device_type == DeviceType.IOS else "http://localhost:8100",
                    device_id=self.device_id,
                )
                if not ok:
                    self.timeline.emit("System check failed")
                    self.failed.emit("System requirements check failed.")
                    return
                if self.isInterruptionRequested():
                    self.finished.emit("Stopped by user.")
                    return
                self.timeline.emit("System check passed")

                self.timeline.emit("Model check started")
                if not check_model_api(self.base_url, self.model, self.api_key):
                    self.timeline.emit("Model check failed")
                    self.failed.emit("Model service check failed.")
                    return
                if self.isInterruptionRequested():
                    self.finished.emit("Stopped by user.")
                    return
                self.timeline.emit("Model check passed")

                model_config = ModelConfig(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    model_name=self.model,
                    lang=self.lang,
                )

                if self.device_type == DeviceType.IOS:
                    agent_config = IOSAgentConfig(
                        max_steps=self.max_steps,
                        wda_url=self.wda_url,
                        device_id=self.device_id,
                        verbose=not self.quiet,
                        lang=self.lang,
                    )
                    agent = IOSPhoneAgent(
                        model_config=model_config,
                        agent_config=agent_config,
                        confirmation_callback=self._gui_confirmation,
                        takeover_callback=self._gui_takeover,
                    )
                else:
                    agent_config = AgentConfig(
                        max_steps=self.max_steps,
                        device_id=self.device_id,
                        verbose=not self.quiet,
                        lang=self.lang,
                    )
                    agent = PhoneAgent(
                        model_config=model_config,
                        agent_config=agent_config,
                        confirmation_callback=self._gui_confirmation,
                        takeover_callback=self._gui_takeover,
                    )

                self.timeline.emit("Task started")
                step_index = 0
                try:
                    result = agent.step(self.task)
                    step_index += 1
                    self.timeline.emit(self._format_step(step_index, result))
                    if self.isInterruptionRequested():
                        agent.cleanup()
                        self.finished.emit("Stopped by user.")
                        return

                    while not result.finished and step_index < self.max_steps:
                        result = agent.step()
                        step_index += 1
                        self.timeline.emit(self._format_step(step_index, result))
                        if self.isInterruptionRequested():
                            agent.cleanup()
                            self.finished.emit("Stopped by user.")
                            return

                    if result.finished:
                        self.finished.emit(result.message or "Task completed")
                    else:
                        agent.cleanup()
                        self.finished.emit("Max steps reached")
                except Exception as exc:
                    agent.cleanup()
                    raise exc
            except Exception as exc:
                self.failed.emit(str(exc))

    def _format_step(self, index, result):
        if result.action:
            meta = result.action.get("_metadata")
            if meta == "finish":
                message = result.action.get("message") or ""
                return f"Step {index}: finish {message}".strip()
            if meta == "do":
                action_name = result.action.get("action", "Unknown")
                return f"Step {index}: {action_name}"
        if result.message:
            return f"Step {index}: {result.message}"
        return f"Step {index}: completed"


class ScriptWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    finished = QtCore.Signal(int)
    failed = QtCore.Signal(str)

    def __init__(self, script_path):
        super().__init__()
        self.script_path = script_path

    def run(self):
        try:
            process = QtCore.QProcess()
            process.setProgram(sys.executable)
            process.setArguments([self.script_path])
            process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
            process.start()
            if not process.waitForStarted(3000):
                self.failed.emit("Failed to start script.")
                return

            while process.state() != QtCore.QProcess.NotRunning:
                process.waitForReadyRead(100)
                data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
                if data:
                    self.log.emit(data)

            exit_code = process.exitCode()
            self.finished.emit(exit_code)
        except Exception as exc:
            self.failed.emit(str(exc))


class VirtualizationSwitchWorker(QtCore.QThread):
    """Debian虚拟化内核切换Worker"""
    log = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)
    status_update = QtCore.Signal(str)

    def __init__(self, target: str):
        """
        target: 'kvm' 或 'vbox'
        """
        super().__init__()
        self.target = target

    def run(self):
        try:
            self.log.emit(f"[{self._timestamp()}] 开始切换到 {self.target.upper()}...\n")

            if self.target == "kvm":
                self.log.emit(f"[{self._timestamp()}] 停止 VirtualBox 服务...\n")
                self._run_cmd(["sudo", "systemctl", "stop", "vboxdrv.service"])

                self.log.emit(f"[{self._timestamp()}] 卸载 VirtualBox 模块...\n")
                self._run_cmd(["sudo", "modprobe", "-r", "vboxnetflt", "vboxnetadp", "vboxdrv"], ignore_error=True)

                self.log.emit(f"[{self._timestamp()}] 加载 KVM 模块...\n")
                self._run_cmd(["sudo", "modprobe", "kvm"])

                self.log.emit(f"[{self._timestamp()}] 加载 CPU 特定 KVM 模块...\n")
                result_intel = self._run_cmd(["sudo", "modprobe", "kvm_intel"], ignore_error=True)
                if result_intel != 0:
                    result_amd = self._run_cmd(["sudo", "modprobe", "kvm_amd"], ignore_error=True)
                    if result_amd != 0:
                        self.log.emit(f"[{self._timestamp()}] 警告: 无法加载 kvm_intel 或 kvm_amd 模块\n")

                self.log.emit(f"[{self._timestamp()}] ✅ 已切换到 KVM\n")
                self.finished.emit(True, "已切换到 KVM")

            elif self.target == "vbox":
                self.log.emit(f"[{self._timestamp()}] 卸载 KVM 模块...\n")
                self._run_cmd(["sudo", "modprobe", "-r", "kvm_intel", "kvm_amd", "kvm"], ignore_error=True)

                self.log.emit(f"[{self._timestamp()}] 启动 VirtualBox 服务...\n")
                result = self._run_cmd(["sudo", "systemctl", "start", "vboxdrv.service"])

                if result == 0:
                    self.log.emit(f"[{self._timestamp()}] ✅ 已切换到 VirtualBox\n")
                    self.finished.emit(True, "已切换到 VirtualBox")
                else:
                    self.log.emit(f"[{self._timestamp()}] ❌ VirtualBox 服务启动失败\n")
                    self.finished.emit(False, "VirtualBox 服务启动失败")
            else:
                self.finished.emit(False, f"未知目标: {self.target}")

        except Exception as exc:
            self.log.emit(f"[{self._timestamp()}] ❌ 错误: {str(exc)}\n")
            self.finished.emit(False, str(exc))

    def _run_cmd(self, cmd, ignore_error=False):
        """执行命令并返回退出码"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                self.log.emit(f"  {result.stdout.strip()}\n")
            if result.stderr and not ignore_error:
                self.log.emit(f"  {result.stderr.strip()}\n")
            return result.returncode
        except subprocess.TimeoutExpired:
            self.log.emit(f"  命令超时: {' '.join(cmd)}\n")
            return -1
        except Exception as e:
            if not ignore_error:
                self.log.emit(f"  命令执行失败: {str(e)}\n")
            return -1

    def _timestamp(self):
        return QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")


def detect_virtualization_status():
    """
    检测当前虚拟化环境状态
    返回: ('kvm', True/False), ('vbox', True/False), message
    """
    kvm_active = False
    vbox_active = False
    messages = []

    # 检测 KVM
    try:
        kvm_dev = os.path.exists("/dev/kvm")
        if kvm_dev:
            result = subprocess.run(
                ["ls", "-l", "/dev/kvm"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                kvm_active = True
                messages.append("KVM: /dev/kvm 存在")
    except Exception:
        pass

    # 检测 VirtualBox
    try:
        result = subprocess.run(
            ["lsmod"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            if "vboxdrv" in result.stdout:
                vbox_active = True
                messages.append("VirtualBox: vboxdrv 模块已加载")
    except Exception:
        pass

    if not kvm_active and not vbox_active:
        messages.append("未检测到活动的虚拟化环境")

    return kvm_active, vbox_active, "; ".join(messages) if messages else "检测完成"


class DiagnosticWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)
    summary = QtCore.Signal(list)
    adb_keyboard_notice = QtCore.Signal(str)

    def __init__(self, mode, device_type, device_id, base_url, model, api_key, wda_url):
        super().__init__()
        self.mode = mode
        self.device_type = device_type
        self.device_id = device_id
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.wda_url = wda_url

    def run(self):
        emitter = StreamEmitter(self.log)
        with contextlib.redirect_stdout(emitter), contextlib.redirect_stderr(emitter):
            try:
                if self.mode == "system":
                    if self.device_type != DeviceType.IOS:
                        set_device_type(self.device_type)
                        if self.device_type == DeviceType.HDC:
                            from phone_agent.hdc import set_hdc_verbose
                            set_hdc_verbose(True)
                        if self.device_type == DeviceType.ADB:
                            ok, installed_now = ensure_adb_keyboard_installed(self.device_id)
                            if installed_now:
                                self.adb_keyboard_notice.emit(
                                    "ADB Keyboard installed. If input fails, enable it in "
                                    "Settings > System > Languages & Input > Virtual Keyboard."
                                )
                    ok = check_system_requirements(
                        self.device_type,
                        wda_url=self.wda_url if self.device_type == DeviceType.IOS else "http://localhost:8100",
                        device_id=self.device_id,
                    )
                    self.summary.emit([
                        {"label": "System check", "status": "ok" if ok else "fail", "detail": "passed" if ok else "failed"}
                    ])
                    self.finished.emit(ok, "System check complete.")

                elif self.mode == "model":
                    ok = check_model_api(self.base_url, self.model, self.api_key)
                    self.summary.emit([
                        {"label": "Model check", "status": "ok" if ok else "fail", "detail": "passed" if ok else "failed"}
                    ])
                    self.finished.emit(ok, "Model check complete.")

                elif self.mode == "wda":
                    if self.device_type != DeviceType.IOS:
                        print("WDA check is only available for iOS.")
                        self.summary.emit([
                            {"label": "WDA check", "status": "skip", "detail": "non-iOS device"}
                        ])
                        self.finished.emit(False, "WDA check skipped.")
                        return
                    print("Checking WebDriverAgent status...")
                    conn = XCTestConnection(wda_url=self.wda_url)
                    status = conn.get_wda_status()
                    if status is None:
                        print("WDA not reachable.")
                        self.summary.emit([
                            {"label": "WDA check", "status": "fail", "detail": "not reachable"}
                        ])
                        self.finished.emit(False, "WDA check failed.")
                    else:
                        print("WDA is reachable.")
                        self.summary.emit([
                            {"label": "WDA check", "status": "ok", "detail": "reachable"}
                        ])
                        self.finished.emit(True, "WDA check complete.")

                elif self.mode == "all":
                    summary = []

                    if self.device_type != DeviceType.IOS:
                        set_device_type(self.device_type)
                        if self.device_type == DeviceType.HDC:
                            from phone_agent.hdc import set_hdc_verbose
                            set_hdc_verbose(True)
                        if self.device_type == DeviceType.ADB:
                            ok, installed_now = ensure_adb_keyboard_installed(self.device_id)
                            if installed_now:
                                self.adb_keyboard_notice.emit(
                                    "ADB Keyboard installed. If input fails, enable it in "
                                    "Settings > System > Languages & Input > Virtual Keyboard."
                                )

                    ok_system = check_system_requirements(
                        self.device_type,
                        wda_url=self.wda_url if self.device_type == DeviceType.IOS else "http://localhost:8100",
                        device_id=self.device_id,
                    )
                    summary.append({
                        "label": "System check",
                        "status": "ok" if ok_system else "fail",
                        "detail": "passed" if ok_system else "failed",
                    })

                    ok_model = check_model_api(self.base_url, self.model, self.api_key)
                    summary.append({
                        "label": "Model check",
                        "status": "ok" if ok_model else "fail",
                        "detail": "passed" if ok_model else "failed",
                    })

                    if self.device_type == DeviceType.IOS:
                        conn = XCTestConnection(wda_url=self.wda_url)
                        status = conn.get_wda_status()
                        ok_wda = status is not None
                        summary.append({
                            "label": "WDA check",
                            "status": "ok" if ok_wda else "fail",
                            "detail": "reachable" if ok_wda else "not reachable",
                        })
                    else:
                        summary.append({
                            "label": "WDA check",
                            "status": "skip",
                            "detail": "non-iOS device",
                        })

                    self.summary.emit(summary)
                    overall_ok = all(item["status"] != "fail" for item in summary)
                    self.finished.emit(overall_ok, "Diagnostics complete.")
                else:
                    self.finished.emit(False, "Unknown diagnostics mode.")
            except Exception as exc:
                self.finished.emit(False, str(exc))


class ScreenshotWorker(QtCore.QThread):
    frame = QtCore.Signal(bytes, bool)
    failed = QtCore.Signal(str)

    def __init__(self, device_type, device_id, wda_url):
        super().__init__()
        self.device_type = device_type
        self.device_id = device_id
        self.wda_url = wda_url

    def run(self):
        try:
            if self.device_type == DeviceType.IOS:
                from phone_agent.xctest import get_screenshot as ios_get_screenshot

                screenshot = ios_get_screenshot(
                    wda_url=self.wda_url,
                    device_id=self.device_id,
                )
            else:
                set_device_type(self.device_type)
                if self.device_type == DeviceType.HDC:
                    from phone_agent.hdc import set_hdc_verbose
                    set_hdc_verbose(True)
                screenshot = get_device_factory().get_screenshot(self.device_id)

            data = base64.b64decode(screenshot.base64_data)
            self.frame.emit(data, screenshot.is_sensitive)
        except Exception as exc:
            self.failed.emit(str(exc))


class ApkInstallWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    progress = QtCore.Signal(int)
    finished = QtCore.Signal(bool, str)

    def __init__(self, apk_path, device_type, device_id):
        super().__init__()
        self.apk_path = apk_path
        self.device_type = device_type
        self.device_id = device_id

    def run(self):
        try:
            self.log.emit(" ApkInstallWorker线程启动\n")
            self.log.emit(f" APK文件路径: {self.apk_path}\n")
            self.log.emit(f" 设备类型: {self.device_type}\n")
            self.log.emit(f" 设备ID: {self.device_id}\n")

            self.log.emit(f" 开始安装: {os.path.basename(self.apk_path)}\n")
            self.progress.emit(10)

            cmd_prefix = ["adb"]
            if self.device_id:
                cmd_prefix = ["adb", "-s", self.device_id]
                self.log.emit(f" 使用指定设备: {self.device_id}\n")
            else:
                self.log.emit(" 未指定设备ID，使用默认ADB\n")

            install_cmd = cmd_prefix + ["install", "-r", self.apk_path]
            self.log.emit(f" 执行命令: {' '.join(install_cmd)}\n")
            self.progress.emit(30)

            self.log.emit(" 等待ADB命令执行...\n")
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            self.progress.emit(90)
            output = (result.stdout + result.stderr).strip()
            self.log.emit(f" ADB命令输出:\n{output}\n")
            self.log.emit(f" 返回码: {result.returncode}\n")

            if result.returncode == 0 and "Success" in output:
                self.progress.emit(100)
                self.log.emit(" 安装成功！\n")
                self.finished.emit(True, "安装成功！")
            else:
                self.log.emit(" 安装失败！\n")
                self.finished.emit(False, f"安装失败 (返回码: {result.returncode})")

        except subprocess.TimeoutExpired:
            self.log.emit(" 安装超时 (5分钟)\n")
            self.finished.emit(False, "安装超时")
        except Exception as exc:
            self.log.emit(f" 安装过程异常: {type(exc).__name__}: {str(exc)}\n")
            import traceback
            self.log.emit(f" 异常详情:\n{traceback.format_exc()}\n")
            self.finished.emit(False, f"安装异常: {str(exc)}")


class MultiDeviceTaskWorker(QtCore.QThread):
    """单个设备的任务执行器，支持多设备并行"""
    log = QtCore.Signal(str, str)  # device_id, message
    step = QtCore.Signal(str, int, str)  # device_id, step_number, action
    finished = QtCore.Signal(str, bool, str)  # device_id, success, result
    screenshot = QtCore.Signal(str, bytes)  # device_id, image_data

    def __init__(self, device_id, device_type, task, config):
        super().__init__()
        self.device_id = device_id
        self.device_type = device_type
        self.task = task
        self.config = config
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _get_action_desc(self, result):
        """Get action description from step result."""
        if result.action:
            meta = result.action.get("_metadata")
            if meta == "finish":
                return "finish"
            if meta == "do":
                return result.action.get("action", "Unknown")
        return "思考中"

    def run(self):
        try:
            self.log.emit(self.device_id, f"开始执行任务: {self.task[:50]}...\n")

            if self.device_type == DeviceType.IOS:
                from phone_agent import IOSPhoneAgent
                from phone_agent.agent_ios import IOSAgentConfig

                agent_config = IOSAgentConfig(
                    wda_url=self.config.get("wda_url", "http://localhost:8100"),
                    device_id=self.device_id,
                    max_steps=self.config.get("max_steps", 50),
                )
                model_config = ModelConfig(
                    base_url=self.config.get("base_url", ""),
                    model_name=self.config.get("model", ""),
                    api_key=self.config.get("api_key", ""),
                )
                agent = IOSPhoneAgent(model_config, agent_config)
            else:
                from phone_agent import PhoneAgent
                from phone_agent.agent import AgentConfig

                set_device_type(self.device_type)
                agent_config = AgentConfig(
                    device_id=self.device_id,
                    lang=self.config.get("lang", "cn"),
                    max_steps=self.config.get("max_steps", 50),
                )
                model_config = ModelConfig(
                    base_url=self.config.get("base_url", ""),
                    model_name=self.config.get("model", ""),
                    api_key=self.config.get("api_key", ""),
                )
                agent = PhoneAgent(model_config, agent_config)

            step_count = 0
            max_steps = self.config.get("max_steps", 50)

            try:
                result = agent.step(self.task)
                step_count += 1

                if self._stop_requested:
                    agent.cleanup()
                    self.log.emit(self.device_id, "任务已停止\n")
                    self.finished.emit(self.device_id, False, "用户停止")
                    return

                action_desc = self._get_action_desc(result)
                self.step.emit(self.device_id, step_count, action_desc)
                self.log.emit(self.device_id, f"步骤 {step_count}: {action_desc}\n")

                if result.thinking:
                    self.log.emit(self.device_id, f"  思考: {result.thinking[:100]}...\n")

                while not result.finished and step_count < max_steps:
                    if self._stop_requested:
                        agent.cleanup()
                        self.log.emit(self.device_id, "任务已停止\n")
                        self.finished.emit(self.device_id, False, "用户停止")
                        return

                    result = agent.step()
                    step_count += 1

                    action_desc = self._get_action_desc(result)
                    self.step.emit(self.device_id, step_count, action_desc)
                    self.log.emit(self.device_id, f"步骤 {step_count}: {action_desc}\n")

                    if result.thinking:
                        self.log.emit(self.device_id, f"  思考: {result.thinking[:100]}...\n")

                if result.finished:
                    self.finished.emit(self.device_id, True, result.message or f"完成，共 {step_count} 步")
                else:
                    agent.cleanup()
                    self.finished.emit(self.device_id, True, f"达到最大步数 {max_steps}")
            except Exception as exc:
                agent.cleanup()
                raise exc

        except Exception as exc:
            self.log.emit(self.device_id, f"错误: {str(exc)}\n")
            self.finished.emit(self.device_id, False, str(exc))


class MultiDeviceTaskManager(QtCore.QObject):
    """多设备任务管理器"""
    all_finished = QtCore.Signal()
    device_log = QtCore.Signal(str, str)  # device_id, message
    device_status = QtCore.Signal(str, str)  # device_id, status
    device_finished = QtCore.Signal(str, bool, str)  # device_id, success, result

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workers = {}  # device_id -> worker
        self.results = {}  # device_id -> (success, result)

    def start_tasks(self, devices, task, config):
        """为多个设备启动任务"""
        self.workers.clear()
        self.results.clear()

        for device_id, device_type in devices:
            worker = MultiDeviceTaskWorker(device_id, device_type, task, config)
            worker.log.connect(self._on_log)
            worker.step.connect(self._on_step)
            worker.finished.connect(self._on_finished)
            self.workers[device_id] = worker
            self.device_status.emit(device_id, "运行中")
            worker.start()

    def stop_all(self):
        """停止所有任务"""
        for device_id, worker in self.workers.items():
            if worker.isRunning():
                worker.request_stop()
                self.device_status.emit(device_id, "停止中")

    def _on_log(self, device_id, message):
        self.device_log.emit(device_id, message)

    def _on_step(self, device_id, step_num, action):
        self.device_status.emit(device_id, f"步骤 {step_num}: {action}")

    def _on_finished(self, device_id, success, result):
        self.results[device_id] = (success, result)
        status = "✓ 完成" if success else "✗ 失败"
        self.device_status.emit(device_id, status)
        self.device_finished.emit(device_id, success, result)

        # 检查是否所有任务都完成
        if len(self.results) == len(self.workers):
            self.all_finished.emit()

    def get_running_count(self):
        return sum(1 for w in self.workers.values() if w.isRunning())

    def get_results_summary(self):
        success = sum(1 for s, _ in self.results.values() if s)
        failed = len(self.results) - success
        return success, failed
