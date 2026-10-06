"""通过 ADB 持续读取 Android 设备与应用的 Logcat 日志。"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from base.apk_manager import (
    AdbCommandError,
    _device_arguments,
    _run_adb,
    adb_executable,
)


LOGCAT_LEVELS = frozenset({"V", "D", "I", "W", "E", "F"})
_PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_END_OF_STREAM = object()


@dataclass(frozen=True)
class LogcatCaptureConfig:
    """一次 Android 日志抓取的参数。"""

    serial: str
    package_name: str = ""
    minimum_level: str = "I"
    keyword: str = ""
    clear_before_start: bool = False
    output_path: str = ""

    def validated(self) -> "LogcatCaptureConfig":
        serial = self.serial.strip()
        package_name = self.package_name.strip()
        minimum_level = self.minimum_level.strip().upper()
        if not serial:
            raise ValueError("请先连接并选择 Android 设备")
        if package_name and not _PACKAGE_NAME_PATTERN.fullmatch(package_name):
            raise ValueError("应用包名格式无效，例如 com.example.app")
        if minimum_level not in LOGCAT_LEVELS:
            raise ValueError("日志级别必须是 V、D、I、W、E 或 F")
        return LogcatCaptureConfig(
            serial=serial,
            package_name=package_name,
            minimum_level=minimum_level,
            keyword=self.keyword.strip(),
            clear_before_start=bool(self.clear_before_start),
            output_path=self.output_path.strip(),
        )


def list_installed_packages(serial: str) -> list[str]:
    """列出设备上用户安装的应用包名。"""
    output = _run_adb(
        _device_arguments(serial, ["shell", "pm", "list", "packages", "-3"]),
        timeout=30,
    )
    packages: set[str] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("package:"):
            package_name = line.removeprefix("package:").strip()
            if _PACKAGE_NAME_PATTERN.fullmatch(package_name):
                packages.add(package_name)
    return sorted(packages, key=str.casefold)


def resolve_application_pid(serial: str, package_name: str) -> int:
    """查找应用当前主进程 PID；应用未运行时返回可读错误。"""
    package = package_name.strip()
    if not _PACKAGE_NAME_PATTERN.fullmatch(package):
        raise ValueError("应用包名格式无效，例如 com.example.app")
    try:
        output = _run_adb(
            _device_arguments(serial, ["shell", "pidof", package]),
            timeout=15,
        )
    except AdbCommandError as error:
        if error.output.strip():
            raise
        raise ValueError(f"应用 {package} 未运行，请先在手机上打开应用") from error
    pid_text = output.strip().split(maxsplit=1)[0] if output.strip() else ""
    if not pid_text.isdigit() or int(pid_text) <= 0:
        raise ValueError(f"应用 {package} 未运行，请先在手机上打开应用")
    return int(pid_text)


def clear_logcat(serial: str) -> None:
    """清空所选设备的 Logcat 环形缓冲区。"""
    _run_adb(_device_arguments(serial, ["logcat", "-c"]), timeout=15)


def build_logcat_arguments(
    serial: str,
    minimum_level: str,
    *,
    pid: Optional[int] = None,
) -> list[str]:
    """构造不经过 shell 拼接的 Logcat 参数，避免设备/包名注入。"""
    cleaned_serial = serial.strip()
    level = minimum_level.strip().upper()
    if not cleaned_serial:
        raise ValueError("请先连接并选择 Android 设备")
    if level not in LOGCAT_LEVELS:
        raise ValueError("日志级别必须是 V、D、I、W、E 或 F")
    arguments = _device_arguments(
        cleaned_serial,
        ["logcat", "-v", "threadtime"],
    )
    if pid is not None:
        if pid <= 0:
            raise ValueError("应用进程 PID 无效")
        arguments.append(f"--pid={pid}")
    arguments.append(f"*:{level}")
    return arguments


class AndroidLogCapture:
    """运行一个可从其他线程安全停止的 ADB Logcat 子进程。"""

    def __init__(
        self,
        config: LogcatCaptureConfig,
        emit_output: Callable[[str], None],
        *,
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        stop_timeout: float = 3.0,
    ) -> None:
        self.config = config.validated()
        self.emit_output = emit_output
        self.popen_factory = popen_factory
        self.stop_timeout = max(0.1, float(stop_timeout))
        self.stop_event = threading.Event()
        self.cancel_requested = threading.Event()
        self._process_lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None

    def request_stop(self) -> None:
        """请求停止，并唤醒可能正阻塞在标准输出读取上的工作线程。"""
        self.cancel_requested.set()
        self.stop_event.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def run(self) -> None:
        """持续读取日志，直到请求停止或 ADB 进程退出。"""
        config = self.config
        if self.stop_event.is_set():
            return
        pid = (
            resolve_application_pid(config.serial, config.package_name)
            if config.package_name
            else None
        )
        if self.stop_event.is_set():
            return
        executable = adb_executable()
        command = [
            executable,
            *build_logcat_arguments(
                config.serial,
                config.minimum_level,
                pid=pid,
            ),
        ]
        output_stream = None
        if config.output_path:
            output_stream = Path(config.output_path).expanduser().open(
                "w",
                encoding="utf-8",
                newline="",
            )
        if self.stop_event.is_set():
            if output_stream is not None:
                output_stream.close()
            return
        try:
            if config.clear_before_start:
                clear_logcat(config.serial)
        except Exception:
            if output_stream is not None:
                output_stream.close()
            raise
        if self.stop_event.is_set():
            if output_stream is not None:
                output_stream.close()
            return
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = self.popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except OSError as error:
            if output_stream is not None:
                output_stream.close()
            raise AdbCommandError(f"无法启动 Logcat：{error}") from error
        except Exception:
            if output_stream is not None:
                output_stream.close()
            raise

        with self._process_lock:
            self._process = process
        if self.stop_event.is_set():
            self.request_stop()

        lines: queue.Queue[object] = queue.Queue(maxsize=10_000)

        def enqueue_output(value: object) -> bool:
            while True:
                try:
                    lines.put(value, timeout=0.1)
                    return True
                except queue.Full:
                    if self.stop_event.is_set():
                        return False

        def read_output() -> None:
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        if not enqueue_output(line):
                            break
            finally:
                enqueue_output(_END_OF_STREAM)

        reader = threading.Thread(
            target=read_output,
            name="adb-logcat-reader",
            daemon=True,
        )
        keyword = config.keyword.casefold()
        reached_end = False
        stop_deadline: Optional[float] = None
        visible_pending: list[str] = []
        last_display_emit = time.monotonic()
        try:
            reader.start()
            while not reached_end:
                if self.stop_event.is_set():
                    if stop_deadline is None:
                        stop_deadline = time.monotonic() + self.stop_timeout
                        self.request_stop()
                    elif time.monotonic() >= stop_deadline:
                        if process.poll() is None:
                            try:
                                process.kill()
                            except OSError:
                                pass
                        break
                try:
                    item = lines.get(timeout=0.1)
                except queue.Empty:
                    if (
                        visible_pending
                        and time.monotonic() - last_display_emit >= 0.05
                    ):
                        self.emit_output("".join(visible_pending))
                        visible_pending.clear()
                        last_display_emit = time.monotonic()
                    if process.poll() is not None and not reader.is_alive():
                        break
                    continue

                raw_batch: list[str] = []
                visible_batch: list[str] = []
                for _ in range(500):
                    if item is _END_OF_STREAM:
                        reached_end = True
                        break
                    line = str(item)
                    raw_batch.append(line)
                    if not keyword or keyword in line.casefold():
                        visible_batch.append(line)
                    try:
                        item = lines.get_nowait()
                    except queue.Empty:
                        break
                if output_stream is not None and raw_batch:
                    output_stream.write("".join(raw_batch))
                    output_stream.flush()
                visible_pending.extend(visible_batch)
                if (
                    visible_pending
                    and (
                        reached_end
                        or time.monotonic() - last_display_emit >= 0.05
                    )
                ):
                    self.emit_output("".join(visible_pending))
                    visible_pending.clear()
                    last_display_emit = time.monotonic()
            if visible_pending:
                self.emit_output("".join(visible_pending))
        except Exception:
            self.stop_event.set()
            raise
        finally:
            try:
                if output_stream is not None:
                    output_stream.close()
            finally:
                return_code = None
                try:
                    return_code = process.poll()
                    if return_code is None:
                        try:
                            process.terminate()
                            return_code = process.wait(timeout=self.stop_timeout)
                        except (OSError, subprocess.TimeoutExpired):
                            try:
                                process.kill()
                            except OSError:
                                pass
                            try:
                                return_code = process.wait(
                                    timeout=self.stop_timeout
                                )
                            except (OSError, subprocess.TimeoutExpired):
                                return_code = process.poll()
                finally:
                    with self._process_lock:
                        self._process = None

        if return_code not in {0, None} and not self.cancel_requested.is_set():
            raise AdbCommandError(f"Logcat 异常退出（{return_code}）")
