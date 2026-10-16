"""后台用户查询客户端测试。"""

import unittest
from unittest.mock import Mock, patch

import jwt

from api.background import Background


class BackgroundUserQueryTests(unittest.TestCase):
    def test_query_user_calls_list_then_detail_with_expected_protocol(self) -> None:
        list_response = Mock()
        list_response.json.return_value = {
            "code": 0,
            "data": [{"id": 13425, "username": "user@example.com"}],
        }
        detail_response = Mock()
        detail_response.json.return_value = {
            "code": 0,
            "data": {"id": 13425, "nickname": "Player_113425"},
        }

        with patch(
            "api.background.requests.post",
            side_effect=(list_response, detail_response),
        ) as post:
            client = Background("huidu")
            client.check_token("test-token")
            result = client.query_user(13425)

        self.assertEqual(result["detail"]["nickname"], "Player_113425")
        self.assertEqual(post.call_count, 2)
        first = post.call_args_list[0]
        self.assertTrue(first.args[0].endswith("/user/GetUserList"))
        self.assertEqual(first.kwargs["json"], {"id": 13425, "timezone": 0})
        self.assertEqual(first.kwargs["headers"]["X-Token"], "test-token")
        self.assertEqual(first.kwargs["headers"]["X-User-Id"], "1")
        second = post.call_args_list[1]
        self.assertTrue(second.args[0].endswith("/user/GetUserInfo"))
        self.assertEqual(
            second.kwargs["json"],
            {"id": 13425, "timezone": 0, "lang": "zh-CN"},
        )

    def test_query_user_does_not_request_detail_when_user_is_not_found(self) -> None:
        response = Mock()
        response.json.return_value = {"code": 0, "data": []}

        with patch("api.background.requests.post", return_value=response) as post:
            client = Background("huidu")
            client.check_token("test-token")
            result = client.query_user(999)

        self.assertEqual(result, {"users": [], "detail": None})
        post.assert_called_once()

    def test_query_automatically_logs_in_and_uses_returned_identity(self) -> None:
        response = Mock()
        response.json.return_value = {"code": 0, "data": []}
        token = jwt.encode(
            {"ID": 9},
            "test-secret-that-is-at-least-32-bytes",
            algorithm="HS256",
        )

        with (
            patch("api.background.login", return_value=token) as login,
            patch("api.background.requests.post", return_value=response) as post,
        ):
            result = Background("huidu").query_user(13425)

        self.assertEqual(result, {"users": [], "detail": None})
        login.assert_called_once_with("https://hdadmin.ushdev.top")
        self.assertEqual(post.call_args.kwargs["headers"]["X-Token"], token)
        self.assertEqual(post.call_args.kwargs["headers"]["X-User-Id"], "9")

    def test_business_error_is_raised(self) -> None:
        response = Mock()
        response.json.return_value = {"code": 7, "msg": "token 已失效"}

        with patch("api.background.requests.post", return_value=response):
            client = Background("huidu")
            client.check_token("expired-token")
            with self.assertRaisesRegex(RuntimeError, "token 已失效"):
                client.find_users(1)


if __name__ == "__main__":
    unittest.main()
