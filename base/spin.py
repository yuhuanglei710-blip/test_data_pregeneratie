"""Helpers for obtaining a game token and placing a test spin."""

import base64
import json
import time
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

import jwt
import requests


GAME_URL_API = "https://ceshigeren-ush-api.szhdev.top/v1/gamehall/self_game_url"
SPIN_API = "https://h5gz-api.szhdev.top/v1/slot/spin"
WEB_ORIGIN = "https://webnew.hotspin777.com"
SPIN_ORIGIN = "https://h5gz.szhdev.top"
REQUEST_TIMEOUT = 30
ERROR_BODY_LIMIT = 300
TOKEN_EXPIRY_LEEWAY = 5

# Tokens are cached only for the lifetime of the current Python process.
_game_token_cache: Dict[str, str] = {}
_game_token_lock = Lock()


def _game_url_headers(user_token: str) -> Dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "Origin": WEB_ORIGIN,
        "Referer": f"{WEB_ORIGIN}/",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14; SM-A556B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Mobile Safari/537.36"
        ),
        "token": user_token,
        "version": "8b339f30eee82f3486f27a5d3e42d12fea8543f0",
    }


def _extract_game_token(result: Dict[str, Any]) -> str:
    encoded_data = result["data"]
    decoded_data = base64.b64decode(encoded_data).decode("utf-8")
    game_info = json.loads(decoded_data)

    game_url = unquote(game_info["url"])
    query_params = parse_qs(urlparse(game_url).query)
    return query_params["sign"][0]


def _is_token_expired(token: str, *, now: Optional[float] = None) -> bool:
    """Check only the JWT expiry; signature validation is intentionally skipped."""
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
        expires_at = float(claims["exp"])
    except (KeyError, TypeError, ValueError, jwt.PyJWTError):
        return True

    current_time = time.time() if now is None else now
    return expires_at <= current_time + TOKEN_EXPIRY_LEEWAY


def _response_summary(response: requests.Response) -> str:
    """Keep an error response useful without flooding the console."""
    body = response.text.strip().replace("\n", " ")
    if len(body) > ERROR_BODY_LIMIT:
        body = f"{body[:ERROR_BODY_LIMIT]}..."
    return body or "无响应内容"


def _print_debug(label: str, response: requests.Response, verbose: bool) -> None:
    if not verbose:
        return

    print(f"[spin:debug] {label} HTTP {response.status_code}")
    try:
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except ValueError:
        print(_response_summary(response))


def get_game_token(user_token: str, *, verbose: bool = False) -> Optional[str]:
    """Exchange a registered user's token for a slot-game token."""
    payload = {
        "type": 1,
        "game_id": 200001,
        "game_channel": 4,
        "exit_event": f"{WEB_ORIGIN}/home",
        "cash_event": f"{WEB_ORIGIN}/backshop",
    }

    try:
        response = requests.post(
            GAME_URL_API,
            headers=_game_url_headers(user_token),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        _print_debug("获取游戏 token", response, verbose)
        if response.status_code != 200:
            print(
                f"[spin] 获取游戏 token 失败（HTTP {response.status_code}）："
                f"{_response_summary(response)}"
            )
            return None

        result = response.json()
        return _extract_game_token(result)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        print(f"[spin] 游戏 token 解析失败：{error}")
    except requests.RequestException as error:
        print(f"[spin] 获取游戏 token 请求失败：{error}")
    return None


def get_valid_game_token(
    user_token: str,
    *,
    verbose: bool = False,
) -> Optional[str]:
    """Reuse the cached game token until its JWT ``exp`` time is reached."""
    cached_token = _game_token_cache.get(user_token)
    if cached_token and not _is_token_expired(cached_token):
        return cached_token

    # Recheck inside the lock so concurrent workers do not refresh it together.
    with _game_token_lock:
        cached_token = _game_token_cache.get(user_token)
        if cached_token and not _is_token_expired(cached_token):
            return cached_token

        game_token = get_game_token(user_token, verbose=verbose)
        if not game_token:
            _game_token_cache.pop(user_token, None)
            return None
        if _is_token_expired(game_token):
            _game_token_cache.pop(user_token, None)
            print("[spin] 新获取的游戏 token 已过期或不包含有效的 exp")
            return None

        _game_token_cache[user_token] = game_token
        return game_token


def dev_spin(
    user_token: str,
    *,
    verbose: bool = False,
) -> Optional[requests.Response]:
    """Obtain a game token and place one development-environment spin."""
    game_token = get_valid_game_token(user_token, verbose=verbose)
    if not game_token:
        return None

    payload = {
        "token": game_token,
        "bet": 10000,
        "money_type": "SC",
        "game_id": 100001,
        "session_id": "",
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "Origin": SPIN_ORIGIN,
        "Referer": f"{SPIN_ORIGIN}/",
        "User-Agent": "Mozilla/5.0",
        "Authorization": f"Bearer {game_token}",
    }

    try:
        response = requests.post(
            SPIN_API,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        _print_debug("下注", response, verbose)
        if response.status_code != 200:
            print(
                f"[spin] 下注失败（HTTP {response.status_code}）："
                f"{_response_summary(response)}"
            )
            return None

        response.json()
        return response
    except (TypeError, ValueError) as error:
        print(f"[spin] 下注响应解析失败：{error}")
    except requests.RequestException as error:
        print(f"[spin] 下注请求失败：{error}")
    return None


if __name__ == "__main__":
    token = "your_user_token_here"
    response = dev_spin(token, verbose=True)
    print("下注结果:", "成功" if response else "失败")
