"""用户注册相关工具。"""

import base64
import http.client
import json
import random
import string
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import jwt
from dotenv import dotenv_values

try:  # Support ``python -m base.user``.
    from .enums import Platform
except ImportError:  # Support ``python base/user.py``.
    from enums import Platform


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_ENVIRONMENTS = {
    "dev": "测试环境",
    "huidu": "灰度环境",
    "prod": "生产环境",
    "yy": "运营环境",
    "individual": "个人服环境",
}
PLATFORM_NAMES = {1: "web", 2: "android", 3: "ios"}

DEFAULT_PASSWORD = "123456"
DEFAULT_PASSWORD_HASH = "e10adc3949ba59abbe56e057f20f883e"
DEFAULT_CHANNEL_CODE = "com.hotspin777.hotspin|testtest|"
DEFAULT_DOWN_ORIGIN = "gpa17drop"

_oaid_lock = threading.Lock()
_last_oaid = 0


class User:
    """可通过前台接口注册的测试用户。"""

    def __init__(self, email: Optional[str] = None, environment: str = "dev"):
        """创建绑定到指定环境的用户。"""
        self.environment = environment
        self.domain = self._load_domain(environment)
        self.email = email or self._generate_email()
        self.password = DEFAULT_PASSWORD_HASH

        self.uid: Optional[int] = None
        self.platform: Optional[int] = None
        self.channel_code: Optional[str] = None
        self.down_origin: Optional[str] = None
        self.token: Optional[str] = None

    @staticmethod
    def _load_domain(environment: str) -> str:
        """从环境文件读取前台接口域名。"""
        if environment not in SUPPORTED_ENVIRONMENTS:
            supported = ", ".join(SUPPORTED_ENVIRONMENTS)
            raise ValueError(f"不支持的环境 {environment!r}，可选值：{supported}")

        env_file = PROJECT_ROOT / f"{environment}.env"
        domain = dotenv_values(env_file).get("domain")
        if not domain:
            raise RuntimeError(f"未在 {env_file.name} 中配置 domain")
        return domain

    @staticmethod
    def _generate_email() -> str:
        """生成不重复的随机邮箱。"""
        letters = "".join(random.choices(string.ascii_lowercase, k=4))
        digits = "".join(random.choices(string.digits, k=2))
        return f"{letters}{digits}@cc.cc"

    @staticmethod
    def _generate_oaid() -> str:
        """生成线程安全的毫秒级设备 ID。"""
        global _last_oaid
        with _oaid_lock:
            current = int(time.time() * 1000)
            _last_oaid = max(current, _last_oaid + 1)
            return str(_last_oaid)

    def register(
        self,
        channel_code: str = DEFAULT_CHANNEL_CODE,
        down_origin: str = DEFAULT_DOWN_ORIGIN,
        platform: int = Platform.ios.value,
        *,
        verbose: bool = False,
    ) -> None:
        """注册用户并保存 uid 和 token。"""
        self.down_origin = down_origin
        self.platform = platform
        self.channel_code = channel_code

        oaid = self._generate_oaid()
        response = self._post_registration(self._build_registration_payload(oaid))
        decoded_response = self._decode_registration_response(response)

        if verbose:
            print(
                "[user:debug] 注册接口响应:",
                json.dumps(decoded_response, ensure_ascii=False, indent=2),
            )

        user_data, token = self._find_registration_data(decoded_response.get("data"))
        if not user_data or not token:
            raise RuntimeError(f"注册失败，接口响应: {decoded_response}")

        self.uid = user_data["id"]
        self.token = token
        if verbose:
            self._print_token_claims(token)

    def _build_registration_payload(self, oaid: str) -> Dict[str, Any]:
        """构建指定平台的注册请求体。"""
        return {
            "oaid": oaid,
            "email": self.email,
            "password": self.password,
            "confirm_password": self.password,
            "platform": self.platform,
            "channel_code": self.channel_code,
            "distribution_channel": self.down_origin,
            "user_agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 "
                "Mobile/15E148 Safari/604.1"
            ),
            "ip_json": json.dumps(
                {
                    "ip": "172.83.157.240",
                    "regionName": "Washington",
                    "countryCode": "US",
                    "city": "Seattle",
                    "country": "United States of America",
                }
            ),
            "entered_code": "",
            "leisure_game_import_token": "",
            "country": "US",
            "province": "Washington",
            "city": "Seattle",
            "phone_os_version": "",
            "adjust_info": json.dumps(
                {
                    "network": self.channel_code,
                    "trackerName": self.down_origin,
                    "trackerToken": "19huppx7",
                    "adid": oaid,
                    "campaign": "b4733853b4790ac2e4aa85e1c2c69438",
                    "creative": "",
                    "costType": "",
                    "costCurrency": "",
                    "costAmount": 0,
                }
            ),
            "area_limit": {
                "language": "zh-CN",
                "isp": "",
                "ip_country": "US",
                "ip_city": "Seattle",
                "ip_province": "Washington",
                "vpn": 0,
                "zone_info": "",
            },
        }

    def _post_registration(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """提交注册请求并返回 JSON 对象。"""
        connection = http.client.HTTPSConnection(self.domain)
        try:
            connection.request(
                "POST",
                "/v1/user/register",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response_data = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

        if not isinstance(response_data, dict):
            raise RuntimeError(f"注册接口返回格式异常: {response_data!r}")
        return response_data

    @classmethod
    def _decode_registration_response(
        cls, response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解码响应中可能经过 Base64 包装的字段。"""
        decoded_response = response.copy()
        for field in ("msg", "data"):
            value = response.get(field)
            if not isinstance(value, str):
                continue

            decoded_value = cls._try_base64_decode(value)
            if decoded_value is None:
                continue

            if field == "data":
                try:
                    decoded_response[field] = json.loads(decoded_value)
                except json.JSONDecodeError:
                    decoded_response[field] = decoded_value
            else:
                decoded_response[field] = decoded_value

        return decoded_response

    @staticmethod
    def _try_base64_decode(value: str) -> Optional[str]:
        """尝试解码 Base64 字符串，失败时返回空值。"""
        try:
            return base64.b64decode(value).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    @staticmethod
    def _find_registration_data(
        data: Any,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """从嵌套 data 中查找用户信息和 token。"""
        if not isinstance(data, dict):
            return None, None

        user_data = data.get("user")
        token = data.get("token")
        if isinstance(user_data, dict) and user_data.get("id") and token:
            return user_data, token

        return User._find_registration_data(data.get("data"))

    @staticmethod
    def _print_token_claims(token: str) -> None:
        """不验签打印 JWT 内容，仅用于本地调试。"""
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
            print("decoded:", claims)
        except jwt.PyJWTError as error:
            print(f"token 解析失败: {error}")

    def login(self) -> None:
        """登录已有用户，功能尚未实现。"""
        raise NotImplementedError("用户登录接口尚未实现")

    @staticmethod
    def map_translate_dic(key: str) -> str:
        """把环境键转换为可读名称。"""
        return SUPPORTED_ENVIRONMENTS.get(key, "Unknown environment")

    @staticmethod
    def map_platform(value: int) -> str:
        """把平台编号转换为可读名称。"""
        return PLATFORM_NAMES.get(value, "Unknown platform")


if __name__ == "__main__":
    user = User(environment="dev")
    user.register(platform=Platform.ios.value, verbose=True)
    print(
        "=================== 注册成功!",
        f"\n环境: {User.map_translate_dic(user.environment)}",
        f"\nuid: {user.uid}",
        f"\n邮箱: {user.email}",
        f"\n密码: {DEFAULT_PASSWORD}",
    )
