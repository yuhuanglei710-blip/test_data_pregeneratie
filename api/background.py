import http.client
import json
from dotenv import load_dotenv
import os


class Background:
    def __init__(self, environment: str = "dev"):
        load_dotenv(f"{environment}.env")
        self.bgm = "/api/operationManage"
        self.domain = os.getenv("background_domain")
        self.token = None

    def pass_kyc(self, user_id: int):
        pass

    def reset_kyc(self, user_id: int):
        pass

    def get_user_info(self, user_id: int):
        conn = http.client.HTTPSConnection(self.domain)
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        payload = json.dumps({
            "user_id": user_id,
            "timezone": 0
        })
        conn.request(
            "POST",
            f"{self.bgm}/user/GetUserList",
            headers=headers,
            body=payload
        )

    def check_token(self, token: str):
        """检查token是否有效"""
        self.token = token
        conn = http.client.HTTPSConnection(self.domain)
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        conn.request("GET", "/api/v1/user/check-token", headers=headers)

    def get_token(self):
        """获取后台最新token"""
        payload = {
            "username": "admin",
            "password": "us.1us.1",
            "captcha": "",
            "captchaId": "2AFQVrvGnQMTrGYtno0e",
            "openCaptcha": "false"
        }
        return self.token


if __name__ == "__main__":
    background = Background(environment="dev")
    background.check_token(token="your_token_here")