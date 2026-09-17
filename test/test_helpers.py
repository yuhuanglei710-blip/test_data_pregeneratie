"""Unit tests for response parsing and other network-free helpers."""

import base64
import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

import jwt

from base import account_batch, add_money, spin, tournment_test
from base.user import User
from tools.timestamp_tool import TimestampTool


TEST_JWT_SECRET = "test-secret-key-with-at-least-32-bytes"


class UserResponseTests(unittest.TestCase):
    def test_parallel_registration_ids_are_unique(self):
        ids = [User._generate_oaid() for _ in range(20)]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids, key=int))

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
    def test_random_spin_count_uses_given_range(self):
        with patch.object(tournment_test.random, "randint", return_value=23) as randint:
            result = tournment_test._resolve_spin_count(30, (20, 30))

        self.assertEqual(result, 23)
        randint.assert_called_once_with(20, 30)

    def test_invalid_random_spin_range_is_rejected(self):
        with self.assertRaises(ValueError):
            tournment_test._resolve_spin_count(30, (30, 20))

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

    def test_stop_request_cancels_before_next_spin(self):
        with patch.object(spin, "dev_spin") as place_spin:
            with self.assertRaises(tournment_test.BatchCancelled):
                tournment_test._place_initial_spins(
                    "user-token",
                    spin_count=3,
                    stop_requested=lambda: True,
                )

        place_spin.assert_not_called()

    def test_accounts_run_in_parallel_and_report_progress(self):
        active = 0
        max_active = 0
        active_lock = threading.Lock()
        progress = []

        def run_account(index, count, **kwargs):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with active_lock:
                active -= 1
            return tournment_test.AccountResult(index, f"account {index}\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = f"{temp_dir}/accounts.txt"
            with (
                patch.object(
                    tournment_test.add_money,
                    "base_url_for_environment",
                    return_value="https://admin.example.test",
                ),
                patch.object(
                    tournment_test,
                    "_create_account_and_bet",
                    side_effect=run_account,
                ),
            ):
                successful = tournment_test.create_accounts_and_bet(
                    count=4,
                    output_file=output_file,
                    max_workers=2,
                    progress_callback=lambda completed, total, successes: (
                        progress.append((completed, total, successes))
                    ),
                )

            with open(output_file, encoding="utf-8") as account_file:
                output_lines = set(account_file.readlines())

        self.assertEqual(successful, 4)
        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(progress[-1], (4, 4, 4))
        self.assertEqual(
            output_lines,
            {"account 1\n", "account 2\n", "account 3\n", "account 4\n"},
        )

    def test_parallel_account_count_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "并行账号数"):
            tournment_test.create_accounts_and_bet(count=1, max_workers=0)


class AccountCreationTests(unittest.TestCase):
    def test_account_only_workflow_exports_registered_accounts(self):
        progress = []

        def register(index, count, **kwargs):
            return account_batch.RegisteredAccount(index, f"account {index}\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = f"{temp_dir}/accounts.txt"
            with patch.object(
                account_batch,
                "_register_account",
                side_effect=register,
            ):
                successful = account_batch.create_accounts(
                    count=3,
                    output_file=output_file,
                    max_workers=2,
                    progress_callback=lambda completed, total, successes: (
                        progress.append((completed, total, successes))
                    ),
                )

            with open(output_file, encoding="utf-8") as account_file:
                lines = set(account_file.readlines())

        self.assertEqual(successful, 3)
        self.assertEqual(progress[-1], (3, 3, 3))
        self.assertEqual(lines, {"account 1\n", "account 2\n", "account 3\n"})


if __name__ == "__main__":
    unittest.main()
