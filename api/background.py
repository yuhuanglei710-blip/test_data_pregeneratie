"""Admin API client skeleton."""

import http.client
import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_BLUEPRINT = "/api/operationManage"


class Background:
    """Expose commonly used admin operations."""

    def __init__(self, environment: str = "dev"):
        self.environment = environment
        load_dotenv(PROJECT_ROOT / f"{environment}.env", override=True)

        self.blueprint = API_BLUEPRINT
        self.domain = os.getenv("background_domain")
        self.token: str | None = None
        if not self.domain:
            raise RuntimeError(f"未在 {environment}.env 中配置 background_domain")

    def pass_kyc(self, user_id: int) -> None:
        """Approve a user's KYC review (not implemented yet)."""
        raise NotImplementedError("KYC 审核接口尚未实现")

    def reset_kyc(self, user_id: int) -> None:
        """Reset a user's KYC review (not implemented yet)."""
        raise NotImplementedError("KYC 重置接口尚未实现")

    def get_user_info(self, user_id: int) -> Dict[str, Any]:
        """Fetch one user's information from the admin API."""
        if not self.token:
            raise RuntimeError("请先通过 check_token 设置后台 token")

        connection = http.client.HTTPSConnection(self.domain)
        try:
            connection.request(
                "POST",
                f"{self.blueprint}/user/GetUserList",
                body=json.dumps({"user_id": user_id, "timezone": 0}),
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            response_data = response.read().decode("utf-8")
        finally:
            connection.close()

        print(response_data)
        result = json.loads(response_data)
        if not isinstance(result, dict):
            raise RuntimeError(f"后台接口返回格式异常: {result!r}")
        return result

    def check_token(self, token: str) -> None:
        """Set the admin token used by subsequent requests."""
        if not token:
            raise ValueError("token 不能为空")
        self.token = token

    def get_token(self) -> str:
        """Log in and fetch an admin token (not implemented yet)."""
        raise NotImplementedError("后台登录接口尚未实现")


if __name__ == "__main__":
    background = Background(environment="dev")
    background.check_token(token="your_token_here")
