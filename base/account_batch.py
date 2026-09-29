"""批量创建账号，不执行加钱或下注。"""

import re
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
from typing import Callable, Dict, Optional, Union

from .enums import Platform
from .database_config import DatabaseConnectionConfig
from .feature_scenario import FeatureScenario, execute_feature_scenario
from .sql_data import SqlTemplate, execute_sql_template
from .tournment_test import DEFAULT_ACCOUNT_COUNT, DEFAULT_MAX_WORKERS
from .user import DEFAULT_CHANNEL_CODE, DEFAULT_PASSWORD, User


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AccountBatchCancelled(RuntimeError):
    """账号创建被安全取消。"""


class AccountBatchCriticalError(RuntimeError):
    """绑定 SQL 或场景发生系统性错误。"""


@dataclass(frozen=True)
class RegisteredAccount:
    """一个待写入文件的注册结果。"""

    index: int
    output_line: str


def _register_account(
    index: int,
    count: int,
    *,
    environment: str,
    platform: int,
    channel_code: str,
    verbose: bool,
    stop_requested: Callable[[], bool],
    email: Optional[str] = None,
    sql_template: Optional[SqlTemplate] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    feature_scenario: Optional[FeatureScenario] = None,
    scenario_database_connection: Optional[DatabaseConnectionConfig] = None,
) -> RegisteredAccount:
    """注册一个账号并生成导出内容。"""
    if stop_requested():
        raise AccountBatchCancelled("用户已停止任务")

    account = User(email=email, environment=environment)
    account.register(
        channel_code=channel_code,
        platform=platform,
        verbose=verbose,
    )
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
                raise AccountBatchCancelled("用户已停止任务") from error
            raise AccountBatchCriticalError(
                f"绑定 SQL 执行失败：{error}"
            ) from error
        print(f"[{index}/{count}] SQL OK · {sql_template.title}")

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
                raise AccountBatchCancelled("用户已停止任务") from error
            raise AccountBatchCriticalError(
                f"功能场景执行失败：{error}"
            ) from error
        print(f"[{index}/{count}] 场景 PASS · {feature_scenario.title}")

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
    platform: int = Platform.ios.value,
    channel_code: str = DEFAULT_CHANNEL_CODE,
    verbose: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
    email: Optional[str] = None,
    sql_template: Optional[SqlTemplate] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    feature_scenario: Optional[FeatureScenario] = None,
    scenario_database_connection: Optional[DatabaseConnectionConfig] = None,
) -> int:
    """并行注册账号并导出成功结果。"""
    if count <= 0:
        raise ValueError("账号数量必须大于 0")
    if max_workers <= 0:
        raise ValueError("并行账号数必须大于 0")
    if platform not in (Platform.android.value, Platform.ios.value):
        raise ValueError("注册平台仅支持 Android 或 iOS")
    if not channel_code.strip():
        raise ValueError("Channel Code 不能为空")
    if email is not None:
        email = validate_custom_email(email)
        if count != 1:
            raise ValueError("自定义邮箱仅支持创建一个账号")

    output_path = Path(output_file)
    success_count = 0
    completed_count = 0
    failed_count = 0
    internal_stop = threading.Event()
    fatal_error: Optional[Exception] = None

    def should_stop() -> bool:
        """合并内部取消和界面停止信号。"""
        return internal_stop.is_set() or bool(stop_requested and stop_requested())

    with output_path.open("w", encoding="utf-8") as account_file:
        worker_count = min(max_workers, count)
        print(
            f"账号创建任务启动：账号={count}，并行账号数={worker_count}，"
            f"渠道源={channel_code}"
        )
        executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="register",
        )
        futures: Dict[Future[RegisteredAccount], int] = {}
        next_index = 1

        def submit_account(index: int) -> None:
            futures[
                executor.submit(
                    _register_account,
                    index,
                    count,
                    environment=environment,
                    platform=platform,
                    channel_code=channel_code,
                    verbose=verbose,
                    stop_requested=should_stop,
                    email=email,
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
                    except (AccountBatchCancelled, CancelledError):
                        processed = False
                    except AccountBatchCriticalError as error:
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
            f"账号创建已停止：成功 {success_count}，失败 {failed_count}，"
            f"实际完成 {completed_count}/{count}，输出文件：{output_path}"
        )
        return success_count
    if fatal_error is not None:
        raise RuntimeError(
            f"账号创建因关键业务错误终止：{fatal_error}；"
            f"成功 {success_count}，失败 {failed_count}，"
            f"实际完成 {completed_count}/{count}"
        ) from fatal_error
    if failed_count:
        raise RuntimeError(
            f"账号创建部分失败：成功 {success_count}，失败 {failed_count}，"
            f"实际完成 {completed_count}/{count}，输出文件：{output_path}"
        )
    print(
        f"账号创建结束：成功 {success_count}，失败 {failed_count}，"
        f"实际完成 {completed_count}/{count}，输出文件：{output_path}"
    )
    return success_count


def validate_custom_email(email: str) -> str:
    """清理并校验定制账号使用的邮箱。"""
    normalized_email = email.strip()
    if not normalized_email:
        raise ValueError("自定义邮箱不能为空")
    if not _EMAIL_PATTERN.fullmatch(normalized_email):
        raise ValueError("自定义邮箱格式不正确")
    return normalized_email


def create_custom_account(
    email: str,
    output_file: Union[str, Path] = "accounts_created.txt",
    *,
    environment: str = "dev",
    platform: int = Platform.ios.value,
    channel_code: str = DEFAULT_CHANNEL_CODE,
    verbose: bool = False,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
    sql_template: Optional[SqlTemplate] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    feature_scenario: Optional[FeatureScenario] = None,
    scenario_database_connection: Optional[DatabaseConnectionConfig] = None,
) -> int:
    """使用指定邮箱创建并导出一个账号。"""
    email = validate_custom_email(email)
    sql_parameters = {}
    if sql_template is not None:
        sql_parameters = {
            "sql_template": sql_template,
            "database_connection": database_connection,
        }
    scenario_parameters = {}
    if feature_scenario is not None:
        scenario_parameters = {
            "feature_scenario": feature_scenario,
            "scenario_database_connection": scenario_database_connection,
        }
    return create_accounts(
        count=1,
        output_file=output_file,
        environment=environment,
        platform=platform,
        channel_code=channel_code,
        verbose=verbose,
        max_workers=1,
        stop_requested=stop_requested,
        progress_callback=progress_callback,
        email=email,
        **sql_parameters,
        **scenario_parameters,
    )
