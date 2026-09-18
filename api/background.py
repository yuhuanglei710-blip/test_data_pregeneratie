"""后台接口客户端。"""

import http.client
import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_BLUEPRINT = "/api/operationManage"


class Background:
    """封装常用后台操作。"""

    def __init__(self, environment: str = "dev"):
        """加载指定环境的后台接口域名。"""
        self.environment = environment
        load_dotenv(PROJECT_ROOT / f"{environment}.env", override=True)

        self.blueprint = API_BLUEPRINT
        self.domain = os.getenv("background_domain")
        self.token: str | None = None
        if not self.domain:
            raise RuntimeError(f"未在 {environment}.env 中配置 background_domain")

    def pass_kyc(self, user_id: int) -> None:
        """通过用户 KYC，功能尚未实现。"""
        raise NotImplementedError("KYC 审核接口尚未实现")

    def reset_kyc(self, user_id: int) -> None:
        """重置用户 KYC，功能尚未实现。"""
        raise NotImplementedError("KYC 重置接口尚未实现")

    def get_user_info(self, user_id: int) -> Dict[str, Any]:
        """从后台接口查询一个用户。"""
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
        """设置后续请求使用的后台 token。"""
        if not token:
            raise ValueError("token 不能为空")
        self.token = token

    def get_token(self) -> str:
        """登录并获取后台 token，功能尚未实现。"""
        raise NotImplementedError("后台登录接口尚未实现")


if __name__ == "__main__":
    background = Background(environment="dev")
    background.check_token(token="your_token_here")
