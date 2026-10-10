"""Unit tests for response parsing and other network-free helpers."""

import base64
import io
import json
import plistlib
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY, Mock, call, patch

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from base import (
    account_batch,
    add_money,
    android_log,
    apk_manager,
    api_request,
    channel_source,
    database_config,
    environment_policy,
    feature_scenario,
    ipa_manager,
    sql_data,
    spin,
    tournment_test,
)
from base.app_config import load_channel_codes, save_channel_codes
from base.database_config import (
    DatabaseConnectionConfig,
    load_database_connections,
    save_database_connection,
)
from base.enums import Platform
from base.user import DEFAULT_CHANNEL_CODE, DEFAULT_PASSWORD_HASH, User
from tools.timestamp_tool import TimestampTool


TEST_JWT_SECRET = "test-secret-key-with-at-least-32-bytes"


class UserResponseTests(unittest.TestCase):
    def test_parallel_registration_ids_are_unique(self):
        ids = [User._generate_oaid() for _ in range(20)]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids, key=int))

    def test_prod_is_not_a_supported_user_environment(self):
        with self.assertRaisesRegex(ValueError, "不支持的环境"):
            User(environment="prod")

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

    def test_login_uses_single_default_password_hash_and_saves_token(self):
        account = User(email="player@cc.cc", environment="dev")
        account.password = "database-double-md5"
        response = {
            "data": {
                "user": {"id": 42},
                "token": "user-token",
            }
        }

        with patch.object(
            account,
            "_post_user_request",
            return_value=response,
        ) as request:
            account.login(platform=3)

        self.assertEqual(account.uid, 42)
        self.assertEqual(account.token, "user-token")
        path, payload, action = request.call_args.args
        self.assertEqual(path, "/v1/user/login")
        self.assertEqual(action, "登录")
        self.assertEqual(payload["email"], "player@cc.cc")
        self.assertEqual(payload["password"], DEFAULT_PASSWORD_HASH)
        self.assertEqual(payload["platform"], 3)
        self.assertEqual(payload["distribution_channel"], "")
        self.assertEqual(
            set(payload),
            {
                "advertising_id",
                "app_version",
                "city",
                "country",
                "data",
                "distribution_channel",
                "email",
                "password",
                "phone_model",
                "phone_os_version",
                "platform",
                "province",
                "res_version",
            },
        )


class RemovedEnvironmentPolicyTests(unittest.TestCase):
    def test_prod_environment_and_known_hosts_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "永久移除"):
            environment_policy.ensure_environment_allowed("prod")
        with self.assertRaisesRegex(ValueError, "生产地址"):
            environment_policy.ensure_url_allowed(
                "https://api.hotspin777.com/v1/user/login"
            )

    def test_prod_marked_values_cannot_be_cached(self):
        with self.assertRaisesRegex(ValueError, "禁止缓存"):
            environment_policy.ensure_cache_value_allowed(
                "test_ua_custom_prod"
            )

    def test_non_prod_environment_and_url_remain_allowed(self):
        environment_policy.ensure_environment_allowed("dev")
        environment_policy.ensure_url_allowed(
            "https://devapi.ushdev.top/v1/user/login"
        )


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
            save_channel_codes("yy", ["yy-code"], config_file)

            dev_codes = load_channel_codes("dev", config_file)
            yy_codes = load_channel_codes("yy", config_file)
            huidu_codes = load_channel_codes("huidu", config_file)

        self.assertEqual(dev_codes, ["dev-code"])
        self.assertEqual(yy_codes, ["yy-code"])
        self.assertEqual(huidu_codes, [DEFAULT_CHANNEL_CODE])

    def test_removed_prod_environment_cannot_be_loaded_or_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/channel_codes.json"
            with self.assertRaisesRegex(ValueError, "不支持的环境"):
                load_channel_codes("prod", config_file)
            with self.assertRaisesRegex(ValueError, "不支持的环境"):
                save_channel_codes("prod", ["forbidden"], config_file)


class ApkManagerTests(unittest.TestCase):
    def test_cache_apk_deduplicates_by_md5_and_updates_attribution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "demo.apk"
            source.write_bytes(b"apk-content")
            config_file = Path(temp_dir) / "apk_packages.json"
            cache_dir = Path(temp_dir) / "apks"

            first = apk_manager.cache_apk(
                source,
                "https://example.test/first",
                config_path=config_file,
                cache_dir=cache_dir,
            )
            second = apk_manager.cache_apk(
                source,
                "https://example.test/second",
                config_path=config_file,
                cache_dir=cache_dir,
            )

            self.assertFalse(first.duplicate)
            self.assertTrue(second.duplicate)
            self.assertEqual(first.package.package_id, second.package.package_id)
            self.assertEqual(
                apk_manager.load_cached_apks(config_file)[0].attribution,
                "https://example.test/second",
            )
            self.assertTrue(Path(second.package.path).is_file())

    def test_install_reports_signature_conflict_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            apk_file = Path(temp_dir) / "demo.apk"
            apk_file.write_bytes(b"apk-content")
            message = (
                "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: Package "
                "com.example.demo signatures do not match previously installed version]"
            )
            with patch.object(
                apk_manager,
                "_run_adb",
                side_effect=apk_manager.AdbCommandError(message, message),
            ):
                result = apk_manager.install_apk("device-1", apk_file)

        self.assertEqual(result.status, "signature-conflict")
        self.assertEqual(result.package_name, "com.example.demo")

    def test_list_devices_parses_status_and_details(self):
        output = (
            "List of devices attached\n"
            "serial-1 device product:test model:Pixel\n"
            "serial-2 unauthorized usb:1-1\n"
        )
        with patch.object(apk_manager, "_run_adb", return_value=output):
            devices = apk_manager.list_android_devices()

        self.assertEqual(
            devices,
            [
                apk_manager.AndroidDevice(
                    "serial-1", "device", "product:test model:Pixel"
                ),
                apk_manager.AndroidDevice("serial-2", "unauthorized", "usb:1-1"),
            ],
        )

    def test_attribution_url_must_be_http(self):
        with self.assertRaisesRegex(ValueError, "http"):
            apk_manager.open_attribution_url("device-1", "javascript:alert(1)")

    def test_long_attribution_url_is_sent_through_adb_stdin(self):
        url = "https://example.test/attribute?payload=" + ("x" * 100_000)
        with patch.object(apk_manager, "_run_adb") as run_adb:
            apk_manager.open_attribution_url("device-1", url)

        arguments = run_adb.call_args.args[0]
        self.assertEqual(arguments, ["-s", "device-1", "shell"])
        self.assertIn(url, run_adb.call_args.kwargs["input_text"])


class AndroidLogTests(unittest.TestCase):
    def test_lists_only_valid_unique_user_packages(self):
        output = (
            "package:com.example.beta\n"
            "package:com.example.alpha\n"
            "package:invalid\n"
            "package:com.example.alpha\n"
        )
        with patch.object(android_log, "_run_adb", return_value=output) as run_adb:
            packages = android_log.list_installed_packages("device-1")

        self.assertEqual(
            packages,
            ["com.example.alpha", "com.example.beta"],
        )
        run_adb.assert_called_once_with(
            ["-s", "device-1", "shell", "pm", "list", "packages", "-3"],
            timeout=30,
        )

    def test_resolves_running_application_pid_without_using_shell(self):
        with patch.object(android_log, "_run_adb", return_value="4321\n") as run_adb:
            pid = android_log.resolve_application_pid(
                "device-1",
                "com.example.app",
            )

        self.assertEqual(pid, 4321)
        run_adb.assert_called_once_with(
            ["-s", "device-1", "shell", "pidof", "com.example.app"],
            timeout=15,
        )

    def test_reports_when_selected_application_is_not_running(self):
        with patch.object(
            android_log,
            "_run_adb",
            side_effect=apk_manager.AdbCommandError("not found"),
        ):
            with self.assertRaisesRegex(ValueError, "未运行"):
                android_log.resolve_application_pid(
                    "device-1",
                    "com.example.app",
                )

    def test_builds_logcat_arguments_with_pid_and_level(self):
        arguments = android_log.build_logcat_arguments(
            "device-1",
            "w",
            pid=4321,
        )

        self.assertEqual(
            arguments,
            [
                "-s",
                "device-1",
                "logcat",
                "-v",
                "threadtime",
                "--pid=4321",
                "*:W",
            ],
        )

    def test_streams_filtered_display_and_writes_complete_log(self):
        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = io.StringIO("Alpha first\nbeta second\n")

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def terminate(self):
                return None

            def kill(self):
                return None

        process = FakeProcess()
        popen_factory = Mock(return_value=process)
        displayed: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            android_log,
            "adb_executable",
            return_value="adb",
        ):
            output_path = Path(temp_dir) / "capture.log"
            capture = android_log.AndroidLogCapture(
                android_log.LogcatCaptureConfig(
                    serial="device-1",
                    minimum_level="D",
                    keyword="BETA",
                    output_path=str(output_path),
                ),
                displayed.append,
                popen_factory=popen_factory,
            )

            capture.run()

            complete_output = output_path.read_text(encoding="utf-8")

        self.assertEqual("".join(displayed), "beta second\n")
        self.assertEqual(complete_output, "Alpha first\nbeta second\n")
        command = popen_factory.call_args.args[0]
        self.assertEqual(
            command,
            ["adb", "-s", "device-1", "logcat", "-v", "threadtime", "*:D"],
        )
        self.assertNotIn("shell", popen_factory.call_args.kwargs)

    def test_stop_request_terminates_running_logcat_process(self):
        process = Mock()
        process.poll.return_value = None
        capture = android_log.AndroidLogCapture(
            android_log.LogcatCaptureConfig(serial="device-1"),
            lambda _text: None,
        )
        capture._process = process

        capture.request_stop()

        self.assertTrue(capture.stop_event.is_set())
        self.assertTrue(capture.cancel_requested.is_set())
        process.terminate.assert_called_once_with()

    def test_does_not_clear_history_when_selected_app_is_not_running(self):
        capture = android_log.AndroidLogCapture(
            android_log.LogcatCaptureConfig(
                serial="device-1",
                package_name="com.example.app",
                clear_before_start=True,
            ),
            lambda _text: None,
        )
        with patch.object(
            android_log,
            "resolve_application_pid",
            side_effect=ValueError("应用未运行"),
        ), patch.object(android_log, "clear_logcat") as clear_logcat:
            with self.assertRaisesRegex(ValueError, "未运行"):
                capture.run()

        clear_logcat.assert_not_called()

    def test_does_not_clear_history_when_output_file_cannot_be_opened(self):
        capture = android_log.AndroidLogCapture(
            android_log.LogcatCaptureConfig(
                serial="device-1",
                clear_before_start=True,
                output_path="capture.log",
            ),
            lambda _text: None,
        )
        with patch.object(
            android_log,
            "adb_executable",
            return_value="adb",
        ), patch.object(
            android_log.Path,
            "open",
            side_effect=PermissionError("denied"),
        ), patch.object(android_log, "clear_logcat") as clear_logcat:
            with self.assertRaisesRegex(PermissionError, "denied"):
                capture.run()

        clear_logcat.assert_not_called()

    def test_output_write_failure_is_not_treated_as_user_cancellation(self):
        class FailingStream:
            closed = False

            def write(self, _text):
                raise OSError("disk full")

            def flush(self):
                return None

            def close(self):
                self.closed = True

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = io.StringIO("one line\n")
                self.return_code = None
                self.terminated = False

            def poll(self):
                return self.return_code

            def terminate(self):
                self.terminated = True
                self.return_code = -15

            def wait(self, timeout=None):
                return self.return_code

            def kill(self):
                self.return_code = -9

        stream = FailingStream()
        process = FakeProcess()
        capture = android_log.AndroidLogCapture(
            android_log.LogcatCaptureConfig(
                serial="device-1",
                output_path="capture.log",
            ),
            lambda _text: None,
            popen_factory=Mock(return_value=process),
        )
        with patch.object(
            android_log,
            "adb_executable",
            return_value="adb",
        ), patch.object(android_log.Path, "open", return_value=stream):
            with self.assertRaisesRegex(OSError, "disk full"):
                capture.run()

        self.assertTrue(stream.closed)
        self.assertTrue(process.terminated)
        self.assertIsNone(capture._process)
        self.assertTrue(capture.stop_event.is_set())
        self.assertFalse(capture.cancel_requested.is_set())

    def test_output_close_failure_still_cleans_up_logcat_process(self):
        class CloseFailingStream:
            def write(self, _text):
                return None

            def flush(self):
                return None

            def close(self):
                raise OSError("close failed")

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = io.StringIO("")
                self.return_code = None
                self.terminated = False

            def poll(self):
                return self.return_code

            def terminate(self):
                self.terminated = True
                self.return_code = -15

            def wait(self, timeout=None):
                return self.return_code

            def kill(self):
                self.return_code = -9

        process = FakeProcess()
        capture = android_log.AndroidLogCapture(
            android_log.LogcatCaptureConfig(
                serial="device-1",
                output_path="capture.log",
            ),
            lambda _text: None,
            popen_factory=Mock(return_value=process),
        )
        with patch.object(
            android_log,
            "adb_executable",
            return_value="adb",
        ), patch.object(
            android_log.Path,
            "open",
            return_value=CloseFailingStream(),
        ):
            with self.assertRaisesRegex(OSError, "close failed"):
                capture.run()

        self.assertTrue(process.terminated)
        self.assertIsNone(capture._process)

    def test_stop_force_kills_logcat_when_terminate_does_not_finish(self):
        release_reader = threading.Event()

        class BlockingOutput:
            def __iter__(self):
                return self

            def __next__(self):
                release_reader.wait()
                raise StopIteration

        class StubbornProcess:
            def __init__(self) -> None:
                self.stdout = BlockingOutput()
                self.return_code = None
                self.killed = False

            def poll(self):
                return self.return_code

            def terminate(self):
                return None

            def kill(self):
                self.killed = True
                self.return_code = -9
                release_reader.set()

            def wait(self, timeout=None):
                if self.return_code is None:
                    raise subprocess.TimeoutExpired("adb", timeout)
                return self.return_code

        process = StubbornProcess()
        capture = android_log.AndroidLogCapture(
            android_log.LogcatCaptureConfig(serial="device-1"),
            lambda _text: None,
            popen_factory=Mock(return_value=process),
            stop_timeout=0.1,
        )
        with patch.object(android_log, "adb_executable", return_value="adb"):
            capture_thread = threading.Thread(target=capture.run)
            capture_thread.start()
            deadline = time.monotonic() + 1
            while capture._process is None and time.monotonic() < deadline:
                time.sleep(0.01)

            capture.request_stop()
            capture_thread.join(timeout=1)

        self.assertFalse(capture_thread.is_alive())
        self.assertTrue(process.killed)


class IpaManagerTests(unittest.TestCase):
    @staticmethod
    def _write_ipa(
        path: Path,
        *,
        bundle_id: str = "com.example.demo",
        devices: tuple[str, ...] = ("device-1",),
        expired: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        private_key = ec.generate_private_key(ec.SECP256R1())
        subject = issuer = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "IPA Test Certificate")]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=30))
            .sign(private_key, hashes.SHA256())
        )
        expiration = now - timedelta(days=1) if expired else now + timedelta(days=20)
        profile = {
            "Name": "Test Ad Hoc",
            "TeamIdentifier": ["TEAM123"],
            "CreationDate": now - timedelta(days=1),
            "ExpirationDate": expiration,
            "ProvisionedDevices": list(devices),
            "DeveloperCertificates": [
                certificate.public_bytes(serialization.Encoding.DER)
            ],
            "Entitlements": {
                "application-identifier": f"TEAM123.{bundle_id}",
            },
        }
        info = {
            "CFBundleIdentifier": bundle_id,
            "CFBundleExecutable": "Demo",
        }
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Payload/Demo.app/Info.plist", plistlib.dumps(info))
            archive.writestr("Payload/Demo.app/Demo", b"mach-o-placeholder")
            archive.writestr("Payload/Demo.app/_CodeSignature/CodeResources", b"signed")
            archive.writestr(
                "Payload/Demo.app/embedded.mobileprovision",
                b"CMS-prefix" + plistlib.dumps(profile) + b"CMS-suffix",
            )

    def test_signature_preflight_checks_device_allowlist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ipa_file = Path(temp_dir) / "demo.ipa"
            self._write_ipa(ipa_file)

            allowed = ipa_manager.verify_ipa_signature(ipa_file, "device-1")
            rejected = ipa_manager.verify_ipa_signature(ipa_file, "device-2")

        self.assertTrue(allowed.valid)
        self.assertEqual(allowed.bundle_id, "com.example.demo")
        self.assertFalse(rejected.valid)
        self.assertIn("不在描述文件白名单", "；".join(rejected.errors))

    def test_cache_accepts_expired_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ipa_file = Path(temp_dir) / "expired.ipa"
            cache_dir = Path(temp_dir) / "cache"
            config_file = Path(temp_dir) / "ipa_packages.json"
            self._write_ipa(ipa_file, expired=True)

            result = ipa_manager.cache_ipa(
                ipa_file,
                config_path=config_file,
                cache_dir=cache_dir,
            )

            self.assertEqual(ipa_manager.load_cached_ipas(config_file), [result.package])
            self.assertTrue(Path(result.package.path).is_file())

    def test_download_is_cached_without_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.ipa"
            cache_dir = Path(temp_dir) / "cache"
            config_file = Path(temp_dir) / "ipa_packages.json"
            self._write_ipa(source)
            payload = source.read_bytes()
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.headers = {"Content-Length": str(len(payload))}
            response.iter_content.return_value = [payload]

            with patch.object(ipa_manager.requests, "get", return_value=response):
                result = ipa_manager.download_and_cache_ipa(
                    "https://example.test/releases/demo.ipa",
                    "https://example.test/track",
                    config_path=config_file,
                    cache_dir=cache_dir,
                )

            cached_files = list(cache_dir.iterdir())

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(result.package.name, "demo.ipa")
        self.assertEqual(result.package.attribution, "https://example.test/track")
        self.assertEqual(len(cached_files), 1)
        self.assertFalse(cached_files[0].name.startswith("."))

    def test_attribution_runs_before_install_after_reading_metadata(self):
        metadata = ipa_manager.IpaMetadata(
            bundle_id="com.example.demo",
        )
        with patch.object(
            ipa_manager, "read_ipa_metadata", return_value=metadata
        ), patch.object(ipa_manager, "open_ios_attribution_url") as open_url, patch.object(
            ipa_manager, "_run_tidevice"
        ) as run_tidevice:
            result = ipa_manager.attribute_and_install_ipa(
                "device-1", "https://example.test/track", "demo.ipa"
            )

        open_url.assert_called_once_with("device-1", "https://example.test/track")
        run_tidevice.assert_called_once_with(
            ["install", "demo.ipa"], udid="device-1", timeout=600
        )
        self.assertEqual(result.bundle_id, "com.example.demo")

    def test_install_does_not_block_expired_or_unlisted_device(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ipa_file = Path(temp_dir) / "demo.ipa"
            self._write_ipa(ipa_file, expired=True)
            for with_attribution in (False, True):
                with self.subTest(with_attribution=with_attribution), patch.object(
                    ipa_manager, "verify_ipa_signature", side_effect=AssertionError("unexpected preflight")
                ), patch.object(ipa_manager, "_run_tidevice") as run_tidevice, patch.object(
                    ipa_manager, "_run_ios_safari"
                ) as open_safari:
                    if with_attribution:
                        result = ipa_manager.attribute_and_install_ipa(
                            "unlisted-device", "https://example.test/track", ipa_file
                        )
                        open_safari.assert_called_once_with("unlisted-device", "https://example.test/track")
                    else:
                        result = ipa_manager.install_ipa("unlisted-device", ipa_file)
                    run_tidevice.assert_called_with(
                        ["install", str(ipa_file)], udid="unlisted-device", timeout=600
                    )
                    self.assertEqual(result.status, "installed")

    def test_cache_and_install_without_signature_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ipa_file = Path(temp_dir) / "demo.ipa"
            with zipfile.ZipFile(ipa_file, "w") as archive:
                archive.writestr(
                    "Payload/Demo.app/Info.plist",
                    plistlib.dumps({"CFBundleIdentifier": "com.example.demo"}),
                )
            result = ipa_manager.cache_ipa(
                ipa_file, config_path=Path(temp_dir) / "packages.json",
                cache_dir=Path(temp_dir) / "cache",
            )
            self.assertEqual(result.package.profile_name, "")
            with patch.object(
                ipa_manager, "_run_tidevice",
                side_effect=ipa_manager.TideviceCommandError("device rejected installation"),
            ):
                with self.assertRaisesRegex(ipa_manager.TideviceCommandError, "device rejected"):
                    ipa_manager.install_ipa("device-1", result.package.path)

    def test_list_ios_devices_parses_tidevice_json(self):
        output = json.dumps(
            [
                {
                    "udid": "device-1",
                    "name": "QA iPhone",
                    "product_version": "18.0",
                    "conn_type": "USB",
                }
            ]
        )
        with patch.object(ipa_manager, "_run_tidevice", return_value=output):
            devices = ipa_manager.list_ios_devices()

        self.assertEqual(
            devices,
            [ipa_manager.IosDevice("device-1", "QA iPhone", "18.0", "USB")],
        )

    def test_safari_url_uses_stdin_and_checks_device_acknowledgement(self):
        url = 'https://example.test/track?a=1&data="hello"' + 'x' * 10000
        runner = Mock(return_value=subprocess.CompletedProcess(
            [], 0, json.dumps({"status": "opened", "udid": "device-1"}), ""
        ))
        with patch.object(ipa_manager, "_ios_python", return_value="ios-python"):
            ipa_manager._run_ios_safari("device-1", url, runner=runner)
        self.assertNotIn(url, runner.call_args.args[0])
        self.assertEqual(json.loads(runner.call_args.kwargs["input"]), {"udid": "device-1", "url": url})
        self.assertEqual(runner.call_args.kwargs["timeout"], 90)

    def test_safari_errors_and_missing_ack_are_not_success(self):
        outputs = [
            subprocess.CompletedProcess([], 1, '{"status":"error","message":"开启远程自动化"}', ""),
            subprocess.CompletedProcess([], 0, "", "Web inspector is not enabled"),
            subprocess.CompletedProcess([], 0, '{"status":"opened","udid":"other-device"}', ""),
        ]
        with patch.object(ipa_manager, "_ios_python", return_value="ios-python"):
            for output in outputs:
                with self.subTest(output=output), self.assertRaises(ipa_manager.TideviceCommandError):
                    ipa_manager._run_ios_safari("device-1", "https://example.test", runner=Mock(return_value=output))

    def test_attribution_failure_prevents_install(self):
        with patch.object(ipa_manager, "read_ipa_metadata", return_value=ipa_manager.IpaMetadata("com.example.demo")), patch.object(
            ipa_manager, "_run_ios_safari", side_effect=ipa_manager.TideviceCommandError("开启远程自动化")
        ), patch.object(ipa_manager, "_run_tidevice") as install:
            with self.assertRaisesRegex(ipa_manager.TideviceCommandError, "开启远程自动化"):
                ipa_manager.attribute_and_install_ipa("device-1", "https://example.test", "demo.ipa")
            install.assert_not_called()


class SqlDataTests(unittest.TestCase):
    def test_templates_are_saved_updated_and_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/sql_templates.json"
            created = sql_data.save_sql_template(
                "VIP 数据",
                "SET @userid=xxx; UPDATE user SET vip_level=1 WHERE id=@userid;",
                path=config_file,
            )
            updated = sql_data.save_sql_template(
                "VIP 数据 v2",
                "SET @userid=xxx; UPDATE user SET vip_level=2 WHERE id=@userid;",
                template_id=created.template_id,
                path=config_file,
            )
            loaded = sql_data.load_sql_templates(config_file)

            self.assertEqual(loaded, [updated])

            sql_data.delete_sql_template(updated.template_id, config_file)

            self.assertEqual(sql_data.load_sql_templates(config_file), [])

    def test_user_id_placeholder_is_replaced_with_integer(self):
        template = sql_data.SqlTemplate(
            "template-id",
            "test",
            "SET @userid = xxx; SELECT @userid;",
        )

        rendered = sql_data.render_sql_template(template, 4321)

        self.assertEqual(rendered, "SET @userid = 4321; SELECT @userid;")

    def test_bare_user_id_declaration_is_normalized_to_mysql_set(self):
        template = sql_data.SqlTemplate(
            "template-id",
            "test",
            "@userid=xxx; SELECT @userid;",
        )

        rendered = sql_data.render_sql_template(template, 4321)

        self.assertEqual(rendered, "SET @userid=4321; SELECT @userid;")

    def test_template_requires_parameter_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "@参数名=xxx"):
                sql_data.save_sql_template(
                    "invalid",
                    "SELECT 1;",
                    path=f"{temp_dir}/sql_templates.json",
                )

    def test_generic_parameters_are_detected_and_rendered_in_order(self):
        template = sql_data.SqlTemplate(
            "template-id",
            "修改 VIP",
            (
                "@userid=xxx;\n"
                "@viplevel = xxx;\n"
                "@nickname=xxx;\n"
                "UPDATE user SET vip_level=@viplevel, nickname=@nickname "
                "WHERE id=@userid;"
            ),
        )

        self.assertEqual(
            sql_data.template_parameter_names(template),
            ["userid", "viplevel", "nickname"],
        )
        rendered = sql_data.render_sql_template(
            template,
            4321,
            {"viplevel": 4, "nickname": "O'Reilly"},
        )

        self.assertIn("SET @userid=4321;", rendered)
        self.assertIn("SET @viplevel = 4;", rendered)
        self.assertIn("SET @nickname='O''Reilly';", rendered)
        self.assertIn("vip_level=@viplevel", rendered)

    def test_generic_template_can_be_saved_without_user_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            saved = sql_data.save_sql_template(
                "切换状态",
                "@status=xxx; UPDATE feature SET status=@status;",
                path=f"{temp_dir}/sql_templates.json",
            )

        self.assertEqual(sql_data.template_parameter_names(saved), ["status"])

    def test_missing_generic_parameter_is_reported(self):
        template = sql_data.SqlTemplate(
            "template-id",
            "test",
            "@userid=xxx; @viplevel=xxx; SELECT @viplevel;",
        )

        with self.assertRaisesRegex(ValueError, "viplevel"):
            sql_data.render_sql_template(template, 4321)

    def test_runtime_parameter_text_recognizes_common_scalar_types(self):
        self.assertEqual(sql_data.parse_runtime_parameter("42"), 42)
        self.assertIs(sql_data.parse_runtime_parameter("true"), True)
        self.assertIsNone(sql_data.parse_runtime_parameter("null"))
        self.assertEqual(sql_data.parse_runtime_parameter("plain text"), "plain text")


class ApiRequestTests(unittest.TestCase):
    def test_templates_are_saved_updated_and_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/api_templates.json"
            created = api_request.save_api_template(
                "查询用户",
                "GET",
                "/users/{{userid}}",
                path=config_file,
            )
            updated = api_request.save_api_template(
                "更新用户",
                "PATCH",
                "/users/{{userid}}",
                '{"Content-Type":"application/json"}',
                '{"enabled":true}',
                template_id=created.template_id,
                path=config_file,
            )

            self.assertEqual(api_request.load_api_templates(config_file), [updated])

            api_request.delete_api_template(updated.template_id, config_file)

            self.assertEqual(api_request.load_api_templates(config_file), [])

    def test_template_parameter_names_are_unique_and_ordered(self):
        template = api_request.ApiTemplate(
            "id",
            "test",
            "POST",
            "https://example.test/{{userid}}",
            '{"Authorization":"Bearer {{token}}"}',
            '{"id":{{userid}}}',
        )

        self.assertEqual(
            api_request.template_parameter_names(template),
            ["userid", "token"],
        )

    def test_execute_renders_url_headers_and_body(self):
        template = api_request.ApiTemplate(
            "id",
            "test",
            "POST",
            "https://example.test/users/{{userid}}",
            '{"Authorization":"Bearer {{token}}"}',
            '{"user_id":{{userid}}}',
            12,
        )
        response = Mock(
            status_code=200,
            text='{"ok":true}',
            headers={"Content-Type": "application/json"},
        )
        with patch.object(
            api_request.requests,
            "request",
            return_value=response,
        ) as request:
            result = api_request.execute_api_template(
                template,
                {"userid": 42, "token": "secret"},
            )

        request.assert_called_once_with(
            "POST",
            "https://example.test/users/42",
            headers={"Authorization": "Bearer secret"},
            data='{"user_id":42}',
            timeout=12,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.response_text, '{"ok":true}')

    def test_missing_runtime_parameter_is_rejected(self):
        template = api_request.ApiTemplate(
            "id",
            "test",
            "GET",
            "https://example.test/users/{{userid}}",
        )

        with self.assertRaisesRegex(ValueError, "userid"):
            api_request.execute_api_template(template, {})

    def test_relative_path_uses_selected_environment_domain(self):
        template = api_request.ApiTemplate(
            "id",
            "test",
            "GET",
            "/v1/users/{{userid}}",
        )
        response = Mock(status_code=200, text="ok", headers={})
        with (
            patch.object(
                api_request,
                "load_environment_api_base_url",
                return_value="https://yyapi.ushdev.top",
            ) as load_domain,
            patch.object(
                api_request.requests,
                "request",
                return_value=response,
            ) as request,
        ):
            api_request.execute_api_template(
                template,
                {"userid": 42},
                "yy",
            )

        load_domain.assert_called_once_with("yy")
        request.assert_called_once_with(
            "GET",
            "https://yyapi.ushdev.top/v1/users/42",
            headers={},
            data=None,
            timeout=30,
        )

    def test_environment_domain_is_loaded_from_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = f"{temp_dir}/yy.env"
            with open(env_file, "w", encoding="utf-8") as stream:
                stream.write("domain='yyapi.example.test'\n")

            base_url = api_request.load_environment_api_base_url("yy", temp_dir)

        self.assertEqual(base_url, "https://yyapi.example.test")

    def test_runtime_parameters_must_be_json_object(self):
        with self.assertRaisesRegex(ValueError, "JSON 对象"):
            api_request.parse_runtime_parameters("[]")

    def test_protocol_base64_fields_are_decoded(self):
        data = base64.b64encode(b'{"status":"ready"}').decode()
        message = base64.b64encode("成功".encode()).decode()

        decoded = api_request.decode_api_protocol_response(
            json.dumps({"code": 0, "data": data, "msg": message})
        )

        self.assertEqual(
            decoded,
            {"code": 0, "data": {"status": "ready"}, "msg": "成功"},
        )

    def test_json_template_preserves_types_and_escapes_strings(self):
        rendered = api_request.render_json_template(
            '{"uid":{{userid}},"token":"Bearer {{token}}"}',
            {"userid": 42, "token": 'a"b'},
        )

        self.assertEqual(
            json.loads(rendered),
            {"uid": 42, "token": 'Bearer a"b'},
        )


class FeatureScenarioTests(unittest.TestCase):
    def test_scenarios_are_saved_and_deleted(self):
        step = feature_scenario.new_step(
            "assert",
            "校验 code",
            {"path": "response.code", "operator": "equals", "expected": 0},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = f"{temp_dir}/feature_scenarios.json"
            saved = feature_scenario.save_feature_scenario(
                "广告触发",
                [step],
                path=config_file,
            )

            self.assertEqual(
                feature_scenario.load_feature_scenarios(config_file),
                [saved],
            )

            feature_scenario.delete_feature_scenario(
                saved.scenario_id,
                config_file,
            )
            self.assertEqual(
                feature_scenario.load_feature_scenarios(config_file),
                [],
            )

    def test_sql_api_extract_and_assert_steps_share_context(self):
        sql_template = sql_data.SqlTemplate(
            "sql-id",
            "准备数据",
            "SET @userid=xxx; SELECT @userid;",
        )
        api_template = api_request.ApiTemplate(
            "api-id",
            "查询状态",
            "GET",
            "/v1/user/{{userid}}",
        )
        steps = [
            feature_scenario.new_step(
                "sql", "准备数据", {"template_id": "sql-id"}
            ),
            feature_scenario.new_step(
                "api", "查询状态", {"template_id": "api-id"}
            ),
            feature_scenario.new_step(
                "extract",
                "提取状态",
                {"path": "response.data.status", "variable": "status"},
            ),
            feature_scenario.new_step(
                "assert",
                "校验状态",
                {"path": "status", "operator": "equals", "expected": "ready"},
            ),
        ]
        scenario = feature_scenario.FeatureScenario("id", "test", tuple(steps))
        sql_result = sql_data.SqlExecutionResult(
            2,
            0,
            1,
            (({"user_id": 42},),),
        )
        api_result = api_request.ApiExecutionResult(
            200,
            10,
            "raw",
            {},
            {"code": 0, "data": {"status": "ready"}, "msg": "成功"},
        )
        with (
            patch.object(
                feature_scenario,
                "execute_sql_template",
                return_value=sql_result,
            ),
            patch.object(
                feature_scenario,
                "execute_api_template",
                return_value=api_result,
            ),
        ):
            context = feature_scenario.execute_feature_scenario(
                scenario,
                environment="yy",
                runtime_parameters={"userid": 42},
                database_connection=DatabaseConnectionConfig(database_name="ush_yy"),
                sql_templates=[sql_template],
                api_templates=[api_template],
            )

        self.assertEqual(context["status"], "ready")
        self.assertEqual(context["sql"], {"user_id": 42})

    def test_cleanup_step_runs_after_assertion_failure(self):
        api_template = api_request.ApiTemplate(
            "cleanup-api",
            "清理",
            "POST",
            "/cleanup",
        )
        scenario = feature_scenario.FeatureScenario(
            "id",
            "test",
            (
                feature_scenario.new_step(
                    "assert",
                    "失败断言",
                    {"path": "userid", "operator": "equals", "expected": 99},
                ),
                feature_scenario.new_step(
                    "api",
                    "清理数据",
                    {"template_id": "cleanup-api"},
                    cleanup=True,
                ),
            ),
        )
        api_result = api_request.ApiExecutionResult(200, 1, "{}", {}, {})
        with patch.object(
            feature_scenario,
            "execute_api_template",
            return_value=api_result,
        ) as execute_api:
            with self.assertRaises(feature_scenario.ScenarioExecutionError):
                feature_scenario.execute_feature_scenario(
                    scenario,
                    environment="dev",
                    runtime_parameters={"userid": 42},
                    api_templates=[api_template],
                    sql_templates=[],
                )

        execute_api.assert_called_once()


class ChannelSourceTests(unittest.TestCase):
    def test_removed_prod_environment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不支持的环境"):
            channel_source.resolve_registration_channel(
                "prod",
                [],
                can_enter_b=True,
                has_new_user_offer=False,
            )

    def test_supported_environment_matches_channel_source(self):
        sources = [channel_source.ChannelSource("matched-code", "", 1)]

        resolved = channel_source.resolve_registration_channel(
            "yy",
            sources,
            can_enter_b=True,
            has_new_user_offer=False,
        )

        self.assertEqual(resolved, "matched-code")

    def test_huidu_uses_dev_log_database(self):
        connection = DatabaseConnectionConfig(database_name="ush_dev")

        database_name = channel_source.log_database_name_for_environment(
            "huidu",
            connection,
        )

        self.assertEqual(database_name, "ush_log_dev")

    def test_yy_uses_its_own_log_database(self):
        connection = DatabaseConnectionConfig(database_name="ush_yy")

        database_name = channel_source.log_database_name_for_environment(
            "yy",
            connection,
        )

        self.assertEqual(database_name, "ush_log_yy")

    def test_explicit_log_database_overrides_environment_default(self):
        connection = DatabaseConnectionConfig(
            database_name="ush_dev",
            log_database_name="custom_gray_log",
        )

        database_name = channel_source.log_database_name_for_environment(
            "huidu",
            connection,
        )

        self.assertEqual(database_name, "custom_gray_log")

    def test_not_entering_b_always_uses_organic(self):
        resolved = channel_source.resolve_channel_source(
            [],
            can_enter_b=False,
            has_new_user_offer=True,
        )

        self.assertEqual(resolved, "Organic")

    def test_new_user_offer_and_preference_are_used_for_matching(self):
        sources = [
            channel_source.ChannelSource("normal", "", 1),
            channel_source.ChannelSource(
                "new-user-default",
                channel_source.NEW_USER_CHANNEL_GROUP,
                1,
            ),
            channel_source.ChannelSource(
                "new-user-preferred",
                channel_source.NEW_USER_CHANNEL_GROUP,
                1,
            ),
        ]

        resolved = channel_source.resolve_channel_source(
            sources,
            can_enter_b=True,
            has_new_user_offer=True,
            preferred_sources=["new-user-preferred"],
        )

        self.assertEqual(resolved, "new-user-preferred")

    def test_channel_sources_are_cached_by_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = f"{temp_dir}/channel_sources.json"
            channel_source.save_channel_sources(
                "dev",
                [channel_source.ChannelSource("dev-source", "", 1)],
                cache_file,
            )
            channel_source.save_channel_sources(
                "yy",
                [channel_source.ChannelSource("yy-source", "group", 0)],
                cache_file,
            )

            cached = channel_source.load_channel_source_config(cache_file)

        self.assertEqual(cached["dev"][0].user_source, "dev-source")
        self.assertEqual(cached["yy"][0].user_source, "yy-source")
        self.assertEqual(cached["huidu"], [])


class DatabaseConfigTests(unittest.TestCase):
    @staticmethod
    def _connection(key_id: str, ssh_host: str) -> DatabaseConnectionConfig:
        return DatabaseConnectionConfig(
            ssh_host=ssh_host,
            ssh_username="deploy",
            ssh_private_key_id=key_id,
            database_name="automation",
            log_database_name="automation_log",
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
                    "yy",
                    self._connection("key-id", "yy-ssh.example.test"),
                    config_file,
                )

            connections = load_database_connections(config_file)

        self.assertEqual(connections["dev"].ssh_host, "dev-ssh.example.test")
        self.assertEqual(connections["dev"].log_database_name, "automation_log")
        self.assertEqual(connections["yy"].ssh_host, "yy-ssh.example.test")
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

    def test_database_tunnel_is_reused_for_same_environment(self):
        connection = self._connection("key-id", "ssh.example.test")
        transport = Mock()
        transport.is_active.return_value = True
        client = Mock()
        client.get_transport.return_value = transport
        server = Mock()
        server.server_address = ("127.0.0.1", 33060)
        database_config.close_shared_database_tunnels()
        with (
            patch.object(
                database_config,
                "_connect_ssh_client",
                return_value=client,
            ) as connect,
            patch.object(
                database_config,
                "_ForwardServer",
                return_value=server,
            ),
        ):
            first = database_config._shared_tunnel_port(connection)
            second = database_config._shared_tunnel_port(connection)

        self.assertEqual(first, 33060)
        self.assertEqual(second, 33060)
        connect.assert_called_once_with(connection)
        transport.set_keepalive.assert_called_once_with(30)
        database_config.close_shared_database_tunnels()


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

    def test_extracts_game_token_from_nested_encoded_url(self):
        game_data = {
            "data": {"url": "https://example.test/play?sign=nested-token"}
        }
        result = {
            "data": base64.b64encode(json.dumps(game_data).encode()).decode()
        }

        self.assertEqual(spin._extract_game_token(result), "nested-token")

    def test_missing_game_url_reports_protocol_details(self):
        result = {
            "code": 1001,
            "data": base64.b64encode(b"{}").decode(),
            "msg": base64.b64encode("游戏未配置".encode()).decode(),
        }

        with self.assertRaisesRegex(ValueError, "游戏未配置"):
            spin._extract_game_token(result)

    def test_decodes_base64_spin_error(self):
        result = spin._decode_api_result(
            {"code": 0, "data": "e30=", "msg": "YmV0IGVycm9y"}
        )

        self.assertEqual(result, {"code": 0, "data": {}, "msg": "bet error"})
        self.assertTrue(spin._spin_failed(result))

    def test_dev_game_token_uses_same_environment_as_login(self):
        game_info = {
            "url": "https://game.example.test/play?sign=dev-game-token"
        }
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": base64.b64encode(
                json.dumps(game_info).encode("utf-8")
            ).decode("ascii")
        }

        with patch.object(spin.requests, "post", return_value=response) as post:
            token = spin.get_game_token("dev-user-token", environment="dev")

        self.assertEqual(token, "dev-game-token")
        self.assertEqual(
            post.call_args.args[0],
            "https://devapi.ushdev.top/v1/gamehall/self_game_url",
        )

    def test_every_supported_spin_environment_uses_its_own_api_domain(self):
        expected = {
            "dev": (
                "https://devapi.ushdev.top/v1/gamehall/self_game_url",
                "https://webnew.hotspin777.com",
            ),
            "huidu": (
                "https://hdapi.ushdev.top/v1/gamehall/self_game_url",
                "https://newhdweb.ushdev.top",
            ),
            "yy": (
                "https://yyapi.ushdev.top/v1/gamehall/self_game_url",
                "https://yyres.ushdev.top",
            ),
            "individual": (
                "https://ceshigeren-ush-api.szhdev.top/v1/gamehall/self_game_url",
                "https://webnew.hotspin777.com",
            ),
        }

        self.assertEqual(set(spin.SPIN_ENVIRONMENT_CONFIGS), set(expected))
        for environment, (game_url_api, web_origin) in expected.items():
            with self.subTest(environment=environment):
                config = spin._config_for_environment(environment)
                self.assertEqual(config.game_url_api, game_url_api)
                self.assertEqual(config.web_origin, web_origin)

    def test_unknown_spin_environment_never_falls_back_to_dev(self):
        with self.assertRaisesRegex(ValueError, "未配置"):
            spin.get_game_token("user-token", environment="missing")

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

    def test_yy_game_token_uses_yy_environment_endpoints(self):
        game_info = {
            "url": "https://game.example.test/play?sign=yy-game-token"
        }
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": base64.b64encode(
                json.dumps(game_info).encode("utf-8")
            ).decode("ascii")
        }

        with patch.object(spin.requests, "post", return_value=response) as post:
            token = spin.get_game_token(
                "yy-user-token",
                environment="yy",
            )

        self.assertEqual(token, "yy-game-token")
        request = post.call_args
        self.assertEqual(
            request.args[0],
            "https://yyapi.ushdev.top/v1/gamehall/self_game_url",
        )
        self.assertEqual(
            request.kwargs["headers"]["Origin"],
            "https://yyres.ushdev.top",
        )
        self.assertNotIn("version", request.kwargs["headers"])
        self.assertEqual(
            request.kwargs["json"]["exit_event"],
            "https://yyres.ushdev.top/home",
        )
        self.assertEqual(
            request.kwargs["json"]["cash_event"],
            "https://yyres.ushdev.top/backshop",
        )

    def test_game_token_retries_while_new_user_token_is_activating(self):
        inactive_response = Mock(status_code=200)
        inactive_response.json.return_value = {
            "code": 0,
            "data": {},
            "msg": "Token not active yet",
        }
        active_response = Mock(status_code=200)
        active_response.json.return_value = {
            "code": 1,
            "data": {
                "url": "https://game.example.test/play?sign=fresh-game-token"
            },
            "msg": "Succeeded",
        }

        with (
            patch.object(
                spin.requests,
                "post",
                side_effect=[inactive_response, inactive_response, active_response],
            ) as post,
            patch.object(spin.time, "sleep") as sleep,
        ):
            token = spin.get_game_token("fresh-user-token")

        self.assertEqual(token, "fresh-game-token")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            sleep.call_args_list,
            [call(0.5), call(1.0)],
        )

    def test_successful_spin_prints_compact_result(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"win": 0}}
        console = io.StringIO()

        with (
            patch.object(spin, "get_valid_game_token", return_value="game-token"),
            patch.object(spin.requests, "post", return_value=response) as post,
            redirect_stdout(console),
        ):
            result = spin.dev_spin("user-token")

        self.assertIs(result, response)
        self.assertEqual(console.getvalue(), '[spin] 下注响应：{"data":{"win":0}}\n')
        self.assertEqual(post.call_args.kwargs["json"]["token"], "game-token")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer game-token",
        )

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

    def test_parallel_spin_does_not_reuse_or_store_session(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": {"win": 0, "session_id": "parallel-session"}
        }

        with (
            patch.object(spin, "get_valid_game_token", return_value="game-token"),
            patch.object(spin.requests, "post", return_value=response) as post,
        ):
            spin.dev_spin(
                "user-token",
                preserve_session=False,
                print_result=False,
            )

        self.assertEqual(post.call_args.kwargs["json"]["session_id"], "")
        self.assertNotIn(("dev", "user-token"), spin._game_session_cache)


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
    def test_stop_does_not_submit_or_count_thousands_of_cancelled_accounts(self):
        stopped = threading.Event()
        calls = []
        progress = []

        def create_one(index, count, **_kwargs):
            calls.append(index)
            stopped.set()
            return tournment_test.AccountResult(index, f"account {index}\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = f"{temp_dir}/accounts.txt"
            with (
                patch.object(
                    tournment_test,
                    "_create_account_and_bet",
                    side_effect=create_one,
                ),
                patch.object(
                    tournment_test.add_money,
                    "base_url_for_environment",
                    return_value="https://admin.example.test",
                ),
            ):
                successful = tournment_test.create_accounts_and_bet(
                    count=10_000,
                    output_file=output_file,
                    max_workers=3,
                    stop_requested=stopped.is_set,
                    progress_callback=lambda *value: progress.append(value),
                )

        self.assertLessEqual(len(calls), 3)
        self.assertEqual(successful, len(calls))
        self.assertTrue(progress)
        self.assertLessEqual(progress[-1][0], 3)
        self.assertEqual(progress[-1][1], 10_000)

    def test_spin_failure_is_reported_instead_of_completed(self):
        progress = []
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = f"{temp_dir}/accounts.txt"
            with (
                patch.object(
                    tournment_test,
                    "_create_account_and_bet",
                    side_effect=tournment_test.SpinWorkflowError("下注失败"),
                ),
                patch.object(
                    tournment_test.add_money,
                    "base_url_for_environment",
                    return_value="https://admin.example.test",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "关键业务错误终止"):
                    tournment_test.create_accounts_and_bet(
                        count=10_000,
                        output_file=output_file,
                        max_workers=1,
                        progress_callback=lambda *value: progress.append(value),
                    )

        self.assertEqual(progress, [(1, 10_000, 0)])

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
        account.login.assert_called_once_with(platform=Platform.ios.value)

    def test_tournament_bound_scenario_receives_account_context(self):
        account = Mock(uid=42, token="user-token", email="scenario@cc.cc")
        scenario = feature_scenario.FeatureScenario(
            "scenario-id",
            "赛后校验",
            (
                feature_scenario.new_step(
                    "assert",
                    "校验 UID",
                    {"path": "userid", "operator": "equals", "expected": 42},
                ),
            ),
        )
        connection = DatabaseConnectionConfig(database_name="ush_dev")
        with (
            patch.object(tournment_test, "User", return_value=account),
            patch.object(
                tournment_test.add_money,
                "add_money",
                return_value={"code": 0},
            ),
            patch.object(tournment_test, "_place_initial_spins"),
            patch.object(
                tournment_test,
                "execute_feature_scenario",
                return_value={"userid": 42},
            ) as execute,
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
                feature_scenario=scenario,
                scenario_database_connection=connection,
            )

        execute.assert_called_once_with(
            scenario,
            environment="dev",
            runtime_parameters={
                "userid": 42,
                "token": "user-token",
                "email": "scenario@cc.cc",
                "platform": Platform.ios.value,
                "channel_code": "tournament-channel",
            },
            database_connection=connection,
            stop_requested=ANY,
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

    def test_spins_can_be_placed_in_parallel(self):
        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def place_spin(*args, **kwargs):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with active_lock:
                active -= 1
            return Mock()

        with (
            patch.object(
                spin,
                "get_valid_game_token",
                return_value="game-token",
            ) as token,
            patch.object(spin, "dev_spin", side_effect=place_spin) as request,
        ):
            tournment_test._place_initial_spins(
                "user-token",
                spin_count=4,
                spin_workers=3,
                environment="huidu",
            )

        token.assert_called_once_with("user-token", environment="huidu")
        self.assertEqual(request.call_count, 4)
        self.assertGreaterEqual(max_active, 2)
        for request_call in request.call_args_list:
            self.assertEqual(request_call.args, ("user-token",))
            self.assertEqual(request_call.kwargs["environment"], "huidu")
            self.assertFalse(request_call.kwargs["preserve_session"])

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

    def test_spin_worker_count_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "下注并发数"):
            tournment_test.create_accounts_and_bet(count=1, spin_workers=0)

    def test_tournament_web_platform_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Android 或 iOS"):
            tournment_test.create_accounts_and_bet(
                count=1,
                platform=Platform.web.value,
            )


class AccountCreationTests(unittest.TestCase):
    def test_bound_sql_runs_with_new_account_uid(self):
        account = Mock(uid=42, token="user-token", email="sql@cc.cc")
        template = sql_data.SqlTemplate(
            "template-id",
            "VIP 数据",
            "SET @userid=xxx; SELECT @userid;",
        )
        connection = DatabaseConnectionConfig(database_name="ush_dev")
        execution_result = sql_data.SqlExecutionResult(2, 1, 0)
        with (
            patch.object(account_batch, "User", return_value=account),
            patch.object(
                account_batch,
                "execute_sql_template",
                return_value=execution_result,
            ) as execute,
        ):
            account_batch._register_account(
                1,
                1,
                environment="dev",
                platform=Platform.ios.value,
                channel_code="channel",
                verbose=False,
                stop_requested=lambda: False,
                sql_template=template,
                database_connection=connection,
            )

        execute.assert_called_once_with(template, 42, connection)

    def test_bound_scenario_receives_new_account_context(self):
        account = Mock(
            uid=42,
            token="user-token",
            email="scenario@cc.cc",
        )
        scenario = feature_scenario.FeatureScenario(
            "scenario-id",
            "广告校验",
            (
                feature_scenario.new_step(
                    "assert",
                    "校验 UID",
                    {"path": "userid", "operator": "equals", "expected": 42},
                ),
            ),
        )
        connection = DatabaseConnectionConfig(database_name="ush_dev")
        with (
            patch.object(account_batch, "User", return_value=account),
            patch.object(
                account_batch,
                "execute_feature_scenario",
                return_value={"userid": 42},
            ) as execute,
        ):
            account_batch._register_account(
                1,
                1,
                environment="dev",
                platform=Platform.ios.value,
                channel_code="channel",
                verbose=False,
                stop_requested=lambda: False,
                feature_scenario=scenario,
                scenario_database_connection=connection,
            )

        execute.assert_called_once_with(
            scenario,
            environment="dev",
            runtime_parameters={
                "userid": 42,
                "token": "user-token",
                "email": "scenario@cc.cc",
                "platform": Platform.ios.value,
                "channel_code": "channel",
            },
            database_connection=connection,
            stop_requested=ANY,
        )

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

    def test_custom_email_is_used_for_registration(self):
        account = Mock(uid=42, token="user-token", email="named@example.com")
        with patch.object(account_batch, "User", return_value=account) as user_factory:
            account_batch._register_account(
                1,
                1,
                environment="dev",
                platform=Platform.ios.value,
                channel_code="ios-channel",
                verbose=False,
                stop_requested=lambda: False,
                email="named@example.com",
            )

        user_factory.assert_called_once_with(
            email="named@example.com",
            environment="dev",
        )

    def test_custom_account_creates_exactly_one_account(self):
        with patch.object(account_batch, "create_accounts", return_value=1) as create:
            successful = account_batch.create_custom_account(
                " named@example.com ",
                output_file="custom.txt",
                environment="huidu",
                platform=Platform.android.value,
                channel_code="custom-channel",
            )

        self.assertEqual(successful, 1)
        create.assert_called_once_with(
            count=1,
            output_file="custom.txt",
            environment="huidu",
            platform=Platform.android.value,
            channel_code="custom-channel",
            verbose=False,
            max_workers=1,
            stop_requested=None,
            progress_callback=None,
            email="named@example.com",
        )

    def test_invalid_custom_email_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "邮箱格式"):
            account_batch.create_accounts(count=1, email="not-an-email")

    def test_custom_email_cannot_be_used_for_a_batch(self):
        with self.assertRaisesRegex(ValueError, "仅支持创建一个账号"):
            account_batch.create_accounts(count=2, email="named@example.com")

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
