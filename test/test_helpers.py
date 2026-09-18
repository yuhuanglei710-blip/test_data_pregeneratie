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

from base import account_batch, add_money, database_config, spin, tournment_test
from base.app_config import load_channel_codes, save_channel_codes
from base.database_config import (
    DatabaseConnectionConfig,
    load_database_connections,
    save_database_connection,
)
from base.enums import Platform
from base.user import DEFAULT_CHANNEL_CODE, User
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


class AppConfigTests(unittest.TestCase):
    def test_missing_channel_code_config_uses_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codes = load_channel_codes("dev", f"{temp_dir}/missing.json")

        self.assertEqual(codes, [DEFAULT_CHANNEL_CODE])

    def test_channel_codes_are_normalized_and_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/channel_codes.json"
            saved = save_channel_codes(
                "dev",
                [" first ", "first", "second"],
                config_file,
            )
            loaded = load_channel_codes("dev", config_file)

        self.assertEqual(saved, ["first", "second"])
        self.assertEqual(loaded, ["first", "second"])

    def test_channel_codes_are_isolated_by_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/channel_codes.json"
            save_channel_codes("dev", ["dev-code"], config_file)
            save_channel_codes("prod", ["prod-code"], config_file)

            dev_codes = load_channel_codes("dev", config_file)
            prod_codes = load_channel_codes("prod", config_file)
            huidu_codes = load_channel_codes("huidu", config_file)

        self.assertEqual(dev_codes, ["dev-code"])
        self.assertEqual(prod_codes, ["prod-code"])
        self.assertEqual(huidu_codes, [DEFAULT_CHANNEL_CODE])


class DatabaseConfigTests(unittest.TestCase):
    @staticmethod
    def _connection(key_id: str, ssh_host: str) -> DatabaseConnectionConfig:
        return DatabaseConnectionConfig(
            ssh_host=ssh_host,
            ssh_username="deploy",
            ssh_private_key_id=key_id,
            database_name="automation",
            database_username="tester",
            database_password="secret",
        )

    def test_connections_are_isolated_by_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = f"{temp_dir}/id_test"
            with open(key_file, "w", encoding="utf-8") as private_key:
                private_key.write("test key")
            config_file = f"{temp_dir}/database_connections.json"
            with patch.object(
                database_config,
                "resolve_private_key_path",
                return_value=key_file,
            ):
                save_database_connection(
                    "dev",
                    self._connection("key-id", "dev-ssh.example.test"),
                    config_file,
                )
                save_database_connection(
                    "prod",
                    self._connection("key-id", "prod-ssh.example.test"),
                    config_file,
                )

            connections = load_database_connections(config_file)

        self.assertEqual(connections["dev"].ssh_host, "dev-ssh.example.test")
        self.assertEqual(connections["prod"].ssh_host, "prod-ssh.example.test")
        self.assertEqual(connections["huidu"].ssh_host, "")

    def test_missing_private_key_is_rejected(self):
        connection = self._connection("missing-key-id", "ssh.example.test")

        with self.assertRaisesRegex(ValueError, "私钥已不存在"):
            database_config.validate_database_connection(connection)
        self.assertFalse(
            database_config.is_database_connection_configured(connection)
        )

    def test_complete_connection_is_detected_as_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = f"{temp_dir}/id_test"
            with open(key_file, "w", encoding="utf-8") as private_key:
                private_key.write("test key")
            connection = self._connection("key-id", "ssh.example.test")
            key = database_config.SshPrivateKey("key-id", "id_test", key_file)

            with patch.object(
                database_config,
                "load_ssh_private_keys",
                return_value={"key-id": key},
            ):
                configured = database_config.is_database_connection_configured(
                    connection
                )

        self.assertTrue(configured)

    def test_private_key_is_imported_once_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = f"{temp_dir}/id_ed25519"
            library_file = f"{temp_dir}/ssh_private_keys.json"
            with open(key_file, "w", encoding="utf-8") as private_key:
                private_key.write("test key")

            first = database_config.import_ssh_private_key(
                key_file,
                library_file,
            )
            second = database_config.import_ssh_private_key(
                key_file,
                library_file,
            )
            loaded = database_config.load_ssh_private_keys(library_file)

            self.assertEqual(first.key_id, second.key_id)
            self.assertEqual(list(loaded), [first.key_id])
            self.assertEqual(loaded[first.key_id].path, first.path)

            database_config.remove_ssh_private_key(
                first.key_id,
                library_file,
            )
            remaining = database_config.load_ssh_private_keys(library_file)

        self.assertEqual(remaining, {})

    def test_ssh_uses_only_selected_private_key(self):
        connection = self._connection("key-id", "ssh.example.test")
        client = Mock()

        with (
            patch("paramiko.SSHClient", return_value=client),
            patch.object(
                database_config,
                "resolve_private_key_path",
                return_value="selected-private-key",
            ),
        ):
            result = database_config._connect_ssh_client(connection)

        self.assertIs(result, client)
        client.connect.assert_called_once_with(
            hostname="ssh.example.test",
            port=22,
            username="deploy",
            key_filename="selected-private-key",
            password=None,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        )


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

    def test_huidu_game_token_uses_gray_environment_endpoints(self):
        game_info = {
            "url": "https://game.example.test/play?sign=huidu-game-token"
        }
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": base64.b64encode(
                json.dumps(game_info).encode("utf-8")
            ).decode("ascii")
        }

        with patch.object(spin.requests, "post", return_value=response) as post:
            token = spin.get_game_token(
                "huidu-user-token",
                environment="huidu",
            )

        self.assertEqual(token, "huidu-game-token")
        request = post.call_args
        self.assertEqual(
            request.args[0],
            "https://hdapi.ushdev.top/v1/gamehall/self_game_url",
        )
        self.assertEqual(
            request.kwargs["headers"]["Origin"],
            "https://newhdweb.ushdev.top",
        )
        self.assertNotIn("version", request.kwargs["headers"])
        self.assertEqual(
            request.kwargs["json"]["exit_event"],
            "https://newhdweb.ushdev.top/home",
        )
        self.assertEqual(
            request.kwargs["json"]["cash_event"],
            "https://newhdweb.ushdev.top/backshop",
        )

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

        fetch.assert_called_once_with(
            "user-token",
            environment="dev",
            verbose=False,
        )
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
    def test_tournament_registration_uses_selected_channel_code(self):
        account = Mock(uid=42, token="user-token", email="tournament@cc.cc")
        with (
            patch.object(tournment_test, "User", return_value=account),
            patch.object(
                tournment_test.add_money,
                "add_money",
                return_value={"code": 0},
            ),
            patch.object(tournment_test, "_place_initial_spins"),
        ):
            tournment_test._create_account_and_bet(
                1,
                1,
                environment="dev",
                platform=Platform.ios.value,
                channel_code="tournament-channel",
                admin_base_url="https://admin.example.test",
                initial_balance=1_000,
                spin_count=3,
                spin_count_range=None,
                bet_amount=100,
                verbose=False,
                stop_requested=lambda: False,
            )

        account.register.assert_called_once_with(
            channel_code="tournament-channel",
            platform=Platform.ios.value,
            verbose=False,
        )

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
                call(
                    "user-token",
                    environment="dev",
                    bet_amount=1_000,
                    verbose=False,
                ),
                call(
                    "user-token",
                    environment="dev",
                    bet_amount=1_000,
                    verbose=False,
                ),
                call(
                    "user-token",
                    environment="dev",
                    bet_amount=1_000,
                    verbose=False,
                ),
            ],
        )

    def test_huidu_environment_is_forwarded_to_every_spin(self):
        with patch.object(spin, "dev_spin", return_value=Mock()) as place_spin:
            tournment_test._place_initial_spins(
                "huidu-user-token",
                spin_count=2,
                environment="huidu",
            )

        self.assertEqual(
            place_spin.call_args_list,
            [
                call(
                    "huidu-user-token",
                    environment="huidu",
                    bet_amount=1_000,
                    verbose=False,
                ),
                call(
                    "huidu-user-token",
                    environment="huidu",
                    bet_amount=1_000,
                    verbose=False,
                ),
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

    def test_tournament_web_platform_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Android 或 iOS"):
            tournment_test.create_accounts_and_bet(
                count=1,
                platform=Platform.web.value,
            )


class AccountCreationTests(unittest.TestCase):
    def test_selected_platform_is_used_for_registration(self):
        account = Mock(uid=42, token="user-token", email="android@cc.cc")
        with patch.object(account_batch, "User", return_value=account):
            result = account_batch._register_account(
                1,
                1,
                environment="dev",
                platform=Platform.android.value,
                channel_code="android-channel",
                verbose=False,
                stop_requested=lambda: False,
            )

        account.register.assert_called_once_with(
            channel_code="android-channel",
            platform=Platform.android.value,
            verbose=False,
        )
        self.assertEqual(result.index, 1)

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

    def test_web_platform_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Android 或 iOS"):
            account_batch.create_accounts(count=1, platform=Platform.web.value)

    def test_empty_channel_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Channel Code"):
            account_batch.create_accounts(count=1, channel_code="  ")


if __name__ == "__main__":
    unittest.main()
