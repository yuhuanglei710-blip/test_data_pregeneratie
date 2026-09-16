"""Batch-create test accounts, add funds, and place initial bets."""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Union

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


DEFAULT_ACCOUNT_COUNT = 26
INITIAL_BALANCE = 1_000_000
INITIAL_SPIN_COUNT = 30
SPIN_CONCURRENCY = 3


def _print_account(account: User, index: int, count: int) -> None:
    print(
        f"[{index}/{count}] 注册成功："
        f"uid={account.uid}，email={account.email}，密码={DEFAULT_PASSWORD}"
    )


def _place_initial_spins(
    user_token: str,
    spin_count: int,
    concurrency: int = SPIN_CONCURRENCY,
    *,
    verbose: bool = False,
) -> None:
    if spin_count <= 0:
        return

    # Prime the cache before creating workers to avoid duplicate token requests.
    if not spin.get_valid_game_token(user_token, verbose=verbose):
        raise RuntimeError("无法获取有效的游戏 token")

    worker_count = max(1, min(concurrency, spin_count))
    failed_spins = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(spin.dev_spin, user_token, verbose=verbose): spin_index
            for spin_index in range(1, spin_count + 1)
        }
        for future in as_completed(futures):
            spin_index = futures[future]
            try:
                if future.result() is None:
                    failed_spins.append(spin_index)
            except Exception as error:
                failed_spins.append(spin_index)
                if verbose:
                    print(f"[spin:debug] 第 {spin_index} 次下注异常：{error}")

    if failed_spins:
        failed_text = ", ".join(map(str, sorted(failed_spins)))
        raise RuntimeError(f"下注失败 {len(failed_spins)}/{spin_count} 次：{failed_text}")


def create_accounts_and_bet(
    count: int = 3,
    output_file: Union[str, Path] = "accounts.txt",
    initial_balance: int = INITIAL_BALANCE,
    spin_count: int = INITIAL_SPIN_COUNT,
    spin_concurrency: int = SPIN_CONCURRENCY,
    *,
    verbose: bool = False,
) -> int:
    """Create accounts, seed their balance, place bets, and export them."""
    output_path = Path(output_file)
    success_count = 0
    with output_path.open("w", encoding="utf-8") as account_file:
        for index in range(1, count + 1):
            try:
                account = User(environment="dev")
                account.register(
                    platform=Platform.ios.value,
                    verbose=verbose,
                )
                _print_account(account, index, count)

                if not account.uid or not account.token:
                    raise RuntimeError("注册成功但未获取到 uid 或 token")

                add_money.add_money(
                    user_id=account.uid,
                    amount=initial_balance,
                    remark="测试加钱",
                )
                _place_initial_spins(
                    account.token,
                    spin_count,
                    concurrency=spin_concurrency,
                    verbose=verbose,
                )

                account_file.write(
                    f"uid: {account.uid}\t"
                    f"email: {account.email}\t"
                    f"password: {DEFAULT_PASSWORD}\n"
                )
                account_file.flush()
                success_count += 1
                print(
                    f"[{index}/{count}] 数据生成完成："
                    f"加钱={initial_balance}，下注={spin_count} 次，"
                    f"并发={spin_concurrency}"
                )
            except Exception as error:
                print(f"[{index}/{count}] 创建账号失败: {error}")
                time.sleep(2)

    print(f"批量任务结束：成功 {success_count}/{count}，输出文件：{output_path}")
    return success_count


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    create_accounts_and_bet(
        count=DEFAULT_ACCOUNT_COUNT,
        output_file=project_root / "accounts.txt",
    )
