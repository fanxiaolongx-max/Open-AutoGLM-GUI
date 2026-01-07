"""Direct QR code pairing for Android wireless debugging without DNS service."""

import base64
import io
import qrcode
import socket
import subprocess
import tempfile
import threading
import time
import logging
import json
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets


class DirectADBQRPairing:
    """
    Direct ADB QR Code pairing for Android wireless debugging.
    
    Uses direct IP connection instead of DNS service.
    Format: WIFI:T:ADB;S:{ip}:{port};P:{password};;
    """
    
    def __init__(self, target_ip: str = "192.168.1.100", target_port: int = 37000):
        self.target_ip = target_ip
        self.target_port = target_port
        self.pairing_password = self._generate_password()
        self.logger = logging.getLogger(f"direct_qr_pair_{int(time.time())}")
        self.logger.setLevel(logging.DEBUG)
        
        # Create handler for detailed logging
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            f"[direct_qr_pair] %(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        self.logger.info(f"直接QR配对初始化: {target_ip}:{target_port}")
        self.logger.info(f"配对密码: {self.pairing_password}")
        
    def _generate_password(self) -> str:
        """Generate a 6-digit pairing password."""
        import random
        return str(random.randint(100000, 999999))
    
    def generate_qr_code(self) -> QtGui.QPixmap:
        """Generate QR code for direct connection."""
        # Format: WIFI:T:ADB;S:IP:Port;P:Password;;
        qr_data = f"WIFI:T:ADB;S:{self.target_ip}:{self.target_port};P:{self.pairing_password};;"
        
        self.logger.info(f"生成QR码: {qr_data}")
        
        # Generate QR code
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
        qimage = QtGui.QImage()
        qimage.loadFromData(buffer.getvalue())
        pixmap = QtGui.QPixmap.fromImage(qimage)
        
        return pixmap
    
    def start_pairing_monitor(self, callback=None) -> threading.Thread:
        """Start monitoring for pairing completion."""
        def monitor():
            self.logger.info("开始监控配对状态...")
            
            # Wait for pairing to complete
            timeout = 120  # 2 minutes timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    # Check if device is paired and connected
                    result = subprocess.run(
                        ['adb', 'devices'], 
                        capture_output=True, 
                        text=True, 
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')[1:]  # Skip header
                        for line in lines:
                            if '\t' in line:
                                device_id, status = line.split('\t')
                                if status == 'device':
                                    self.logger.info(f"发现已连接设备: {device_id}")
                                    if callback:
                                        callback(f"✅ 配对成功！设备: {device_id}")
                                    return device_id
                    
                    if callback:
                        callback(f"等待配对中... ({int(time.time() - start_time)}s)")
                    
                    time.sleep(2)
                    
                except subprocess.TimeoutExpired:
                    continue
                except Exception as e:
                    self.logger.error(f"监控配对时出错: {e}")
                    if callback:
                        callback(f"❌ 监控出错: {str(e)}")
                    break
            
            self.logger.warning("配对超时")
            if callback:
                callback("⏰ 配对超时，请重试")
            return None
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        return thread


class DirectQRCodeDialog(QtWidgets.QDialog):
    """Dialog for direct QR code pairing without DNS service."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 直接二维码配对")
        self.setFixedSize(500, 600)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        
        self.pairing = None
        self.monitor_thread = None
        self.paired_device = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QtWidgets.QLabel("📱 直接二维码配对")
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: 600;
            color: #fafafa;
            margin-bottom: 10px;
        """)
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        
        # Description
        desc = QtWidgets.QLabel(
            "请确保手机和电脑在同一局域网内，\n"
            "然后使用手机扫描下方二维码进行配对。"
        )
        desc.setStyleSheet("""
            font-size: 14px;
            color: #a1a1aa;
            margin-bottom: 20px;
        """)
        desc.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(desc)
        
        # IP Input section
        ip_layout = QtWidgets.QHBoxLayout()
        ip_label = QtWidgets.QLabel("设备IP:")
        ip_label.setStyleSheet("font-size: 14px; color: #d4d4d8;")
        
        self.ip_input = QtWidgets.QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        self.ip_input.setText("192.168.1.100")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background: rgba(24, 24, 27, 0.8);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 8px;
                padding: 8px 12px;
                color: #fafafa;
                font-size: 14px;
            }
        """)
        
        port_label = QtWidgets.QLabel("端口:")
        port_label.setStyleSheet("font-size: 14px; color: #d4d4d8;")
        
        self.port_input = QtWidgets.QSpinBox()
        self.port_input.setRange(30000, 60000)
        self.port_input.setValue(37000)
        self.port_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.port_input.setStyleSheet("""
            QSpinBox {
                background: rgba(24, 24, 27, 0.8);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 8px;
                padding: 8px 12px;
                color: #fafafa;
                font-size: 14px;
            }
        """)
        
        self.generate_btn = QtWidgets.QPushButton("生成二维码")
        self.generate_btn.setObjectName("primary")
        self.generate_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self._generate_qr_code)
        
        ip_layout.addWidget(ip_label)
        ip_layout.addWidget(self.ip_input)
        ip_layout.addWidget(port_label)
        ip_layout.addWidget(self.port_input)
        ip_layout.addWidget(self.generate_btn)
        ip_layout.addStretch()
        
        layout.addLayout(ip_layout)
        
        # QR Code display
        self.qr_label = QtWidgets.QLabel()
        self.qr_label.setAlignment(QtCore.Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet("""
            QLabel {
                background: white;
                border: 2px solid rgba(63, 63, 70, 0.3);
                border-radius: 12px;
                padding: 20px;
            }
        """)
        self.qr_label.setText("请输入IP地址并生成二维码")
        layout.addWidget(self.qr_label)
        
        # Password display
        self.password_label = QtWidgets.QLabel()
        self.password_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: #6366f1;
            background: rgba(99, 102, 241, 0.1);
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 8px;
            padding: 10px 20px;
        """)
        self.password_label.setAlignment(QtCore.Qt.AlignCenter)
        self.password_label.setVisible(False)
        layout.addWidget(self.password_label)
        
        # Status
        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("""
            font-size: 14px;
            color: #71717a;
            margin-top: 10px;
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.cancel_btn = QtWidgets.QPushButton("取消")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.ok_btn = QtWidgets.QPushButton("完成")
        self.ok_btn.setObjectName("success")
        self.ok_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setEnabled(False)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.ok_btn)
        
        layout.addLayout(button_layout)
        
        # Generate initial QR code
        self._generate_qr_code()
    
    def _generate_qr_code(self):
        """Generate QR code with current IP and port."""
        ip = self.ip_input.text().strip()
        port = self.port_input.value()
        
        if not ip:
            self.status_label.setText("❌ 请输入设备IP地址")
            return
        
        # Validate IP format
        try:
            socket.inet_aton(ip)
        except socket.error:
            self.status_label.setText("❌ IP地址格式不正确")
            return
        
        try:
            # Create pairing instance
            self.pairing = DirectADBQRPairing(ip, port)
            
            # Generate and display QR code
            pixmap = self.pairing.generate_qr_code()
            self.qr_label.setPixmap(pixmap.scaled(300, 300, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            
            # Show password
            self.password_label.setText(f"🔑 配对码: {self.pairing.pairing_password}")
            self.password_label.setVisible(True)
            
            # Start monitoring
            self.status_label.setText("📱 请使用手机扫描二维码...")
            self.monitor_thread = self.pairing.start_pairing_monitor(self._on_status_update)
            
        except Exception as e:
            self.status_label.setText(f"❌ 生成二维码失败: {str(e)}")
    
    def _on_status_update(self, text):
        """Handle status updates from pairing monitor."""
        # Update status in main thread
        QtCore.QMetaObject.invokeMethod(
            self.status_label, "setText",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, text)
        )
        
        # Check if pairing succeeded
        if "✅ 配对成功" in text:
            self.paired_device = text.split("设备: ")[-1]
            self.ok_btn.setEnabled(True)
            QtCore.QMetaObject.invokeMethod(
                self, "accept",
                QtCore.Qt.QueuedConnection
            )
    
    def get_paired_device(self) -> Optional[str]:
        """Get the paired device ID."""
        return self.paired_device
