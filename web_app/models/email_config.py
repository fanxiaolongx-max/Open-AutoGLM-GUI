# -*- coding: utf-8 -*-
"""
Email configuration data model.
Pure dataclass without Qt dependencies.
"""

from dataclasses import dataclass, asdict


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
