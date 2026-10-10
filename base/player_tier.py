"""玩家净利润、利润率、分层计算与测试数据构造。"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Optional

from .database_config import DatabaseConnectionConfig, open_database_connection
from .fund_and_spin import (
    DEFAULT_SPIN_WORKERS,
    INITIAL_BALANCE,
    INITIAL_SPIN_COUNT,
    fund_and_spin,
)
from .spin import DEFAULT_BET_CENTS
from .user import User


CHARGE_FEE_RATE = Decimal("0.07")
WITHDRAW_FEE_RATE = Decimal("0.035")
MAX_UNSIGNED_INT = 4_294_967_295
# 服务端只有累计充值达到 350000 美分时才会参与用户分层。构造值额外
# 留出 50000 美分余量，避免测试数据全部落在服务端判断边界上。
MINIMUM_TIER_CHARGE_TOTAL = 350_000
CONSTRUCTION_CHARGE_TOTAL = 400_000
# 净利润严格超过 10,000 美元（1,000,000 分）时，优先判定为顶级玩家。
TOP_NET_PROFIT_THRESHOLD = Decimal("1000000")
TARGET_NET_PROFIT_TOP = "net_profit_top"
# 特殊构造目标使用 7,000,000 分充值、15% 利润率：净利润为 1,050,000 分。
# 该利润率按普通规则本应属于核心玩家，可明确验证净利润规则的优先级。
NET_PROFIT_TOP_CONSTRUCTION_CHARGE_TOTAL = 7_000_000
NET_PROFIT_TOP_TARGET_RATE = Decimal("0.15")
SECONDS_PER_DAY = 24 * 60 * 60
REGISTRATION_AGE_WITHIN_7_DAYS = "within_7_days"
REGISTRATION_AGE_OVER_7_DAYS = "over_7_days"
REGISTRATION_AGE_LABELS = {
    REGISTRATION_AGE_WITHIN_7_DAYS: "7天内",
    REGISTRATION_AGE_OVER_7_DAYS: "大于7天",
}

TIER_ARBITRAGE = "arbitrage"
TIER_NORMAL = "normal"
TIER_CORE = "core"
TIER_TOP = "top"
TIER_UNCLASSIFIED = "unclassified"

TIER_LABELS = {
    TIER_ARBITRAGE: "套利用户",
    TIER_NORMAL: "普通用户",
    TIER_CORE: "核心玩家",
    TIER_TOP: "顶级玩家",
    TIER_UNCLASSIFIED: "未分层",
}

TARGET_PROFIT_RATES = {
    TIER_ARBITRAGE: Decimal("-0.02"),
    TIER_NORMAL: Decimal("0.05"),
    TIER_CORE: Decimal("0.15"),
    TIER_TOP: Decimal("0.25"),
}

TARGET_TIER_LABELS = {
    **{tier: TIER_LABELS[tier] for tier in TARGET_PROFIT_RATES},
    TARGET_NET_PROFIT_TOP: "净利润顶级玩家",
}


@dataclass(frozen=True)
class PlayerTierMetrics:
    """玩家分层所需的数据库原值及计算结果，金额单位为分。"""

    user_id: int
    charge_total: int
    withdraw_total: int
    balance: int
    net_profit: Decimal
    profit_rate: Optional[Decimal]
    tier: str
    user_segment: Optional[int] = None
    created_at: Optional[int] = None

    @property
    def tier_label(self) -> str:
        return TIER_LABELS[self.tier]


@dataclass(frozen=True)
class PlayerLoginCredentials:
    """自动登录所需且不会返回到界面的用户字段。"""

    email: str
    platform: int


def _non_negative_integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是非负整数")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}必须是非负整数") from error
    if normalized < 0:
        raise ValueError(f"{label}必须是非负整数")
    return normalized


def calculate_player_tier(
    charge_total: object,
    withdraw_total: object,
    balance: object,
    *,
    user_id: int = 0,
) -> PlayerTierMetrics:
    """按累计充值、累计提现和当前余额计算净利润与玩家分层。"""
    charge = _non_negative_integer(charge_total, "累计充值")
    withdraw = _non_negative_integer(withdraw_total, "累计提现")
    current_balance = _non_negative_integer(balance, "当前余额")
    net_profit = (
        Decimal(charge)
        - Decimal(withdraw)
        - CHARGE_FEE_RATE * Decimal(charge)
        - WITHDRAW_FEE_RATE * Decimal(withdraw)
        - Decimal(current_balance)
    )
    if charge == 0:
        return PlayerTierMetrics(
            int(user_id),
            charge,
            withdraw,
            current_balance,
            net_profit,
            None,
            TIER_UNCLASSIFIED,
        )
    profit_rate = net_profit / Decimal(charge)
    if net_profit > TOP_NET_PROFIT_THRESHOLD:
        tier = TIER_TOP
    elif profit_rate < Decimal("-0.01"):
        tier = TIER_ARBITRAGE
    elif profit_rate < Decimal("0.10"):
        tier = TIER_NORMAL
    elif profit_rate < Decimal("0.20"):
        tier = TIER_CORE
    else:
        tier = TIER_TOP
    return PlayerTierMetrics(
        int(user_id),
        charge,
        withdraw,
        current_balance,
        net_profit,
        profit_rate,
        tier,
    )


def build_player_tier_values(
    current: PlayerTierMetrics,
    target_tier: str,
) -> PlayerTierMetrics:
    """保留已达标的累计充值，并调整余额构造目标分层区间。"""
    if target_tier not in TARGET_TIER_LABELS:
        raise ValueError("不支持的目标分层")
    charge = (
        current.charge_total
        if current.charge_total > MINIMUM_TIER_CHARGE_TOTAL
        else CONSTRUCTION_CHARGE_TOTAL
    )
    if target_tier == TARGET_NET_PROFIT_TOP:
        charge = max(charge, NET_PROFIT_TOP_CONSTRUCTION_CHARGE_TOTAL)
        target_rate = NET_PROFIT_TOP_TARGET_RATE
    else:
        target_rate = TARGET_PROFIT_RATES[target_tier]
    withdraw = 0
    target_net_profit = target_rate * Decimal(charge)
    rounding = ROUND_HALF_UP
    if (
        target_tier in {TIER_NORMAL, TIER_CORE}
        and target_net_profit > TOP_NET_PROFIT_THRESHOLD
    ):
        # 保留高累计充值时，不能让普通/核心目标被净利润优先规则重新判成顶级。
        target_net_profit = TOP_NET_PROFIT_THRESHOLD
        rounding = ROUND_CEILING
    balance = int(
        (
            Decimal("0.93") * Decimal(charge) - target_net_profit
        ).to_integral_value(
            rounding=rounding
        )
    )
    if balance > MAX_UNSIGNED_INT:
        raise ValueError("计算出的当前余额超出 user 表字段范围")
    proposed = calculate_player_tier(
        charge,
        withdraw,
        balance,
        user_id=current.user_id,
    )
    expected_tier = TIER_TOP if target_tier == TARGET_NET_PROFIT_TOP else target_tier
    if proposed.tier != expected_tier:
        if target_tier == TIER_CORE and charge > 10_000_000:
            raise ValueError(
                "当前累计充值超过 10,000,000 分；保留该充值额时，"
                "核心玩家所需的最低 10% 净利润已超过顶级阈值，无法构造"
            )
        raise ValueError("整数金额舍入后未能落入目标分层")
    if (
        target_tier == TARGET_NET_PROFIT_TOP
        and proposed.net_profit <= TOP_NET_PROFIT_THRESHOLD
    ):
        raise ValueError("整数金额舍入后净利润未超过 1,000,000 分")
    return proposed


def resolve_registration_created_at(
    created_at: object,
    registration_age: str,
    *,
    now: Optional[int] = None,
) -> int:
    """按目标注册时长保留或校正 Unix 时间戳。"""
    current_created_at = _non_negative_integer(created_at, "注册时间")
    if registration_age not in REGISTRATION_AGE_LABELS:
        raise ValueError("不支持的注册时长")
    current_time = (
        int(time.time())
        if now is None
        else _non_negative_integer(now, "当前时间")
    )
    seven_days_ago = current_time - 7 * SECONDS_PER_DAY
    if registration_age == REGISTRATION_AGE_WITHIN_7_DAYS:
        if current_created_at >= seven_days_ago:
            return current_created_at
        return current_time - 5 * SECONDS_PER_DAY
    if current_created_at < seven_days_ago:
        return current_created_at
    return current_time - 8 * SECONDS_PER_DAY


def _metrics_from_row(row: object, user_id: int) -> PlayerTierMetrics:
    if not isinstance(row, (tuple, list)) or len(row) < 4:
        raise ValueError("数据库返回的玩家数据格式无效")
    metrics = calculate_player_tier(
        row[1], row[2], row[3], user_id=int(row[0] or user_id)
    )
    if len(row) < 5:
        return metrics
    return replace(metrics, created_at=_non_negative_integer(row[4], "注册时间"))


def _fetch_user_segment(cursor: object, user_id: int) -> Optional[int]:
    cursor.execute(
        "SELECT user_segment FROM user_base WHERE user_id=%s LIMIT 1",
        (int(user_id),),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if not isinstance(row, (tuple, list)) or not row:
        raise ValueError("数据库返回的 user_segment 数据格式无效")
    if row[0] is None:
        return None
    return _non_negative_integer(row[0], "user_segment")


def fetch_player_tier(
    user_id: int,
    connection: DatabaseConnectionConfig,
) -> PlayerTierMetrics:
    """从所选环境的 user 表读取玩家分层数据。"""
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("UID 必须是大于 0 的整数")
    with open_database_connection(connection) as database:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT id, charge_total, withdraw_total, money, created_at "
                "FROM `user` WHERE id=%s LIMIT 1",
                (int(user_id),),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"未找到 UID {int(user_id)}")
            user_segment = _fetch_user_segment(cursor, int(user_id))
    return replace(
        _metrics_from_row(row, int(user_id)),
        user_segment=user_segment,
    )


def fetch_player_login_credentials(
    user_id: int,
    connection: DatabaseConnectionConfig,
) -> PlayerLoginCredentials:
    """按 UID 读取自动登录所需的邮箱和平台。"""
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("UID 必须是大于 0 的整数")
    with open_database_connection(connection) as database:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT email, platform "
                "FROM `user` WHERE id=%s LIMIT 1",
                (int(user_id),),
            )
            row = cursor.fetchone()
    if not isinstance(row, (tuple, list)) or len(row) < 2:
        raise ValueError(f"未找到 UID {int(user_id)} 的登录信息")
    email = str(row[0] or "").strip()
    if not email:
        raise ValueError("数据库中的用户邮箱为空，无法自动登录")
    return PlayerLoginCredentials(
        email=email,
        platform=int(row[1] if row[1] is not None else 0),
    )


def construct_player_tier(
    user_id: int,
    target_tier: str,
    connection: DatabaseConnectionConfig,
    registration_age: Optional[str] = None,
) -> PlayerTierMetrics:
    """锁定玩家记录并写入目标分层及所选注册时长的数据。"""
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("UID 必须是大于 0 的整数")
    with open_database_connection(connection) as database:
        try:
            with database.cursor() as cursor:
                cursor.execute(
                    "SELECT id, charge_total, withdraw_total, money, created_at "
                    "FROM `user` WHERE id=%s LIMIT 1 FOR UPDATE",
                    (int(user_id),),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"未找到 UID {int(user_id)}")
                current = _metrics_from_row(row, int(user_id))
                proposed = build_player_tier_values(current, target_tier)
                if registration_age is None:
                    update_sql = (
                        "UPDATE `user` SET charge_total=%s, withdraw_total=%s, money=%s "
                        "WHERE id=%s"
                    )
                    update_parameters = (
                        proposed.charge_total,
                        proposed.withdraw_total,
                        proposed.balance,
                        proposed.user_id,
                    )
                else:
                    if current.created_at is None:
                        raise ValueError("数据库未返回 user.created_at")
                    created_at = resolve_registration_created_at(
                        current.created_at,
                        registration_age,
                    )
                    proposed = replace(proposed, created_at=created_at)
                    update_sql = (
                        "UPDATE `user` SET charge_total=%s, withdraw_total=%s, money=%s, "
                        "created_at=%s WHERE id=%s"
                    )
                    update_parameters = (
                        proposed.charge_total,
                        proposed.withdraw_total,
                        proposed.balance,
                        created_at,
                        proposed.user_id,
                    )
                cursor.execute(update_sql, update_parameters)
                if int(cursor.rowcount) != 1:
                    raise RuntimeError("玩家分层数据更新失败")
                proposed = replace(
                    proposed,
                    user_segment=_fetch_user_segment(cursor, proposed.user_id),
                )
            database.commit()
            return proposed
        except Exception:
            database.rollback()
            raise


def prepare_turnover_and_construct_player_tier(
    user_id: int,
    target_tier: str,
    connection: DatabaseConnectionConfig,
    registration_age: str,
    *,
    environment: str,
    initial_balance: int = INITIAL_BALANCE,
    spin_count: int = INITIAL_SPIN_COUNT,
    bet_amount: int = DEFAULT_BET_CENTS,
    spin_workers: int = DEFAULT_SPIN_WORKERS,
) -> PlayerTierMetrics:
    """新用户被改为大于 7 天前，先通过加钱和下注形成流水。"""
    current = fetch_player_tier(user_id, connection)
    if current.created_at is None:
        raise ValueError("数据库未返回 user.created_at")
    target_created_at = resolve_registration_created_at(
        current.created_at,
        registration_age,
    )
    is_new_user_being_aged = (
        registration_age == REGISTRATION_AGE_OVER_7_DAYS
        and target_created_at != current.created_at
    )
    if is_new_user_being_aged:
        credentials = fetch_player_login_credentials(user_id, connection)
        account = User(email=credentials.email, environment=environment)

        def refresh_user_token() -> str:
            """后台加钱完成后重新登录，获取仍然有效的用户 Token。"""
            account.login(platform=credentials.platform)
            if account.uid != int(user_id):
                raise RuntimeError(
                    f"自动登录返回 UID {account.uid}，"
                    f"与目标 UID {int(user_id)} 不一致"
                )
            if not account.token:
                raise RuntimeError("自动登录成功但未获取到用户 Token")
            return account.token

        fund_and_spin(
            user_id,
            None,
            environment=environment,
            amount=initial_balance,
            spin_count=spin_count,
            bet_amount=bet_amount,
            spin_workers=spin_workers,
            refresh_user_token=refresh_user_token,
        )
    return construct_player_tier(
        user_id,
        target_tier,
        connection,
        registration_age,
    )
