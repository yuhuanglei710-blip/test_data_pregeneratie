"""Helpers for obtaining a game token and placing a test spin."""

import base64
import binascii
import json
import time
from dataclasses import dataclass
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
DEFAULT_BET_CENTS = 1_000


@dataclass(frozen=True)
class SpinEnvironmentConfig:
    game_url_api: str
    web_origin: str
    spin_api: str = SPIN_API
    spin_origin: str = SPIN_ORIGIN
    version: Optional[str] = "8b339f30eee82f3486f27a5d3e42d12fea8543f0"
    user_agent: str = (
        "Mozilla/5.0 (Linux; Android 14; SM-A556B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Mobile Safari/537.36"
    )


SPIN_ENVIRONMENT_CONFIGS = {
    "dev": SpinEnvironmentConfig(
        game_url_api=GAME_URL_API,
        web_origin=WEB_ORIGIN,
    ),
    "huidu": SpinEnvironmentConfig(
        game_url_api="https://hdapi.ushdev.top/v1/gamehall/self_game_url",
        web_origin="https://newhdweb.ushdev.top",
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 "
            "Mobile/15E148 Safari/604.1"
        ),
        version=None,
    ),
}

_game_token_cache: Dict[tuple[str, str], str] = {}
_game_session_cache: Dict[tuple[str, str], str] = {}


def _config_for_environment(environment: str) -> SpinEnvironmentConfig:
    """Resolve endpoints while preserving the former defaults for other envs."""
    return SPIN_ENVIRONMENT_CONFIGS.get(
        environment,
        SPIN_ENVIRONMENT_CONFIGS["dev"],
    )


def _game_url_headers(
    user_token: str,
    config: SpinEnvironmentConfig,
) -> Dict[str, str]:
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "Origin": config.web_origin,
        "Referer": f"{config.web_origin}/",
        "User-Agent": config.user_agent,
        "token": user_token,
    }
    if config.version:
        headers["version"] = config.version
    return headers


def _extract_game_token(result: Dict[str, Any]) -> str:
    encoded_data = result["data"]
    decoded_data = base64.b64decode(encoded_data).decode("utf-8")
    game_info = json.loads(decoded_data)

    game_url = unquote(game_info["url"])
    query_params = parse_qs(urlparse(game_url).query)
    return query_params["sign"][0]


def _decode_base64_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    try:
        decoded_text = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value

    try:
        return json.loads(decoded_text)
    except json.JSONDecodeError:
        return decoded_text


def _decode_api_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Decode Base64-wrapped ``data`` and ``msg`` fields for readable output."""
    decoded_result = result.copy()
    for field in ("data", "msg"):
        if field in decoded_result:
            decoded_result[field] = _decode_base64_value(decoded_result[field])
    return decoded_result


def _is_token_expired(token: str, *, now: Optional[float] = None) -> bool:
    """Check the JWT ``exp`` locally without verifying its signature."""
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


def _spin_failed(result: Dict[str, Any]) -> bool:
    message = result.get("msg")
    if isinstance(message, str):
        normalized_message = message.casefold()
        if any(word in normalized_message for word in ("error", "fail", "失败", "错误")):
            return True
    return result.get("data") == {} and bool(message)


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


def get_game_token(
    user_token: str,
    *,
    environment: str = "dev",
    verbose: bool = False,
) -> Optional[str]:
    """Exchange a registered user's token for a slot-game token."""
    config = _config_for_environment(environment)
    payload = {
        "type": 1,
        "game_id": 200001,
        "game_channel": 4,
        "exit_event": f"{config.web_origin}/home",
        "cash_event": f"{config.web_origin}/backshop",
    }

    try:
        response = requests.post(
            config.game_url_api,
            headers=_game_url_headers(user_token, config),
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
    environment: str = "dev",
    verbose: bool = False,
) -> Optional[str]:
    """Reuse a game token until its JWT expiry time is reached."""
    cache_key = (environment, user_token)
    cached_token = _game_token_cache.get(cache_key)
    if cached_token and not _is_token_expired(cached_token):
        return cached_token

    game_token = get_game_token(
        user_token,
        environment=environment,
        verbose=verbose,
    )
    if not game_token or _is_token_expired(game_token):
        _game_token_cache.pop(cache_key, None)
        _game_session_cache.pop(cache_key, None)
        return None

    _game_token_cache[cache_key] = game_token
    _game_session_cache.pop(cache_key, None)
    return game_token


def dev_spin(
    user_token: str,
    *,
    environment: str = "dev",
    bet_amount: int = DEFAULT_BET_CENTS,
    verbose: bool = False,
    print_result: bool = True,
) -> Optional[requests.Response]:
    """Place one spin while preserving the token and ordered game session."""
    if bet_amount <= 0:
        raise ValueError("下注金额必须大于 0")

    config = _config_for_environment(environment)
    cache_key = (environment, user_token)
    game_token = get_valid_game_token(
        user_token,
        environment=environment,
        verbose=verbose,
    )
    if not game_token:
        return None

    payload = {
        "token": game_token,
        "bet": bet_amount,
        "money_type": "SC",
        "game_id": 100001,
        "session_id": _game_session_cache.get(cache_key, ""),
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "Origin": config.spin_origin,
        "Referer": f"{config.spin_origin}/",
        "User-Agent": "Mozilla/5.0",
        "Authorization": f"Bearer {game_token}",
    }

    try:
        response = requests.post(
            config.spin_api,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if verbose:
            print(f"[spin:debug] 下注 HTTP {response.status_code}")
        if response.status_code != 200:
            print(
                f"[spin] 下注失败（HTTP {response.status_code}）："
                f"{_response_summary(response)}"
            )
            return None

        result = _decode_api_result(response.json())
        if print_result:
            indent = 2 if verbose else None
            separators = None if verbose else (",", ":")
            formatted_result = json.dumps(
                result,
                ensure_ascii=False,
                indent=indent,
                separators=separators,
            )
            print(f"[spin] 下注响应：{formatted_result}")
        if _spin_failed(result):
            print(f"[spin] 下注业务失败：{result.get('msg', '未知错误')}")
            return None

        result_data = result.get("data")
        if isinstance(result_data, dict):
            session_id = result_data.get("session_id")
            if isinstance(session_id, str) and session_id:
                _game_session_cache[cache_key] = session_id
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
