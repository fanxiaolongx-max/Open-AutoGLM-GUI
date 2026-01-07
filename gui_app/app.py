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


class HoverExpandCard(QtWidgets.QFrame):
    """鼠标悬停时自动展开的卡片控件"""
    
    def __init__(self, collapsed_stretch=2, expanded_stretch=4, parent=None):
        super().__init__(parent)
        self.collapsed_stretch = collapsed_stretch
        self.expanded_stretch = expanded_stretch
        self.setObjectName("card")
        self._animation = None
        
    def enterEvent(self, event):
        """鼠标进入时展开"""
        super().enterEvent(event)
        self._animate_stretch(self.expanded_stretch)
        
    def leaveEvent(self, event):
        """鼠标离开时收缩"""
        super().leaveEvent(event)
        self._animate_stretch(self.collapsed_stretch)
        
    def _animate_stretch(self, target_stretch):
        """动画改变 stretch 因子"""
        parent_layout = self.parentWidget().layout() if self.parentWidget() else None
        if parent_layout and isinstance(parent_layout, QtWidgets.QBoxLayout):
            index = parent_layout.indexOf(self)
            if index >= 0:
                parent_layout.setStretch(index, target_stretch)


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
    confirmation_required = QtCore.Signal(str)  # Signal for confirmation requests
    takeover_required = QtCore.Signal(str)  # Signal for takeover requests

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
        auto_confirm=True,  # Auto-confirm sensitive operations in GUI mode
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
            # In non-auto mode, we still auto-confirm but log it
            self.log.emit("✅ 已确认执行\n")
            return True

    def _gui_takeover(self, message: str) -> None:
        """Takeover callback for GUI mode - logs and continues."""
        self.log.emit(f"\n👋 需要手动操作: {message}\n")
        self.takeover_required.emit(message)
        self.log.emit("⏳ 等待3秒后自动继续...\n")
        # Wait a bit to give user time to see the message
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
                result = agent.step(self.task)
                step_index += 1
                self.timeline.emit(self._format_step(step_index, result))
                if self.isInterruptionRequested():
                    self.finished.emit("Stopped by user.")
                    return

                while not result.finished and step_index < self.max_steps:
                    result = agent.step()
                    step_index += 1
                    self.timeline.emit(self._format_step(step_index, result))
                    if self.isInterruptionRequested():
                        self.finished.emit("Stopped by user.")
                        return

                if result.finished:
                    self.finished.emit(result.message or "Task completed")
                else:
                    self.finished.emit("Max steps reached")
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
        import shutil
        try:
            self.log.emit(f"[{self._timestamp()}] 开始切换到 {self.target.upper()}...\n")

            if self.target == "kvm":
                # 切换到 KVM
                self.log.emit(f"[{self._timestamp()}] 停止 VirtualBox 服务...\n")
                self._run_cmd(["sudo", "systemctl", "stop", "vboxdrv.service"])

                self.log.emit(f"[{self._timestamp()}] 卸载 VirtualBox 模块...\n")
                self._run_cmd(["sudo", "modprobe", "-r", "vboxnetflt", "vboxnetadp", "vboxdrv"], ignore_error=True)

                self.log.emit(f"[{self._timestamp()}] 加载 KVM 模块...\n")
                self._run_cmd(["sudo", "modprobe", "kvm"])

                # 尝试加载 Intel 或 AMD 的 KVM 模块
                self.log.emit(f"[{self._timestamp()}] 加载 CPU 特定 KVM 模块...\n")
                result_intel = self._run_cmd(["sudo", "modprobe", "kvm_intel"], ignore_error=True)
                if result_intel != 0:
                    result_amd = self._run_cmd(["sudo", "modprobe", "kvm_amd"], ignore_error=True)
                    if result_amd != 0:
                        self.log.emit(f"[{self._timestamp()}] 警告: 无法加载 kvm_intel 或 kvm_amd 模块\n")

                self.log.emit(f"[{self._timestamp()}] ✅ 已切换到 KVM\n")
                self.finished.emit(True, "已切换到 KVM")

            elif self.target == "vbox":
                # 切换到 VirtualBox
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
                            ok, installed_now = ensure_adb_keyboard_installed(
                                self.device_id
                            )
                            if installed_now:
                                self.adb_keyboard_notice.emit(
                                    "ADB Keyboard installed. If input fails, enable it in "
                                    "Settings > System > Languages & Input > Virtual Keyboard."
                                )
                    ok = check_system_requirements(
                        self.device_type,
                        wda_url=self.wda_url
                        if self.device_type == DeviceType.IOS
                        else "http://localhost:8100",
                        device_id=self.device_id,
                    )
                    self.summary.emit(
                        [
                            {
                                "label": "System check",
                                "status": "ok" if ok else "fail",
                                "detail": "passed" if ok else "failed",
                            }
                        ]
                    )
                    self.finished.emit(ok, "System check complete.")
                elif self.mode == "model":
                    ok = check_model_api(self.base_url, self.model, self.api_key)
                    self.summary.emit(
                        [
                            {
                                "label": "Model check",
                                "status": "ok" if ok else "fail",
                                "detail": "passed" if ok else "failed",
                            }
                        ]
                    )
                    self.finished.emit(ok, "Model check complete.")
                elif self.mode == "wda":
                    if self.device_type != DeviceType.IOS:
                        print("WDA check is only available for iOS.")
                        self.summary.emit(
                            [
                                {
                                    "label": "WDA check",
                                    "status": "skip",
                                    "detail": "non-iOS device",
                                }
                            ]
                        )
                        self.finished.emit(False, "WDA check skipped.")
                        return
                    print("Checking WebDriverAgent status...")
                    conn = XCTestConnection(wda_url=self.wda_url)
                    status = conn.get_wda_status()
                    if status is None:
                        print("WDA not reachable.")
                        self.summary.emit(
                            [
                                {
                                    "label": "WDA check",
                                    "status": "fail",
                                    "detail": "not reachable",
                                }
                            ]
                        )
                        self.finished.emit(False, "WDA check failed.")
                    else:
                        print("WDA is reachable.")
                        self.summary.emit(
                            [
                                {
                                    "label": "WDA check",
                                    "status": "ok",
                                    "detail": "reachable",
                                }
                            ]
                        )
                        self.finished.emit(True, "WDA check complete.")
                elif self.mode == "all":
                    summary = []

                    if self.device_type != DeviceType.IOS:
                        set_device_type(self.device_type)
                        if self.device_type == DeviceType.HDC:
                            from phone_agent.hdc import set_hdc_verbose

                            set_hdc_verbose(True)
                        if self.device_type == DeviceType.ADB:
                            ok, installed_now = ensure_adb_keyboard_installed(
                                self.device_id
                            )
                            if installed_now:
                                self.adb_keyboard_notice.emit(
                                    "ADB Keyboard installed. If input fails, enable it in "
                                    "Settings > System > Languages & Input > Virtual Keyboard."
                                )

                    ok_system = check_system_requirements(
                        self.device_type,
                        wda_url=self.wda_url
                        if self.device_type == DeviceType.IOS
                        else "http://localhost:8100",
                        device_id=self.device_id,
                    )
                    summary.append(
                        {
                            "label": "System check",
                            "status": "ok" if ok_system else "fail",
                            "detail": "passed" if ok_system else "failed",
                        }
                    )

                    ok_model = check_model_api(self.base_url, self.model, self.api_key)
                    summary.append(
                        {
                            "label": "Model check",
                            "status": "ok" if ok_model else "fail",
                            "detail": "passed" if ok_model else "failed",
                        }
                    )

                    if self.device_type == DeviceType.IOS:
                        conn = XCTestConnection(wda_url=self.wda_url)
                        status = conn.get_wda_status()
                        ok_wda = status is not None
                        summary.append(
                            {
                                "label": "WDA check",
                                "status": "ok" if ok_wda else "fail",
                                "detail": "reachable" if ok_wda else "not reachable",
                            }
                        )
                    else:
                        summary.append(
                            {
                                "label": "WDA check",
                                "status": "skip",
                                "detail": "non-iOS device",
                            }
                        )

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
            
            # ADB-only interface, no need to check device type
            self.log.emit(f" 开始安装: {os.path.basename(self.apk_path)}\n")
            self.progress.emit(10)

            # Always use ADB for ADB-only interface
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

            # First step with task
            result = agent.step(self.task)
            step_count += 1

            if self._stop_requested:
                self.log.emit(self.device_id, "任务已停止\n")
                self.finished.emit(self.device_id, False, "用户停止")
                return

            action_desc = self._get_action_desc(result)
            self.step.emit(self.device_id, step_count, action_desc)
            self.log.emit(self.device_id, f"步骤 {step_count}: {action_desc}\n")

            if result.thinking:
                self.log.emit(self.device_id, f"  思考: {result.thinking[:100]}...\n")

            # Continue until finished or max steps
            while not result.finished and step_count < max_steps:
                if self._stop_requested:
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
                self.finished.emit(self.device_id, True, f"达到最大步数 {max_steps}")

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
        status = "✓ 完成" if success else f"✗ 失败"
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


class DragDropTextEdit(QtWidgets.QPlainTextEdit):
    """支持拖拽文件导入的文本编辑框"""
    fileImported = QtCore.Signal(str)  # 导入的文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_hover = False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile().lower()
                # 支持常见文本文件格式
                if file_path.endswith(('.txt', '.md', '.json', '.yaml', '.yml', '.py', '.sh')):
                    event.acceptProposedAction()
                    self._drag_hover = True
                    self._update_drag_style()
                    return
        # 允许正常的文本拖拽
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_hover = False
        self._update_drag_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drag_hover = False
        self._update_drag_style()

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.setPlainText(content)
                    self.fileImported.emit(file_path)
                    event.acceptProposedAction()
                    return
                except Exception:
                    pass

        # 允许正常的文本拖拽
        if event.mimeData().hasText():
            super().dropEvent(event)
            return

        event.ignore()

    def _update_drag_style(self):
        if self._drag_hover:
            self.setStyleSheet(
                """
                QPlainTextEdit {
                    background: rgba(99, 102, 241, 0.1);
                    border: 2px dashed rgba(99, 102, 241, 0.8);
                    border-radius: 8px;
                }
                """
            )
        else:
            self.setStyleSheet("")


class DropZoneWidget(QtWidgets.QLabel):
    fileDropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._update_style(False)

    def _update_style(self, hover):
        if hover:
            self.setStyleSheet(
                """
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(99, 102, 241, 0.15), stop:1 rgba(139, 92, 246, 0.15));
                    border: 2px dashed rgba(99, 102, 241, 0.8);
                    border-radius: 16px;
                    color: #a78bfa;
                    font-size: 16px;
                    font-weight: 600;
                    padding: 40px;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QLabel {
                    background: rgba(24, 24, 27, 0.6);
                    border: 2px dashed rgba(63, 63, 70, 0.6);
                    border-radius: 16px;
                    color: #71717a;
                    font-size: 16px;
                    font-weight: 500;
                    padding: 40px;
                }
                """
            )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.apk'):
                event.acceptProposedAction()
                self._update_style(True)
                self.setText("📦 松开以安装APK")
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._update_style(False)
        self.setText("📱 拖拽APK文件到此处安装\n\n支持 .apk 格式")

    def dropEvent(self, event):
        self._update_style(False)
        self.setText("📱 拖拽APK文件到此处安装\n\n支持 .apk 格式")
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith('.apk'):
                    self.fileDropped.emit(file_path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("鱼塘管理器")

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
                "脚本管理",
                "应用目录",
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
            "脚本管理": self._build_scripts_page(),
            "应用目录": self._build_apps_page(),
            "系统诊断": self._build_diagnostics_page(),
            "运行日志": self._build_logs_page(),
            "系统设置": self._build_settings_page(),
        }

        for name in self.pages:
            self.stack.addWidget(self.pages[name])

        root = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(root)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self._load_settings()
        self._apply_style()
        self._refresh_devices()
        self._refresh_apps()
        self._refresh_scripts()
        self._refresh_dashboard()
        self._refresh_scheduled_tasks()
        self._start_preview()
        self.scheduled_tasks_manager.start()  # 启动定时任务调度器
        self.sched_countdown_timer.start()  # 启动倒计时更新定时器
        
        # 设置 PIN 请求回调（当解锁需要 PIN 但未配置时触发）
        from phone_agent.adb.unlock import set_pin_request_callback
        set_pin_request_callback(self._request_pin_dialog)

    def closeEvent(self, event):
        """Handle window close event."""
        try:
            # Stop all managers and timers
            self.scheduled_tasks_manager.stop()
            self.preview_timer.stop()
            self.sched_countdown_timer.stop()
            
            # Stop all worker threads
            if hasattr(self, 'task_worker') and self.task_worker:
                self.task_worker.terminate()
                self.task_worker.wait(1000)  # Wait up to 1 second
            
            if hasattr(self, 'script_worker') and self.script_worker:
                self.script_worker.terminate()
                self.script_worker.wait(1000)
            
            if hasattr(self, 'diagnostic_worker') and self.diagnostic_worker:
                self.diagnostic_worker.terminate()
                self.diagnostic_worker.wait(1000)
            
            if hasattr(self, 'preview_worker') and self.preview_worker:
                self.preview_worker.terminate()
                self.preview_worker.wait(1000)
            
            if hasattr(self, 'apk_install_worker') and self.apk_install_worker:
                self.apk_install_worker.terminate()
                self.apk_install_worker.wait(1000)
            
            if hasattr(self, 'gemini_task_worker') and self.gemini_task_worker:
                self.gemini_task_worker.terminate()
                self.gemini_task_worker.wait(1000)
            
            # Clean up multi-device manager
            if hasattr(self, 'multi_device_manager'):
                self.multi_device_manager.stop_all()
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        super().closeEvent(event)

    def _apply_style(self):
        # 根据字体缩放计算实际字体大小
        base_font = int(12 * self.font_scale)
        title_font = int(20 * self.font_scale)
        card_title_font = int(14 * self.font_scale)
        metric_font = int(24 * self.font_scale)
        small_font = int(11 * self.font_scale)

        self.setStyleSheet(
            f"""
            /* ═══════════════════════════════════════════════════════════════════
               Open AutoGLM - Premium UI Theme
               Inspired by Linear, Vercel, Raycast, Arc Browser
               Modern glassmorphism + subtle gradients + micro-interactions
            ═══════════════════════════════════════════════════════════════════ */

            * {{
                font-family: 'Helvetica Neue', 'PingFang SC';
                font-size: {base_font}px;
                outline: none;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Base Container - Deep Space Background
            ───────────────────────────────────────────────────────────────── */
            QWidget {{
                background-color: #09090b;
                color: #fafafa;
            }}

            QMainWindow {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #09090b, stop:0.5 #0c0c0f, stop:1 #09090b);
            }}

            /* ─────────────────────────────────────────────────────────────────
               Navigation Sidebar - Frosted Glass Effect
            ───────────────────────────────────────────────────────────────── */
            QListWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(24, 24, 27, 0.95), stop:1 rgba(18, 18, 20, 0.98));
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 12px;
                padding: 6px 4px;
                margin: 6px;
            }}

            QListWidget::item {{
                color: #a1a1aa;
                padding: 10px 14px;
                margin: 2px 4px;
                border-radius: 8px;
                border: 1px solid transparent;
            }}

            QListWidget::item:hover {{
                background: rgba(63, 63, 70, 0.4);
                color: #e4e4e7;
                border: 1px solid rgba(82, 82, 91, 0.3);
            }}

            QListWidget::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(99, 102, 241, 0.9), stop:1 rgba(139, 92, 246, 0.9));
                color: #ffffff;
                font-weight: 600;
                border: 1px solid rgba(167, 139, 250, 0.5);
            }}

            /* ─────────────────────────────────────────────────────────────────
               Cards & Panels - Elevated Glass Surfaces
            ───────────────────────────────────────────────────────────────── */
            QFrame {{
                background: transparent;
            }}

            QFrame#card {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(24, 24, 27, 0.9), stop:1 rgba(18, 18, 20, 0.95));
                border: 1px solid rgba(63, 63, 70, 0.4);
                border-radius: 12px;
                padding: 16px;
            }}

            QFrame#card:hover {{
                border: 1px solid rgba(99, 102, 241, 0.3);
            }}

            /* ─────────────────────────────────────────────────────────────────
               Typography - Modern Hierarchy
            ───────────────────────────────────────────────────────────────── */
            QLabel {{
                color: #e4e4e7;
                background: transparent;
            }}

            QLabel#title {{
                font-size: {title_font}px;
                font-weight: 700;
                color: #fafafa;
                padding: 6px 0 12px 0;
                letter-spacing: -0.5px;
            }}

            QLabel#cardTitle {{
                font-size: {card_title_font}px;
                font-weight: 600;
                color: #f4f4f5;
                padding-bottom: 6px;
                letter-spacing: -0.2px;
            }}

            QLabel#metricValue {{
                font-size: {metric_font}px;
                font-weight: 700;
                color: #a78bfa;
                letter-spacing: -1px;
            }}

            QLabel#metricLabel {{
                font-size: {small_font}px;
                font-weight: 500;
                color: #71717a;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Buttons - Gradient & Glow Effects
            ───────────────────────────────────────────────────────────────── */
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6366f1, stop:1 #8b5cf6);
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                color: #ffffff;
                font-weight: 600;
                font-size: {base_font}px;
                min-height: 18px;
            }}

            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #818cf8, stop:1 #a78bfa);
            }}

            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4f46e5, stop:1 #7c3aed);
            }}

            QPushButton:disabled {{
                background: rgba(39, 39, 42, 0.8);
                color: #52525b;
                border: 1px solid rgba(63, 63, 70, 0.3);
            }}

            QPushButton#secondary {{
                background: rgba(39, 39, 42, 0.6);
                border: 1px solid rgba(63, 63, 70, 0.5);
                color: #a1a1aa;
            }}

            QPushButton#secondary:hover {{
                background: rgba(63, 63, 70, 0.6);
                border: 1px solid rgba(82, 82, 91, 0.6);
                color: #e4e4e7;
            }}

            QPushButton#success {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #10b981, stop:1 #059669);
            }}

            QPushButton#success:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #34d399, stop:1 #10b981);
            }}

            QPushButton#danger {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ef4444, stop:1 #dc2626);
            }}

            QPushButton#danger:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f87171, stop:1 #ef4444);
            }}

            /* ─────────────────────────────────────────────────────────────────
               Input Fields - Sleek & Modern
            ───────────────────────────────────────────────────────────────── */
            QLineEdit, QSpinBox, QComboBox {{
                background: rgba(24, 24, 27, 0.8);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 8px;
                padding: 8px 12px;
                color: #fafafa;
                min-height: 18px;
                min-width: 200px;
                selection-background-color: rgba(99, 102, 241, 0.5);
            }}

            QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
                border: 1px solid rgba(82, 82, 91, 0.7);
                background: rgba(30, 30, 33, 0.9);
            }}

            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 1px solid rgba(99, 102, 241, 0.7);
                background: rgba(24, 24, 27, 1);
            }}

            QLineEdit::placeholder {{
                color: #52525b;
            }}

            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}

            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #71717a;
                margin-right: 10px;
            }}

            QComboBox QAbstractItemView {{
                background: rgba(24, 24, 27, 0.98);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 8px;
                padding: 4px;
                selection-background-color: rgba(99, 102, 241, 0.5);
            }}

            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                height: 0px;
                border: none;
                background: none;
            }}

            QSpinBox::up-arrow, QSpinBox::down-arrow {{
                width: 0px;
                height: 0px;
                border: none;
                background: none;
            }}

            QTimeEdit, QDateTimeEdit {{
                background: rgba(24, 24, 27, 0.8);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 8px;
                padding: 8px 12px;
                color: #fafafa;
                min-height: 18px;
                selection-background-color: rgba(99, 102, 241, 0.5);
            }}

            QTimeEdit:hover, QDateTimeEdit:hover {{
                border: 1px solid rgba(82, 82, 91, 0.7);
                background: rgba(30, 30, 33, 0.9);
            }}

            QTimeEdit:focus, QDateTimeEdit:focus {{
                border: 1px solid rgba(99, 102, 241, 0.7);
                background: rgba(24, 24, 27, 1);
            }}

            QTimeEdit::up-button, QTimeEdit::down-button,
            QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
                background: transparent;
                border: none;
                width: 20px;
                subcontrol-origin: border;
            }}

            QTimeEdit::up-button, QDateTimeEdit::up-button {{
                subcontrol-position: top right;
            }}

            QTimeEdit::down-button, QDateTimeEdit::down-button {{
                subcontrol-position: bottom right;
            }}

            QTimeEdit::up-arrow, QDateTimeEdit::up-arrow {{
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #71717a;
                width: 0;
                height: 0;
            }}

            QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {{
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #71717a;
                width: 0;
                height: 0;
            }}

            QTimeEdit::up-arrow:hover, QDateTimeEdit::up-arrow:hover,
            QTimeEdit::down-arrow:hover, QDateTimeEdit::down-arrow:hover {{
                border-bottom-color: #a78bfa;
                border-top-color: #a78bfa;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Text Areas - Code Editor Style
            ───────────────────────────────────────────────────────────────── */
            QPlainTextEdit, QTextEdit {{
                background: rgba(18, 18, 20, 0.95);
                border: 1px solid rgba(63, 63, 70, 0.4);
                border-radius: 10px;
                padding: 10px;
                color: #e4e4e7;
                font-family: 'Menlo', 'Monaco';
                font-size: {base_font}px;
                line-height: 1.5;
                selection-background-color: rgba(99, 102, 241, 0.4);
            }}

            QPlainTextEdit:focus, QTextEdit:focus {{
                border: 1px solid rgba(99, 102, 241, 0.5);
            }}

            /* ─────────────────────────────────────────────────────────────────
               Splitter - Subtle Dividers
            ───────────────────────────────────────────────────────────────── */
            QSplitter::handle {{
                background: rgba(63, 63, 70, 0.3);
                width: 2px;
                margin: 0 6px;
                border-radius: 1px;
            }}

            QSplitter::handle:hover {{
                background: rgba(99, 102, 241, 0.6);
            }}

            /* ─────────────────────────────────────────────────────────────────
               Timeline List - Activity Feed Style
            ───────────────────────────────────────────────────────────────── */
            QListWidget#timeline_list {{
                background: rgba(18, 18, 20, 0.6);
                border: 1px solid rgba(63, 63, 70, 0.3);
                border-radius: 10px;
                padding: 6px;
            }}

            QListWidget#timeline_list::item {{
                padding: 8px 12px;
                margin: 2px 0;
                border-radius: 6px;
                border: none;
                color: #a1a1aa;
                font-size: {small_font}px;
            }}

            QListWidget#timeline_list::item:hover {{
                background: rgba(63, 63, 70, 0.3);
                color: #e4e4e7;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Scrollbars - Minimal & Elegant
            ───────────────────────────────────────────────────────────────── */
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px;
                border-radius: 3px;
            }}

            QScrollBar::handle:vertical {{
                background: rgba(82, 82, 91, 0.5);
                border-radius: 3px;
                min-height: 30px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: rgba(99, 102, 241, 0.6);
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 6px;
                margin: 2px 4px;
                border-radius: 3px;
            }}

            QScrollBar::handle:horizontal {{
                background: rgba(82, 82, 91, 0.5);
                border-radius: 3px;
                min-width: 30px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background: rgba(99, 102, 241, 0.6);
            }}

            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Message Boxes & Tooltips
            ───────────────────────────────────────────────────────────────── */
            QMessageBox {{
                background: rgba(24, 24, 27, 0.98);
            }}

            QMessageBox QLabel {{
                color: #e4e4e7;
            }}

            QToolTip {{
                background: rgba(24, 24, 27, 0.95);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 6px;
                padding: 6px 10px;
                color: #e4e4e7;
                font-size: {small_font}px;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Form Labels
            ───────────────────────────────────────────────────────────────── */
            QFormLayout QLabel {{
                font-weight: 500;
                color: #a1a1aa;
                padding-right: 10px;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Status Indicators
            ───────────────────────────────────────────────────────────────── */
            QLabel#status_ok {{
                color: #10b981;
                font-weight: 600;
            }}

            QLabel#status_error {{
                color: #ef4444;
                font-weight: 600;
            }}

            QLabel#status_warning {{
                color: #f59e0b;
                font-weight: 600;
            }}

            QLabel#status_info {{
                color: #6366f1;
                font-weight: 600;
            }}

            /* ─────────────────────────────────────────────────────────────────
               Preview Area - Device Frame Style
            ───────────────────────────────────────────────────────────────── */
            QLabel#preview {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #18181b, stop:1 #09090b);
                border: 2px solid rgba(63, 63, 70, 0.5);
                border-radius: 16px;
            }}
            """
        )

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
        elif index == 1:  # Device hub page
            # Auto detect devices when switching to device hub
            QtCore.QTimer.singleShot(500, self._auto_detect_and_clean)

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
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
            color: #fafafa;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        """)

        subtitle = QtWidgets.QLabel("这是您的自动化工作区概览")
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: #a1a1aa;
            font-weight: 400;
            letter-spacing: 0.2px;
        """)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        # Metrics Grid with enhanced cards
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(16)

        self.metric_device = self._create_metric_card(
            "当前设备", "-", "已连接的设备", "device"
        )
        self.metric_model = self._create_metric_card(
            "AI模型", "-", "使用中的语言模型", "model"
        )
        self.metric_tasks = self._create_metric_card(
            "已完成任务", "0", "成功执行次数", "tasks"
        )
        self.metric_status = self._create_metric_card(
            "系统状态", "就绪", "所有系统运行正常", "status"
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
            ("设备中心", 1, "secondary"),    # 设备中心 (index 1)
            ("模型服务", 2, "secondary"),    # 模型服务 (index 2)
            ("定时任务", 4, "secondary"),    # 定时任务 (index 4)
            ("系统诊断", 9, "secondary"),    # 系统诊断 (index 9)
            ("系统设置", 11, "secondary"),   # 系统设置 (index 11)
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
        header.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
            color: #fafafa;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        """)

        subtitle = QtWidgets.QLabel("连接和管理您的安卓、鸿蒙或iOS设备")
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: #a1a1aa;
            font-weight: 400;
            letter-spacing: 0.2px;
        """)

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

        self.device_type_combo = NoWheelComboBox()
        self.device_type_combo.addItems(["adb"])
        self.device_type_combo.currentTextChanged.connect(self._refresh_devices)
        self.device_type_combo.currentTextChanged.connect(self._refresh_apps)
        self.device_type_combo.currentTextChanged.connect(self._refresh_dashboard)

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
            self.pin_status.setText(f"此设备已配置 PIN")
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

    def _build_model_service(self):
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

        header = QtWidgets.QLabel("模型服务")
        header.setObjectName("title")
        header.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
            color: #fafafa;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        """)

        subtitle = QtWidgets.QLabel("配置和管理多个AI模型服务，支持智谱BigModel、ModelScope等")
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: #a1a1aa;
            font-weight: 400;
            letter-spacing: 0.2px;
        """)

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Main content - 2 column layout
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(16)

        # Left Panel - Services List
        left_card = QtWidgets.QFrame()
        left_card.setObjectName("card")
        left_card.setMinimumWidth(280)
        left_card.setMaximumWidth(350)
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 12, 16, 12)
        left_layout.setSpacing(10)

        list_header = QtWidgets.QLabel("服务列表")
        list_header.setObjectName("cardTitle")

        self.service_list = QtWidgets.QListWidget()
        self.service_list.setMinimumHeight(200)
        self.service_list.currentRowChanged.connect(self._on_service_selected)

        # Service list buttons
        list_btn_layout = QtWidgets.QHBoxLayout()
        list_btn_layout.setSpacing(6)

        self.add_service_btn = QtWidgets.QPushButton("添加")
        self.add_service_btn.setObjectName("secondary")
        self.add_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.add_service_btn.clicked.connect(self._add_new_service)

        self.delete_service_btn = QtWidgets.QPushButton("删除")
        self.delete_service_btn.setObjectName("danger")
        self.delete_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.delete_service_btn.clicked.connect(self._delete_current_service)

        self.activate_service_btn = QtWidgets.QPushButton("激活")
        self.activate_service_btn.setObjectName("success")
        self.activate_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.activate_service_btn.clicked.connect(self._activate_current_service)

        list_btn_layout.addWidget(self.add_service_btn)
        list_btn_layout.addWidget(self.delete_service_btn)
        list_btn_layout.addWidget(self.activate_service_btn)

        # Preset templates
        preset_header = QtWidgets.QLabel("快速添加模板")
        preset_header.setStyleSheet("color: #71717a; font-size: 12px; margin-top: 10px;")

        self.preset_combo = NoWheelComboBox()
        self.preset_combo.addItem("选择预置模板...")
        for preset in self.model_services_manager.get_preset_templates():
            self.preset_combo.addItem(preset.name, preset.id)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)

        left_layout.addWidget(list_header)
        left_layout.addWidget(self.service_list)
        left_layout.addLayout(list_btn_layout)
        left_layout.addWidget(preset_header)
        left_layout.addWidget(self.preset_combo)
        left_layout.addStretch()

        # Right Panel - Service Details
        right_card = QtWidgets.QFrame()
        right_card.setObjectName("card")
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(12)

        detail_header = QtWidgets.QLabel("服务配置")
        detail_header.setObjectName("cardTitle")

        # Service status badge
        self.service_status_label = QtWidgets.QLabel("未选择服务")
        self.service_status_label.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 6px 12px; border-radius: 6px;"
        )

        # Form
        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        self.service_name_input = QtWidgets.QLineEdit()
        self.service_name_input.setPlaceholderText("服务显示名称")

        self.base_url_input = QtWidgets.QLineEdit()
        self.base_url_input.setPlaceholderText("http://localhost:8000/v1")

        self.model_input = QtWidgets.QLineEdit()
        self.model_input.setPlaceholderText("autoglm-phone-9b")

        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setPlaceholderText("您的API密钥（可选）")

        self.service_desc_input = QtWidgets.QLineEdit()
        self.service_desc_input.setPlaceholderText("服务描述（可选）")

        # Advanced settings (collapsible idea - just show key ones)
        self.max_tokens_input = NoWheelSpinBox()
        self.max_tokens_input.setRange(100, 10000)
        self.max_tokens_input.setValue(3000)

        self.temperature_input = NoWheelDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(0.0)

        form.addRow("服务名称", self.service_name_input)
        form.addRow("服务地址", self.base_url_input)
        form.addRow("模型名称", self.model_input)
        form.addRow("API密钥", self.api_key_input)
        form.addRow("描述", self.service_desc_input)
        form.addRow("最大Token", self.max_tokens_input)
        form.addRow("Temperature", self.temperature_input)

        # Action Buttons
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(10)

        self.save_service_btn = QtWidgets.QPushButton("保存配置")
        self.save_service_btn.setObjectName("success")
        self.save_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.save_service_btn.clicked.connect(self._save_current_service)

        self.test_service_btn = QtWidgets.QPushButton("测试连接")
        self.test_service_btn.setObjectName("secondary")
        self.test_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.test_service_btn.clicked.connect(self._test_current_service)

        actions.addWidget(self.save_service_btn)
        actions.addWidget(self.test_service_btn)
        actions.addStretch()

        right_layout.addWidget(detail_header)
        right_layout.addWidget(self.service_status_label)
        right_layout.addLayout(form)
        right_layout.addLayout(actions)
        right_layout.addStretch()

        content_layout.addWidget(left_card)
        content_layout.addWidget(right_card, 1)

        # Global Settings Card (max_steps and lang are global)
        global_card = QtWidgets.QFrame()
        global_card.setObjectName("card")
        global_layout = QtWidgets.QVBoxLayout(global_card)
        global_layout.setContentsMargins(16, 12, 16, 12)
        global_layout.setSpacing(10)

        global_header = QtWidgets.QLabel("全局设置")
        global_header.setObjectName("cardTitle")

        global_form = QtWidgets.QHBoxLayout()
        global_form.setSpacing(20)

        max_steps_label = QtWidgets.QLabel("最大步数:")
        self.max_steps_input = NoWheelSpinBox()
        self.max_steps_input.setRange(1, 500)
        self.max_steps_input.setValue(100)
        self.max_steps_input.setFixedWidth(100)

        lang_label = QtWidgets.QLabel("语言:")
        self.lang_combo = NoWheelComboBox()
        self.lang_combo.addItems(["cn", "en"])
        self.lang_combo.setFixedWidth(80)

        global_form.addWidget(max_steps_label)
        global_form.addWidget(self.max_steps_input)
        global_form.addSpacing(20)
        global_form.addWidget(lang_label)
        global_form.addWidget(self.lang_combo)
        global_form.addStretch()

        self.save_global_btn = QtWidgets.QPushButton("保存全局设置")
        self.save_global_btn.setObjectName("secondary")
        self.save_global_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.save_global_btn.clicked.connect(self._save_settings)

        global_layout.addWidget(global_header)
        global_layout.addLayout(global_form)
        global_layout.addWidget(self.save_global_btn, alignment=QtCore.Qt.AlignLeft)

        layout.addWidget(header_widget)
        layout.addLayout(content_layout, 1)
        layout.addWidget(global_card)

        # Initialize service list
        self._refresh_service_list()

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)

        return page

    def _refresh_service_list(self):
        """刷新服务列表"""
        self.service_list.clear()
        services = self.model_services_manager.get_all_services()
        for service in services:
            prefix = "✓ " if service.is_active else "  "
            item = QtWidgets.QListWidgetItem(f"{prefix}{service.name}")
            item.setData(QtCore.Qt.UserRole, service.id)
            if service.is_active:
                item.setForeground(QtGui.QColor("#10b981"))
            self.service_list.addItem(item)

        # Select the active service
        active = self.model_services_manager.get_active_service()
        if active:
            for i in range(self.service_list.count()):
                item = self.service_list.item(i)
                if item.data(QtCore.Qt.UserRole) == active.id:
                    self.service_list.setCurrentRow(i)
                    break

    def _on_service_selected(self, row):
        """服务选择变化时更新详情"""
        if row < 0:
            self._clear_service_form()
            return

        item = self.service_list.item(row)
        if not item:
            return

        service_id = item.data(QtCore.Qt.UserRole)
        service = self.model_services_manager.get_service_by_id(service_id)
        if service:
            self._load_service_to_form(service)

    def _load_service_to_form(self, service: ModelServiceConfig):
        """将服务配置加载到表单"""
        self.service_name_input.setText(service.name)
        self.base_url_input.setText(service.base_url)
        self.model_input.setText(service.model_name)
        self.api_key_input.setText(service.api_key)
        self.service_desc_input.setText(service.description)
        self.max_tokens_input.setValue(service.max_tokens)
        self.temperature_input.setValue(service.temperature)

        if service.is_active:
            self.service_status_label.setText("✓ 当前激活的服务")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 6px 12px; border-radius: 6px;"
            )
        else:
            self.service_status_label.setText("未激活")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
                "padding: 6px 12px; border-radius: 6px;"
            )

    def _clear_service_form(self):
        """清空服务表单"""
        self.service_name_input.clear()
        self.base_url_input.clear()
        self.model_input.clear()
        self.api_key_input.clear()
        self.service_desc_input.clear()
        self.max_tokens_input.setValue(3000)
        self.temperature_input.setValue(0.0)
        self.service_status_label.setText("未选择服务")
        self.service_status_label.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 6px 12px; border-radius: 6px;"
        )

    def _get_current_service_id(self) -> str:
        """获取当前选中的服务ID"""
        current = self.service_list.currentItem()
        if current:
            return current.data(QtCore.Qt.UserRole)
        return ""

    def _save_current_service(self):
        """保存当前服务配置"""
        service_id = self._get_current_service_id()
        if not service_id:
            self._append_log("请先选择一个服务。\n")
            return

        service = self.model_services_manager.get_service_by_id(service_id)
        if not service:
            return

        # Update from form
        service.name = self.service_name_input.text().strip() or "未命名服务"
        service.base_url = self.base_url_input.text().strip()
        service.model_name = self.model_input.text().strip()
        service.api_key = self.api_key_input.text().strip()
        service.description = self.service_desc_input.text().strip()
        service.max_tokens = self.max_tokens_input.value()
        service.temperature = self.temperature_input.value()

        self.model_services_manager.update_service(service)
        self._refresh_service_list()
        self._append_log(f"服务 [{service.name}] 配置已保存。\n")
        self._refresh_dashboard()

    def _test_current_service(self):
        """测试当前服务连接"""
        service_id = self._get_current_service_id()
        if not service_id:
            self._append_log("请先选择一个服务。\n")
            return

        # Create temp config from form
        temp_service = ModelServiceConfig(
            id="temp",
            name=self.service_name_input.text().strip(),
            base_url=self.base_url_input.text().strip(),
            api_key=self.api_key_input.text().strip(),
            model_name=self.model_input.text().strip(),
        )

        self.service_status_label.setText("测试中...")
        self.service_status_label.setStyleSheet(
            "font-size: 12px; color: #6366f1; background: rgba(99, 102, 241, 0.15); "
            "padding: 6px 12px; border-radius: 6px;"
        )
        QtWidgets.QApplication.processEvents()

        success, message = self.model_services_manager.test_service(temp_service)

        if success:
            self.service_status_label.setText(f"✓ {message}")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 6px 12px; border-radius: 6px;"
            )
        else:
            self.service_status_label.setText(f"✗ {message}")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #ef4444; background: rgba(239, 68, 68, 0.15); "
                "padding: 6px 12px; border-radius: 6px;"
            )

        self._append_log(f"测试服务连接: {message}\n")

    def _add_new_service(self):
        """添加新服务"""
        new_service = ModelServiceConfig(
            name="新服务",
            base_url="http://localhost:8000/v1",
            model_name="autoglm-phone-9b",
            api_key="",
            description="",
        )
        self.model_services_manager.add_service(new_service)
        self._refresh_service_list()

        # Select the new service
        for i in range(self.service_list.count()):
            item = self.service_list.item(i)
            if item.data(QtCore.Qt.UserRole) == new_service.id:
                self.service_list.setCurrentRow(i)
                break

        self._append_log("已添加新服务，请配置详细信息。\n")

    def _delete_current_service(self):
        """删除当前服务"""
        service_id = self._get_current_service_id()
        if not service_id:
            return

        services = self.model_services_manager.get_all_services()
        if len(services) <= 1:
            self._append_log("至少需要保留一个服务。\n")
            return

        service = self.model_services_manager.get_service_by_id(service_id)
        if service:
            reply = QtWidgets.QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除服务 [{service.name}] 吗？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self.model_services_manager.delete_service(service_id)
                self._refresh_service_list()
                self._append_log(f"服务 [{service.name}] 已删除。\n")

    def _activate_current_service(self):
        """激活当前服务"""
        service_id = self._get_current_service_id()
        if not service_id:
            return

        self.model_services_manager.activate_service(service_id)
        self._refresh_service_list()

        service = self.model_services_manager.get_service_by_id(service_id)
        if service:
            self._append_log(f"服务 [{service.name}] 已激活。\n")
            self._load_service_to_form(service)
            self._refresh_dashboard()

    def _on_preset_selected(self, index):
        """从预置模板创建服务"""
        if index <= 0:
            return

        preset_id = self.preset_combo.itemData(index)
        if preset_id:
            new_service = self.model_services_manager.create_from_preset(preset_id)
            if new_service:
                self.model_services_manager.add_service(new_service)
                self._refresh_service_list()

                # Select the new service
                for i in range(self.service_list.count()):
                    item = self.service_list.item(i)
                    if item.data(QtCore.Qt.UserRole) == new_service.id:
                        self.service_list.setCurrentRow(i)
                        break

                self._append_log(f"已从模板创建服务 [{new_service.name}]。\n")

        # Reset combo
        self.preset_combo.setCurrentIndex(0)

    def _build_task_runner(self):
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
        header.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
            color: #fafafa;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        """)

        subtitle = QtWidgets.QLabel("支持多设备并行执行AI驱动的自动化任务")
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: #a1a1aa;
            font-weight: 400;
            letter-spacing: 0.2px;
        """)

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

        preview_controls.addStretch()
        preview_controls.addWidget(self.preview_start_btn)
        preview_controls.addWidget(self.preview_stop_btn)
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
                else:
                    self._append_log(f"  ⚠ {message}\n")

        self.multi_device_manager.start_tasks(devices, task, config)
        self._append_timeline(f"批量任务开始: {len(devices)} 个设备")

    def _stop_multi_task(self):
        """停止所有设备的任务"""
        stopped_tasks = []
        
        # Stop multi-device tasks
        if hasattr(self, 'multi_device_manager') and self.multi_device_manager.workers:
            running_count = len([w for w in self.multi_device_manager.workers.values() if w.isRunning()])
            if running_count > 0:
                self.multi_device_manager.stop_all()
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
        self.scheduled_task_list.setColumnCount(6)
        self.scheduled_task_list.setHorizontalHeaderLabels(
            ["启用", "任务名称", "调度类型", "下次执行", "执行次数", "操作"]
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
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)  # 调度类型 - 可调整
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)  # 下次执行 - 可调整
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Interactive)  # 执行次数 - 可调整
        # 设置默认列宽
        self.scheduled_task_list.setColumnWidth(0, 50)
        self.scheduled_task_list.setColumnWidth(1, 150)
        self.scheduled_task_list.setColumnWidth(2, 70)
        self.scheduled_task_list.setColumnWidth(3, 120)
        self.scheduled_task_list.setColumnWidth(4, 70)
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
        self.sched_device_list.setMinimumHeight(60)
        self.sched_device_list.setMaximumHeight(100)

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
            self.scheduled_task_list.setItem(row, 2, type_item)

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
            self.scheduled_task_list.setItem(row, 3, next_item)

            # Run count
            count_item = QtWidgets.QTableWidgetItem(str(task.run_count))
            self.scheduled_task_list.setItem(row, 4, count_item)

            # Actions - 使用紧凑按钮样式
            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(4)

            # 按钮紧凑样式
            btn_style = """
                QPushButton {
                    padding: 2px 8px;
                    font-size: 11px;
                    min-height: 20px;
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
            self.scheduled_task_list.setCellWidget(row, 5, actions_widget)

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
        self._restore_sched_device_lock()

    def _on_sched_task_failed(self, task_id, msg):
        """定时任务失败回调"""
        self._append_sched_log(f"任务失败: {msg}\n")
        self.scheduled_tasks_manager.mark_task_finished(task_id)
        self._restore_sched_device_lock()

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
        if task_id:
            success, failed = self.multi_device_manager.get_results_summary()
            self._append_sched_log(f"多设备任务完成: {success} 成功, {failed} 失败\n")
            self.scheduled_tasks_manager.mark_task_finished(task_id)
            self._sched_multi_task_id = None
        
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

    def _build_file_manager(self):
        """构建文件管理页面"""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 8)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("📁 文件管理")
        header.setStyleSheet("font-size: 24px; font-weight: 600; color: #fafafa;")

        subtitle = QtWidgets.QLabel("通过 ADB 管理设备文件系统")
        subtitle.setStyleSheet("font-size: 13px; color: #71717a;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Toolbar - 设备选择
        device_toolbar = QtWidgets.QHBoxLayout()
        device_toolbar.setSpacing(8)

        device_label = QtWidgets.QLabel("设备:")
        device_label.setStyleSheet("font-size: 13px; color: #a1a1aa;")

        self.file_device_combo = QtWidgets.QComboBox()
        self.file_device_combo.setMinimumWidth(200)
        self.file_device_combo.setPlaceholderText("选择设备...")
        self.file_device_combo.currentIndexChanged.connect(self._file_manager_device_changed)

        refresh_device_btn = QtWidgets.QPushButton("刷新设备")
        refresh_device_btn.setObjectName("secondary")
        refresh_device_btn.setCursor(QtCore.Qt.PointingHandCursor)
        refresh_device_btn.clicked.connect(self._file_manager_refresh_devices)

        device_toolbar.addWidget(device_label)
        device_toolbar.addWidget(self.file_device_combo)
        device_toolbar.addWidget(refresh_device_btn)
        device_toolbar.addStretch()

        # Toolbar - 路径导航
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(8)

        self.file_path_input = QtWidgets.QLineEdit()
        self.file_path_input.setPlaceholderText("输入路径，如 /sdcard/")
        self.file_path_input.setText("/sdcard/")
        self.file_path_input.returnPressed.connect(self._file_manager_navigate)

        go_btn = QtWidgets.QPushButton("前往")
        go_btn.setObjectName("primary")
        go_btn.setCursor(QtCore.Qt.PointingHandCursor)
        go_btn.clicked.connect(self._file_manager_navigate)

        refresh_btn = QtWidgets.QPushButton("🔄 刷新")
        refresh_btn.setObjectName("secondary")
        refresh_btn.setCursor(QtCore.Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._file_manager_refresh)

        parent_btn = QtWidgets.QPushButton("⬆️ 上级目录")
        parent_btn.setObjectName("secondary")
        parent_btn.setCursor(QtCore.Qt.PointingHandCursor)
        parent_btn.clicked.connect(self._file_manager_go_up)

        toolbar.addWidget(self.file_path_input, 1)
        toolbar.addWidget(go_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(parent_btn)

        # Content area
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(12)

        # Quick access panel
        quick_card = QtWidgets.QFrame()
        quick_card.setObjectName("card")
        quick_card.setFixedWidth(180)
        quick_layout = QtWidgets.QVBoxLayout(quick_card)
        quick_layout.setContentsMargins(12, 12, 12, 12)
        quick_layout.setSpacing(4)

        quick_title = QtWidgets.QLabel("快速访问")
        quick_title.setObjectName("cardTitle")
        quick_layout.addWidget(quick_title)

        quick_paths = [
            ("📱 内部存储", "/sdcard/"),
            ("📸 相册", "/sdcard/DCIM/"),
            ("📥 下载", "/sdcard/Download/"),
            ("🎵 音乐", "/sdcard/Music/"),
            ("🎬 视频", "/sdcard/Movies/"),
            ("📄 文档", "/sdcard/Documents/"),
            ("📦 应用数据", "/data/data/"),
            ("⚙️ 系统", "/system/"),
        ]

        for label, path in quick_paths:
            btn = QtWidgets.QPushButton(label)
            btn.setObjectName("secondary")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setToolTip(path)
            btn.clicked.connect(lambda checked, p=path: self._file_manager_go_to(p))
            quick_layout.addWidget(btn)

        quick_layout.addStretch()

        # File list panel
        file_card = QtWidgets.QFrame()
        file_card.setObjectName("card")
        file_layout = QtWidgets.QVBoxLayout(file_card)
        file_layout.setContentsMargins(12, 12, 12, 12)
        file_layout.setSpacing(8)

        file_title = QtWidgets.QLabel("文件列表")
        file_title.setObjectName("cardTitle")

        self.file_list = QtWidgets.QTreeWidget()
        self.file_list.setHeaderLabels(["名称", "大小", "权限", "修改时间"])
        self.file_list.setColumnWidth(0, 300)
        self.file_list.setColumnWidth(1, 100)
        self.file_list.setColumnWidth(2, 100)
        self.file_list.setColumnWidth(3, 150)
        self.file_list.setRootIsDecorated(False)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.itemDoubleClicked.connect(self._file_manager_item_double_clicked)
        self.file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_manager_context_menu)

        file_layout.addWidget(file_title)
        file_layout.addWidget(self.file_list, 1)

        # Action buttons
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.setSpacing(8)

        upload_btn = QtWidgets.QPushButton("📤 上传文件")
        upload_btn.setObjectName("primary")
        upload_btn.setCursor(QtCore.Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._file_manager_upload)

        download_btn = QtWidgets.QPushButton("📥 下载")
        download_btn.setObjectName("secondary")
        download_btn.setCursor(QtCore.Qt.PointingHandCursor)
        download_btn.clicked.connect(self._file_manager_download)

        new_folder_btn = QtWidgets.QPushButton("📁 新建文件夹")
        new_folder_btn.setObjectName("secondary")
        new_folder_btn.setCursor(QtCore.Qt.PointingHandCursor)
        new_folder_btn.clicked.connect(self._file_manager_new_folder)

        delete_btn = QtWidgets.QPushButton("🗑️ 删除")
        delete_btn.setObjectName("danger")
        delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        delete_btn.clicked.connect(self._file_manager_delete)

        action_layout.addWidget(upload_btn)
        action_layout.addWidget(download_btn)
        action_layout.addWidget(new_folder_btn)
        action_layout.addWidget(delete_btn)
        action_layout.addStretch()

        file_layout.addLayout(action_layout)

        # Status bar
        self.file_status = QtWidgets.QLabel("就绪")
        self.file_status.setStyleSheet(
            "font-size: 11px; color: #71717a; padding: 4px 8px;"
        )

        file_layout.addWidget(self.file_status)

        content_layout.addWidget(quick_card)
        content_layout.addWidget(file_card, 1)

        layout.addWidget(header_widget)
        layout.addLayout(device_toolbar)
        layout.addLayout(toolbar)
        layout.addLayout(content_layout, 1)

        # 初始化时刷新设备列表
        QtCore.QTimer.singleShot(500, self._file_manager_refresh_devices)

        return page

    def _file_manager_refresh_devices(self):
        """刷新文件管理器的设备列表"""
        import subprocess
        
        self.file_device_combo.clear()
        
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            lines = result.stdout.strip().split("\n")[1:]  # 跳过第一行 "List of devices attached"
            for line in lines:
                if "\tdevice" in line:
                    device_id = line.split("\t")[0]
                    self.file_device_combo.addItem(device_id, device_id)
            
            if self.file_device_combo.count() == 0:
                self.file_status.setText("未检测到设备，请连接设备后点击刷新")
            else:
                self.file_status.setText(f"检测到 {self.file_device_combo.count()} 个设备")
                
        except FileNotFoundError:
            self.file_status.setText("ADB 未安装，请先安装 Android SDK Platform Tools")
        except Exception as e:
            self.file_status.setText(f"获取设备列表失败: {str(e)}")

    def _file_manager_device_changed(self, index):
        """设备选择变化时刷新文件列表"""
        if index >= 0:
            self._file_manager_list_dir(self.file_path_input.text().strip())

    def _get_file_manager_device_id(self):
        """获取当前选择的设备ID"""
        if self.file_device_combo.count() > 0:
            return self.file_device_combo.currentData()
        return None

    def _file_manager_navigate(self):
        """导航到指定路径"""
        path = self.file_path_input.text().strip()
        if path:
            self._file_manager_list_dir(path)

    def _file_manager_refresh(self):
        """刷新当前目录"""
        path = self.file_path_input.text().strip()
        if path:
            self._file_manager_list_dir(path)

    def _file_manager_go_up(self):
        """返回上级目录"""
        path = self.file_path_input.text().strip()
        if path and path != "/":
            parent = "/".join(path.rstrip("/").split("/")[:-1])
            if not parent:
                parent = "/"
            self._file_manager_go_to(parent)

    def _file_manager_go_to(self, path):
        """跳转到指定路径"""
        self.file_path_input.setText(path)
        self._file_manager_list_dir(path)

    def _file_manager_list_dir(self, path):
        """列出目录内容"""
        import subprocess
        
        self.file_list.clear()
        
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
            
        self.file_status.setText(f"正在加载: {path}")
        QtWidgets.QApplication.processEvents()

        adb_prefix = ["adb", "-s", device_id]

        try:
            # 使用 ls -la 获取详细信息
            result = subprocess.run(
                adb_prefix + ["shell", f"ls -la '{path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                self.file_status.setText(f"错误: {result.stderr.strip()}")
                return

            lines = result.stdout.strip().split("\n")
            file_count = 0
            dir_count = 0

            for line in lines:
                if not line.strip() or line.startswith("total"):
                    continue

                parts = line.split()
                if len(parts) < 8:
                    continue

                perms = parts[0]
                size = parts[4] if len(parts) > 4 else "-"
                date = f"{parts[5]} {parts[6]}" if len(parts) > 6 else "-"
                name = " ".join(parts[7:]) if len(parts) > 7 else parts[-1]

                # 跳过 . 和 ..
                if name in [".", ".."]:
                    continue

                item = QtWidgets.QTreeWidgetItem()
                
                # 根据类型添加图标
                if perms.startswith("d"):
                    item.setText(0, f"📁 {name}")
                    item.setData(0, QtCore.Qt.UserRole, ("dir", name))
                    dir_count += 1
                elif perms.startswith("l"):
                    item.setText(0, f"🔗 {name}")
                    item.setData(0, QtCore.Qt.UserRole, ("link", name))
                else:
                    # 根据扩展名显示不同图标
                    ext = name.split(".")[-1].lower() if "." in name else ""
                    icon = self._get_file_icon(ext)
                    item.setText(0, f"{icon} {name}")
                    item.setData(0, QtCore.Qt.UserRole, ("file", name))
                    file_count += 1

                item.setText(1, self._format_size(size))
                item.setText(2, perms)
                item.setText(3, date)

                self.file_list.addTopLevelItem(item)

            self.file_status.setText(f"共 {dir_count} 个文件夹, {file_count} 个文件")

        except subprocess.TimeoutExpired:
            self.file_status.setText("操作超时")
        except Exception as e:
            self.file_status.setText(f"错误: {str(e)}")

    def _get_file_icon(self, ext):
        """根据扩展名返回文件图标"""
        icons = {
            "jpg": "🖼️", "jpeg": "🖼️", "png": "🖼️", "gif": "🖼️", "bmp": "🖼️", "webp": "🖼️",
            "mp4": "🎬", "mkv": "🎬", "avi": "🎬", "mov": "🎬", "wmv": "🎬",
            "mp3": "🎵", "wav": "🎵", "flac": "🎵", "aac": "🎵", "ogg": "🎵",
            "apk": "📦", "zip": "📦", "rar": "📦", "7z": "📦", "tar": "📦", "gz": "📦",
            "txt": "📄", "log": "📄", "md": "📄", "json": "📄", "xml": "📄",
            "pdf": "📕", "doc": "📘", "docx": "📘", "xls": "📗", "xlsx": "📗",
            "py": "🐍", "js": "📜", "html": "🌐", "css": "🎨",
        }
        return icons.get(ext, "📄")

    def _format_size(self, size_str):
        """格式化文件大小"""
        try:
            size = int(size_str)
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            else:
                return f"{size / (1024 * 1024 * 1024):.2f} GB"
        except:
            return size_str

    def _file_manager_item_double_clicked(self, item, column):
        """双击项目"""
        data = item.data(0, QtCore.Qt.UserRole)
        if data:
            item_type, name = data
            if item_type == "dir":
                current_path = self.file_path_input.text().strip().rstrip("/")
                new_path = f"{current_path}/{name}"
                self._file_manager_go_to(new_path)

    def _file_manager_context_menu(self, position):
        """右键菜单"""
        item = self.file_list.itemAt(position)
        if not item:
            return

        menu = QtWidgets.QMenu()
        
        download_action = menu.addAction("📥 下载")
        rename_action = menu.addAction("✏️ 重命名")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 删除")

        action = menu.exec_(self.file_list.mapToGlobal(position))

        if action == download_action:
            self._file_manager_download()
        elif action == rename_action:
            self._file_manager_rename()
        elif action == delete_action:
            self._file_manager_delete()

    def _file_manager_upload(self):
        """上传文件到设备"""
        import subprocess
        
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择要上传的文件"
        )
        if not file_path:
            return

        device_path = self.file_path_input.text().strip()
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        self.file_status.setText(f"正在上传: {file_path}")
        QtWidgets.QApplication.processEvents()

        try:
            result = subprocess.run(
                adb_prefix + ["push", file_path, device_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                self.file_status.setText("上传成功")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"上传失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"上传错误: {str(e)}")

    def _file_manager_download(self):
        """从设备下载文件"""
        import subprocess
        
        item = self.file_list.currentItem()
        if not item:
            self.file_status.setText("请先选择要下载的文件")
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return

        item_type, name = data
        if item_type == "dir":
            self.file_status.setText("暂不支持下载文件夹")
            return

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存文件", name
        )
        if not save_path:
            return

        device_path = self.file_path_input.text().strip().rstrip("/") + "/" + name
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        self.file_status.setText(f"正在下载: {name}")
        QtWidgets.QApplication.processEvents()

        try:
            result = subprocess.run(
                adb_prefix + ["pull", device_path, save_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                self.file_status.setText(f"下载成功: {save_path}")
            else:
                self.file_status.setText(f"下载失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"下载错误: {str(e)}")

    def _file_manager_new_folder(self):
        """新建文件夹"""
        import subprocess
        
        name, ok = QtWidgets.QInputDialog.getText(
            self, "新建文件夹", "请输入文件夹名称:"
        )
        if not ok or not name:
            return

        device_path = self.file_path_input.text().strip().rstrip("/") + "/" + name
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        try:
            result = subprocess.run(
                adb_prefix + ["shell", f"mkdir -p '{device_path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.file_status.setText(f"文件夹创建成功: {name}")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"创建失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"创建错误: {str(e)}")

    def _file_manager_delete(self):
        """删除文件或文件夹"""
        import subprocess
        
        item = self.file_list.currentItem()
        if not item:
            self.file_status.setText("请先选择要删除的项目")
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return

        item_type, name = data

        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除 '{name}' 吗？\n此操作不可恢复！",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        device_path = self.file_path_input.text().strip().rstrip("/") + "/" + name
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        # 使用 -rf 删除文件夹
        rm_cmd = "rm -rf" if item_type == "dir" else "rm"

        try:
            result = subprocess.run(
                adb_prefix + ["shell", f"{rm_cmd} '{device_path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.file_status.setText(f"删除成功: {name}")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"删除失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"删除错误: {str(e)}")

    def _file_manager_rename(self):
        """重命名文件或文件夹"""
        import subprocess
        
        item = self.file_list.currentItem()
        if not item:
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return

        item_type, old_name = data

        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "重命名", "请输入新名称:", text=old_name
        )
        if not ok or not new_name or new_name == old_name:
            return

        base_path = self.file_path_input.text().strip().rstrip("/")
        old_path = f"{base_path}/{old_name}"
        new_path = f"{base_path}/{new_name}"
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        try:
            result = subprocess.run(
                adb_prefix + ["shell", f"mv '{old_path}' '{new_path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.file_status.setText(f"重命名成功: {old_name} → {new_name}")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"重命名失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"重命名错误: {str(e)}")

    def _build_scripts_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("脚本管理")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("运行自定义Python自动化脚本")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Scripts List Card
        scripts_card = QtWidgets.QFrame()
        scripts_card.setObjectName("card")
        scripts_layout = QtWidgets.QVBoxLayout(scripts_card)

        scripts_title = QtWidgets.QLabel("可用脚本")
        scripts_title.setObjectName("cardTitle")

        self.script_list = QtWidgets.QListWidget()
        self.script_list.setMinimumHeight(150)

        scripts_layout.addWidget(scripts_title)
        scripts_layout.addWidget(self.script_list)

        # Run Button
        self.run_script_btn = QtWidgets.QPushButton("运行所选脚本")
        self.run_script_btn.setObjectName("success")
        self.run_script_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.run_script_btn.clicked.connect(self._run_script)

        # Output Log Card
        log_card = QtWidgets.QFrame()
        log_card.setObjectName("card")
        log_layout = QtWidgets.QVBoxLayout(log_card)

        log_title = QtWidgets.QLabel("脚本输出")
        log_title.setObjectName("cardTitle")

        self.script_log = QtWidgets.QPlainTextEdit()
        self.script_log.setReadOnly(True)
        self.script_log.setPlaceholderText("脚本输出将显示在这里...")

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.script_log)

        layout.addWidget(header_widget)
        layout.addWidget(scripts_card)
        layout.addWidget(self.run_script_btn)
        layout.addWidget(log_card, 1)
        return page

    def _build_apps_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("应用目录")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("浏览支持自动化的应用程序")
        subtitle.setStyleSheet("color: #71717a; font-size: 14px;")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Search Card
        search_card = QtWidgets.QFrame()
        search_card.setObjectName("card")
        search_layout = QtWidgets.QVBoxLayout(search_card)

        self.apps_search = QtWidgets.QLineEdit()
        self.apps_search.setPlaceholderText("按名称搜索应用...")
        self.apps_search.textChanged.connect(self._filter_apps)

        search_layout.addWidget(self.apps_search)

        # Apps List Card
        apps_card = QtWidgets.QFrame()
        apps_card.setObjectName("card")
        apps_layout = QtWidgets.QVBoxLayout(apps_card)

        apps_title = QtWidgets.QLabel("支持的应用")
        apps_title.setObjectName("cardTitle")

        self.apps_list = QtWidgets.QListWidget()

        apps_layout.addWidget(apps_title)
        apps_layout.addWidget(self.apps_list)

        layout.addWidget(header_widget)
        layout.addWidget(search_card)
        layout.addWidget(apps_card, 1)
        return page

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

        self.default_device_type = NoWheelComboBox()
        self.default_device_type.addItems(["adb", "hdc", "ios"])
        self.default_device_type.currentTextChanged.connect(self._apply_default_device)

        form.addRow("默认设备类型", self.default_device_type)

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

    def _apply_default_device(self, value):
        self.device_type_combo.setCurrentText(value)

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

    def _append_script_log(self, text):
        self.script_log.moveCursor(QtGui.QTextCursor.End)
        self.script_log.insertPlainText(text)
        self.script_log.moveCursor(QtGui.QTextCursor.End)

        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(text)
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _append_diag_log(self, text):
        self.diagnostics_log.moveCursor(QtGui.QTextCursor.End)
        self.diagnostics_log.insertPlainText(text)
        self.diagnostics_log.moveCursor(QtGui.QTextCursor.End)

        self.logs_view.moveCursor(QtGui.QTextCursor.End)
        self.logs_view.insertPlainText(text)
        self.logs_view.moveCursor(QtGui.QTextCursor.End)

    def _refresh_dashboard(self):
        device_type = self.device_type_combo.currentText()
        # Find the metric value labels within each card
        for child in self.metric_device.findChildren(QtWidgets.QLabel):
            if child.objectName() == "metricValue":
                child.setText(device_type.upper())
                break
        # Update model display from active service
        active_service = self.model_services_manager.get_active_service()
        model_name = active_service.model_name if active_service else "-"
        for child in self.metric_model.findChildren(QtWidgets.QLabel):
            if child.objectName() == "metricValue":
                child.setText(model_name or "-")
                break

    def _load_settings(self):
        # Load global settings (device, max_steps, lang)
        self.max_steps_input.setValue(int(self.settings.value("max_steps", 100)))
        self.lang_combo.setCurrentText(self.settings.value("lang", "cn"))
        self.device_type_combo.setCurrentText(
            self.settings.value("device_type", "adb")
        )
        self.default_device_type.setCurrentText(
            self.settings.value("device_type", "adb")
        )
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

    def _increment_tasks_counter(self):
        """Increment the completed tasks counter on the dashboard."""
        metric_label = self.metric_tasks.findChild(QtWidgets.QLabel, "metricValue")
        if metric_label:
            try:
                current = int(metric_label.text()) if metric_label.text() else 0
            except ValueError:
                current = 0
            metric_label.setText(str(current + 1))

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
        if not self.preview_timer.isActive():
            self.preview_timer.start()
        self.preview_status.setText("预览运行中。")
        self.preview_start_btn.setEnabled(False)
        self.preview_stop_btn.setEnabled(True)
        self._request_preview_frame()

    def _stop_preview(self):
        self.preview_timer.stop()
        self.preview_status.setText("预览已停止。")
        self.preview_start_btn.setEnabled(True)
        self.preview_stop_btn.setEnabled(False)

    def _snapshot_preview(self):
        self._request_preview_frame()

    def _request_preview_frame(self):
        if self.preview_inflight:
            return
        self.preview_inflight = True
        device_type = self._current_device_type()
        
        # Use preview device selection if available, otherwise fallback to device list
        device_id = None
        if hasattr(self, 'preview_devices') and self.preview_devices:
            if self.preview_current_index < len(self.preview_devices):
                device = self.preview_devices[self.preview_current_index]
                device_id = device.get('id', '')
        
        # Fallback to device list selection
        if not device_id:
            device_id = self._get_selected_device_id()
            
        if not device_id:
            self.preview_status.setText("未选择设备")
            self.preview_inflight = False
            return
        
        # Only update device status when device changes or first time
        if not hasattr(self, '_last_preview_device_id') or self._last_preview_device_id != device_id:
            self._last_preview_device_id = device_id
            # Update device status only when device changes or first time
            if device_id:
                self.preview_status.setText(f"预览设备: {device_id}")
        
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
            self.preview_status.setText("预览解码失败。")
            return
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

    def _refresh_scripts(self):
        self.script_list.clear()
        roots = [Path("scripts"), Path("examples")]
        items = []
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.glob("*.py")):
                items.append(str(path))
        if not items:
            self.script_list.addItem("没有找到脚本。")
        else:
            self.script_list.addItems(items)

    def _run_script(self):
        current = self.script_list.currentItem()
        if not current:
            self._append_script_log("请选择一个脚本来运行。\n")
            return

        # Check for task conflicts
        if self._check_task_conflicts():
            return

        path = current.text()
        if not os.path.exists(path):
            self._append_script_log("脚本未找到。\n")
            return

        self.script_log.clear()
        self.script_worker = ScriptWorker(path)
        self.script_worker.log.connect(self._append_script_log)
        self.script_worker.finished.connect(
            lambda code: self._append_script_log(f"\n退出代码: {code}\n")
        )
        self.script_worker.failed.connect(
            lambda msg: self._append_script_log(f"\n错误: {msg}\n")
        )
        self.script_worker.start()

    def _refresh_apps(self):
        self.apps_list.clear()
        device_type = self._current_device_type()
        if device_type == DeviceType.HDC:
            apps = list_harmonyos_apps()
        elif device_type == DeviceType.IOS:
            apps = list_ios_apps()
        else:
            apps = list_supported_apps()
        for app in sorted(apps):
            self.apps_list.addItem(app)

    def _filter_apps(self, text):
        for i in range(self.apps_list.count()):
            item = self.apps_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

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
