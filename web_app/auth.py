# -*- coding: utf-8 -*-
"""
Token-based authentication for the web API, supporting browser sessions,
X-API-Key header, Authorization Bearer tokens, and api_key query parameters.
"""

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from web_app.config import config_manager
from web_app.services.auth_service import SESSION_COOKIE_NAME, auth_service
from web_app.services.api_key_service import api_key_service

# API key headers and queries
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


def extract_token_from_request(request: Request, explicit_token: str = "") -> str:
    """Extract API key token from headers, auth header, or query params."""
    if explicit_token:
        return explicit_token.strip()

    # 1. Check X-API-Key header
    header_val = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if header_val:
        return header_val.strip()

    # 2. Check Authorization: Bearer <token>
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and auth_header.strip().lower().startswith("bearer "):
        return auth_header.strip()[7:].strip()

    # 3. Check query param
    query_val = request.query_params.get("api_key")
    if query_val:
        return query_val.strip()

    return ""


async def verify_token(
    request: Request,
    api_key: str = Security(api_key_header),
) -> bool:
    """
    Verify browser session or API key token.

    If session is valid, allows request.
    If valid API key is supplied, allows request.
    If auth is disabled in config, allows request.
    Otherwise raises 401 Unauthorized.
    """
    # 1. Browser session cookie check
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
    if session_cookie and auth_service.verify_session(session_cookie):
        return True

    # 2. Extract API token from headers or query
    token = extract_token_from_request(request, explicit_token=api_key)

    # 3. Validate against APIKeyService
    if token:
        if api_key_service.validate_key(token):
            return True
        if config_manager.validate_token(token):
            return True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. If auth is not enabled, allow all requests
    config = config_manager.get_config()
    if not config.auth_enabled:
        return True

    # 5. Missing token and auth enabled
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key required (Authorization: Bearer <key> or X-API-Key)",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def verify_token_header_or_query(
    request: Request,
    api_key_header_val: str = Security(api_key_header),
    api_key_query_val: str = Security(api_key_query),
) -> bool:
    """Verify token from headers, Bearer auth, query, or browser session."""
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
    if session_cookie and auth_service.verify_session(session_cookie):
        return True

    token = extract_token_from_request(request, explicit_token=api_key_header_val or api_key_query_val)
    if token:
        if api_key_service.validate_key(token):
            return True
        if config_manager.validate_token(token):
            return True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    config = config_manager.get_config()
    if not config.auth_enabled:
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key required (X-API-Key header, Authorization Bearer, or api_key query)",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_optional_auth(api_key: str = Security(api_key_header)) -> bool:
    """Optional authentication check."""
    config = config_manager.get_config()
    if not config.auth_enabled:
        return True
    if not api_key:
        return False
    return api_key_service.validate_key(api_key) or config_manager.validate_token(api_key)
