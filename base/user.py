import http.client
import json
import base64
import time
import random
import string

#抽象用户类，创建用户模拟数据
class User:
    #初始化用户信息，可指定环境、邮箱、平台、渠道代码，默认创建ios，b面用户,密码写死123456
    def __init__(self, 
                 email:str = ''.join(random.choices(string.ascii_lowercase, k=4)) + ''.join(random.choices(string.digits, k=2)) + "@cc.cc",
                 platform: int = 3,
                 channel_code: str = 'TT_iOS_funrise',
                 environment: str = "devapi.ushdev.top",
                 ):
        self.email = email
        self.password="e10adc3949ba59abbe56e057f20f883e"
        self.platform = platform
        self.channel_code = channel_code
        self.environment = environment
        self.uid = None
        self.token = None

    #创建注册函数,oaid为当前时间戳
    def register(self,platform: int=3, 
                channel_code: str='TT_iOS_funrise',
                ):
        #创建HTTPS连接
        conn = http.client.HTTPSConnection(self.environment)
        oaid = str(int(time.time() * 1000))
        #设置请求体
        payload = json.dumps({
        "oaid": oaid,
        "email": self.email,
        "password": self.password,
        "confirm_password": self.password,
        "platform": self.platform,
        "channel_code": self.channel_code,
        "distribution_channel": "dev",
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
            "trackerName": channel_code,
            "trackerToken": "19huppx7",
            "adid": oaid,
            "campaign": "",
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
        print(json.dumps(response, ensure_ascii=False, indent=2))

        if isinstance(response.get("data"), dict):
            self.uid = response["data"]["user"]["id"]
            self.token = response["data"].get("token")
            
        elif res_data:
            self.uid = res_data["data"]["user"]["id"]
            self.token = res_data["data"]["token"]

    def login(self):
        email = self.email
        password = self.password
        
        pass


if __name__ == "__main__":
    user = User()
    user.register()
    print("注册成功!"'\n',
          "邮箱:", user.email, '\n', 
          "密码:", user.password,'\n', 
          "token:", getattr(user, 'token', None),'\n', 
          "uid:", getattr(user, 'uid', None))
