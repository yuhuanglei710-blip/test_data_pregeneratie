"""Tests for player profit calculation, classification and data construction."""

import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from base.database_config import DatabaseConnectionConfig
from base.player_tier import (
    CONSTRUCTION_CHARGE_TOTAL,
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


class _FakeCursor:
    def __init__(
        self,
        row: tuple[int, int, int, int],
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
        row: tuple[int, int, int, int],
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
        self.assertEqual(result.balance, 273_000)
        self.assertEqual(result.user_segment, 2)
        update_sql, update_parameters = database.fake_cursor.executions[1]
        self.assertIn("money=%s", update_sql)
        self.assertEqual(update_parameters, (350_000, 0, 273_000, 42))
        segment_sql, segment_parameters = database.fake_cursor.executions[2]
        self.assertIn("FROM user_base", segment_sql)
        self.assertEqual(segment_parameters, (42,))


if __name__ == "__main__":
    unittest.main()
