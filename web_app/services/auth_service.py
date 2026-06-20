# -*- coding: utf-8 -*-
"""Username/password authentication and signed browser sessions."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from web_app.services.config_storage import config_storage


AUTH_CONFIG_KEY = "login_auth"
SESSION_COOKIE_NAME = "autoglm_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
PBKDF2_ITERATIONS = 310_000


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return _b64encode(digest)


@dataclass
class AuthConfig:
    username: str
    password_salt: str
    password_hash: str
    session_secret: str
    revision: int = 1


class AuthService:
    """Persist credentials and issue tamper-resistant, expiring session tokens."""

    def __init__(self):
        self.config = self._load_or_create()

    def _load_or_create(self) -> AuthConfig:
        data = config_storage.get(AUTH_CONFIG_KEY)
        required = {"username", "password_salt", "password_hash", "session_secret"}
        if isinstance(data, dict) and required.issubset(data):
            return AuthConfig(
                username=str(data["username"]),
                password_salt=str(data["password_salt"]),
                password_hash=str(data["password_hash"]),
                session_secret=str(data["session_secret"]),
                revision=max(1, int(data.get("revision", 1))),
            )

        salt = secrets.token_bytes(16)
        config = AuthConfig(
            username="admin",
            password_salt=_b64encode(salt),
            password_hash=_hash_password("admin", salt),
            session_secret=secrets.token_urlsafe(48),
        )
        self._save(config)
        return config

    def _save(self, config: AuthConfig) -> None:
        config_storage.set(
            AUTH_CONFIG_KEY,
            {
                "username": config.username,
                "password_salt": config.password_salt,
                "password_hash": config.password_hash,
                "session_secret": config.session_secret,
                "revision": config.revision,
            },
            "auth",
        )

    def verify_credentials(self, username: str, password: str) -> bool:
        if not hmac.compare_digest(username, self.config.username):
            return False
        candidate = _hash_password(password, _b64decode(self.config.password_salt))
        return hmac.compare_digest(candidate, self.config.password_hash)

    def create_session(self) -> str:
        payload = {
            "u": self.config.username,
            "r": self.config.revision,
            "exp": int(time.time()) + SESSION_MAX_AGE,
            "n": secrets.token_urlsafe(12),
        }
        encoded = _b64encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        signature = hmac.new(
            self.config.session_secret.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded}.{_b64encode(signature)}"

    def verify_session(self, token: str) -> bool:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = hmac.new(
                self.config.session_secret.encode("utf-8"),
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(
                _b64decode(supplied_signature), expected_signature
            ):
                return False
            payload = json.loads(_b64decode(encoded))
            return (
                payload.get("u") == self.config.username
                and int(payload.get("r", 0)) == self.config.revision
                and int(payload.get("exp", 0)) >= int(time.time())
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            return False

    def update_credentials(
        self,
        current_password: str,
        username: str,
        new_password: str,
    ) -> bool:
        if not self.verify_credentials(self.config.username, current_password):
            return False

        salt = secrets.token_bytes(16)
        self.config.username = username.strip()
        self.config.password_salt = _b64encode(salt)
        self.config.password_hash = _hash_password(new_password, salt)
        self.config.revision += 1
        self.config.session_secret = secrets.token_urlsafe(48)
        self._save(self.config)
        return True


auth_service = AuthService()
