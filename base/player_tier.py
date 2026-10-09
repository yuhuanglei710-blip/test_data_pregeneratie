"""玩家净利润、利润率、分层计算与测试数据构造。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Optional

from .database_config import DatabaseConnectionConfig, open_database_connection


CHARGE_FEE_RATE = Decimal("0.07")
WITHDRAW_FEE_RATE = Decimal("0.035")
MAX_UNSIGNED_INT = 4_294_967_295

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

    @property
    def tier_label(self) -> str:
        return TIER_LABELS[self.tier]


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
    if profit_rate < Decimal("-0.01"):
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
    """保持当前余额不变，构造目标分层区间内的累计充值和提现。"""
    if target_tier not in TARGET_PROFIT_RATES:
        raise ValueError("不支持的目标分层")
    target_rate = TARGET_PROFIT_RATES[target_tier]
    charge_factor = Decimal("0.93") - target_rate
    required_charge = (
        Decimal(current.balance) / charge_factor
    ).to_integral_value(rounding=ROUND_CEILING) + 10_000
    charge = max(current.charge_total, 100_000, int(required_charge))
    if charge > MAX_UNSIGNED_INT:
        raise ValueError("当前余额过高，无法在 user 表字段范围内构造目标分层")
    withdraw = int(
        (
            (charge_factor * Decimal(charge) - Decimal(current.balance))
            / Decimal("1.035")
        ).to_integral_value(rounding=ROUND_HALF_UP)
    )
    withdraw = max(0, withdraw)
    if withdraw > MAX_UNSIGNED_INT:
        raise ValueError("计算出的累计提现超出 user 表字段范围")
    proposed = calculate_player_tier(
        charge,
        withdraw,
        current.balance,
        user_id=current.user_id,
    )
    if proposed.tier != target_tier:
        raise ValueError("整数金额舍入后未能落入目标分层，请调整当前余额后重试")
    return proposed


def _metrics_from_row(row: object, user_id: int) -> PlayerTierMetrics:
    if not isinstance(row, (tuple, list)) or len(row) < 4:
        raise ValueError("数据库返回的玩家数据格式无效")
    return calculate_player_tier(row[1], row[2], row[3], user_id=int(row[0] or user_id))


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
                "SELECT id, charge_total, withdraw_total, money "
                "FROM `user` WHERE id=%s LIMIT 1",
                (int(user_id),),
            )
            row = cursor.fetchone()
    if row is None:
        raise ValueError(f"未找到 UID {int(user_id)}")
    return _metrics_from_row(row, int(user_id))


def construct_player_tier(
    user_id: int,
    target_tier: str,
    connection: DatabaseConnectionConfig,
) -> PlayerTierMetrics:
    """锁定玩家记录并写入目标分层数据，仅修改累计充值和累计提现。"""
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("UID 必须是大于 0 的整数")
    with open_database_connection(connection) as database:
        try:
            with database.cursor() as cursor:
                cursor.execute(
                    "SELECT id, charge_total, withdraw_total, money "
                    "FROM `user` WHERE id=%s LIMIT 1 FOR UPDATE",
                    (int(user_id),),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"未找到 UID {int(user_id)}")
                current = _metrics_from_row(row, int(user_id))
                proposed = build_player_tier_values(current, target_tier)
                cursor.execute(
                    "UPDATE `user` SET charge_total=%s, withdraw_total=%s "
                    "WHERE id=%s",
                    (
                        proposed.charge_total,
                        proposed.withdraw_total,
                        proposed.user_id,
                    ),
                )
                if int(cursor.rowcount) != 1:
                    raise RuntimeError("玩家分层数据更新失败")
            database.commit()
            return proposed
        except Exception:
            database.rollback()
            raise
