"""PySide6 desktop controller for the parallel test-data workflow."""

import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from base import spin
from base.account_batch import create_accounts
from base.tournment_test import (
    DEFAULT_ACCOUNT_COUNT,
    DEFAULT_MAX_WORKERS,
    INITIAL_BALANCE,
    INITIAL_SPIN_COUNT,
    create_accounts_and_bet,
)
from base.user import SUPPORTED_ENVIRONMENTS


PROJECT_ROOT = Path(__file__).resolve().parent


APP_STYLESHEET = """
QWidget {
    color: #d6d9df;
    font-family: "Segoe UI";
    font-size: 13px;
}
QWidget#root {
    background: #0e0f12;
}
QFrame#topBar {
    background: #0e0f12;
    border-bottom: 1px solid #26292f;
}
QLabel#eyebrow, QLabel#terminalMeta, QLabel#fieldHint {
    color: #6f747e;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}
QLabel#title {
    color: #f4f5f7;
    font-size: 24px;
    font-weight: 700;
}
QLabel#statusPill {
    background: #1a1d22;
    border: 1px solid #2d3138;
    border-radius: 14px;
    padding: 6px 12px;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
    font-weight: 600;
}
QFrame#settingsPanel, QFrame#terminalPanel {
    background: #17191d;
    border: 1px solid #292c33;
    border-radius: 10px;
}
QFrame#terminalPanel {
    background: #121316;
}
QTabWidget#modeTabs::pane {
    background: transparent;
    border: 0;
}
QTabWidget#modeTabs QTabBar::tab {
    min-width: 118px;
    color: #737882;
    background: transparent;
    border: 0;
    border-bottom: 2px solid #292c33;
    padding: 10px 4px;
    font-weight: 600;
}
QTabWidget#modeTabs QTabBar::tab:hover {
    color: #cdd0d6;
}
QTabWidget#modeTabs QTabBar::tab:selected {
    color: #f4f5f7;
    border-bottom-color: #f0f2f4;
}
QLabel#sectionTitle {
    color: #f1f2f4;
    font-size: 15px;
    font-weight: 650;
}
QLabel#fieldLabel {
    color: #aeb2ba;
    font-size: 12px;
}
QLineEdit, QSpinBox, QComboBox {
    min-height: 36px;
    color: #f0f1f3;
    background: #0f1013;
    border: 1px solid #30343b;
    border-radius: 7px;
    padding: 0 10px;
    selection-background-color: #4a515d;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
    border-color: #484d56;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #7b828e;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: #5f646d;
    background: #1d2025;
    border-color: #292c32;
}
QComboBox::drop-down {
    width: 28px;
    border: 0;
}
QComboBox QAbstractItemView {
    color: #e7e9ec;
    background: #17191d;
    border: 1px solid #343840;
    selection-background-color: #2c3037;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 20px;
    background: #181a1f;
    border: 0;
}
QCheckBox {
    color: #b9bdc5;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #0f1013;
    border: 1px solid #3a3e46;
    border-radius: 4px;
}
QCheckBox::indicator:checked {
    background: #7bd99d;
    border-color: #7bd99d;
}
QPushButton#modeButton {
    min-height: 34px;
    color: #777c86;
    background: #101114;
    border: 1px solid #30343b;
    border-radius: 6px;
    padding: 0 12px;
    font-weight: 600;
}
QPushButton#modeButton:hover {
    color: #d7dae0;
    border-color: #4b5059;
}
QPushButton#modeButton:checked {
    color: #111216;
    background: #f0f2f4;
    border-color: #f0f2f4;
}
QPushButton#modeButton:disabled {
    color: #555a63;
    background: #191b20;
    border-color: #292c32;
}
QPushButton {
    min-height: 36px;
    border-radius: 7px;
    padding: 0 14px;
    font-weight: 600;
}
QPushButton#primaryButton {
    color: #101114;
    background: #f0f2f4;
    border: 1px solid #f0f2f4;
}
QPushButton#primaryButton:hover {
    background: #ffffff;
    border-color: #ffffff;
}
QPushButton#primaryButton:pressed {
    background: #d9dce0;
}
QPushButton#secondaryButton, QPushButton#stopButton, QPushButton#browseButton {
    color: #c7cad0;
    background: #1b1e23;
    border: 1px solid #383c44;
}
QPushButton#secondaryButton:hover, QPushButton#stopButton:hover,
QPushButton#browseButton:hover {
    color: #ffffff;
    background: #252930;
    border-color: #555b66;
}
QPushButton:disabled {
    color: #5c616a;
    background: #1a1c20;
    border-color: #2b2e34;
}
QLabel#online {
    color: #79d59a;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
    font-weight: 700;
}
QLabel#sessionTitle {
    color: #eceef1;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 13px;
    font-weight: 700;
}
QProgressBar {
    min-height: 5px;
    max-height: 5px;
    background: #292c32;
    border: 0;
    border-radius: 2px;
    text-align: center;
}
QProgressBar::chunk {
    background: #79d59a;
    border-radius: 2px;
}
QPlainTextEdit#terminal {
    color: #cfd3da;
    background: #090a0c;
    border: 1px solid #25282e;
    border-radius: 8px;
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
    selection-background-color: #343a43;
}
QScrollBar:vertical {
    width: 9px;
    margin: 4px 2px;
    background: transparent;
}
QScrollBar::handle:vertical {
    min-height: 28px;
    background: #353941;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #4a4f59;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


class QueueWriter:
    """Forward stdout fragments to a Qt signal from any worker thread."""

    def __init__(self, emit: Callable[[str], None]):
        self.emit = emit

    def write(self, text: str) -> int:
        if text:
            self.emit(text)
        return len(text)

    def flush(self) -> None:
        return None


class WorkflowWorker(QObject):
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


class WorkflowWindow(QMainWindow):
    """Termius-inspired controller window backed by a Qt worker thread."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automation Console")
        self.resize(1220, 800)
        self.setMinimumSize(1000, 680)

        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[WorkflowWorker] = None
        self.close_after_stop = False
        self.config_widgets: list[QWidget] = []

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.setStyleSheet(APP_STYLESHEET)

        page = QVBoxLayout(root)
        page.setContentsMargins(22, 0, 22, 22)
        page.setSpacing(18)
        page.addWidget(self._build_top_bar())

        workspace = QHBoxLayout()
        workspace.setSpacing(14)
        workspace.addWidget(self._build_settings_panel())
        workspace.addWidget(self._build_terminal_panel(), 1)
        page.addLayout(workspace, 1)

        self._set_status("●  READY", "#79d59a")
        self._append_log("runner@local:~$ ready\n")

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(88)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 12, 4, 12)

        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("自动化控制台")
        title.setObjectName("title")
        eyebrow = QLabel("$ test-data / parallel-runner")
        eyebrow.setObjectName("eyebrow")
        titles.addWidget(title)
        titles.addWidget(eyebrow)
        layout.addLayout(titles)
        layout.addStretch()

        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _build_settings_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel.setFixedWidth(370)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(16)

        title = QLabel("任务配置")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.mode_tabs = QTabWidget()
        self.mode_tabs.setObjectName("modeTabs")
        self.mode_tabs.addTab(self._build_account_tab(), "创建账号")
        self.mode_tabs.addTab(self._build_tournament_tab(), "锦标赛数据")
        self.mode_tabs.currentChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_tabs, 1)

        self.mode_hint = QLabel("只注册账号并导出账号信息，不执行加钱或下注。")
        self.mode_hint.setObjectName("fieldHint")
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.start_button = QPushButton("创建账号")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._start)
        buttons.addWidget(self.start_button, 1)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        buttons.addWidget(self.stop_button, 1)
        layout.addLayout(buttons)

        self.config_widgets.append(self.mode_tabs)
        return panel

    def _build_account_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(14)
        form = self._form_layout()

        self.account_environment = QComboBox()
        self.account_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self._add_form_row(form, 0, "运行环境", self.account_environment)

        self.account_count = self._spin_box(DEFAULT_ACCOUNT_COUNT, maximum=100_000)
        self._add_form_row(form, 1, "账号数量", self.account_count)

        self.account_max_workers = self._spin_box(DEFAULT_MAX_WORKERS, maximum=100)
        (
            account_execution_mode,
            self.account_serial_button,
            self.account_parallel_button,
        ) = self._execution_mode_control(self.account_max_workers)
        self._add_form_row(form, 2, "执行方式", account_execution_mode)
        self._add_form_row(form, 3, "并行账号", self.account_max_workers)

        self.account_output_file = QLineEdit(
            str(PROJECT_ROOT / "accounts_created.txt")
        )
        account_output, self.account_browse_button = self._output_field(
            self.account_output_file
        )
        self._add_form_row(form, 4, "输出文件", account_output)
        layout.addLayout(form)

        self.account_verbose = QCheckBox("显示调试日志")
        layout.addWidget(self.account_verbose)
        layout.addStretch()

        self.config_widgets.extend(
            [
                self.account_environment,
                self.account_count,
                self.account_max_workers,
                self.account_serial_button,
                self.account_parallel_button,
                self.account_output_file,
                self.account_browse_button,
                self.account_verbose,
            ]
        )
        return page

    def _build_tournament_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(14)
        form = self._form_layout()

        self.environment = QComboBox()
        self.environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self._add_form_row(form, 0, "运行环境", self.environment)

        self.count = self._spin_box(DEFAULT_ACCOUNT_COUNT, maximum=100_000)
        self._add_form_row(form, 1, "账号数量", self.count)

        self.max_workers = self._spin_box(DEFAULT_MAX_WORKERS, maximum=100)
        (
            tournament_execution_mode,
            self.serial_button,
            self.parallel_button,
        ) = self._execution_mode_control(self.max_workers)
        self._add_form_row(form, 2, "执行方式", tournament_execution_mode)
        self._add_form_row(form, 3, "并行账号", self.max_workers)

        self.balance = self._spin_box(INITIAL_BALANCE)
        self._add_form_row(form, 4, "加钱金额", self.balance)

        self.spin_count = self._spin_box(INITIAL_SPIN_COUNT, maximum=100_000)
        self._add_form_row(form, 5, "下注次数", self.spin_count)

        self.bet_amount = self._spin_box(spin.DEFAULT_BET_CENTS)
        self._add_form_row(form, 6, "下注金额", self.bet_amount, "美分")

        self.output_file = QLineEdit(str(PROJECT_ROOT / "accounts.txt"))
        tournament_output, self.browse_button = self._output_field(self.output_file)
        self._add_form_row(form, 7, "输出文件", tournament_output)
        layout.addLayout(form)

        self.random_spins = QCheckBox("每个账号随机下注次数")
        self.random_spins.toggled.connect(self._toggle_random_inputs)
        layout.addWidget(self.random_spins)

        random_row = QHBoxLayout()
        random_row.setSpacing(8)
        min_label = QLabel("MIN")
        min_label.setObjectName("fieldHint")
        random_row.addWidget(min_label)
        self.spin_min = self._spin_box(20, maximum=100_000)
        self.spin_min.setEnabled(False)
        random_row.addWidget(self.spin_min)
        max_label = QLabel("MAX")
        max_label.setObjectName("fieldHint")
        random_row.addWidget(max_label)
        self.spin_max = self._spin_box(INITIAL_SPIN_COUNT, maximum=100_000)
        self.spin_max.setEnabled(False)
        random_row.addWidget(self.spin_max)
        layout.addLayout(random_row)

        self.verbose = QCheckBox("显示调试日志")
        layout.addWidget(self.verbose)
        layout.addStretch()

        self.config_widgets.extend(
            [
                self.environment,
                self.count,
                self.max_workers,
                self.serial_button,
                self.parallel_button,
                self.balance,
                self.spin_count,
                self.bet_amount,
                self.output_file,
                self.browse_button,
                self.random_spins,
                self.spin_min,
                self.spin_max,
                self.verbose,
            ]
        )
        return page

    @staticmethod
    def _form_layout() -> QGridLayout:
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(11)
        form.setColumnStretch(1, 1)
        return form

    def _execution_mode_control(
        self,
        max_workers: QSpinBox,
    ) -> tuple[QWidget, QPushButton, QPushButton]:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        serial = QPushButton("串行")
        serial.setObjectName("modeButton")
        serial.setCheckable(True)
        parallel = QPushButton("并行")
        parallel.setObjectName("modeButton")
        parallel.setCheckable(True)
        parallel.setChecked(True)

        group = QButtonGroup(holder)
        group.setExclusive(True)
        group.addButton(serial)
        group.addButton(parallel)
        serial.toggled.connect(lambda _checked: self._sync_execution_mode_inputs())
        parallel.toggled.connect(lambda _checked: self._sync_execution_mode_inputs())
        row.addWidget(serial, 1)
        row.addWidget(parallel, 1)
        max_workers.setEnabled(True)
        return holder, serial, parallel

    def _output_field(self, line_edit: QLineEdit) -> tuple[QWidget, QPushButton]:
        row = QHBoxLayout()
        row.setSpacing(7)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit, 1)
        browse = QPushButton("…")
        browse.setObjectName("browseButton")
        browse.setFixedWidth(42)
        browse.clicked.connect(lambda: self._browse_output(line_edit))
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        return holder, browse

    def _build_terminal_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("terminalPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(12)

        session_row = QHBoxLayout()
        self.session_title = QLabel("ACCOUNT CREATE")
        self.session_title.setObjectName("sessionTitle")
        session_row.addWidget(self.session_title)
        session_row.addStretch()
        online = QLabel("●  LOCAL")
        online.setObjectName("online")
        session_row.addWidget(online)
        session_row.addSpacing(8)
        clear = QPushButton("清空")
        clear.setObjectName("secondaryButton")
        clear.clicked.connect(self._clear_log)
        session_row.addWidget(clear)
        layout.addLayout(session_row)

        progress_row = QHBoxLayout()
        progress_label = QLabel("TASK PROGRESS")
        progress_label.setObjectName("terminalMeta")
        progress_row.addWidget(progress_label)
        progress_row.addStretch()
        self.progress_text = QLabel("0 / 0")
        self.progress_text.setObjectName("terminalMeta")
        progress_row.addWidget(self.progress_text)
        layout.addLayout(progress_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        output_label = QLabel("OUTPUT")
        output_label.setObjectName("terminalMeta")
        layout.addWidget(output_label)

        self.log = QPlainTextEdit()
        self.log.setObjectName("terminal")
        self.log.setReadOnly(True)
        self.log.setUndoRedoEnabled(False)
        self.log.document().setMaximumBlockCount(20_000)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed_font.setPointSize(10)
        self.log.setFont(fixed_font)
        layout.addWidget(self.log, 1)
        return panel

    @staticmethod
    def _spin_box(value: int, *, maximum: int = 2_000_000_000) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(1, maximum)
        widget.setValue(value)
        widget.setGroupSeparatorShown(True)
        widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        return widget

    @staticmethod
    def _add_form_row(
        layout: QGridLayout,
        row: int,
        label_text: str,
        widget: QWidget,
        suffix: str = "",
    ) -> None:
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)
        if suffix:
            hint = QLabel(suffix)
            hint.setObjectName("fieldHint")
            layout.addWidget(hint, row, 2)

    @Slot(bool)
    def _toggle_random_inputs(self, enabled: bool) -> None:
        self.spin_count.setEnabled(not enabled and not self._is_running())
        self.spin_min.setEnabled(enabled and not self._is_running())
        self.spin_max.setEnabled(enabled and not self._is_running())

    def _sync_execution_mode_inputs(self) -> None:
        if hasattr(self, "account_max_workers"):
            self.account_max_workers.setEnabled(
                not self._is_running() and self.account_parallel_button.isChecked()
            )
        if hasattr(self, "max_workers"):
            self.max_workers.setEnabled(
                not self._is_running() and self.parallel_button.isChecked()
            )

    @Slot(int)
    def _on_mode_changed(self, index: int) -> None:
        if index == 0:
            self.mode_hint.setText("只注册账号并导出账号信息，不执行加钱或下注。")
            self.start_button.setText("创建账号")
            self.session_title.setText("ACCOUNT CREATE")
        else:
            self.mode_hint.setText("注册账号、加钱并连续下注，生成锦标赛测试数据。")
            self.start_button.setText("生成锦标赛数据")
            self.session_title.setText("TOURNAMENT DATA")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_text.setText("0 / 0")

    def _browse_output(self, line_edit: QLineEdit) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "选择账号输出文件",
            line_edit.text(),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if selected:
            line_edit.setText(selected)

    def _parameters(self) -> tuple[Callable[..., int], dict, str]:
        if self.mode_tabs.currentIndex() == 0:
            output_path = Path(self.account_output_file.text()).expanduser()
            if not output_path.name:
                raise ValueError("请选择输出文件")
            return (
                create_accounts,
                {
                    "count": self.account_count.value(),
                    "max_workers": (
                        self.account_max_workers.value()
                        if self.account_parallel_button.isChecked()
                        else 1
                    ),
                    "environment": self.account_environment.currentText(),
                    "output_file": output_path,
                    "verbose": self.account_verbose.isChecked(),
                },
                "create-accounts",
            )

        output_path = Path(self.output_file.text()).expanduser()
        if not output_path.name:
            raise ValueError("请选择输出文件")

        parameters = {
            "count": self.count.value(),
            "initial_balance": self.balance.value(),
            "bet_amount": self.bet_amount.value(),
            "max_workers": self.max_workers.value() if self.parallel_button.isChecked() else 1,
            "spin_count": self.spin_count.value(),
            "spin_count_range": None,
            "environment": self.environment.currentText(),
            "output_file": output_path,
            "verbose": self.verbose.isChecked(),
        }
        if self.random_spins.isChecked():
            minimum = self.spin_min.value()
            maximum = self.spin_max.value()
            if maximum < minimum:
                raise ValueError("随机次数的最大值不能小于最小值")
            parameters["spin_count"] = maximum
            parameters["spin_count_range"] = (minimum, maximum)
        return create_accounts_and_bet, parameters, "generate-tournament-data"

    @Slot()
    def _start(self) -> None:
        try:
            workflow, parameters, command = self._parameters()
        except ValueError as error:
            QMessageBox.critical(self, "参数错误", str(error))
            return

        output_file = parameters["output_file"]
        if output_file.exists():
            answer = QMessageBox.question(
                self,
                "覆盖文件",
                f"{output_file}\n已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._set_running(True)
        self._set_status("●  RUNNING", "#79d59a")
        self.progress.setRange(0, parameters["count"])
        self.progress.setValue(0)
        self.progress_text.setText(f"0 / {parameters['count']}  ·  OK 0")
        self._append_log(f"\nrunner@local:~$ {command}\n")

        self.worker_thread = QThread(self)
        self.worker = WorkflowWorker(workflow, parameters)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.done.connect(self.worker_thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._on_thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    @Slot()
    def _stop(self) -> None:
        if self.worker:
            self.worker.request_stop()
        self.stop_button.setEnabled(False)
        self._set_status("●  STOPPING", "#d7b56d")
        self._append_log("\n[signal] stop requested; waiting for active requests\n")

    @Slot(int, int, int)
    def _on_progress(self, completed: int, total: int, successful: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(completed)
        self.progress_text.setText(f"{completed} / {total}  ·  OK {successful}")
        self._set_status(
            f"●  RUNNING  {completed}/{total}  OK {successful}",
            "#79d59a",
        )

    @Slot(int, bool)
    def _on_completed(self, successful: int, cancelled: bool) -> None:
        if cancelled:
            self._set_status(f"●  STOPPED  OK {successful}", "#d7b56d")
            self._append_log("[stopped] workflow cancelled\n")
        else:
            self._set_status(f"●  DONE  OK {successful}", "#79d59a")
            self._append_log("[done] workflow completed\n")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_status("●  FAILED", "#e27d84")
        self._append_log(f"\n[error] {message}\n")
        QMessageBox.critical(self, "任务失败", message)

    @Slot()
    def _on_thread_finished(self) -> None:
        self.worker = None
        self.worker_thread = None
        self._set_running(False)
        if self.close_after_stop:
            self.close_after_stop = False
            self.close()

    @Slot(str)
    def _append_log(self, text: str) -> None:
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    @Slot()
    def _clear_log(self) -> None:
        self.log.clear()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        for widget in self.config_widgets:
            widget.setEnabled(not running)
        if not running:
            self._toggle_random_inputs(self.random_spins.isChecked())
            self._sync_execution_mode_inputs()

    def _is_running(self) -> bool:
        return bool(self.worker_thread and self.worker_thread.isRunning())

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_running():
            answer = QMessageBox.question(
                self,
                "退出",
                "任务仍在运行。停止任务并退出？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.close_after_stop = True
            self._stop()
            event.ignore()
            return
        event.accept()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Automation Console")
    app.setStyle("Fusion")
    window = WorkflowWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
