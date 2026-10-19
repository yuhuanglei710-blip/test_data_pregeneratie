"""获取游戏 token 并执行测试下注。"""

import base64
import binascii
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional
from urllib.parse import parse_qs, unquote, urlparse

import jwt
import requests

try:  # Support package and direct script imports.
    from .api_request import load_environment_api_base_url
    from .env_config import config_section, required_string
except ImportError:  # pragma: no cover - compatibility for direct execution.
    from api_request import load_environment_api_base_url
    from env_config import config_section, required_string


_SPIN_CONFIG = config_section("spin")


def _mapping_value(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"env.json 的 spin.{key} 必须是 JSON 对象")
    return value


def _positive_int_value(key: str) -> int:
    value = _SPIN_CONFIG.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"env.json 的 spin.{key} 必须是正整数")
    return value


GAME_URL_PATH = required_string(
    _SPIN_CONFIG,
    "game_url_path",
    context="spin",
)
SPIN_API = required_string(_SPIN_CONFIG, "spin_api", context="spin")
SPIN_ORIGIN = required_string(_SPIN_CONFIG, "spin_origin", context="spin")
REQUEST_TIMEOUT = _positive_int_value("request_timeout")
ERROR_BODY_LIMIT = _positive_int_value("error_body_limit")
TOKEN_EXPIRY_LEEWAY = _positive_int_value("token_expiry_leeway")
DEFAULT_BET_CENTS = _positive_int_value("default_bet_cents")
GAME_URL_REQUEST = _mapping_value(_SPIN_CONFIG, "game_url_request")
BET_REQUEST = _mapping_value(_SPIN_CONFIG, "bet_request")
DEFAULT_USER_AGENT = required_string(
    _SPIN_CONFIG,
    "user_agent",
    context="spin",
)
SPIN_USER_AGENT = required_string(
    _SPIN_CONFIG,
    "spin_user_agent",
    context="spin",
)
try:
    TOKEN_ACTIVATION_RETRY_DELAYS = tuple(
        float(value) for value in _SPIN_CONFIG["token_activation_retry_delays"]
    )
except (KeyError, TypeError, ValueError) as error:
    raise RuntimeError(
        "env.json 的 spin.token_activation_retry_delays 必须是数字数组"
    ) from error


@dataclass(frozen=True)
class SpinEnvironmentConfig:
    """单个下注环境的接口和浏览器参数。"""

    environment: str
    web_origin: str
    spin_api: str = SPIN_API
    spin_origin: str = SPIN_ORIGIN
    version: Optional[str] = None
    user_agent: str = DEFAULT_USER_AGENT

    @property
    def game_url_api(self) -> str:
        """始终从所选环境读取前台 API，禁止跨环境复用地址。"""
        return f"{load_environment_api_base_url(self.environment)}{GAME_URL_PATH}"


def _load_spin_environment_configs() -> Dict[str, SpinEnvironmentConfig]:
    configured = _mapping_value(_SPIN_CONFIG, "environments")
    result: Dict[str, SpinEnvironmentConfig] = {}
    for environment, raw_config in configured.items():
        if not isinstance(raw_config, dict):
            raise RuntimeError(
                f"env.json 的 spin.environments.{environment} 必须是 JSON 对象"
            )
        version = raw_config.get("version")
        if version is not None and not isinstance(version, str):
            raise RuntimeError(
                f"env.json 的 spin.environments.{environment}.version "
                "必须是字符串或 null"
            )
        result[str(environment)] = SpinEnvironmentConfig(
            environment=str(environment),
            web_origin=required_string(
                raw_config,
                "web_origin",
                context=f"spin.environments.{environment}",
            ),
            spin_api=str(raw_config.get("spin_api") or SPIN_API),
            spin_origin=str(raw_config.get("spin_origin") or SPIN_ORIGIN),
            version=version,
            user_agent=str(raw_config.get("user_agent") or DEFAULT_USER_AGENT),
        )
    return result


SPIN_ENVIRONMENT_CONFIGS = _load_spin_environment_configs()

_game_token_cache: Dict[tuple[str, str], str] = {}
_game_session_cache: Dict[tuple[str, str], str] = {}


def _config_for_environment(environment: str) -> SpinEnvironmentConfig:
    """读取下注环境配置；缺失时必须停止，不能回退到其他环境。"""
    try:
        return SPIN_ENVIRONMENT_CONFIGS[environment]
    except KeyError as error:
        supported = "、".join(SPIN_ENVIRONMENT_CONFIGS)
        raise ValueError(
            f"下注环境 {environment!r} 未配置，可选值：{supported}"
        ) from error


def _game_url_headers(
    user_token: str,
    config: SpinEnvironmentConfig,
) -> Dict[str, str]:
    """构建当前环境获取游戏地址的请求头。"""
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
    """解码游戏地址响应并提取 sign token。"""
    game_info = _decode_base64_value(result.get("data"))

    def find_url(value: Any) -> Optional[str]:
        if isinstance(value, dict):
            url = value.get("url")
            if isinstance(url, str) and url:
                return url
            for nested in value.values():
                found = find_url(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = find_url(nested)
                if found:
                    return found
        return None

    raw_url = find_url(game_info)
    if not raw_url:
        message = _decode_base64_value(result.get("msg"))
        compact_data = json.dumps(
            game_info,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(compact_data) > ERROR_BODY_LIMIT:
            compact_data = f"{compact_data[:ERROR_BODY_LIMIT]}..."
        raise ValueError(
            f"接口未返回游戏地址 url（code={result.get('code')!r}, "
            f"msg={message!r}, data={compact_data}）"
        )

    game_url = unquote(raw_url)
    query_params = parse_qs(urlparse(game_url).query)
    signs = query_params.get("sign")
    if not signs or not signs[0]:
        raise ValueError("游戏地址缺少 sign 参数")
    return signs[0]


def _decode_base64_value(value: Any) -> Any:
    """尝试把 Base64 值解码为 JSON 或文本。"""
    if not isinstance(value, str):
        return value

    try:
        padded = value + "=" * (-len(value) % 4)
        decoded_text = base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value

    try:
        return json.loads(decoded_text)
    except json.JSONDecodeError:
        return decoded_text


def _decode_api_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """解码响应中的 data 和 msg 字段。"""
    decoded_result = result.copy()
    for field in ("data", "msg"):
        if field in decoded_result:
            decoded_result[field] = _decode_base64_value(decoded_result[field])
    return decoded_result


def _is_token_expired(token: str, *, now: Optional[float] = None) -> bool:
    """不验签，仅根据 exp 判断 JWT 是否过期。"""
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
    """判断下注响应是否业务失败。"""
    message = result.get("msg")
    if isinstance(message, str):
        normalized_message = message.casefold()
        if any(word in normalized_message for word in ("error", "fail", "失败", "错误")):
            return True
    return result.get("data") == {} and bool(message)


def _response_summary(response: requests.Response) -> str:
    """截断错误响应，避免刷满终端。"""
    body = response.text.strip().replace("\n", " ")
    if len(body) > ERROR_BODY_LIMIT:
        body = f"{body[:ERROR_BODY_LIMIT]}..."
    return body or "无响应内容"


def _print_debug(label: str, response: requests.Response, verbose: bool) -> None:
    """仅在调试模式下打印完整响应。"""
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
    """用用户 token 换取游戏 token。"""
    config = _config_for_environment(environment)
    payload = {
        "type": GAME_URL_REQUEST["type"],
        "game_id": GAME_URL_REQUEST["game_id"],
        "game_channel": GAME_URL_REQUEST["game_channel"],
        "exit_event": f"{config.web_origin}{GAME_URL_REQUEST['exit_path']}",
        "cash_event": f"{config.web_origin}{GAME_URL_REQUEST['cash_path']}",
    }

    retry_delays = (*TOKEN_ACTIVATION_RETRY_DELAYS, None)
    for attempt, retry_delay in enumerate(retry_delays, 1):
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
            message = _decode_base64_value(result.get("msg"))
            token_not_active = (
                isinstance(message, str)
                and "token not active yet" in message.casefold()
            )
            if token_not_active and retry_delay is not None:
                print(
                    "[spin] 登录 Token 尚不能换取游戏 Token，"
                    f"{retry_delay:g} 秒后重试 "
                    f"({attempt}/{len(retry_delays)})"
                )
                time.sleep(retry_delay)
                continue
            return _extract_game_token(result)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            print(f"[spin] 登录 Token 换取游戏 Token 失败：{error}")
            return None
        except requests.RequestException as error:
            print(f"[spin] 获取游戏 token 请求失败：{error}")
            return None
    return None


def get_valid_game_token(
    user_token: str,
    *,
    environment: str = "dev",
    verbose: bool = False,
) -> Optional[str]:
    """复用未过期的游戏 token。"""
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
    preserve_session: bool = True,
    verbose: bool = False,
    print_result: bool = True,
) -> Optional[requests.Response]:
    """执行一次下注，可选择是否维护连续 session。"""
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
        "money_type": BET_REQUEST["money_type"],
        "game_id": BET_REQUEST["game_id"],
        "session_id": (
            _game_session_cache.get(cache_key, "") if preserve_session else ""
        ),
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "Origin": config.spin_origin,
        "Referer": f"{config.spin_origin}/",
        "User-Agent": SPIN_USER_AGENT,
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
            if preserve_session and isinstance(session_id, str) and session_id:
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
