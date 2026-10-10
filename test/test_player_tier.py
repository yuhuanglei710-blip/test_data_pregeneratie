"""Tests for player profit calculation, classification and data construction."""

import unittest
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from base.database_config import DatabaseConnectionConfig
from base.player_tier import (
    CONSTRUCTION_CHARGE_TOTAL,
    MINIMUM_TIER_CHARGE_TOTAL,
    REGISTRATION_AGE_OVER_7_DAYS,
    REGISTRATION_AGE_WITHIN_7_DAYS,
    SECONDS_PER_DAY,
    TARGET_PROFIT_RATES,
    TIER_ARBITRAGE,
    TIER_CORE,
    TIER_NORMAL,
    TIER_TOP,
    TIER_UNCLASSIFIED,
    build_player_tier_values,
    calculate_player_tier,
    construct_player_tier,
    fetch_player_tier,
    prepare_turnover_and_construct_player_tier,
    resolve_registration_created_at,
)


class PlayerTierCalculationTests(unittest.TestCase):
    def test_formula_and_exact_classification_boundaries(self) -> None:
        arbitrage = calculate_player_tier(10_000, 0, 9_401)
        normal = calculate_player_tier(10_000, 0, 9_400)
        core = calculate_player_tier(10_000, 0, 8_300)
        top = calculate_player_tier(10_000, 0, 7_300)

        self.assertEqual(arbitrage.net_profit, Decimal("-101.00"))
        self.assertEqual(arbitrage.tier, TIER_ARBITRAGE)
        self.assertEqual(normal.profit_rate, Decimal("-0.01"))
        self.assertEqual(normal.tier, TIER_NORMAL)
        self.assertEqual(core.profit_rate, Decimal("0.10"))
        self.assertEqual(core.tier, TIER_CORE)
        self.assertEqual(top.profit_rate, Decimal("0.20"))
        self.assertEqual(top.tier, TIER_TOP)

    def test_zero_charge_is_not_classified(self) -> None:
        metrics = calculate_player_tier(0, 1_000, 500)
        self.assertIsNone(metrics.profit_rate)
        self.assertEqual(metrics.tier, TIER_UNCLASSIFIED)

    def test_constructed_values_hit_each_target_with_small_charge(self) -> None:
        current = calculate_player_tier(20_000, 2_000, 250_000, user_id=42)
        for target in TARGET_PROFIT_RATES:
            with self.subTest(target=target):
                proposed = build_player_tier_values(current, target)
                self.assertEqual(proposed.tier, target)
                self.assertEqual(
                    proposed.profit_rate,
                    TARGET_PROFIT_RATES[target],
                )
                self.assertEqual(
                    proposed.charge_total,
                    CONSTRUCTION_CHARGE_TOTAL,
                )
                self.assertGreaterEqual(proposed.charge_total, 350_000)
                self.assertEqual(proposed.withdraw_total, 0)
                self.assertLess(proposed.balance, CONSTRUCTION_CHARGE_TOTAL)

    def test_constructed_values_preserve_charge_above_minimum(self) -> None:
        current = calculate_player_tier(525_000, 2_000, 250_000, user_id=42)

        proposed = build_player_tier_values(current, TIER_CORE)

        self.assertEqual(proposed.charge_total, 525_000)
        self.assertEqual(proposed.profit_rate, TARGET_PROFIT_RATES[TIER_CORE])

    def test_minimum_boundary_uses_safe_construction_value(self) -> None:
        current = calculate_player_tier(
            MINIMUM_TIER_CHARGE_TOTAL,
            0,
            0,
            user_id=42,
        )

        proposed = build_player_tier_values(current, TIER_NORMAL)

        self.assertEqual(proposed.charge_total, CONSTRUCTION_CHARGE_TOTAL)
        self.assertGreater(proposed.charge_total, MINIMUM_TIER_CHARGE_TOTAL)

    def test_registration_age_keeps_matching_timestamps(self) -> None:
        now = 2_000_000
        recent = now - 2 * SECONDS_PER_DAY
        old = now - 20 * SECONDS_PER_DAY

        self.assertEqual(
            resolve_registration_created_at(
                recent,
                REGISTRATION_AGE_WITHIN_7_DAYS,
                now=now,
            ),
            recent,
        )
        self.assertEqual(
            resolve_registration_created_at(
                old,
                REGISTRATION_AGE_OVER_7_DAYS,
                now=now,
            ),
            old,
        )

    def test_registration_age_corrects_non_matching_timestamps(self) -> None:
        now = 2_000_000

        self.assertEqual(
            resolve_registration_created_at(
                now - 20 * SECONDS_PER_DAY,
                REGISTRATION_AGE_WITHIN_7_DAYS,
                now=now,
            ),
            now - 5 * SECONDS_PER_DAY,
        )
        self.assertEqual(
            resolve_registration_created_at(
                now - 2 * SECONDS_PER_DAY,
                REGISTRATION_AGE_OVER_7_DAYS,
                now=now,
            ),
            now - 8 * SECONDS_PER_DAY,
        )


class _FakeCursor:
    def __init__(
        self,
        row: tuple[int, ...],
        user_segment: int = 0,
    ) -> None:
        self.row = row
        self.user_segment = user_segment
        self.rowcount = 0
        self.executions: list[tuple[str, tuple[int, ...]]] = []
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str, parameters: tuple[int, ...]) -> None:
        self.executions.append((sql, parameters))
        self.last_sql = sql
        if sql.startswith("UPDATE"):
            self.rowcount = 1

    def fetchone(self):
        if "FROM user_base" in self.last_sql:
            return (self.user_segment,)
        return self.row


class _FakeDatabase:
    def __init__(
        self,
        row: tuple[int, ...],
        user_segment: int = 0,
    ) -> None:
        self.fake_cursor = _FakeCursor(row, user_segment)
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> _FakeCursor:
        return self.fake_cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class PlayerTierDatabaseTests(unittest.TestCase):
    def test_fetch_returns_user_base_segment(self) -> None:
        database = _FakeDatabase((42, 350_000, 0, 273_000), user_segment=3)

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.player_tier.open_database_connection",
            side_effect=connection_context,
        ):
            result = fetch_player_tier(42, DatabaseConnectionConfig())

        self.assertEqual(result.user_segment, 3)
        segment_sql, segment_parameters = database.fake_cursor.executions[1]
        self.assertIn("FROM user_base", segment_sql)
        self.assertEqual(segment_parameters, (42,))

    def test_construct_updates_totals_and_balance(self) -> None:
        database = _FakeDatabase(
            (42, 10_000, 2_000, 35_000),
            user_segment=2,
        )

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.player_tier.open_database_connection",
            side_effect=connection_context,
        ):
            result = construct_player_tier(
                42,
                TIER_CORE,
                DatabaseConnectionConfig(),
            )

        self.assertTrue(database.committed)
        self.assertFalse(database.rolled_back)
        self.assertEqual(result.tier, TIER_CORE)
        self.assertEqual(result.charge_total, CONSTRUCTION_CHARGE_TOTAL)
        self.assertEqual(result.withdraw_total, 0)
        self.assertEqual(result.balance, 312_000)
        self.assertEqual(result.user_segment, 2)
        update_sql, update_parameters = database.fake_cursor.executions[1]
        self.assertIn("money=%s", update_sql)
        self.assertEqual(update_parameters, (400_000, 0, 312_000, 42))
        segment_sql, segment_parameters = database.fake_cursor.executions[2]
        self.assertIn("FROM user_base", segment_sql)
        self.assertEqual(segment_parameters, (42,))

    def test_construct_updates_created_at_for_selected_registration_age(self) -> None:
        now = 2_000_000
        database = _FakeDatabase(
            (42, 10_000, 2_000, 35_000, now - 2 * SECONDS_PER_DAY),
            user_segment=2,
        )

        @contextmanager
        def connection_context(_connection):
            yield database

        with (
            patch(
                "base.player_tier.open_database_connection",
                side_effect=connection_context,
            ),
            patch("base.player_tier.time.time", return_value=now),
        ):
            result = construct_player_tier(
                42,
                TIER_CORE,
                DatabaseConnectionConfig(),
                REGISTRATION_AGE_OVER_7_DAYS,
            )

        expected_created_at = now - 8 * SECONDS_PER_DAY
        self.assertEqual(result.created_at, expected_created_at)
        update_sql, update_parameters = database.fake_cursor.executions[1]
        self.assertIn("created_at=%s", update_sql)
        self.assertEqual(
            update_parameters,
            (400_000, 0, 312_000, expected_created_at, 42),
        )

    def test_new_user_gets_turnover_before_registration_time_changes(self) -> None:
        now = 2_000_000
        current = replace(
            calculate_player_tier(400_000, 0, 312_000, user_id=42),
            created_at=now - SECONDS_PER_DAY,
        )
        events = []

        def prepare_turnover(*_args, **_kwargs):
            events.append("turnover")

        def construct(*_args, **_kwargs):
            events.append("construct")
            return current

        with (
            patch("base.player_tier.time.time", return_value=now),
            patch("base.player_tier.fetch_player_tier", return_value=current),
            patch(
                "base.player_tier.fund_and_spin",
                side_effect=prepare_turnover,
            ) as fund,
            patch(
                "base.player_tier.construct_player_tier",
                side_effect=construct,
            ),
        ):
            result = prepare_turnover_and_construct_player_tier(
                42,
                TIER_CORE,
                DatabaseConnectionConfig(),
                REGISTRATION_AGE_OVER_7_DAYS,
                environment="dev",
                user_token="user-token",
                initial_balance=1_000,
                spin_count=3,
                bet_amount=100,
            )

        self.assertIs(result, current)
        self.assertEqual(events, ["turnover", "construct"])
        fund.assert_called_once_with(
            42,
            "user-token",
            environment="dev",
            amount=1_000,
            spin_count=3,
            bet_amount=100,
            spin_workers=5,
        )

    def test_existing_old_user_skips_turnover(self) -> None:
        now = 2_000_000
        current = replace(
            calculate_player_tier(400_000, 0, 312_000, user_id=42),
            created_at=now - 10 * SECONDS_PER_DAY,
        )

        with (
            patch("base.player_tier.time.time", return_value=now),
            patch("base.player_tier.fetch_player_tier", return_value=current),
            patch("base.player_tier.fund_and_spin") as fund,
            patch(
                "base.player_tier.construct_player_tier",
                return_value=current,
            ) as construct,
        ):
            prepare_turnover_and_construct_player_tier(
                42,
                TIER_CORE,
                DatabaseConnectionConfig(),
                REGISTRATION_AGE_OVER_7_DAYS,
                environment="dev",
            )

        fund.assert_not_called()
        construct.assert_called_once()


if __name__ == "__main__":
    unittest.main()
