# -*- coding: utf-8 -*-
"""邮件服务模块 - 用于发送任务执行报告邮件"""

import json
import smtplib
import ssl
from dataclasses import dataclass, asdict
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6 import QtCore


@dataclass
class EmailConfig:
    """邮件服务器配置"""
    smtp_server: str = ""
    smtp_port: int = 465
    use_ssl: bool = True
    use_tls: bool = False
    sender_email: str = ""
    sender_password: str = ""
    recipient_emails: str = ""  # 逗号分隔的收件人列表
    enabled: bool = False  # 是否启用自动发送

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EmailConfig":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    def get_recipients(self) -> list[str]:
        """获取收件人列表"""
        if not self.recipient_emails:
            return []
        return [email.strip() for email in self.recipient_emails.split(",") if email.strip()]


class EmailService(QtCore.QObject):
    """邮件发送服务"""

    send_started = QtCore.Signal()
    send_finished = QtCore.Signal(bool, str)  # success, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = EmailConfig()
        self.config_file = Path.home() / ".autoglm" / "email_config.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()

    def _load_config(self):
        """从配置文件加载邮件配置"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.config = EmailConfig.from_dict(data)
            except Exception:
                self.config = EmailConfig()

    def _save_config(self):
        """保存邮件配置到文件"""
        self.config_file.write_text(
            json.dumps(self.config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def update_config(self, config: EmailConfig):
        """更新邮件配置"""
        self.config = config
        self._save_config()

    def get_config(self) -> EmailConfig:
        """获取当前邮件配置"""
        return self.config

    def send_task_report(
        self,
        task_name: str,
        success_count: int,
        failed_count: int,
        total_count: int,
        details: str,
        screenshot_data: Optional[bytes] = None,
        is_scheduled: bool = False
    ) -> tuple[bool, str]:
        """
        发送任务执行报告邮件

        Args:
            task_name: 任务名称
            success_count: 成功数量
            failed_count: 失败数量
            total_count: 总数量
            details: 执行详情日志
            screenshot_data: 截图二进制数据（可选）
            is_scheduled: 是否是定时任务

        Returns:
            (success, message) 元组
        """
        if not self.config.enabled:
            return False, "邮件发送未启用"

        if not self.config.smtp_server or not self.config.sender_email:
            return False, "邮件服务器未配置"

        recipients = self.config.get_recipients()
        if not recipients:
            return False, "未配置收件人"

        try:
            self.send_started.emit()

            # 创建邮件
            msg = MIMEMultipart("related")

            # 邮件主题
            task_type = "定时任务" if is_scheduled else "手动任务"
            status = "成功" if failed_count == 0 else "部分失败" if success_count > 0 else "失败"
            msg["Subject"] = f"[鱼塘管理器] {task_type}执行报告 - {status}"
            msg["From"] = self.config.sender_email
            msg["To"] = ", ".join(recipients)

            # 构建 HTML 正文
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 状态颜色
            if failed_count == 0:
                status_color = "#10b981"  # 绿色
                status_bg = "#d1fae5"
            elif success_count > 0:
                status_color = "#f59e0b"  # 橙色
                status_bg = "#fef3c7"
            else:
                status_color = "#ef4444"  # 红色
                status_bg = "#fee2e2"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #e5e5e5;
            padding-bottom: 20px;
            margin-bottom: 25px;
        }}
        .header h1 {{
            color: #18181b;
            margin: 0;
            font-size: 24px;
        }}
        .header .subtitle {{
            color: #71717a;
            font-size: 14px;
            margin-top: 8px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 16px;
            background: {status_bg};
            color: {status_color};
            margin: 15px 0;
        }}
        .stats {{
            display: flex;
            justify-content: space-around;
            margin: 25px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 8px;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: 700;
            color: #18181b;
        }}
        .stat-label {{
            font-size: 13px;
            color: #71717a;
            margin-top: 4px;
        }}
        .stat-success .stat-value {{ color: #10b981; }}
        .stat-failed .stat-value {{ color: #ef4444; }}
        .section {{
            margin: 25px 0;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: #18181b;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e5e5e5;
        }}
        .details {{
            background: #18181b;
            color: #a1a1aa;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 12px;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
        }}
        .screenshot {{
            text-align: center;
            margin: 20px 0;
        }}
        .screenshot img {{
            max-width: 300px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }}
        .footer {{
            text-align: center;
            color: #a1a1aa;
            font-size: 12px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e5e5e5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>鱼塘管理器 - 任务执行报告</h1>
            <div class="subtitle">{task_type} | {now}</div>
        </div>

        <div style="text-align: center;">
            <span class="status-badge">{status}</span>
        </div>

        <div class="section">
            <div class="section-title">任务信息</div>
            <p><strong>任务名称:</strong> {task_name}</p>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{total_count}</div>
                <div class="stat-label">总设备数</div>
            </div>
            <div class="stat stat-success">
                <div class="stat-value">{success_count}</div>
                <div class="stat-label">成功</div>
            </div>
            <div class="stat stat-failed">
                <div class="stat-value">{failed_count}</div>
                <div class="stat-label">失败</div>
            </div>
        </div>

        {"<div class='section'><div class='section-title'>执行截图</div><div class='screenshot'><img src='cid:screenshot'></div></div>" if screenshot_data else ""}

        <div class="section">
            <div class="section-title">执行日志</div>
            <div class="details">{details[-2000:] if len(details) > 2000 else details}</div>
        </div>

        <div class="footer">
            此邮件由鱼塘管理器自动发送<br>
            AI驱动的手机自动化工具
        </div>
    </div>
</body>
</html>
"""

            # 添加 HTML 正文
            msg_alternative = MIMEMultipart("alternative")
            msg.attach(msg_alternative)

            # 纯文本版本
            text_body = f"""
鱼塘管理器 - 任务执行报告
========================

任务类型: {task_type}
执行时间: {now}
任务名称: {task_name}
执行状态: {status}

执行统计:
- 总设备数: {total_count}
- 成功: {success_count}
- 失败: {failed_count}

执行日志:
{details[-2000:] if len(details) > 2000 else details}

---
此邮件由鱼塘管理器自动发送
"""
            msg_alternative.attach(MIMEText(text_body, "plain", "utf-8"))
            msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))

            # 添加截图附件
            if screenshot_data:
                img = MIMEImage(screenshot_data)
                img.add_header("Content-ID", "<screenshot>")
                img.add_header("Content-Disposition", "inline", filename="screenshot.png")
                msg.attach(img)

            # 发送邮件
            if self.config.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    context=context
                ) as server:
                    server.login(self.config.sender_email, self.config.sender_password)
                    server.sendmail(
                        self.config.sender_email,
                        recipients,
                        msg.as_string()
                    )
            else:
                with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                    if self.config.use_tls:
                        server.starttls()
                    server.login(self.config.sender_email, self.config.sender_password)
                    server.sendmail(
                        self.config.sender_email,
                        recipients,
                        msg.as_string()
                    )

            self.send_finished.emit(True, "邮件发送成功")
            return True, "邮件发送成功"

        except smtplib.SMTPAuthenticationError:
            error_msg = "邮件认证失败，请检查邮箱和密码/授权码"
            self.send_finished.emit(False, error_msg)
            return False, error_msg
        except smtplib.SMTPConnectError:
            error_msg = "无法连接到邮件服务器，请检查服务器地址和端口"
            self.send_finished.emit(False, error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"邮件发送失败: {str(e)}"
            self.send_finished.emit(False, error_msg)
            return False, error_msg

    def send_test_email(self) -> tuple[bool, str]:
        """发送测试邮件"""
        if not self.config.smtp_server or not self.config.sender_email:
            return False, "请先配置邮件服务器信息"

        recipients = self.config.get_recipients()
        if not recipients:
            return False, "请先配置收件人"

        # 临时启用发送
        original_enabled = self.config.enabled
        self.config.enabled = True

        try:
            success, message = self.send_task_report(
                task_name="测试任务",
                success_count=1,
                failed_count=0,
                total_count=1,
                details="这是一封测试邮件，用于验证邮件配置是否正确。\n\n如果您收到此邮件，说明邮件服务配置成功！",
                screenshot_data=None,
                is_scheduled=False
            )
            return success, message
        finally:
            self.config.enabled = original_enabled


class EmailSendWorker(QtCore.QThread):
    """邮件发送 Worker 线程"""
    finished = QtCore.Signal(bool, str)

    def __init__(
        self,
        email_service: EmailService,
        task_name: str,
        success_count: int,
        failed_count: int,
        total_count: int,
        details: str,
        screenshot_data: Optional[bytes] = None,
        is_scheduled: bool = False
    ):
        super().__init__()
        self.email_service = email_service
        self.task_name = task_name
        self.success_count = success_count
        self.failed_count = failed_count
        self.total_count = total_count
        self.details = details
        self.screenshot_data = screenshot_data
        self.is_scheduled = is_scheduled

    def run(self):
        success, message = self.email_service.send_task_report(
            task_name=self.task_name,
            success_count=self.success_count,
            failed_count=self.failed_count,
            total_count=self.total_count,
            details=self.details,
            screenshot_data=self.screenshot_data,
            is_scheduled=self.is_scheduled
        )
        self.finished.emit(success, message)
