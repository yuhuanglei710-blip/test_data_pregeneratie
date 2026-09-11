import http.client

class Background:
    def __init__(self, domain: str):
        self.domain = domain
        self.token = none

    def check_token(self, token: str):
        self.token = token
        conn = http.client.HTTPSConnection(self.domain)
        headers = {
            'Authorization': f'Bearer {self.token}'
        }
        conn.request("GET", "/api/v1/user/check-token", headers=headers)


    def get_token(self):
        payload = {"username":"admin","password":"us.1us.1","captcha":"","captchaId":"2AFQVrvGnQMTrGYtno0e","openCaptcha":false}
        return self.token



if __name__ == "__main__":
    background = Background(domain="api.example.com")
    background.check_token(token="your_token_here")