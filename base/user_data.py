"""按 UID 直接读取和更新 user 表中的用户数据。"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

from .database_config import DatabaseConnectionConfig, open_database_connection


ALLOWED_PACKAGE_NAMES = ("a", "b", "web")
ALLOWED_PLATFORMS = (1, 2, 3)
NUMERIC_USER_FIELDS = (
    "vip_level",
    "charge_total",
    "money",
    "bonus",
    "withdraw_total",
    "charge_times",
    "withdraw_times",
    "platform",
    "user_segment",
)
USER_TABLE_EDITABLE_FIELDS = (
    "vip_level",
    "charge_total",
    "money",
    "bonus",
    "withdraw_total",
    "charge_times",
    "withdraw_times",
    "pkg_name",
    "platform",
)
EDITABLE_USER_FIELDS = (
    *USER_TABLE_EDITABLE_FIELDS,
    "user_segment",
)
USER_DETAIL_FIELDS = (
    "id",
    "email",
    "username",
    "nickname",
    "distribution_channel",
    "login_distribution_channel",
    "channel_code",
    "advertising_id",
    *USER_TABLE_EDITABLE_FIELDS,
    "user_segment",
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


def normalize_editable_user_values(values: Mapping[str, object]) -> Dict[str, object]:
    """校验用户页允许写入的数字、包名、平台和分层字段。"""
    missing = [field for field in EDITABLE_USER_FIELDS if field not in values]
    if missing:
        raise ValueError(f"缺少用户字段：{', '.join(missing)}")
    normalized: Dict[str, object] = {}
    for field in NUMERIC_USER_FIELDS:
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
    package_name = str(values["pkg_name"]).strip()
    if package_name not in ALLOWED_PACKAGE_NAMES:
        raise ValueError("pkg_name 只允许选择 a、b 或 web")
    if normalized["platform"] not in ALLOWED_PLATFORMS:
        raise ValueError("platform 只允许选择 1、2 或 3")
    normalized["pkg_name"] = package_name
    return normalized


def _values_from_row(row: object) -> Dict[str, object]:
    if not isinstance(row, (tuple, list)) or len(row) < len(EDITABLE_USER_FIELDS):
        raise RuntimeError("数据库返回的用户字段格式无效")
    values: Dict[str, object] = {}
    for index, field in enumerate(EDITABLE_USER_FIELDS):
        value = row[index]
        values[field] = (
            int(value or 0) if field in NUMERIC_USER_FIELDS else str(value or "")
        )
    return values


def _detail_from_row(row: object) -> Dict[str, object]:
    if not isinstance(row, (tuple, list)) or len(row) < len(USER_DETAIL_FIELDS):
        raise RuntimeError("数据库返回的用户数据格式无效")
    detail = {
        field: row[index]
        for index, field in enumerate(USER_DETAIL_FIELDS)
    }
    for field in NUMERIC_USER_FIELDS:
        detail[field] = int(detail[field] or 0)
    detail["id"] = int(detail["id"])
    detail["pkg_name"] = str(detail["pkg_name"] or "")
    return detail


def _detail_columns(alias: str = "u") -> str:
    user_columns = ", ".join(
        f"{alias}.`{field}`"
        for field in USER_DETAIL_FIELDS
        if field != "user_segment"
    )
    return (
        f"{user_columns}, (SELECT ub.user_segment FROM user_base AS ub "
        f"WHERE ub.user_id={alias}.id LIMIT 1) AS user_segment"
    )


def fetch_users(
    search_value: object,
    connection: DatabaseConnectionConfig,
    *,
    limit: int = 50,
) -> List[Dict[str, object]]:
    """按 UID 精确查询，或按邮箱关键字模糊查询用户。"""
    query = str(search_value).strip()
    if not query:
        raise ValueError("请输入 UID 或邮箱关键字")
    if limit <= 0 or limit > 200:
        raise ValueError("查询条数必须在 1 到 200 之间")
    if query.isdigit():
        where_sql = "u.id=%s"
        parameters = (_normalize_user_id(query),)
    else:
        where_sql = "u.email LIKE %s"
        parameters = (f"%{query}%",)
    with open_database_connection(connection) as database:
        with database.cursor() as cursor:
            cursor.execute(
                f"SELECT {_detail_columns()} FROM `user` AS u "
                f"WHERE {where_sql} ORDER BY u.id DESC LIMIT {int(limit)}",
                parameters,
            )
            rows = cursor.fetchall()
    if not isinstance(rows, (tuple, list)):
        raise RuntimeError("数据库返回的用户列表格式无效")
    return [_detail_from_row(row) for row in rows]


def fetch_user(
    user_id: int,
    connection: DatabaseConnectionConfig,
) -> Optional[Dict[str, object]]:
    """使用参数化 SQL 按 user.id 直接读取页面所需字段。"""
    users = fetch_users(_normalize_user_id(user_id), connection, limit=1)
    return users[0] if users else None


def update_user_fields(
    user_id: int,
    values: Mapping[str, object],
    connection: DatabaseConnectionConfig,
) -> Dict[str, object]:
    """使用参数化 SQL 按 user.id 更新允许编辑的字段并返回数据库新值。"""
    normalized_user_id = _normalize_user_id(user_id)
    normalized = normalize_editable_user_values(values)
    columns = ", ".join(f"`{field}`" for field in USER_TABLE_EDITABLE_FIELDS)
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
                    "bonus=%s, withdraw_total=%s, charge_times=%s, withdraw_times=%s, "
                    "pkg_name=%s, platform=%s WHERE id=%s",
                    tuple(normalized[field] for field in USER_TABLE_EDITABLE_FIELDS)
                    + (normalized_user_id,),
                )
                cursor.execute(
                    "UPDATE user_base SET user_segment=%s WHERE user_id=%s",
                    (normalized["user_segment"], normalized_user_id),
                )
                cursor.execute(
                    f"SELECT {columns}, (SELECT ub.user_segment FROM user_base AS ub "
                    "WHERE ub.user_id=u.id LIMIT 1) AS user_segment "
                    "FROM `user` AS u WHERE u.id=%s LIMIT 1",
                    (normalized_user_id,),
                )
                updated = cursor.fetchone()
                if updated is None:
                    raise RuntimeError("更新后无法读取用户数据")
                normalized_updated = _values_from_row(updated)
                if normalized_updated["user_segment"] != normalized["user_segment"]:
                    raise RuntimeError("用户分层记录不存在或更新失败")
            database.commit()
            return normalized_updated
        except Exception:
            database.rollback()
            raise
