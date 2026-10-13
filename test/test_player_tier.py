"""Tests for player profit calculation, classification and data construction."""

import unittest
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from unittest.mock import ANY, Mock, patch

from base.database_config import DatabaseConnectionConfig
from base.player_tier import (
    CONSTRUCTION_CHARGE_TOTAL,
    FB_CONSTRUCTION_CHARGE_TOTAL,
    FB_MINIMUM_TIER_CHARGE_TOTAL,
    LOSS_OBSERVATION_BOUNDARY,
    MINIMUM_TIER_CHARGE_TOTAL,
    NET_PROFIT_TOP_CONSTRUCTION_CHARGE_TOTAL,
    NET_PROFIT_TOP_TARGET_RATE,
    PlayerLoginCredentials,
    PLAYER_CHANNEL_FB,
    REGISTRATION_AGE_OVER_7_DAYS,
    REGISTRATION_AGE_WITHIN_7_DAYS,
    SECONDS_PER_DAY,
    TARGET_NET_PROFIT_TOP,
    TARGET_PROFIT_RATES,
    TOP_NET_PROFIT_THRESHOLD,
    TIER_ARBITRAGE,
    TIER_CORE,
    TIER_NORMAL,
    TIER_TOP,
    TIER_UNCLASSIFIED,
    build_player_tier_values,
    calculate_player_tier,
    construct_player_tier,
    fetch_player_login_credentials,
    fetch_player_tier,
    prepare_turnover_and_construct_player_tier,
    resolve_player_charge_limits,
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

    def test_net_profit_top_rule_is_strict_and_precedes_profit_rate(self) -> None:
        exact_threshold = calculate_player_tier(7_000_000, 0, 5_510_000)
        above_threshold = calculate_player_tier(7_000_000, 0, 5_509_999)

        self.assertEqual(exact_threshold.net_profit, TOP_NET_PROFIT_THRESHOLD)
        self.assertEqual(exact_threshold.tier, TIER_CORE)
        self.assertEqual(
            above_threshold.net_profit,
            TOP_NET_PROFIT_THRESHOLD + 1,
        )
        self.assertLess(above_threshold.profit_rate, Decimal("0.20"))
        self.assertEqual(above_threshold.tier, TIER_TOP)

    def test_constructed_values_hit_each_target_with_small_charge(self) -> None:
        current = calculate_player_tier(20_000, 2_000, 250_000, user_id=42)
        for target in TARGET_PROFIT_RATES:
            with self.subTest(target=target):
                proposed = build_player_tier_values(current, target)
                self.assertEqual(proposed.tier, target)
                if target == TIER_ARBITRAGE:
                    self.assertLess(proposed.profit_rate, Decimal("-0.01"))
                    self.assertLessEqual(
                        proposed.net_profit,
                        -Decimal(LOSS_OBSERVATION_BOUNDARY),
                    )
                else:
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
                if target != TIER_ARBITRAGE:
                    self.assertLess(proposed.balance, CONSTRUCTION_CHARGE_TOTAL)

    def test_constructed_values_preserve_charge_above_minimum(self) -> None:
        current = calculate_player_tier(525_000, 2_000, 250_000, user_id=42)

        proposed = build_player_tier_values(current, TIER_CORE)

        self.assertEqual(proposed.charge_total, 525_000)
        self.assertEqual(proposed.profit_rate, TARGET_PROFIT_RATES[TIER_CORE])

    def test_construct_net_profit_top_proves_priority_over_profit_rate(self) -> None:
        current = calculate_player_tier(20_000, 0, 0, user_id=42)

        proposed = build_player_tier_values(current, TARGET_NET_PROFIT_TOP)

        self.assertEqual(
            proposed.charge_total,
            NET_PROFIT_TOP_CONSTRUCTION_CHARGE_TOTAL,
        )
        self.assertEqual(proposed.profit_rate, NET_PROFIT_TOP_TARGET_RATE)
        self.assertGreater(proposed.net_profit, TOP_NET_PROFIT_THRESHOLD)
        self.assertEqual(proposed.tier, TIER_TOP)

    def test_construct_core_after_net_profit_top_stays_below_priority_rule(self) -> None:
        current = build_player_tier_values(
            calculate_player_tier(20_000, 0, 0, user_id=42),
            TARGET_NET_PROFIT_TOP,
        )

        proposed = build_player_tier_values(current, TIER_CORE)

        self.assertEqual(
            proposed.charge_total,
            NET_PROFIT_TOP_CONSTRUCTION_CHARGE_TOTAL,
        )
        self.assertLessEqual(proposed.net_profit, TOP_NET_PROFIT_THRESHOLD)
        self.assertGreaterEqual(proposed.profit_rate, Decimal("0.10"))
        self.assertLess(proposed.profit_rate, Decimal("0.20"))
        self.assertEqual(proposed.tier, TIER_CORE)

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

    def test_fb_player_uses_its_own_safe_charge_threshold(self) -> None:
        current = calculate_player_tier(
            FB_MINIMUM_TIER_CHARGE_TOTAL,
            0,
            0,
            user_id=42,
        )

        proposed = build_player_tier_values(
            current,
            TIER_CORE,
            player_channel=PLAYER_CHANNEL_FB,
        )

        self.assertEqual(proposed.charge_total, FB_CONSTRUCTION_CHARGE_TOTAL)
        self.assertGreater(
            proposed.charge_total,
            FB_MINIMUM_TIER_CHARGE_TOTAL,
        )
        self.assertEqual(proposed.profit_rate, TARGET_PROFIT_RATES[TIER_CORE])

    def test_fb_player_preserves_charge_above_its_threshold(self) -> None:
        current = calculate_player_tier(30_000, 0, 0, user_id=42)

        proposed = build_player_tier_values(
            current,
            TIER_NORMAL,
            player_channel=PLAYER_CHANNEL_FB,
        )

        self.assertEqual(proposed.charge_total, 30_000)

    def test_general_vip5_and_vip6_use_their_own_safe_thresholds(self) -> None:
        current = calculate_player_tier(20_000, 0, 0, user_id=42)

        vip5 = build_player_tier_values(
            current,
            TIER_NORMAL,
            target_vip_level=5,
        )
        vip6 = build_player_tier_values(
            current,
            TIER_NORMAL,
            target_vip_level=6,
        )

        self.assertEqual(vip5.charge_total, 1_650_000)
        self.assertEqual(vip5.vip_level, 5)
        self.assertEqual(vip6.charge_total, 8_050_000)
        self.assertEqual(vip6.vip_level, 6)

    def test_arbitrage_construction_avoids_observation_period(self) -> None:
        current = calculate_player_tier(0, 0, 0, user_id=42)

        for player_channel in ("general", PLAYER_CHANNEL_FB):
            with self.subTest(player_channel=player_channel):
                proposed = build_player_tier_values(
                    current,
                    TIER_ARBITRAGE,
                    player_channel=player_channel,
                )
                self.assertLessEqual(
                    proposed.net_profit,
                    -Decimal(LOSS_OBSERVATION_BOUNDARY),
                )
                self.assertEqual(proposed.tier, TIER_ARBITRAGE)

    def test_charge_limits_reject_non_segment_vip(self) -> None:
        with self.assertRaisesRegex(ValueError, "VIP4、VIP5 或 VIP6"):
            resolve_player_charge_limits("general", 3)

    def test_unknown_player_channel_is_rejected(self) -> None:
        current = calculate_player_tier(30_000, 0, 0, user_id=42)

        with self.assertRaisesRegex(ValueError, "初始渠道"):
            build_player_tier_values(
                current,
                TIER_NORMAL,
                player_channel="unknown",
            )

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
        row: tuple[object, ...],
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
        row: tuple[object, ...],
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
    def test_fetch_login_credentials_by_uid(self) -> None:
        database = _FakeDatabase(
            (
                "player@cc.cc",
                3,
            )
        )

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.player_tier.open_database_connection",
            side_effect=connection_context,
        ):
            credentials = fetch_player_login_credentials(
                42,
                DatabaseConnectionConfig(),
            )

        self.assertEqual(credentials.email, "player@cc.cc")
        self.assertEqual(credentials.platform, 3)
        self.assertEqual(database.fake_cursor.executions[0][1], (42,))

    def test_fetch_returns_user_base_segment(self) -> None:
        database = _FakeDatabase(
            (42, 350_000, 0, 270_000, 3_000, 4, 1_900_000),
            user_segment=3,
        )

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.player_tier.open_database_connection",
            side_effect=connection_context,
        ):
            result = fetch_player_tier(42, DatabaseConnectionConfig())

        self.assertEqual(result.user_segment, 3)
        self.assertEqual(result.money, 270_000)
        self.assertEqual(result.bonus, 3_000)
        self.assertEqual(result.balance, 273_000)
        self.assertEqual(result.vip_level, 4)
        self.assertEqual(result.net_profit, Decimal("52500.00"))
        self.assertEqual(result.profit_rate, Decimal("0.15"))
        query_sql = database.fake_cursor.executions[0][0]
        self.assertIn("money, bonus", query_sql)
        segment_sql, segment_parameters = database.fake_cursor.executions[1]
        self.assertIn("FROM user_base", segment_sql)
        self.assertEqual(segment_parameters, (42,))

    def test_construct_updates_totals_and_balance(self) -> None:
        database = _FakeDatabase(
            (42, 10_000, 2_000, 30_000, 5_000, 0, 1_900_000),
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
        self.assertEqual(result.money, 307_000)
        self.assertEqual(result.bonus, 5_000)
        self.assertEqual(result.vip_level, 4)
        self.assertEqual(result.user_segment, 2)
        update_sql, update_parameters = database.fake_cursor.executions[1]
        self.assertIn("money=%s", update_sql)
        self.assertIn("bonus=%s", update_sql)
        self.assertEqual(
            update_parameters,
            (400_000, 0, 307_000, 5_000, 4, 42),
        )
        segment_sql, segment_parameters = database.fake_cursor.executions[2]
        self.assertIn("FROM user_base", segment_sql)
        self.assertEqual(segment_parameters, (42,))

    def test_construct_updates_created_at_for_selected_registration_age(self) -> None:
        now = 2_000_000
        database = _FakeDatabase(
            (
                42,
                10_000,
                2_000,
                30_000,
                5_000,
                0,
                now - 2 * SECONDS_PER_DAY,
            ),
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
            (400_000, 0, 307_000, 5_000, 4, expected_created_at, 42),
        )

    def test_construct_caps_bonus_when_it_exceeds_target_balance(self) -> None:
        database = _FakeDatabase(
            (42, 10_000, 2_000, 30_000, 500_000, 0, 1_900_000),
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

        self.assertEqual(result.balance, 312_000)
        self.assertEqual(result.money, 0)
        self.assertEqual(result.bonus, 312_000)
        update_sql, update_parameters = database.fake_cursor.executions[1]
        self.assertIn("bonus=%s", update_sql)
        self.assertEqual(
            update_parameters,
            (400_000, 0, 0, 312_000, 4, 42),
        )

    def test_new_user_gets_turnover_before_registration_time_changes(self) -> None:
        now = 2_000_000
        current = replace(
            calculate_player_tier(400_000, 0, 312_000, user_id=42),
            created_at=now - SECONDS_PER_DAY,
        )
        credentials = PlayerLoginCredentials(
            "player@cc.cc",
            3,
        )
        events = []
        account = Mock(uid=42, token="auto-user-token")

        def prepare_turnover(*_args, **kwargs):
            events.append("turnover")
            self.assertEqual(
                kwargs["refresh_user_token"](),
                "auto-user-token",
            )

        def construct(*_args, **kwargs):
            events.append("construct")
            self.assertEqual(kwargs["player_channel"], PLAYER_CHANNEL_FB)
            return current

        with (
            patch("base.player_tier.time.time", return_value=now),
            patch("base.player_tier.fetch_player_tier", return_value=current),
            patch(
                "base.player_tier.fetch_player_login_credentials",
                return_value=credentials,
            ),
            patch("base.player_tier.User", return_value=account) as user_factory,
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
                player_channel=PLAYER_CHANNEL_FB,
                initial_balance=1_000,
                spin_count=3,
                bet_amount=100,
            )

        self.assertIs(result, current)
        self.assertEqual(events, ["turnover", "construct"])
        user_factory.assert_called_once_with(
            email="player@cc.cc",
            environment="dev",
        )
        account.login.assert_called_once_with(platform=3)
        fund.assert_called_once_with(
            42,
            None,
            environment="dev",
            amount=1_000,
            spin_count=3,
            bet_amount=100,
            spin_workers=5,
            refresh_user_token=ANY,
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
