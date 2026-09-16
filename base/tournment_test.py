"""Batch-create test accounts, add funds, and place initial bets."""

import json
import sys
import time
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


DEFAULT_ACCOUNT_COUNT = 30
INITIAL_BALANCE = 1_000_000
INITIAL_SPIN_COUNT = 30


class SpinWorkflowError(RuntimeError):
    """Stop the batch when the game service rejects a spin."""


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
) -> None:
    for spin_index in range(1, spin_count + 1):
        if spin.dev_spin(
            user_token,
            bet_amount=bet_amount,
            verbose=verbose,
        ) is None:
            raise SpinWorkflowError(f"第 {spin_index}/{spin_count} 次下注失败")


def create_accounts_and_bet(
    count: int = 3,
    output_file: Union[str, Path] = "accounts.txt",
    initial_balance: int = INITIAL_BALANCE,
    spin_count: int = INITIAL_SPIN_COUNT,
    bet_amount: int = spin.DEFAULT_BET_CENTS,
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

                money_result = add_money.add_money(
                    user_id=account.uid,
                    amount=initial_balance,
                    remark="测试加钱",
                )
                print(
                    "[money] 加钱响应："
                    + json.dumps(
                        money_result,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                if not add_money.operation_succeeded(money_result):
                    raise RuntimeError(f"加钱业务失败：{money_result}")

                _place_initial_spins(
                    account.token,
                    spin_count,
                    bet_amount=bet_amount,
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
                    f"单次金额={bet_amount} 美分"
                )
            except SpinWorkflowError as error:
                print(f"[{index}/{count}] 创建账号失败: {error}")
                print("检测到下注业务错误，已停止剩余批量任务")
                break
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
