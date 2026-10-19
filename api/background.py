"""后台用户查询接口客户端。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
import jwt

from base.add_money import login
from base.env_config import environment_config, required_string


API_BLUEPRINT = "/api/operationManage"
REQUEST_TIMEOUT = 15


def _normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


class Background:
    """封装后台用户查找与详情查询。"""

    def __init__(self, environment: str = "dev"):
        domain = required_string(
            environment_config(environment),
            "back_ground_url",
            context=f"environment.{environment}",
        )

        self.environment = environment
        self.base_url = _normalize_base_url(domain)
        self.blueprint = API_BLUEPRINT
        self.token: str | None = None

    def check_token(self, token: str) -> None:
        """注入后台 token，主要供测试或已有会话复用。"""
        normalized_token = token.strip()
        if not normalized_token:
            raise ValueError("token 不能为空")
        self.token = normalized_token

    def get_token(self) -> str:
        """复用项目后台登录逻辑获取当前环境 token。"""
        self.token = login(self.base_url)
        return self.token

    def _operator_user_id(self) -> str:
        """从后台登录 token 中读取操作员 ID。"""
        if not self.token:
            return "1"
        try:
            claims = jwt.decode(
                self.token,
                options={"verify_signature": False, "verify_exp": False},
            )
        except jwt.PyJWTError:
            return "1"
        value = claims.get("ID", 1)
        return str(value)

    def _headers(self) -> Dict[str, str]:
        if not self.token:
            self.get_token()
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "X-Token": self.token,
            "X-User-Id": self._operator_user_id(),
        }

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}{self.blueprint}/user/{endpoint}",
            headers=self._headers(),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as error:
            raise RuntimeError("后台接口未返回合法 JSON") from error
        if not isinstance(result, dict):
            raise RuntimeError(f"后台接口返回格式异常: {result!r}")
        if result.get("code") != 0:
            message = str(result.get("msg") or "未知错误")
            raise RuntimeError(f"后台接口查询失败: {message}")
        return result

    def find_users(self, user_id: int) -> List[Dict[str, Any]]:
        """调用 GetUserList 按 UID 查找用户。"""
        if int(user_id) <= 0:
            raise ValueError("用户 UID 必须是正整数")
        result = self._post(
            "GetUserList",
            {"id": int(user_id), "timezone": 0},
        )
        data = result.get("data")
        if not isinstance(data, list):
            raise RuntimeError("GetUserList 返回的 data 不是列表")
        return [item for item in data if isinstance(item, dict)]

    def get_user_info(self, user_id: int) -> Dict[str, Any]:
        """调用 GetUserInfo 查询用户详细信息。"""
        if int(user_id) <= 0:
            raise ValueError("用户 UID 必须是正整数")
        result = self._post(
            "GetUserInfo",
            {"id": int(user_id), "timezone": 0, "lang": "zh-CN"},
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("GetUserInfo 返回的 data 不是对象")
        return data

    def query_user(self, user_id: int) -> Dict[str, Any]:
        """先查找用户，再读取详情和 KYC 状态。"""
        users = self.find_users(user_id)
        if not users:
            return {"users": [], "detail": None, "kyc_status": None}
        return {
            "users": users,
            "detail": self.get_user_info(user_id),
            "kyc_status": self.get_kyc_status(user_id),
        }

    @staticmethod
    def _extract_kyc_status(value: Any) -> Optional[int]:
        """兼容对象、列表及嵌套 data 的 KYC 状态响应。"""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        if isinstance(value, dict):
            keyed = value.get("10011")
            parsed = Background._extract_kyc_status(keyed)
            if parsed is not None:
                return parsed
            direct = value.get("status", value.get("kyc_status"))
            parsed = Background._extract_kyc_status(direct)
            if parsed is not None:
                return parsed
            for key in ("data", "list", "items"):
                parsed = Background._extract_kyc_status(value.get(key))
                if parsed is not None:
                    return parsed
            return None
        if isinstance(value, list):
            preferred = [
                item
                for item in value
                if isinstance(item, dict) and str(item.get("key")) == "10011"
            ]
            for item in preferred or value:
                parsed = Background._extract_kyc_status(item)
                if parsed is not None:
                    return parsed
        return None

    def get_kyc_status(self, user_id: int) -> Optional[int]:
        """调用 GetKycStatus 查询 KYC 状态。"""
        if int(user_id) <= 0:
            raise ValueError("用户 UID 必须是正整数")
        result = self._post("GetKycStatus", {"user_id": int(user_id)})
        return self._extract_kyc_status(result.get("data"))

    def update_kyc_status(self, user_id: int, status: int) -> Optional[int]:
        """将 KYC 更新为失败（2）或通过（3），随后读取最新状态。"""
        if int(user_id) <= 0:
            raise ValueError("用户 UID 必须是正整数")
        if int(status) not in (2, 3):
            raise ValueError("KYC 状态只允许更新为失败（2）或通过（3）")
        self._post(
            "UpdateKycStatus",
            {"user_id": int(user_id), "key": "10011", "status": int(status)},
        )
        return self.get_kyc_status(user_id)

    def pass_kyc(self, user_id: int) -> None:
        self.update_kyc_status(user_id, 3)

    def reset_kyc(self, user_id: int) -> None:
        self.update_kyc_status(user_id, 2)

if __name__ == "__main__":
    background = Background(environment="dev")
    print(background.query_user(1))
