"""主窗口使用的后台任务对象。

线程对象只执行耗时工作并发射信号；所有界面更新仍由主线程处理。
"""

import threading
from contextlib import redirect_stderr, redirect_stdout
from typing import Callable, Dict

from PySide6.QtCore import QObject, Signal, Slot

from base.android_log import AndroidLogCapture, LogcatCaptureConfig
from base.channel_source import fetch_channel_sources, save_channel_sources
from base.database_config import DatabaseConnectionConfig, test_database_connection

class QueueWriter:
    """把工作线程的标准输出转发给 Qt 信号。"""

    def __init__(self, emit: Callable[[str], None]):
        self.emit = emit
        self._lock = threading.Lock()
        self._buffers: Dict[int, str] = {}

    def write(self, text: str) -> int:
        if not text:
            return 0
        thread_id = threading.get_ident()
        with self._lock:
            buffered = self._buffers.get(thread_id, "") + text
            while "\n" in buffered:
                line, buffered = buffered.split("\n", 1)
                self.emit(f"{line}\n")
            if buffered:
                self._buffers[thread_id] = buffered
            else:
                self._buffers.pop(thread_id, None)
        return len(text)

    def flush(self) -> None:
        with self._lock:
            for text in self._buffers.values():
                if text:
                    self.emit(text)
            self._buffers.clear()


class WorkflowWorker(QObject):
    """在 Qt 工作线程中执行账号任务。"""

    log = Signal(str)
    progress = Signal(int, int, int)
    completed = Signal(int, bool)
    failed = Signal(str)
    done = Signal()

    def __init__(self, workflow: Callable[..., int], parameters: dict):
        super().__init__()
        self.workflow = workflow
        self.parameters = parameters
        self.stop_event = threading.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    @Slot()
    def run(self) -> None:
        """执行任务并发送日志、进度和结果。"""
        writer = QueueWriter(self.log.emit)
        try:
            with redirect_stdout(writer), redirect_stderr(writer):
                success_count = self.workflow(
                    **self.parameters,
                    stop_requested=self.stop_event.is_set,
                    progress_callback=self.progress.emit,
                )
            self.completed.emit(success_count, self.stop_event.is_set())
        except Exception as error:
            self.failed.emit(f"任务异常：{error}")
        finally:
            self.done.emit()


class ActionWorker(QObject):
    """执行一个有返回值的动作，并把结果或异常转成 Qt 信号。"""

    succeeded = Signal(object)
    failed = Signal(str)
    done = Signal()

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self.action = action

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self.action())
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.done.emit()


class DatabaseTestWorker(ActionWorker):
    """在线程中测试数据库连接，避免阻塞界面。"""

    def __init__(self, connection: DatabaseConnectionConfig):
        super().__init__(lambda: test_database_connection(connection))


class ChannelSourceUpdateWorker(QObject):
    """在后台从日志库更新账号渠道参数缓存。"""

    succeeded = Signal(str, object)
    failed = Signal(str, str)
    done = Signal()

    def __init__(
        self,
        environment: str,
        connection: DatabaseConnectionConfig,
    ) -> None:
        super().__init__()
        self.environment = environment
        self.connection = connection

    @Slot()
    def run(self) -> None:
        try:
            sources = fetch_channel_sources(self.environment, self.connection)
            saved_sources = save_channel_sources(self.environment, sources)
            self.succeeded.emit(self.environment, saved_sources)
        except Exception as error:
            self.failed.emit(self.environment, str(error))
        finally:
            self.done.emit()


class ApkActionWorker(ActionWorker):
    """兼容旧名称：所有一次性后台动作都使用同一实现。"""


class AndroidLogWorker(QObject):
    """在独立线程中持续转发 ADB Logcat 输出。"""

    output = Signal(str)
    failed = Signal(str)
    done = Signal()

    def __init__(self, config: LogcatCaptureConfig) -> None:
        super().__init__()
        self.capture = AndroidLogCapture(config, self.output.emit)

    def request_stop(self) -> None:
        self.capture.request_stop()

    @Slot()
    def run(self) -> None:
        try:
            self.capture.run()
        except Exception as error:
            if not self.capture.cancel_requested.is_set():
                self.failed.emit(str(error))
        finally:
            self.done.emit()


# 数据库连接弹窗
