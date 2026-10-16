"""通用工具数据层的离线测试。"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from base.quick_access import (
    QuickAccessField,
    QuickAccessLink,
    load_quick_access,
    quick_access_share_text,
    save_quick_access,
    validate_quick_access_link,
)
from base.ssh_host import (
    AUTH_KEY_ONLY,
    AUTH_PASSWORD_ONLY,
    SshHostConfig,
    load_ssh_hosts,
    save_ssh_hosts,
    validate_ssh_host,
)
from tools.timestamp_tool import offset_timestamp, parse_timestamp


class TimestampParsingTests(unittest.TestCase):
    def test_parses_seconds_and_milliseconds(self) -> None:
        reference = datetime.fromtimestamp(0, timezone.utc)
        seconds = parse_timestamp("1704067200", now=reference)
        milliseconds = parse_timestamp("1704067200000", now=reference)
        self.assertEqual(seconds.epoch_seconds, 1704067200)
        self.assertEqual(seconds.epoch_milliseconds, 1704067200000)
        self.assertEqual(milliseconds.epoch_seconds, seconds.epoch_seconds)
        self.assertIn("2024-01-01 08:00:00", seconds.utc_plus_8)
        eleven_digits = parse_timestamp("10000000000", now=reference)
        self.assertEqual(eleven_digits.epoch_milliseconds, 10000000000)

    def test_parses_iso_and_applies_offset(self) -> None:
        parsed = parse_timestamp("2024-01-01T00:00:00Z")
        shifted = offset_timestamp(parsed.epoch_seconds, 2)
        self.assertEqual(shifted.epoch_seconds, parsed.epoch_seconds + 7200)
        self.assertEqual(parsed.iso_8601, "2024-01-01T00:00:00.000Z")

    def test_rejects_invalid_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "无法识别"):
            parse_timestamp("not-a-date")


class QuickAccessStorageTests(unittest.TestCase):
    def test_round_trip_and_share_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quick.json"
            link = QuickAccessLink(
                name="测试后台",
                url="https://example.test/admin",
                category="测试环境",
                is_top=True,
                fields=[
                    QuickAccessField("username", "tester"),
                    QuickAccessField("password", "secret"),
                ],
            )
            save_quick_access([link], ["文档"], path)
            links, categories = load_quick_access(path)
            self.assertEqual(links, [link])
            self.assertEqual(set(categories), {"测试环境", "文档"})
            self.assertIn("username：tester", quick_access_share_text(link))

    def test_rejects_bad_url_and_duplicate_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "完整"):
            validate_quick_access_link(QuickAccessLink(name="bad", url="example.com"))
        with self.assertRaisesRegex(ValueError, "不能重复"):
            validate_quick_access_link(
                QuickAccessLink(
                    name="重复字段",
                    url="https://example.test",
                    fields=[QuickAccessField("user", "a"), QuickAccessField("USER", "b")],
                )
            )


class SshHostStorageTests(unittest.TestCase):
    def test_password_host_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ssh.json"
            host = SshHostConfig(
                name="测试机",
                host="192.0.2.1",
                username="root",
                auth_type=AUTH_PASSWORD_ONLY,
                password="secret",
            )
            save_ssh_hosts([host], path)
            self.assertEqual(load_ssh_hosts(path), [host])

    def test_authentication_requirements(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须填写密码"):
            validate_ssh_host(
                SshHostConfig(
                    name="测试机",
                    host="192.0.2.1",
                    username="root",
                    auth_type=AUTH_PASSWORD_ONLY,
                )
            )
        with self.assertRaisesRegex(ValueError, "必须选择私钥"):
            validate_ssh_host(
                SshHostConfig(
                    name="测试机",
                    host="192.0.2.1",
                    username="root",
                    auth_type=AUTH_KEY_ONLY,
                )
            )


if __name__ == "__main__":
    unittest.main()
