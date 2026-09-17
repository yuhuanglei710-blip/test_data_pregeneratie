"""Parallel account-registration workflow without funding or betting."""

import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Union

from .enums import Platform
from .tournment_test import DEFAULT_ACCOUNT_COUNT, DEFAULT_MAX_WORKERS
from .user import DEFAULT_PASSWORD, User


class AccountBatchCancelled(RuntimeError):
    """Raised when account registration is cancelled cooperatively."""


@dataclass(frozen=True)
class RegisteredAccount:
    index: int
    output_line: str


def _register_account(
    index: int,
    count: int,
    *,
    environment: str,
    verbose: bool,
    stop_requested: Callable[[], bool],
) -> RegisteredAccount:
    if stop_requested():
        raise AccountBatchCancelled("用户已停止任务")

    account = User(environment=environment)
    account.register(platform=Platform.ios.value, verbose=verbose)
    if not account.uid or not account.token:
        raise RuntimeError("注册成功但未获取到 uid 或 token")

    print(
        f"[{index}/{count}] 注册成功："
        f"uid={account.uid}，email={account.email}，密码={DEFAULT_PASSWORD}"
    )
    return RegisteredAccount(
        index=index,
        output_line=(
            f"uid: {account.uid}\t"
            f"email: {account.email}\t"
            f"password: {DEFAULT_PASSWORD}\n"
        ),
    )


def create_accounts(
    count: int = DEFAULT_ACCOUNT_COUNT,
    output_file: Union[str, Path] = "accounts_created.txt",
    *,
    environment: str = "dev",
    verbose: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """Register accounts concurrently and export successful credentials."""
    if count <= 0:
        raise ValueError("账号数量必须大于 0")
    if max_workers <= 0:
        raise ValueError("并行账号数必须大于 0")

    output_path = Path(output_file)
    success_count = 0
    completed_count = 0
    internal_stop = threading.Event()

    def should_stop() -> bool:
        return internal_stop.is_set() or bool(stop_requested and stop_requested())

    with output_path.open("w", encoding="utf-8") as account_file:
        worker_count = min(max_workers, count)
        print(f"账号创建任务启动：账号={count}，并行账号数={worker_count}")
        executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="register",
        )
        futures: Dict[Future[RegisteredAccount], int] = {
            executor.submit(
                _register_account,
                index,
                count,
                environment=environment,
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
                except (AccountBatchCancelled, CancelledError):
                    pass
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
    print(f"账号创建结束：成功 {success_count}/{count}，输出文件：{output_path}")
    return success_count
