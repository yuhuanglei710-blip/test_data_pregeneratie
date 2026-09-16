"""Helpers for adding test funds through the admin API."""

import os
import time
from typing import Any, Dict, Optional

import jwt
import requests


BASE_URL = os.getenv("ADMIN_BASE_URL", "https://admin.ushdev.top")
USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_PASSWORD", "us.1us.1")
REQUEST_TIMEOUT = 15

x_token: Optional[str] = None


def _browser_headers() -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
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


def login() -> str:
    """Log in to the admin API and cache its token."""
    global x_token

    response = requests.post(
        f"{BASE_URL}/api/base/login",
        headers=_browser_headers(),
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
    x_token = _extract_token(result)
    if not x_token:
        raise RuntimeError(f"登录响应中未找到 token：{result}")
    return x_token


def add_money(user_id: int, amount: int, remark: str = "") -> Dict[str, Any]:
    """Add funds to a user, refreshing the admin token when necessary."""
    if _is_token_expired(x_token):
        login()

    headers = _browser_headers()
    headers.update({"X-Token": x_token or "", "X-User-Id": "1"})

    response = requests.post(
        f"{BASE_URL}/api/operationManage/user/UpdateUserAccount",
        headers=headers,
        json={"id": user_id, "type": 1, "remark": remark, "num": amount},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()
