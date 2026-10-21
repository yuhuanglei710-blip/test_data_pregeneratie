"""按 UID 直接读取和更新 user 表中的用户数据。"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .database_config import DatabaseConnectionConfig, open_database_connection


EDITABLE_USER_FIELDS = (
    "vip_level",
    "charge_total",
    "money",
    "bonus",
    "withdraw_total",
    "charge_times",
    "withdraw_times",
)
USER_DETAIL_FIELDS = (
    "id",
    "email",
    "username",
    "nickname",
    "platform",
    "pkg_name",
    "distribution_channel",
    "login_distribution_channel",
    "channel_code",
    "advertising_id",
    *EDITABLE_USER_FIELDS,
)
MAX_UNSIGNED_INT = 4_294_967_295


def _normalize_user_id(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("UID 必须是正整数")
    try:
        user_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("UID 必须是正整数") from error
    if user_id <= 0:
        raise ValueError("UID 必须是正整数")
    return user_id


def normalize_editable_user_values(values: Mapping[str, object]) -> Dict[str, int]:
    """校验允许写入 user 表的六个非负整数字段。"""
    missing = [field for field in EDITABLE_USER_FIELDS if field not in values]
    if missing:
        raise ValueError(f"缺少用户字段：{', '.join(missing)}")
    normalized: Dict[str, int] = {}
    for field in EDITABLE_USER_FIELDS:
        value = values[field]
        if isinstance(value, bool):
            raise ValueError(f"{field} 必须是非负整数")
        try:
            number = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field} 必须是非负整数") from error
        if number < 0 or number > MAX_UNSIGNED_INT:
            raise ValueError(f"{field} 必须在 0 到 {MAX_UNSIGNED_INT} 之间")
        normalized[field] = number
    if normalized["vip_level"] > 255:
        raise ValueError("vip_level 必须在 0 到 255 之间")
    return normalized


def _values_from_row(row: object) -> Dict[str, int]:
    if not isinstance(row, (tuple, list)) or len(row) < len(EDITABLE_USER_FIELDS):
        raise RuntimeError("数据库返回的用户字段格式无效")
    return {
        field: int(row[index] or 0)
        for index, field in enumerate(EDITABLE_USER_FIELDS)
    }


def _detail_from_row(row: object) -> Dict[str, object]:
    if not isinstance(row, (tuple, list)) or len(row) < len(USER_DETAIL_FIELDS):
        raise RuntimeError("数据库返回的用户数据格式无效")
    detail = {
        field: row[index]
        for index, field in enumerate(USER_DETAIL_FIELDS)
    }
    for field in EDITABLE_USER_FIELDS:
        detail[field] = int(detail[field] or 0)
    detail["id"] = int(detail["id"])
    detail["platform"] = int(detail["platform"] or 0)
    return detail


def fetch_user(
    user_id: int,
    connection: DatabaseConnectionConfig,
) -> Optional[Dict[str, object]]:
    """使用参数化 SQL 按 user.id 直接读取页面所需字段。"""
    normalized_user_id = _normalize_user_id(user_id)
    columns = ", ".join(f"`{field}`" for field in USER_DETAIL_FIELDS)
    with open_database_connection(connection) as database:
        with database.cursor() as cursor:
            cursor.execute(
                f"SELECT {columns} FROM `user` WHERE id=%s LIMIT 1",
                (normalized_user_id,),
            )
            row = cursor.fetchone()
    return None if row is None else _detail_from_row(row)


def update_user_fields(
    user_id: int,
    values: Mapping[str, object],
    connection: DatabaseConnectionConfig,
) -> Dict[str, int]:
    """使用参数化 SQL 按 user.id 更新允许编辑的字段并返回数据库新值。"""
    normalized_user_id = _normalize_user_id(user_id)
    normalized = normalize_editable_user_values(values)
    columns = ", ".join(EDITABLE_USER_FIELDS)
    with open_database_connection(connection) as database:
        try:
            with database.cursor() as cursor:
                cursor.execute(
                    f"SELECT {columns} FROM `user` WHERE id=%s LIMIT 1 FOR UPDATE",
                    (normalized_user_id,),
                )
                if cursor.fetchone() is None:
                    raise ValueError(f"未找到 UID {normalized_user_id}")
                cursor.execute(
                    "UPDATE `user` SET vip_level=%s, charge_total=%s, money=%s, "
                    "bonus=%s, withdraw_total=%s, charge_times=%s, withdraw_times=%s "
                    "WHERE id=%s",
                    tuple(normalized[field] for field in EDITABLE_USER_FIELDS)
                    + (normalized_user_id,),
                )
                cursor.execute(
                    f"SELECT {columns} FROM `user` WHERE id=%s LIMIT 1",
                    (normalized_user_id,),
                )
                updated = cursor.fetchone()
                if updated is None:
                    raise RuntimeError("更新后无法读取用户数据")
            database.commit()
            return _values_from_row(updated)
        except Exception:
            database.rollback()
            raise
