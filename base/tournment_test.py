"""批量创建账号、加钱并执行初始下注。"""

import random
import sys
import threading
from concurrent.futures import (
    FIRST_COMPLETED,
    CancelledError,
    Future,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

try:  # Support ``python -m base.tournment_test``.
    from . import add_money, spin
    from .database_config import DatabaseConnectionConfig
    from .enums import Platform
    from .feature_scenario import FeatureScenario, execute_feature_scenario
    from .fund_and_spin import (
        DEFAULT_SPIN_WORKERS,
        INITIAL_BALANCE,
        INITIAL_SPIN_COUNT,
        FundingWorkflowCancelled,
        SpinWorkflowError,
        fund_and_spin,
        place_spins,
    )
    from .sql_data import SqlTemplate, execute_sql_template
    from .user import DEFAULT_CHANNEL_CODE, DEFAULT_PASSWORD, User
except ImportError:  # Support ``python base/tournment_test.py``.
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import add_money
    import spin
    from database_config import DatabaseConnectionConfig
    from enums import Platform
    from feature_scenario import FeatureScenario, execute_feature_scenario
    from fund_and_spin import (
        DEFAULT_SPIN_WORKERS,
        INITIAL_BALANCE,
        INITIAL_SPIN_COUNT,
        FundingWorkflowCancelled,
        SpinWorkflowError,
        fund_and_spin,
        place_spins,
    )
    from sql_data import SqlTemplate, execute_sql_template
    from user import DEFAULT_CHANNEL_CODE, DEFAULT_PASSWORD, User


DEFAULT_ACCOUNT_COUNT = 30
DEFAULT_MAX_WORKERS = 5
BatchCancelled = FundingWorkflowCancelled


class BatchCriticalError(RuntimeError):
    """数据库、场景等系统性错误，需要停止整个批量任务。"""


@dataclass(frozen=True)
class AccountResult:
    """返回给调度线程的成功账号数据。"""

    index: int
    output_line: str


def _resolve_spin_count(
    fixed_count: int,
    spin_count_range: Optional[Tuple[int, int]],
) -> int:
    """为单个账号确定固定或随机下注次数。"""
    if spin_count_range is None:
        if fixed_count <= 0:
            raise ValueError("下注次数必须大于 0")
        return fixed_count

    minimum, maximum = spin_count_range
    if minimum <= 0 or maximum < minimum:
        raise ValueError("随机下注次数范围无效")
    return random.randint(minimum, maximum)


def _print_account(account: User, index: int, count: int) -> None:
    """打印简短的注册成功信息。"""
    print(
        f"[{index}/{count}] 注册成功："
        f"uid={account.uid}，email={account.email}，密码={DEFAULT_PASSWORD}"
    )


_place_initial_spins = place_spins


def _create_account_and_bet(
    index: int,
    count: int,
    *,
    environment: str,
    platform: int,
    channel_code: str,
    admin_base_url: str,
    initial_balance: int,
    spin_count: int,
    spin_count_range: Optional[Tuple[int, int]],
    bet_amount: int,
    spin_workers: int = 1,
    verbose: bool,
    stop_requested: Callable[[], bool],
    sql_template: Optional[SqlTemplate] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    feature_scenario: Optional[FeatureScenario] = None,
    scenario_database_connection: Optional[DatabaseConnectionConfig] = None,
) -> AccountResult:
    """执行单个账号的注册、加钱和初始下注流程。"""
    if stop_requested():
        raise BatchCancelled("用户已停止任务")

    account_spin_count = _resolve_spin_count(spin_count, spin_count_range)
    if spin_count_range is not None:
        print(
            f"[{index}/{count}] 随机下注次数：{account_spin_count} "
            f"（范围 {spin_count_range[0]}-{spin_count_range[1]}）"
        )

    account = User(environment=environment)
    account.register(
        channel_code=channel_code,
        platform=platform,
        verbose=verbose,
    )
    _print_account(account, index, count)

    if not account.uid or not account.token:
        raise RuntimeError("注册成功但未获取到 uid 或 token")

    if sql_template is not None:
        if database_connection is None:
            raise ValueError("绑定 SQL 时必须配置当前环境数据库")
        try:
            execute_sql_template(
                sql_template,
                account.uid,
                database_connection,
            )
        except Exception as error:
            if stop_requested():
                raise BatchCancelled("用户已停止任务") from error
            raise BatchCriticalError(f"绑定 SQL 执行失败：{error}") from error
        print(f"[{index}/{count}] SQL OK · {sql_template.title}")

    registered_user_id = int(account.uid)

    def refresh_user_token() -> str:
        """后台加钱会使旧 token 失效，下注前必须重新登录。"""
        account.login(platform=platform)
        if account.uid != registered_user_id:
            raise RuntimeError(
                f"重新登录返回 UID {account.uid}，与目标 UID "
                f"{registered_user_id} 不一致"
            )
        if not account.token:
            raise RuntimeError("重新登录成功但未获取到用户 Token")
        return account.token

    fund_and_spin(
        account.uid,
        account.token,
        environment=environment,
        amount=initial_balance,
        spin_count=account_spin_count,
        spin_workers=spin_workers,
        bet_amount=bet_amount,
        verbose=verbose,
        stop_requested=stop_requested,
        admin_base_url=admin_base_url,
        refresh_user_token=refresh_user_token,
        spin_runner=_place_initial_spins,
        log_prefix=f"[{index}/{count}] ",
    )

    if feature_scenario is not None:
        try:
            execute_feature_scenario(
                feature_scenario,
                environment=environment,
                runtime_parameters={
                    "userid": account.uid,
                    "token": account.token,
                    "email": account.email,
                    "platform": platform,
                    "channel_code": channel_code,
                },
                database_connection=scenario_database_connection,
                stop_requested=stop_requested,
            )
        except Exception as error:
            if stop_requested():
                raise BatchCancelled("用户已停止任务") from error
            raise BatchCriticalError(f"功能场景执行失败：{error}") from error
        print(f"[{index}/{count}] 场景 PASS · {feature_scenario.title}")

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
    platform: int = Platform.ios.value,
    channel_code: str = DEFAULT_CHANNEL_CODE,
    verbose: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    spin_workers: int = DEFAULT_SPIN_WORKERS,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
    sql_template: Optional[SqlTemplate] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    feature_scenario: Optional[FeatureScenario] = None,
    scenario_database_connection: Optional[DatabaseConnectionConfig] = None,
) -> int:
    """按账号并发和下注并发配置批量生成测试数据。"""
    if count <= 0:
        raise ValueError("账号数量必须大于 0")
    if max_workers <= 0:
        raise ValueError("并行账号数必须大于 0")
    if spin_workers <= 0:
        raise ValueError("下注并发数必须大于 0")
    if platform not in (Platform.android.value, Platform.ios.value):
        raise ValueError("注册平台仅支持 Android 或 iOS")
    if not channel_code.strip():
        raise ValueError("Channel Code 不能为空")

    output_path = Path(output_file)
    success_count = 0
    completed_count = 0
    failed_count = 0
    admin_base_url = add_money.base_url_for_environment(environment)
    internal_stop = threading.Event()
    fatal_error: Optional[Exception] = None

    def should_stop() -> bool:
        """合并流程错误和界面停止信号。"""
        return internal_stop.is_set() or bool(stop_requested and stop_requested())

    with output_path.open("w", encoding="utf-8") as account_file:
        worker_count = min(max_workers, count)
        print(f"批量任务启动：账号={count}，并行账号数={worker_count}")
        executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="account",
        )
        futures: Dict[Future[AccountResult], int] = {}
        next_index = 1

        def submit_account(index: int) -> None:
            futures[
                executor.submit(
                    _create_account_and_bet,
                    index,
                    count,
                    environment=environment,
                    platform=platform,
                    channel_code=channel_code,
                    admin_base_url=admin_base_url,
                    initial_balance=initial_balance,
                    spin_count=spin_count,
                    spin_count_range=spin_count_range,
                    bet_amount=bet_amount,
                    spin_workers=spin_workers,
                    verbose=verbose,
                    stop_requested=should_stop,
                    sql_template=sql_template,
                    database_connection=database_connection,
                    feature_scenario=feature_scenario,
                    scenario_database_connection=scenario_database_connection,
                )
            ] = index

        while next_index <= count and len(futures) < worker_count:
            submit_account(next_index)
            next_index += 1

        try:
            while futures:
                done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    index = futures.pop(future)
                    processed = True
                    try:
                        result = future.result()
                        account_file.write(result.output_line)
                        account_file.flush()
                        success_count += 1
                    except (BatchCancelled, CancelledError):
                        processed = False
                    except (SpinWorkflowError, BatchCriticalError) as error:
                        failed_count += 1
                        first_fatal = fatal_error is None
                        fatal_error = fatal_error or error
                        print(f"[{index}/{count}] 创建账号失败: {error}")
                        if first_fatal:
                            print("检测到关键业务错误，正在停止剩余批量任务")
                        internal_stop.set()
                    except Exception as error:
                        failed_count += 1
                        print(f"[{index}/{count}] 创建账号失败: {error}")
                    finally:
                        if processed:
                            completed_count += 1
                            if progress_callback:
                                progress_callback(
                                    completed_count,
                                    count,
                                    success_count,
                                )

                if should_stop():
                    internal_stop.set()
                    for pending_future in tuple(futures):
                        pending_future.cancel()
                    continue

                while next_index <= count and len(futures) < worker_count:
                    submit_account(next_index)
                    next_index += 1
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    if stop_requested and stop_requested():
        print(
            f"批量任务已停止：成功 {success_count}，失败 {failed_count}，"
            f"实际完成 {completed_count}/{count}，输出文件：{output_path}"
        )
        return success_count
    if fatal_error is not None:
        raise RuntimeError(
            f"批量任务因关键业务错误终止：{fatal_error}；"
            f"成功 {success_count}，失败 {failed_count}，"
            f"实际完成 {completed_count}/{count}"
        ) from fatal_error
    if failed_count:
        raise RuntimeError(
            f"批量任务部分失败：成功 {success_count}，失败 {failed_count}，"
            f"实际完成 {completed_count}/{count}，输出文件：{output_path}"
        )

    print(
        f"批量任务结束：成功 {success_count}，失败 {failed_count}，"
        f"实际完成 {completed_count}/{count}，输出文件：{output_path}"
    )
    return success_count


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    create_accounts_and_bet(
        count=DEFAULT_ACCOUNT_COUNT,
        output_file=project_root / "accounts.txt",
    )
