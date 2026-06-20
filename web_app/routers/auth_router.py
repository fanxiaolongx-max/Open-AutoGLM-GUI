# -*- coding: utf-8 -*-
"""Browser login API."""

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from web_app.services.auth_service import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    auth_service,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])
_login_failures: dict[str, deque[float]] = defaultdict(deque)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class CredentialsRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=4, max_length=256)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


@router.get("/status")
async def auth_status(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    authenticated = auth_service.verify_session(token)
    return {
        "authenticated": authenticated,
        "username": auth_service.config.username if authenticated else "",
        "default_credentials": (
            auth_service.config.username == "admin"
            and auth_service.verify_credentials("admin", "admin")
        ),
    }


@router.post("/login")
async def login(request: Request, body: LoginRequest, response: Response):
    client = _client_key(request)
    now = time.monotonic()
    failures = _login_failures[client]
    while failures and now - failures[0] > 300:
        failures.popleft()
    if len(failures) >= 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请稍后再试",
        )

    if not auth_service.verify_credentials(body.username, body.password):
        failures.append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )

    failures.clear()
    _set_session_cookie(request, response, auth_service.create_session())
    return {"success": True, "username": auth_service.config.username}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"success": True}


@router.get("/credentials")
async def get_credentials():
    return {"username": auth_service.config.username}


@router.put("/credentials")
async def update_credentials(
    request: Request,
    body: CredentialsRequest,
    response: Response,
):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="账号不能为空")
    if not auth_service.update_credentials(
        body.current_password,
        username,
        body.new_password,
    ):
        raise HTTPException(status_code=400, detail="当前密码不正确")

    _set_session_cookie(request, response, auth_service.create_session())
    return {"success": True, "username": auth_service.config.username}
