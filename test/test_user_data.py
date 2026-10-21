"""user 表可编辑字段写入测试。"""

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from base.database_config import DatabaseConnectionConfig
from base.user_data import (
    fetch_user,
    fetch_users,
    normalize_editable_user_values,
    update_user_fields,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters):
        self.executions.append((sql, parameters))

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        rows = self.rows
        self.rows = []
        return rows


class _Database:
    def __init__(self, rows):
        self.fake_cursor = _Cursor(rows)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class UserDataTests(unittest.TestCase):
    def test_updates_only_allowed_fields_by_user_id(self) -> None:
        values = {
            "vip_level": 5,
            "charge_total": 200_000,
            "money": 90_000,
            "bonus": 5_000,
            "withdraw_total": 30_000,
            "charge_times": 8,
            "withdraw_times": 2,
            "pkg_name": "a",
            "platform": 3,
            "user_segment": 2,
        }
        database = _Database(
            [
                (4, 100_000, 50_000, 2_000, 10_000, 3, 1, "b", 2),
                (5, 200_000, 90_000, 5_000, 30_000, 8, 2, "a", 3, 2),
            ]
        )

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.user_data.open_database_connection",
            side_effect=connection_context,
        ):
            updated = update_user_fields(
                607425,
                values,
                DatabaseConnectionConfig(),
            )

        self.assertTrue(database.committed)
        self.assertFalse(database.rolled_back)
        self.assertEqual(updated, values)
        update_sql, parameters = database.fake_cursor.executions[1]
        self.assertIn("UPDATE `user` SET", update_sql)
        self.assertTrue(update_sql.endswith("WHERE id=%s"))
        self.assertEqual(
            parameters,
            (5, 200_000, 90_000, 5_000, 30_000, 8, 2, "a", 3, 607425),
        )
        segment_sql, segment_parameters = database.fake_cursor.executions[2]
        self.assertIn("UPDATE user_base", segment_sql)
        self.assertEqual(segment_parameters, (2, 607425))

    def test_fetches_user_detail_directly_by_user_id(self) -> None:
        database = _Database(
            [
                (
                    607425,
                    "user@example.com",
                    "user@example.com",
                    "Player",
                    "gpa17drop",
                    "login-drop",
                    "Applovin-iOS",
                    "advertising-123",
                    5,
                    200_000,
                    90_000,
                    5_000,
                    30_000,
                    8,
                    2,
                    "web",
                    3,
                    2,
                )
            ]
        )

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.user_data.open_database_connection",
            side_effect=connection_context,
        ):
            detail = fetch_user(607425, DatabaseConnectionConfig())

        self.assertIsNotNone(detail)
        self.assertEqual(detail["pkg_name"], "web")
        self.assertEqual(detail["platform"], 3)
        self.assertEqual(detail["user_segment"], 2)
        self.assertEqual(detail["money"], 90_000)
        self.assertEqual(detail["bonus"], 5_000)
        query, parameters = database.fake_cursor.executions[0]
        self.assertIn("`pkg_name`", query)
        self.assertIn("`platform`", query)
        self.assertIn("`money`", query)
        self.assertIn("`bonus`", query)
        self.assertEqual(parameters, (607425,))

    def test_fuzzy_email_query_returns_all_matches(self) -> None:
        row = (
            1, "alex@example.com", "alex", "Alex", "a", "b", "c", "ad",
            4, 100, 80, 20, 10, 2, 1, "a", 2, 3,
        )
        database = _Database([row, (2, *row[1:])])

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.user_data.open_database_connection",
            side_effect=connection_context,
        ):
            users = fetch_users("alex@", DatabaseConnectionConfig())

        self.assertEqual([user["id"] for user in users], [1, 2])
        query, parameters = database.fake_cursor.executions[0]
        self.assertIn("u.email LIKE %s", query)
        self.assertEqual(parameters, ("%alex@%",))

    def test_missing_user_rolls_back(self) -> None:
        database = _Database([None])

        @contextmanager
        def connection_context(_connection):
            yield database

        with patch(
            "base.user_data.open_database_connection",
            side_effect=connection_context,
        ):
            with self.assertRaisesRegex(ValueError, "未找到 UID 7"):
                update_user_fields(
                    7,
                    {field: 0 for field in (
                        "vip_level",
                        "charge_total",
                        "money",
                        "bonus",
                        "withdraw_total",
                        "charge_times",
                        "withdraw_times",
                    )} | {"pkg_name": "a", "platform": 1, "user_segment": 0},
                    DatabaseConnectionConfig(),
                )

        self.assertFalse(database.committed)
        self.assertTrue(database.rolled_back)

    def test_rejects_out_of_range_values(self) -> None:
        values = {
            "vip_level": 256,
            "charge_total": 0,
            "money": 0,
            "bonus": 0,
            "withdraw_total": 0,
            "charge_times": 0,
            "withdraw_times": 0,
            "pkg_name": "a",
            "platform": 1,
            "user_segment": 0,
        }
        with self.assertRaisesRegex(ValueError, "vip_level"):
            normalize_editable_user_values(values)


if __name__ == "__main__":
    unittest.main()
