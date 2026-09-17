"""Helpers for adding test funds through the admin API."""

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
import requests
from dotenv import dotenv_values


BASE_URL = os.getenv("ADMIN_BASE_URL", "https://admin.ushdev.top")
USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_PASSWORD", "us.1us.1")
REQUEST_TIMEOUT = 15
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_token_cache: Dict[str, str] = {}
_token_lock = threading.Lock()


def _normalize_base_url(value: str) -> str:
    """Return an absolute admin URL without a trailing slash."""
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def base_url_for_environment(environment: str) -> str:
    """Resolve the admin API URL from ``<environment>.env``."""
    env_file = PROJECT_ROOT / f"{environment}.env"
    domain = dotenv_values(env_file).get("background_domain")
    if domain:
        return _normalize_base_url(domain)
    if environment == "dev":
        return _normalize_base_url(BASE_URL)
    raise RuntimeError(f"{env_file.name} 未配置 background_domain")


def _browser_headers(base_url: str = BASE_URL) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": base_url,
        "Referer": f"{base_url}/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),
    }


def _extract_token(result: Dict[str, Any]) -> Optional[str]:
    data = result.get("data")
    nested_data = data if isinstance(data, dict) else {}
    return (
        result.get("token")
        or result.get("x-token")
        or nested_data.get("token")
        or nested_data.get("x-token")
    )


def _is_token_expired(token: Optional[str]) -> bool:
    if not token:
        return True

    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
    except jwt.PyJWTError:
        return True

    return claims.get("exp", 0) <= int(time.time())


def login(base_url: str = BASE_URL) -> str:
    """Log in to the admin API and cache its token."""
    base_url = _normalize_base_url(base_url)

    response = requests.post(
        f"{base_url}/api/base/login",
        headers=_browser_headers(base_url),
        json={
            "username": USERNAME,
            "password": PASSWORD,
            "captcha": "",
            "captchaId": "14YVKmV707eSOh4dVQ3v",
            "openCaptcha": False,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    result = response.json()
    token = _extract_token(result)
    if not token:
        raise RuntimeError(f"登录响应中未找到 token：{result}")
    _token_cache[base_url] = token
    return token


def add_money(
    user_id: int,
    amount: int,
    remark: str = "",
    *,
    base_url: str = BASE_URL,
) -> Dict[str, Any]:
    """Add funds to a user, refreshing the admin token when necessary."""
    base_url = _normalize_base_url(base_url)
    with _token_lock:
        token = _token_cache.get(base_url)
        if _is_token_expired(token):
            token = login(base_url)

    headers = _browser_headers(base_url)
    headers.update({"X-Token": token or "", "X-User-Id": "1"})

    response = requests.post(
        f"{base_url}/api/operationManage/user/UpdateUserAccount",
        headers=headers,
        json={"id": user_id, "type": 1, "remark": remark, "num": amount},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def operation_succeeded(result: Dict[str, Any]) -> bool:
    """Admin operations use ``code == 0`` for business success."""
    return result.get("code") == 0
