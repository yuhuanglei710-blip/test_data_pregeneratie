import http.client
import json
from dotenv import load_dotenv
import os
import jwt

class Background:
    '''
    后台管理接口的复用，仅挑选最常用部分接口
    '''
    def __init__(self, environment: str = "dev"):
        '''
        加载环境文件，获取环境变量。
        初始化蓝图，域名，token为None。
        '''
        load_dotenv(f"{environment}.env")
        self.environment = environment
        self.blueprint = "/api/operationManage"
        self.domain = os.getenv("background_domain")
        self.token = None

    def pass_kyc(self, user_id: int):
        '''
        通过用户KYC审核
        '''
        pass

    def reset_kyc(self, user_id: int):
        '''
        重置用户KYC审核
        '''
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
            f"{self.blueprint}/user/GetUserList",
            headers=headers,
            body=payload
        )
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        print(data)
        return json.loads(data)

    def check_token(self, token: str):
        """
        检查token是否缓存token以及有效性
        """
        self.token = token
        

    def get_token(self):
        """
        通过接口伪造登录获取后台最新token
        """
        payload = {
            "username": "admin",
            "password": "us.1us.1",
            "captcha": "",
            "captchaId": "2AFQVrvGnQMTrGYtno0e",
            "openCaptcha": "false"
        }


if __name__ == "__main__":
    background = Background(environment="dev")
    background.check_token(token="your_token_here")