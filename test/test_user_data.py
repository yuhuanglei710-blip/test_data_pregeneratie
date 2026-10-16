"""user 表可编辑字段写入测试。"""

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from base.database_config import DatabaseConnectionConfig
from base.user_data import normalize_editable_user_values, update_user_fields


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
            "withdraw_total": 30_000,
            "charge_times": 8,
            "withdraw_times": 2,
        }
        database = _Database(
            [
                (4, 100_000, 50_000, 10_000, 3, 1),
                (5, 200_000, 90_000, 30_000, 8, 2),
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
            (5, 200_000, 90_000, 30_000, 8, 2, 607425),
        )

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
                        "withdraw_total",
                        "charge_times",
                        "withdraw_times",
                    )},
                    DatabaseConnectionConfig(),
                )

        self.assertFalse(database.committed)
        self.assertTrue(database.rolled_back)

    def test_rejects_out_of_range_values(self) -> None:
        values = {
            "vip_level": 256,
            "charge_total": 0,
            "money": 0,
            "withdraw_total": 0,
            "charge_times": 0,
            "withdraw_times": 0,
        }
        with self.assertRaisesRegex(ValueError, "vip_level"):
            normalize_editable_user_values(values)


if __name__ == "__main__":
    unittest.main()
