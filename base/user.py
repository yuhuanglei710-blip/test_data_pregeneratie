import http.client
import json
import base64
import os
import time
import random
import string
from dotenv import load_dotenv
#抽象用户类，创建用户模拟数据
class User:
    #初始化用户信息，可指定环境、邮箱、平台、渠道代码，默认创建ios，b面用户,密码写死123456
    def __init__(self, 
                 email:str = ''.join(random.choices(string.ascii_lowercase, k=4)) + ''.join(random.choices(string.digits, k=2)) + "@cc.cc",
                 environment: str = "dev",
                 ):
        print(environment)
        self.environment = environment
        #根据环境变量加载不同的配置文件
        if self.environment not in ["dev","huidu","prod","yy","individual"]:
            return "Invalid environment. Choose from 'dev', 'huidu', or 'prod'."
        else:
            load_dotenv(f"{self.environment}.env")
            self.domain = os.getenv("domain")
        self.email = email
        self.password="e10adc3949ba59abbe56e057f20f883e"
        self.uid = None
        self.platform = None
        self.channel_code = None
        self.token = None

    #创建注册函数,oaid为当前时间戳
    def register(self,
                channel_code: str='com.ushafdemo.androidapk|None|',
                down_origin: str='gpa17drop',
                platform: int = 3,
                ):
        self.down_origin = down_origin
        self.platform = platform
        self.channel_code = channel_code
        #创建HTTPS连接
        conn = http.client.HTTPSConnection(self.domain)
        oaid = str(int(time.time() * 1000))
        #设置请求体
        payload = json.dumps({
        "oaid": oaid,
        "email": self.email,
        "password": self.password,
        "confirm_password": self.password,
        "platform": self.platform,
        "channel_code": self.channel_code,
        "distribution_channel": self.down_origin,
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
        "ip_json": json.dumps({
            "ip": "172.83.157.240",
            "regionName": "Washington",
            "countryCode": "US",
            "city": "Seattle",
            "country": "United States of America"
        }),
        "entered_code": "",
        "leisure_game_import_token": "",
        "country": "US",
        "province": "Washington",
        "city": "Seattle",
        "phone_os_version": "",
        "adjust_info": json.dumps({
            "network": self.channel_code,
            "trackerName": self.down_origin,
            "trackerToken": "19huppx7",
            "adid": oaid,
            "campaign": "b4733853b4790ac2e4aa85e1c2c69438",
            "creative": "",
            "costType": "",
            "costCurrency": "",
            "costAmount": 0
        }),
        "area_limit": {
            "language": "zh-CN",
            "isp": "",
            "ip_country": "US",
            "ip_city": "Seattle",
            "ip_province": "Washington",
            "vpn": 0,
            "zone_info": ""
        }
        })
        #设置请求头
        headers = {
        'Content-Type': 'application/json'
        }
        #发送请求获取响应
        conn.request("POST", "/v1/user/register", payload, headers)
        res = conn.getresponse()
        data = res.read()
        response = json.loads(data.decode("utf-8"))


        #base64解码msg和data字段
        if "msg" in response:
            response["msg"] = base64.b64decode(response["msg"]).decode("utf-8")
        res_data = ""
        if "data" in response:
            res_data = base64.b64decode(response["data"]).decode("utf-8")
            try:
                response["data"] = json.loads(res_data)
            except json.JSONDecodeError:
                response["data"] = res_data
        #print(json.dumps(response, ensure_ascii=False, indent=2))

        if isinstance(response.get("data"), dict):
            self.uid = response["data"]["user"]["id"]
            self.token = response["data"].get("token")
            
        elif res_data:
            self.uid = res_data["data"]["user"]["id"]
            self.token = res_data["data"]["token"]
    #登录用于获取所有用户信息
    def login(self):
        email = self.email
        password = self.password
        pass

    @staticmethod    
    def map_translate_dic(key):
        '''
        将key映射为对应的值
        '''
        mapping = {
            "dev": "测试环境",
            "huidu": "灰度环境",
            "prod": "生产环境",
            "yy": " 运营环境",
            "individual": "个人服环境"
        }
        if mapping.get(key):
            return mapping[key]
        return "Unknown environment"

    @staticmethod
    def map_platform(value):
        mapping = {
            1: "web",
            2: "android",
            3: "ios",
        }
        if mapping.get(value):
            return mapping[value]
        return "Unknown platform"

if __name__ == "__main__":
    user = User(environment="dev")
    user.register(platform=1)
    print('===================', "注册成功!", '\n',
          "环境:", User.map_translate_dic(user.environment), '\n',
          "uid:", getattr(user, 'uid', None), '\n',
          "邮箱:", user.email, '\n', 
          "密码:", '123456','\n',  
          )
