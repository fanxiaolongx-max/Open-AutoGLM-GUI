"""QR code utilities for Android wireless debugging pairing."""

import base64
import io
import qrcode
import socket
import subprocess
import tempfile
import threading
import time
import logging
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets


class ADBQRCodePairing:
    """
    ADB QR Code pairing for Android wireless debugging.
    
    Generates QR codes in the format: WIFI:T:ADB;S:{name};P:{password};;
    and handles the pairing process.
    """
    
    def __init__(self):
        self.pairing_service_name = f"autoglm_qr_{int(time.time())}"
        self.pairing_password = self._generate_password()
        self.mdns_server = None
        self.pairing_port = None
        self.is_listening = False
        self.logger = logging.getLogger(f"qr_pairing_{self.pairing_service_name}")
        self.logger.setLevel(logging.DEBUG)
        
        # Create handler for detailed logging
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            f"[{self.pairing_service_name}] %(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        self.logger.info(f"QR配对服务初始化: {self.pairing_service_name}")
        self.logger.info(f"配对密码: {self.pairing_password}")
        
    def _generate_password(self) -> str:
        """Generate a 6-digit pairing password."""
        import random
        return str(random.randint(100000, 999999))
    
    def generate_qr_code_data(self) -> str:
        """Generate QR code data for ADB pairing."""
        return f"WIFI:T:ADB;S:{self.pairing_service_name};P:{self.pairing_password};;"
    
    def generate_qr_code_image(self, size: int = 300) -> QtGui.QPixmap:
        """Generate QR code image as QPixmap."""
        qr_data = self.generate_qr_code_data()
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to QPixmap
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        
        # Scale to desired size
        if size != pixmap.width():
            pixmap = pixmap.scaled(
                size, size, 
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
        
        return pixmap
    
    def start_mdns_service(self) -> Tuple[bool, str]:
        """Start mDNS service for ADB pairing discovery."""
        try:
            self.logger.info("启动mDNS服务...")
            
            # Find available port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('', 0))
            self.pairing_port = sock.getsockname()[1]
            sock.close()
            
            self.logger.info(f"分配端口: {self.pairing_port}")
            
            # Start mDNS service using dns-sd (available on macOS/Linux)
            # On Windows, we'd need a different approach
            cmd = [
                'dns-sd', '-R', 
                self.pairing_service_name,
                '_adb-tls-pairing._tcp',
                'local',
                str(self.pairing_port)
            ]
            
            self.logger.info(f"执行命令: {' '.join(cmd)}")
            
            self.mdns_server = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0
            )
            
            # Give it a moment to start
            time.sleep(0.5)
            
            if self.mdns_server.poll() is None:  # Process is still running
                self.is_listening = True
                self.logger.info("✅ mDNS服务启动成功")
                
                # Start monitoring thread for device requests
                threading.Thread(target=self._monitor_mdns_requests, daemon=True).start()
                
                return True, f"mDNS service started on port {self.pairing_port}"
            else:
                stdout, stderr = self.mdns_server.communicate()
                self.logger.error(f"mDNS服务启动失败: {stderr.decode()}")
                return False, "Failed to start mDNS service"
                
        except FileNotFoundError:
            # dns-sd not available, try alternative approach
            self.logger.warning("dns-sd不可用，尝试zeroconf...")
            return self._start_alternative_mdns()
        except Exception as e:
            self.logger.error(f"mDNS服务启动异常: {e}")
            return False, f"Failed to start mDNS service: {str(e)}"
    
    def _monitor_mdns_requests(self):
        """Monitor mDNS requests from Android devices."""
        self.logger.info("开始监控Android设备请求...")
        
        while self.is_listening and self.mdns_server:
            try:
                # Check if there's any output from dns-sd
                if self.mdns_server.poll() is not None:
                    stdout, stderr = self.mdns_server.communicate()
                    if stdout:
                        self.logger.info(f"mDNS输出: {stdout.decode()}")
                    if stderr:
                        self.logger.warning(f"mDNS错误: {stderr.decode()}")
                    break
                    
                # Monitor ADB for device connections
                try:
                    result = subprocess.run(
                        ["adb", "devices"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    
                    output = result.stdout
                    if "device" in output:
                        lines = output.strip().split('\n')[1:]  # Skip header
                        for line in lines:
                            if '\tdevice' in line:
                                device_id = line.split('\t')[0]
                                self.logger.info(f"📱 检测到设备连接: {device_id}")
                                
                                # Get device info
                                try:
                                    model_result = subprocess.run(
                                        ["adb", "-s", device_id, "shell", "getprop", "ro.product.model"],
                                        capture_output=True,
                                        text=True,
                                        timeout=5
                                    )
                                    model = model_result.stdout.strip()
                                    
                                    version_result = subprocess.run(
                                        ["adb", "-s", device_id, "shell", "getprop", "ro.build.version.release"],
                                        capture_output=True,
                                        text=True,
                                        timeout=5
                                    )
                                    version = version_result.stdout.strip()
                                    
                                    self.logger.info(f"📱 设备信息: {model} (Android {version})")
                                    
                                except Exception as e:
                                    self.logger.warning(f"获取设备信息失败: {e}")
                                    
                except subprocess.TimeoutExpired:
                    pass
                except Exception as e:
                    self.logger.warning(f"ADB检查异常: {e}")
                
                time.sleep(3)  # Check every 3 seconds
                
            except Exception as e:
                self.logger.error(f"监控线程异常: {e}")
                break
                
        self.logger.info("监控线程结束")
    
    def _start_alternative_mdns(self) -> Tuple[bool, str]:
        """Alternative mDNS implementation using zeroconf."""
        try:
            from zeroconf import ServiceInfo, Zeroconf, ServiceListener
            
            class PairingListener(ServiceListener):
                def __init__(self, parent):
                    self.parent = parent
                    
                def add_service(self, zeroconf, type, name):
                    self.parent.logger.info(f"🔍 发现服务: {name} (类型: {type})")
                    
                def remove_service(self, zeroconf, type, name):
                    self.parent.logger.info(f"❌ 服务移除: {name}")
                    
                def update_service(self, zeroconf, type, name):
                    self.parent.logger.debug(f"🔄 服务更新: {name}")
            
            self.logger.info("使用zeroconf启动mDNS服务...")
            
            # Create service info
            info = ServiceInfo(
                "_adb-tls-pairing._tcp.local.",
                f"{self.pairing_service_name}._adb-tls-pairing._tcp.local.",
                addresses=[socket.inet_aton(socket.gethostbyname(socket.gethostname()))],
                port=self.pairing_port,
                properties={},
            )
            
            self.logger.info(f"注册服务: {info.name} 在端口 {info.port}")
            
            self.zeroconf = Zeroconf()
            self.zeroconf.register_service(info)
            self.is_listening = True
            
            self.logger.info("✅ zeroconf mDNS服务启动成功")
            
            # Start monitoring thread
            threading.Thread(target=self._monitor_mdns_requests, daemon=True).start()
            
            return True, f"Alternative mDNS service started on port {self.pairing_port}"
            
        except ImportError:
            return False, "Neither dns-sd nor zeroconf available for mDNS"
        except Exception as e:
            return False, f"Failed to start alternative mDNS: {str(e)}"
    
    def stop_mdns_service(self):
        """Stop mDNS service."""
        self.logger.info("停止mDNS服务...")
        self.is_listening = False
        
        if self.mdns_server:
            try:
                self.logger.info("终止dns-sd进程...")
                self.mdns_server.terminate()
                self.mdns_server.wait(timeout=5)
                self.logger.info("✅ dns-sd进程已终止")
            except:
                try:
                    self.logger.warning("强制终止dns-sd进程...")
                    self.mdns_server.kill()
                    self.logger.info("✅ dns-sd进程已强制终止")
                except:
                    self.logger.error("❌ 无法终止dns-sd进程")
            self.mdns_server = None
        
        if hasattr(self, 'zeroconf'):
            try:
                self.logger.info("关闭zeroconf服务...")
                self.zeroconf.unregister_all_services()
                self.zeroconf.close()
                self.logger.info("✅ zeroconf服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭zeroconf服务失败: {e}")
            self.zeroconf = None
        
        self.logger.info("mDNS服务已停止")
    
    def wait_for_pairing(self, timeout: int = 60, callback=None) -> Tuple[bool, str]:
        """Wait for device pairing to complete."""
        if not self.is_listening:
            self.logger.error("mDNS服务未运行")
            return False, "mDNS service not running"
        
        self.logger.info(f"开始等待设备配对，超时时间: {timeout}秒")
        start_time = time.time()
        
        while time.time() - start_time < timeout and self.is_listening:
            # Check if we can detect paired devices
            try:
                result = subprocess.run(
                    ["adb", "devices"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                output = result.stdout
                self.logger.debug(f"ADB设备列表: {output.strip()}")
                
                if "device" in output and "offline" not in output:
                    # Found a connected device
                    lines = output.strip().split('\n')[1:]  # Skip header
                    for line in lines:
                        if '\tdevice' in line:
                            device_id = line.split('\t')[0]
                            self.logger.info(f"🎉 设备配对成功: {device_id}")
                            
                            if callback:
                                callback(f"设备已配对并连接: {device_id}")
                            return True, f"设备配对成功: {device_id}"
                
            except subprocess.TimeoutExpired:
                self.logger.warning("ADB命令超时")
                pass
            except Exception as e:
                self.logger.error(f"ADB检查异常: {e}")
                pass
            
            if callback:
                elapsed = int(time.time() - start_time)
                callback(f"等待设备配对... ({elapsed}/{timeout}秒)")
            
            time.sleep(2)
        
        self.logger.error("配对超时")
        return False, "配对超时"
    
    def get_pairing_info(self) -> dict:
        """Get current pairing information."""
        return {
            "service_name": self.pairing_service_name,
            "password": self.pairing_password,
            "port": self.pairing_port,
            "qr_data": self.generate_qr_code_data(),
            "is_listening": self.is_listening
        }


class QRCodeDialog(QtWidgets.QDialog):
    """Dialog for displaying QR code and managing pairing process."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Android 设备二维码配对")
        self.setModal(True)
        self.setMinimumSize(600, 700)
        
        self.pairing = ADBQRCodePairing()
        self.setup_ui()
        
    def setup_ui(self):
        """Setup dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QtWidgets.QLabel("扫描二维码进行设备配对")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        
        # Instructions
        instructions = QtWidgets.QLabel(
            "1. 确保Android设备已开启开发者选项和无线调试\n"
            "2. 在设备上选择'使用二维码配对设备'\n"
            "3. 扫描下方二维码完成配对"
        )
        instructions.setStyleSheet("color: #666; font-size: 14px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # QR Code display
        self.qr_label = QtWidgets.QLabel()
        self.qr_label.setAlignment(QtCore.Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        layout.addWidget(self.qr_label)
        
        # Pairing info
        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet("color: #333; font-size: 12px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        # Status
        self.status_label = QtWidgets.QLabel("准备生成二维码...")
        self.status_label.setStyleSheet("color: #666; font-size: 14px;")
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Log display
        log_group = QtWidgets.QGroupBox("详细日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        
        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.refresh_btn = QtWidgets.QPushButton("刷新二维码")
        self.refresh_btn.clicked.connect(self.refresh_qr_code)
        
        self.cancel_btn = QtWidgets.QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Generate initial QR code
        self.refresh_qr_code()
    
    def append_log(self, message):
        """Append log message to log display."""
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.log_text.appendPlainText(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def refresh_qr_code(self):
        """Refresh QR code and start pairing service."""
        # Clear previous logs
        self.log_text.clear()
        self.append_log("开始刷新二维码...")
        
        # Stop previous service
        self.pairing.stop_mdns_service()
        
        # Create new pairing instance
        self.pairing = ADBQRCodePairing()
        
        # Connect logging to UI
        import logging
        class LogHandler(logging.Handler):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                
            def emit(self, record):
                msg = self.format(record)
                QtCore.QMetaObject.invokeMethod(
                    self.parent, "append_log",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, msg)
                )
        
        handler = LogHandler(self)
        handler.setLevel(logging.DEBUG)
        self.pairing.logger.addHandler(handler)
        
        # Generate QR code
        pixmap = self.pairing.generate_qr_code_image(300)
        self.qr_label.setPixmap(pixmap)
        self.append_log("二维码生成完成")
        
        # Show pairing info
        info = self.pairing.get_pairing_info()
        self.info_label.setText(
            f"服务名: {info['service_name']}\n"
            f"配对码: {info['password']}\n"
            f"端口: {info['port'] or '启动中...'}"
        )
        self.append_log(f"配对信息: 服务名={info['service_name']}, 密码={info['password']}")
        
        # Start mDNS service
        success, message = self.pairing.start_mdns_service()
        if success:
            self.status_label.setText("二维码已生成，等待设备扫描...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.append_log("✅ mDNS服务启动成功")
            
            # Start pairing monitoring in background
            threading.Thread(
                target=self._monitor_pairing,
                daemon=True
            ).start()
        else:
            self.status_label.setText(f"启动服务失败: {message}")
            self.progress_bar.setVisible(False)
            self.append_log(f"❌ mDNS服务启动失败: {message}")
    
    def finish_pairing(self):
        """Finish pairing process (called from Qt thread)."""
        self.progress_bar.setVisible(False)
        success = hasattr(self, '_pairing_success') and self._pairing_success
        message = getattr(self, '_pairing_message', '')
        
        if success:
            self.status_label.setText(f"✅ {message}")
            self.append_log(f"🎉 配对成功: {message}")
            QtWidgets.QMessageBox.information(self, "配对成功", message)
            self.accept()
        else:
            self.status_label.setText(f"❌ {message}")
            self.append_log(f"❌ 配对失败: {message}")
    
    def _monitor_pairing(self):
        """Monitor pairing process in background."""
        def update_status(text):
            QtCore.QMetaObject.invokeMethod(
                self.status_label, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, text)
            )
        
        self.append_log("开始监控配对过程...")
        success, message = self.pairing.wait_for_pairing(
            timeout=120,
            callback=lambda text: update_status(text)
        )
        
        # Store results for Qt thread
        self._pairing_success = success
        self._pairing_message = message
        
        # Call finish_pairing in Qt thread
        QtCore.QMetaObject.invokeMethod(
            self, "finish_pairing", 
            QtCore.Qt.QueuedConnection
        )
    
    def closeEvent(self, event):
        """Clean up when dialog is closed."""
        self.append_log("关闭对话框，停止配对服务...")
        self.pairing.stop_mdns_service()
        super().closeEvent(event)
    
    def get_paired_device(self) -> Optional[str]:
        """Get the paired device ID after successful pairing."""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            output = result.stdout
            lines = output.strip().split('\n')[1:]  # Skip header
            for line in lines:
                if '\tdevice' in line:
                    return line.split('\t')[0]
        except:
            pass
        return None
