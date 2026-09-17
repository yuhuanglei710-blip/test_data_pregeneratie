"""Batch-create test accounts, add funds, and place initial bets."""

import json
import random
import sys
import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

try:  # Support ``python -m base.tournment_test``.
    from . import add_money, spin
    from .enums import Platform
    from .user import DEFAULT_PASSWORD, User
except ImportError:  # Support ``python base/tournment_test.py``.
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import add_money
    import spin
    from enums import Platform
    from user import DEFAULT_PASSWORD, User


DEFAULT_ACCOUNT_COUNT = 30
INITIAL_BALANCE = 1_000_000
INITIAL_SPIN_COUNT = 30
DEFAULT_MAX_WORKERS = 5


class SpinWorkflowError(RuntimeError):
    """Stop the batch when the game service rejects a spin."""


class BatchCancelled(RuntimeError):
    """Raised when a caller requests a cooperative stop."""


@dataclass(frozen=True)
class AccountResult:
    """Successful account data returned to the coordinator thread."""

    index: int
    output_line: str


def _resolve_spin_count(
    fixed_count: int,
    spin_count_range: Optional[Tuple[int, int]],
) -> int:
    if spin_count_range is None:
        if fixed_count <= 0:
            raise ValueError("下注次数必须大于 0")
        return fixed_count

    minimum, maximum = spin_count_range
    if minimum <= 0 or maximum < minimum:
        raise ValueError("随机下注次数范围无效")
    return random.randint(minimum, maximum)


def _print_account(account: User, index: int, count: int) -> None:
    print(
        f"[{index}/{count}] 注册成功："
        f"uid={account.uid}，email={account.email}，密码={DEFAULT_PASSWORD}"
    )


def _place_initial_spins(
    user_token: str,
    spin_count: int,
    bet_amount: int = spin.DEFAULT_BET_CENTS,
    *,
    verbose: bool = False,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> None:
    for spin_index in range(1, spin_count + 1):
        if stop_requested and stop_requested():
            raise BatchCancelled("用户已停止任务")
        if spin.dev_spin(
            user_token,
            bet_amount=bet_amount,
            verbose=verbose,
        ) is None:
            raise SpinWorkflowError(f"第 {spin_index}/{spin_count} 次下注失败")


def _create_account_and_bet(
    index: int,
    count: int,
    *,
    environment: str,
    admin_base_url: str,
    initial_balance: int,
    spin_count: int,
    spin_count_range: Optional[Tuple[int, int]],
    bet_amount: int,
    verbose: bool,
    stop_requested: Callable[[], bool],
) -> AccountResult:
    """Run one account pipeline; each account's spins remain ordered."""
    if stop_requested():
        raise BatchCancelled("用户已停止任务")

    account_spin_count = _resolve_spin_count(spin_count, spin_count_range)
    if spin_count_range is not None:
        print(
            f"[{index}/{count}] 随机下注次数：{account_spin_count} "
            f"（范围 {spin_count_range[0]}-{spin_count_range[1]}）"
        )

    account = User(environment=environment)
    account.register(platform=Platform.ios.value, verbose=verbose)
    _print_account(account, index, count)

    if not account.uid or not account.token:
        raise RuntimeError("注册成功但未获取到 uid 或 token")

    money_result = add_money.add_money(
        user_id=account.uid,
        amount=initial_balance,
        remark="测试加钱",
        base_url=admin_base_url,
    )
    print(
        f"[{index}/{count}] [money] 加钱响应："
        + json.dumps(money_result, ensure_ascii=False, separators=(",", ":"))
    )
    if not add_money.operation_succeeded(money_result):
        raise RuntimeError(f"加钱业务失败：{money_result}")

    _place_initial_spins(
        account.token,
        account_spin_count,
        bet_amount=bet_amount,
        verbose=verbose,
        stop_requested=stop_requested,
    )

    print(
        f"[{index}/{count}] 数据生成完成："
        f"加钱={initial_balance}，下注={account_spin_count} 次，"
        f"单次金额={bet_amount} 美分"
    )
    return AccountResult(
        index=index,
        output_line=(
            f"uid: {account.uid}\t"
            f"email: {account.email}\t"
            f"password: {DEFAULT_PASSWORD}\n"
        ),
    )


def create_accounts_and_bet(
    count: int = 3,
    output_file: Union[str, Path] = "accounts.txt",
    initial_balance: int = INITIAL_BALANCE,
    spin_count: int = INITIAL_SPIN_COUNT,
    bet_amount: int = spin.DEFAULT_BET_CENTS,
    *,
    spin_count_range: Optional[Tuple[int, int]] = None,
    environment: str = "dev",
    verbose: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """Create accounts in parallel and export successful account records.

    Accounts run concurrently, while spins for the same account remain serial so
    that the game ``session_id`` chain is preserved. ``progress_callback`` gets
    ``(completed, total, successful)`` after every finished account pipeline.
    """
    if count <= 0:
        raise ValueError("账号数量必须大于 0")
    if max_workers <= 0:
        raise ValueError("并行账号数必须大于 0")

    output_path = Path(output_file)
    success_count = 0
    completed_count = 0
    admin_base_url = add_money.base_url_for_environment(environment)
    internal_stop = threading.Event()

    def should_stop() -> bool:
        return internal_stop.is_set() or bool(stop_requested and stop_requested())

    with output_path.open("w", encoding="utf-8") as account_file:
        worker_count = min(max_workers, count)
        print(f"批量任务启动：账号={count}，并行账号数={worker_count}")
        executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="account",
        )
        futures: Dict[Future[AccountResult], int] = {
            executor.submit(
                _create_account_and_bet,
                index,
                count,
                environment=environment,
                admin_base_url=admin_base_url,
                initial_balance=initial_balance,
                spin_count=spin_count,
                spin_count_range=spin_count_range,
                bet_amount=bet_amount,
                verbose=verbose,
                stop_requested=should_stop,
            ): index
            for index in range(1, count + 1)
        }

        try:
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result = future.result()
                    account_file.write(result.output_line)
                    account_file.flush()
                    success_count += 1
                except (BatchCancelled, CancelledError):
                    pass
                except SpinWorkflowError as error:
                    print(f"[{index}/{count}] 创建账号失败: {error}")
                    print("检测到下注业务错误，正在停止剩余批量任务")
                    internal_stop.set()
                except Exception as error:
                    print(f"[{index}/{count}] 创建账号失败: {error}")
                finally:
                    completed_count += 1
                    if progress_callback:
                        progress_callback(completed_count, count, success_count)

                if should_stop():
                    internal_stop.set()
                    for pending_future in futures:
                        if not pending_future.done():
                            pending_future.cancel()
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    if stop_requested and stop_requested():
        print("用户已停止任务")

    print(f"批量任务结束：成功 {success_count}/{count}，输出文件：{output_path}")
    return success_count


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    create_accounts_and_bet(
        count=DEFAULT_ACCOUNT_COUNT,
        output_file=project_root / "accounts.txt",
    )
