"""可供不同数据准备流程复用的用户加钱与下注能力。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

try:  # Support package and direct script imports.
    from . import add_money, spin
except ImportError:  # pragma: no cover - compatibility for direct execution.
    import add_money
    import spin


INITIAL_BALANCE = 1_000_000
INITIAL_SPIN_COUNT = 30
DEFAULT_SPIN_WORKERS = 5


class SpinWorkflowError(RuntimeError):
    """游戏服务拒绝下注。"""


class FundingWorkflowCancelled(RuntimeError):
    """调用方请求安全停止加钱与下注流程。"""


@dataclass(frozen=True)
class FundAndSpinResult:
    """一次加钱与下注流程实际使用的参数。"""

    user_id: int
    added_amount: int
    spin_count: int
    bet_amount: int


def place_spins(
    user_token: str,
    spin_count: int,
    bet_amount: int = spin.DEFAULT_BET_CENTS,
    *,
    environment: str = "dev",
    spin_workers: int = 1,
    verbose: bool = False,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> None:
    """按所选并发数完成一个已有用户的下注。"""
    if not isinstance(user_token, str) or not user_token.strip():
        raise ValueError("用户 Token 不能为空")
    if spin_count <= 0:
        raise ValueError("下注次数必须大于 0")
    if bet_amount <= 0:
        raise ValueError("下注金额必须大于 0")
    if spin_workers <= 0:
        raise ValueError("下注并发数必须大于 0")

    if spin_workers > 1:
        if not spin.get_valid_game_token(user_token, environment=environment):
            raise SpinWorkflowError("获取游戏 token 失败")

        def place_parallel_spin(spin_index: int) -> None:
            if stop_requested and stop_requested():
                raise FundingWorkflowCancelled("用户已停止任务")
            if spin.dev_spin(
                user_token,
                environment=environment,
                bet_amount=bet_amount,
                preserve_session=False,
                verbose=verbose,
            ) is None:
                raise SpinWorkflowError(f"第 {spin_index}/{spin_count} 次下注失败")

        with ThreadPoolExecutor(
            max_workers=min(spin_workers, spin_count),
            thread_name_prefix="spin",
        ) as executor:
            futures = [
                executor.submit(place_parallel_spin, spin_index)
                for spin_index in range(1, spin_count + 1)
            ]
            for future in as_completed(futures):
                future.result()
        return

    for spin_index in range(1, spin_count + 1):
        if stop_requested and stop_requested():
            raise FundingWorkflowCancelled("用户已停止任务")
        if spin.dev_spin(
            user_token,
            environment=environment,
            bet_amount=bet_amount,
            verbose=verbose,
        ) is None:
            raise SpinWorkflowError(f"第 {spin_index}/{spin_count} 次下注失败")


def fund_and_spin(
    user_id: int,
    user_token: Optional[str],
    *,
    environment: str,
    amount: int = INITIAL_BALANCE,
    spin_count: int = INITIAL_SPIN_COUNT,
    bet_amount: int = spin.DEFAULT_BET_CENTS,
    spin_workers: int = DEFAULT_SPIN_WORKERS,
    verbose: bool = False,
    stop_requested: Optional[Callable[[], bool]] = None,
    admin_base_url: Optional[str] = None,
    refresh_user_token: Optional[Callable[[], str]] = None,
    spin_runner: Callable[..., None] = place_spins,
    log_prefix: str = "",
) -> FundAndSpinResult:
    """给已有用户加钱并完成下注，任一步失败都终止后续处理。"""
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("UID 必须是大于 0 的整数")
    initial_token = user_token.strip() if isinstance(user_token, str) else ""
    if not initial_token and refresh_user_token is None:
        raise ValueError("用户 Token 不能为空")
    if amount <= 0:
        raise ValueError("加钱金额必须大于 0")
    if spin_count <= 0:
        raise ValueError("下注次数必须大于 0")
    if bet_amount <= 0:
        raise ValueError("下注金额必须大于 0")
    if spin_workers <= 0:
        raise ValueError("下注并发数必须大于 0")
    if stop_requested and stop_requested():
        raise FundingWorkflowCancelled("用户已停止任务")

    # 所有地址都必须在加钱前解析成功，禁止错误环境先改余额再失败，
    # 也禁止未配置的环境静默回退到 dev。
    base_url = admin_base_url or add_money.base_url_for_environment(environment)
    spin_config = spin._config_for_environment(environment)
    game_url_api = spin_config.game_url_api
    print(
        f"{log_prefix}[flow] 环境={environment}，"
        f"后台={base_url}，登录/游戏入口={game_url_api}"
    )
    money_result = add_money.add_money(
        user_id=int(user_id),
        amount=amount,
        remark="测试加钱",
        base_url=base_url,
    )
    print(
        f"{log_prefix}[money] 加钱响应："
        + json.dumps(money_result, ensure_ascii=False, separators=(",", ":"))
    )
    if not add_money.operation_succeeded(money_result):
        raise RuntimeError(f"加钱业务失败：{money_result}")

    if stop_requested and stop_requested():
        raise FundingWorkflowCancelled("用户已停止任务")
    active_token = (
        refresh_user_token()
        if refresh_user_token is not None
        else initial_token
    )
    if not isinstance(active_token, str) or not active_token.strip():
        raise RuntimeError("加钱后重新登录未获取到用户 Token")

    spin_runner(
        active_token,
        spin_count,
        environment=environment,
        spin_workers=spin_workers,
        bet_amount=bet_amount,
        verbose=verbose,
        stop_requested=stop_requested,
    )
    return FundAndSpinResult(int(user_id), amount, spin_count, bet_amount)
