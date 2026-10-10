"""Tests for the shared funding and spin workflow."""

import unittest
from unittest.mock import Mock, patch

from base import fund_and_spin


class FundAndSpinTests(unittest.TestCase):
    def test_funds_before_running_spins(self) -> None:
        events = []
        spin_runner = Mock(side_effect=lambda *_args, **_kwargs: events.append("spin"))
        refresh_token = Mock(
            side_effect=lambda: events.append("refresh") or "fresh-user-token"
        )

        with (
            patch.object(
                fund_and_spin.add_money,
                "add_money",
                side_effect=lambda **_kwargs: events.append("money") or {"code": 0},
            ) as add,
            patch.object(
                fund_and_spin.add_money,
                "operation_succeeded",
                return_value=True,
            ),
        ):
            result = fund_and_spin.fund_and_spin(
                42,
                None,
                environment="dev",
                amount=1_000,
                spin_count=3,
                bet_amount=100,
                spin_workers=2,
                admin_base_url="https://admin.example.test",
                refresh_user_token=refresh_token,
                spin_runner=spin_runner,
            )

        self.assertEqual(events, ["money", "refresh", "spin"])
        self.assertEqual(result.user_id, 42)
        add.assert_called_once_with(
            user_id=42,
            amount=1_000,
            remark="测试加钱",
            base_url="https://admin.example.test",
        )
        spin_runner.assert_called_once_with(
            "fresh-user-token",
            3,
            environment="dev",
            spin_workers=2,
            bet_amount=100,
            verbose=False,
            stop_requested=None,
        )
        refresh_token.assert_called_once_with()

    def test_failed_funding_does_not_place_spins(self) -> None:
        spin_runner = Mock()
        refresh_token = Mock(return_value="fresh-user-token")
        with (
            patch.object(
                fund_and_spin.add_money,
                "add_money",
                return_value={"code": 1},
            ),
            patch.object(
                fund_and_spin.add_money,
                "operation_succeeded",
                return_value=False,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "加钱业务失败"):
                fund_and_spin.fund_and_spin(
                    42,
                    "user-token",
                    environment="dev",
                    admin_base_url="https://admin.example.test",
                    refresh_user_token=refresh_token,
                    spin_runner=spin_runner,
                )

        refresh_token.assert_not_called()
        spin_runner.assert_not_called()

    def test_invalid_environment_is_rejected_before_funding(self) -> None:
        with patch.object(fund_and_spin.add_money, "add_money") as add:
            with self.assertRaisesRegex(ValueError, "未配置"):
                fund_and_spin.fund_and_spin(
                    42,
                    "user-token",
                    environment="missing",
                    admin_base_url="https://admin.example.test",
                    spin_runner=Mock(),
                )

        add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
