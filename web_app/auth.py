# -*- coding: utf-8 -*-
"""
Simple token-based authentication for the web API.
"""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from web_app.config import config_manager

# API key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


async def verify_token(api_key: str = Security(api_key_header)) -> bool:
    """
    Verify the API token.

    If authentication is disabled, always returns True.
    If enabled, validates the token against the configured value.
    """
    config = config_manager.get_config()

    # If auth is not enabled, allow all requests
    if not config.auth_enabled:
        return True

    # If auth is enabled, validate the token
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not config_manager.validate_token(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True


async def verify_token_header_or_query(
    api_key_header_val: str = Security(api_key_header),
    api_key_query_val: str = Security(api_key_query),
) -> bool:
    """Verify token from either X-API-Key header or api_key query (for img src etc.)."""
    config = config_manager.get_config()
    if not config.auth_enabled:
        return True
    token = api_key_header_val or api_key_query_val
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required (X-API-Key header or api_key query)",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not config_manager.validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return True


def get_optional_auth(api_key: str = Security(api_key_header)) -> bool:
    """
    Optional authentication check.
    Returns True if auth is disabled or token is valid.
    Returns False if auth is enabled and token is invalid (but doesn't raise).
    """
    config = config_manager.get_config()

    if not config.auth_enabled:
        return True

    if not api_key:
        return False

    return config_manager.validate_token(api_key)
