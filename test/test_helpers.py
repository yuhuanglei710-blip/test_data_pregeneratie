"""Unit tests for response parsing and other network-free helpers."""

import base64
import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

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

    def test_extracts_nested_admin_token(self):
        result = {"data": {"x-token": "admin-token"}}

        self.assertEqual(add_money._extract_token(result), "admin-token")

    def test_extracts_game_token_from_encoded_url(self):
        game_data = {"url": "https://example.test/play?sign=game-token"}
        result = {
            "data": base64.b64encode(json.dumps(game_data).encode()).decode()
        }

        self.assertEqual(spin._extract_game_token(result), "game-token")

    def test_successful_spin_is_quiet_by_default(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"win": 0}}
        console = io.StringIO()

        game_token = jwt.encode(
            {"exp": int(time.time()) + 60},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        with (
            patch.object(spin, "get_valid_game_token", return_value=game_token),
            patch.object(spin.requests, "post", return_value=response),
            redirect_stdout(console),
        ):
            result = spin.dev_spin("user-token")

        self.assertIs(result, response)
        self.assertEqual(console.getvalue(), "")

    def test_reuses_unexpired_game_token(self):
        game_token = jwt.encode(
            {"exp": int(time.time()) + 60},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )

        with patch.object(spin, "get_game_token", return_value=game_token) as fetch:
            first = spin.get_valid_game_token("user-token")
            second = spin.get_valid_game_token("user-token")

        self.assertEqual(first, game_token)
        self.assertEqual(second, game_token)
        fetch.assert_called_once_with("user-token", verbose=False)

    def test_refreshes_expired_game_token(self):
        expired_token = jwt.encode(
            {"exp": int(time.time()) - 60},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        fresh_token = jwt.encode(
            {"exp": int(time.time()) + 60},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        spin._game_token_cache["user-token"] = expired_token

        with patch.object(spin, "get_game_token", return_value=fresh_token) as fetch:
            result = spin.get_valid_game_token("user-token")

        self.assertEqual(result, fresh_token)
        fetch.assert_called_once_with("user-token", verbose=False)


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
    def test_spins_use_at_most_three_workers(self):
        counter_lock = threading.Lock()
        active_workers = 0
        maximum_workers = 0

        def fake_spin(user_token, *, verbose=False):
            nonlocal active_workers, maximum_workers
            with counter_lock:
                active_workers += 1
                maximum_workers = max(maximum_workers, active_workers)
            time.sleep(0.02)
            with counter_lock:
                active_workers -= 1
            return Mock()

        with (
            patch.object(spin, "get_valid_game_token", return_value="game-token"),
            patch.object(spin, "dev_spin", side_effect=fake_spin) as place_spin,
        ):
            tournment_test._place_initial_spins(
                "user-token",
                spin_count=9,
                concurrency=3,
            )

        self.assertEqual(place_spin.call_count, 9)
        self.assertGreater(maximum_workers, 1)
        self.assertLessEqual(maximum_workers, 3)


if __name__ == "__main__":
    unittest.main()
