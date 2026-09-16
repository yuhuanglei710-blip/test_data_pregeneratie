"""Unit tests for response parsing and other network-free helpers."""

import base64
import io
import json
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

import jwt

from base import add_money, spin, tournment_test
from base.user import User
from tools.timestamp_tool import TimestampTool


TEST_JWT_SECRET = "test-secret-key-with-at-least-32-bytes"


class UserResponseTests(unittest.TestCase):
    def test_decodes_base64_registration_data(self):
        payload = {"user": {"id": 42}, "token": "token-value"}
        encoded_payload = base64.b64encode(json.dumps(payload).encode()).decode()

        response = User._decode_registration_response({"data": encoded_payload})

        self.assertEqual(response["data"], payload)

    def test_finds_registration_data_inside_nested_wrapper(self):
        payload = {"data": {"user": {"id": 42}, "token": "token-value"}}

        user_data, token = User._find_registration_data(payload)

        self.assertEqual(user_data, {"id": 42})
        self.assertEqual(token, "token-value")


class ApiParsingTests(unittest.TestCase):
    def setUp(self):
        spin._game_token_cache.clear()
        spin._game_session_cache.clear()

    def test_extracts_nested_admin_token(self):
        result = {"data": {"x-token": "admin-token"}}

        self.assertEqual(add_money._extract_token(result), "admin-token")

    def test_admin_operation_requires_success_code(self):
        self.assertTrue(add_money.operation_succeeded({"code": 0}))
        self.assertFalse(add_money.operation_succeeded({"code": 1}))

    def test_extracts_game_token_from_encoded_url(self):
        game_data = {"url": "https://example.test/play?sign=game-token"}
        result = {
            "data": base64.b64encode(json.dumps(game_data).encode()).decode()
        }

        self.assertEqual(spin._extract_game_token(result), "game-token")

    def test_decodes_base64_spin_error(self):
        result = spin._decode_api_result(
            {"code": 0, "data": "e30=", "msg": "YmV0IGVycm9y"}
        )

        self.assertEqual(result, {"code": 0, "data": {}, "msg": "bet error"})
        self.assertTrue(spin._spin_failed(result))

    def test_successful_spin_prints_compact_result(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"win": 0}}
        console = io.StringIO()

        with (
            patch.object(spin, "get_valid_game_token", return_value="game-token"),
            patch.object(spin.requests, "post", return_value=response),
            redirect_stdout(console),
        ):
            result = spin.dev_spin("user-token")

        self.assertIs(result, response)
        self.assertEqual(console.getvalue(), '[spin] 下注响应：{"data":{"win":0}}\n')

    def test_reuses_token_and_passes_session_to_next_spin(self):
        game_token = jwt.encode(
            {"exp": int(time.time()) + 60},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        first_response = Mock(status_code=200)
        first_response.json.return_value = {
            "data": {"win": 0, "session_id": "session-1"},
            "msg": "Succeeded",
        }
        second_response = Mock(status_code=200)
        second_response.json.return_value = {
            "data": {"win": 0, "session_id": "session-2"},
            "msg": "Succeeded",
        }

        with (
            patch.object(spin, "get_game_token", return_value=game_token) as fetch,
            patch.object(
                spin.requests,
                "post",
                side_effect=[first_response, second_response],
            ) as post,
        ):
            spin.dev_spin("user-token", print_result=False)
            spin.dev_spin("user-token", print_result=False)

        fetch.assert_called_once_with("user-token", verbose=False)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["session_id"], "")
        self.assertEqual(
            post.call_args_list[1].kwargs["json"]["session_id"],
            "session-1",
        )


class TimestampToolTests(unittest.TestCase):
    def test_adds_and_subtracts_duration(self):
        self.assertEqual(
            TimestampTool.modify_timestamp(timestamp=100, minutes=1),
            160,
        )
        self.assertEqual(
            TimestampTool.modify_timestamp(timestamp=100, seconds=30, method=2),
            70,
        )


class BatchWorkflowTests(unittest.TestCase):
    def test_spins_are_placed_serially(self):
        with patch.object(spin, "dev_spin", return_value=Mock()) as place_spin:
            tournment_test._place_initial_spins(
                "user-token",
                spin_count=3,
            )

        self.assertEqual(place_spin.call_count, 3)
        self.assertEqual(
            place_spin.call_args_list,
            [
                call("user-token", bet_amount=1_000, verbose=False),
                call("user-token", bet_amount=1_000, verbose=False),
                call("user-token", bet_amount=1_000, verbose=False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
