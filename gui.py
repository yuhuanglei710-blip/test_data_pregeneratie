"""自动化测试数据桌面控制台。"""

import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from base import spin
from base.account_batch import create_accounts
from base.app_config import load_channel_code_config, save_channel_codes
from base.database_config import (
    DatabaseConnectionConfig,
    SshPrivateKey,
    import_ssh_private_key,
    is_database_connection_configured,
    load_database_connections,
    load_ssh_private_keys,
    remove_ssh_private_key,
    save_database_connection,
    test_database_connection,
    validate_database_connection,
)
from base.enums import Platform
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
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QWidget#root, QFrame#topBar { background: #0e0f12; }
QFrame#topBar { border-bottom: 1px solid #26292f; }

QLabel#title { color: #f4f5f7; font-size: 24px; font-weight: 700; }
QLabel#sectionTitle { color: #f1f2f4; font-size: 15px; font-weight: 650; }
QLabel#fieldLabel { color: #aeb2ba; font-size: 12px; }
QLabel#eyebrow, QLabel#terminalMeta, QLabel#fieldHint,
QLabel#navigationMeta {
    color: #6f747e;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}
QLabel#navigationBrand, QLabel#sessionTitle {
    color: #f4f5f7;
    font-family: "Cascadia Mono", "Consolas";
    font-weight: 700;
}
QLabel#navigationBrand { font-size: 15px; }
QLabel#sessionTitle { font-size: 13px; }
QLabel#online { color: #79d59a; font-weight: 700; }
QLabel#statusPill, QLabel#connectionStatus {
    background: #1a1d22;
    border: 1px solid #30343b;
    border-radius: 7px;
    padding: 8px 12px;
}
QLabel#statusPill {
    border-radius: 14px;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
    font-weight: 600;
}

QFrame#settingsPanel, QFrame#terminalPanel, QFrame#navigation,
QFrame#configCard {
    background: #17191d;
    border: 1px solid #292c33;
    border-radius: 10px;
}
QFrame#terminalPanel, QFrame#configCard { background: #121418; }
QFrame#navigation { background: #15171b; }

QPushButton {
    min-height: 36px;
    border-radius: 7px;
    padding: 0 14px;
    font-weight: 600;
}
QPushButton#navigationButton {
    min-height: 42px;
    color: #888d97;
    background: transparent;
    border: 0;
    padding: 0 14px;
    text-align: left;
}
QPushButton#navigationButton:hover, QPushButton#navigationButton:checked {
    color: #fff;
    background: #2a2e35;
}
QPushButton#primaryButton, QPushButton#modeButton:checked {
    color: #101114;
    background: #f0f2f4;
    border: 1px solid #f0f2f4;
}
QPushButton#primaryButton:hover { background: #fff; border-color: #fff; }
QPushButton#secondaryButton, QPushButton#stopButton,
QPushButton#browseButton, QPushButton#modeButton {
    color: #c7cad0;
    background: #1b1e23;
    border: 1px solid #383c44;
}
QPushButton#modeButton { color: #777c86; background: #101114; }
QPushButton#secondaryButton:hover, QPushButton#stopButton:hover,
QPushButton#browseButton:hover, QPushButton#modeButton:hover {
    color: #fff;
    background: #252930;
    border-color: #555b66;
}
QPushButton:disabled, QPushButton#navigationButton:disabled {
    color: #555a63;
    background: #191b20;
    border-color: #292c32;
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
QLineEdit:hover, QSpinBox:hover, QComboBox:hover { border-color: #484d56; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #7b828e; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: #5f646d;
    background: #1d2025;
}
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button {
    width: 24px;
    background: #181a1f;
    border: 0;
}
QComboBox QAbstractItemView {
    color: #e7e9ec;
    background: #17191d;
    border: 1px solid #343840;
    selection-background-color: #2c3037;
}

QListWidget#channelCodeList, QPlainTextEdit#terminal {
    color: #d7dae0;
    background: #090a0c;
    border: 1px solid #30343b;
    border-radius: 7px;
    padding: 6px;
}
QListWidget#channelCodeList::item { min-height: 32px; padding: 4px 8px; }
QListWidget#channelCodeList::item:selected { color: #fff; background: #30353d; }
QPlainTextEdit#terminal {
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
}

QCheckBox { color: #b9bdc5; spacing: 8px; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #0f1013;
    border: 1px solid #3a3e46;
    border-radius: 4px;
}
QCheckBox::indicator:checked { background: #7bd99d; border-color: #7bd99d; }

QProgressBar {
    min-height: 5px;
    max-height: 5px;
    background: #292c32;
    border: 0;
    border-radius: 2px;
}
QProgressBar::chunk { background: #79d59a; border-radius: 2px; }

QScrollArea#settingsScroll, QWidget#settingsPage { background: transparent; border: 0; }
QScrollBar:vertical { width: 9px; margin: 4px 2px; background: transparent; }
QScrollBar::handle:vertical {
    min-height: 28px;
    background: #353941;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #4a4f59; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# 后台线程与输出转发
class QueueWriter:
    """把工作线程的标准输出转发给 Qt 信号。"""

    def __init__(self, emit: Callable[[str], None]):
        self.emit = emit

    def write(self, text: str) -> int:
        if text:
            self.emit(text)
        return len(text)

    def flush(self) -> None:
        return None


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


class DatabaseTestWorker(QObject):
    """在线程中测试数据库连接，避免阻塞界面。"""

    succeeded = Signal(str)
    failed = Signal(str)
    done = Signal()

    def __init__(self, connection: DatabaseConnectionConfig):
        super().__init__()
        self.connection = connection

    @Slot()
    def run(self) -> None:
        """测试连接并发送简短结果。"""
        try:
            self.succeeded.emit(test_database_connection(self.connection))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.done.emit()


# 数据库连接弹窗
class DatabaseConnectionDialog(QDialog):
    """编辑单个环境的 SSH 数据库连接。"""

    def __init__(
        self,
        environment: str,
        connection: DatabaseConnectionConfig,
        private_keys: Dict[str, SshPrivateKey],
        parent: QWidget,
    ):
        super().__init__(parent)
        self.environment = environment
        self.saved_connection: Optional[DatabaseConnectionConfig] = None
        self.test_thread: Optional[QThread] = None
        self.test_worker: Optional[DatabaseTestWorker] = None
        self.setWindowTitle(f"数据库连接 · {environment}")
        self.setModal(True)
        self.resize(640, 650)
        self.setMinimumSize(560, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel(f"{environment} · SSH 数据库连接")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        description = QLabel(
            "SSH 仅使用导入的私钥文件；不使用 SSH 密码、Agent 或自动密钥搜索。"
        )
        description.setObjectName("fieldHint")
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(11)
        form.setColumnStretch(1, 1)

        self.ssh_host = QLineEdit(connection.ssh_host)
        self.ssh_host.setPlaceholderText("SSH 跳板机地址")
        self._add_row(form, 0, "SSH 主机", self.ssh_host)

        self.ssh_port = self._port_spin(connection.ssh_port)
        self._add_row(form, 1, "SSH 端口", self.ssh_port)

        self.ssh_username = QLineEdit(connection.ssh_username)
        self.ssh_username.setPlaceholderText("SSH 用户名")
        self._add_row(form, 2, "SSH 用户", self.ssh_username)

        self.ssh_private_key = QComboBox()
        for key in private_keys.values():
            self.ssh_private_key.addItem(key.name, key.key_id)
        if self.ssh_private_key.count() == 0:
            self.ssh_private_key.addItem("请先在参数配置中导入私钥", None)
            self.ssh_private_key.setEnabled(False)
        selected_key = self.ssh_private_key.findData(
            connection.ssh_private_key_id
        )
        if selected_key >= 0:
            self.ssh_private_key.setCurrentIndex(selected_key)
        self._add_row(form, 3, "SSH 私钥", self.ssh_private_key)

        self.database_host = QLineEdit(connection.database_host)
        self.database_host.setPlaceholderText("SSH 服务器可访问的数据库地址")
        self._add_row(form, 4, "数据库主机", self.database_host)

        self.database_port = self._port_spin(connection.database_port)
        self._add_row(form, 5, "数据库端口", self.database_port)

        self.database_name = QLineEdit(connection.database_name)
        self._add_row(form, 6, "数据库名称", self.database_name)

        self.database_username = QLineEdit(connection.database_username)
        self._add_row(form, 7, "数据库用户", self.database_username)

        self.database_password = QLineEdit(connection.database_password)
        self.database_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_row(form, 8, "数据库密码", self.database_password)
        layout.addLayout(form)

        self.connection_status = QLabel("可先测试连接，确认无误后保存。")
        self.connection_status.setObjectName("connectionStatus")
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)
        layout.addStretch()

        buttons = QHBoxLayout()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        self.test_button = QPushButton("测试连接")
        self.test_button.setObjectName("secondaryButton")
        self.test_button.clicked.connect(self._test_connection)
        buttons.addWidget(self.test_button)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self.editable_widgets = [
            self.ssh_host,
            self.ssh_port,
            self.ssh_username,
            self.ssh_private_key,
            self.database_host,
            self.database_port,
            self.database_name,
            self.database_username,
            self.database_password,
            self.cancel_button,
            self.test_button,
            self.save_button,
        ]

    @staticmethod
    def _port_spin(value: int) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(1, 65535)
        widget.setValue(value)
        widget.setGroupSeparatorShown(True)
        widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        return widget

    @staticmethod
    def _add_row(
        layout: QGridLayout,
        row: int,
        label_text: str,
        widget: QWidget,
    ) -> None:
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        label.setFixedWidth(96)
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)

    def connection(self) -> DatabaseConnectionConfig:
        """把当前表单整理为连接配置。"""
        selected_key_id = self.ssh_private_key.currentData()
        return DatabaseConnectionConfig(
            ssh_host=self.ssh_host.text().strip(),
            ssh_port=self.ssh_port.value(),
            ssh_username=self.ssh_username.text().strip(),
            ssh_private_key_id=selected_key_id or "",
            database_host=self.database_host.text().strip(),
            database_port=self.database_port.value(),
            database_name=self.database_name.text().strip(),
            database_username=self.database_username.text().strip(),
            database_password=self.database_password.text(),
        )

    @Slot()
    def _save(self) -> None:
        """校验并保存当前环境连接。"""
        connection = self.connection()
        try:
            self.saved_connection = save_database_connection(
                self.environment,
                connection,
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.accept()

    @Slot()
    def _test_connection(self) -> None:
        """异步测试当前表单中的连接。"""
        if self.test_thread and self.test_thread.isRunning():
            return
        connection = self.connection()
        try:
            validate_database_connection(connection)
        except ValueError as error:
            QMessageBox.critical(self, "参数错误", str(error))
            return

        self._set_testing(True)
        self.connection_status.setText("正在通过 SSH 私钥建立连接…")
        self.test_thread = QThread(self)
        self.test_worker = DatabaseTestWorker(connection)
        self.test_worker.moveToThread(self.test_thread)
        self.test_thread.started.connect(self.test_worker.run)
        self.test_worker.succeeded.connect(self.connection_status.setText)
        self.test_worker.failed.connect(
            lambda message: self.connection_status.setText(
                f"连接失败：{message or '请检查 SSH 与数据库配置'}"
            )
        )
        self.test_worker.done.connect(self.test_thread.quit)
        self.test_worker.done.connect(self.test_worker.deleteLater)
        self.test_thread.finished.connect(self._test_finished)
        self.test_thread.finished.connect(self.test_thread.deleteLater)
        self.test_thread.start()

    @Slot()
    def _test_finished(self) -> None:
        self.test_worker = None
        self.test_thread = None
        self._set_testing(False)

    def _set_testing(self, testing: bool) -> None:
        for widget in self.editable_widgets:
            widget.setEnabled(not testing)

    def reject(self) -> None:
        if self.test_thread and self.test_thread.isRunning():
            QMessageBox.information(self, "正在测试连接", "连接测试结束后才能关闭。")
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.test_thread and self.test_thread.isRunning():
            QMessageBox.information(self, "正在测试连接", "连接测试结束后才能关闭。")
            event.ignore()
            return
        event.accept()


# 主窗口
class WorkflowWindow(QMainWindow):
    """Termius 风格的自动化控制台主窗口。"""

    def __init__(self):
        """加载本地配置并构建主窗口。"""
        super().__init__()
        self.setWindowTitle("Automation Console")
        self.resize(1280, 820)
        self.setMinimumSize(1040, 700)

        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[WorkflowWorker] = None
        self.close_after_stop = False
        self.current_section = 0
        self.config_widgets: list[QWidget] = []
        self.navigation_buttons: list[QPushButton] = []
        self.database_status_button: Optional[QPushButton] = None
        self.database_breath_bright = True
        self.channel_codes_by_environment = load_channel_code_config()
        self.database_connections_by_environment = load_database_connections()
        self.ssh_private_keys = load_ssh_private_keys()

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
        workspace.addWidget(self._build_navigation())
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_task_workspace())
        self.content_stack.addWidget(self._build_config_workspace())
        workspace.addWidget(self.content_stack, 1)
        page.addLayout(workspace, 1)

        self._set_status("●  READY", "#79d59a")
        self._append_log("runner@local:~$ ready\n")
        self.database_breath_timer = QTimer(self)
        self.database_breath_timer.timeout.connect(self._animate_database_status)
        self.database_breath_timer.start(850)
        self._update_database_status_button()

    # 页面结构
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
        self.eyebrow = QLabel("$ account / create")
        self.eyebrow.setObjectName("eyebrow")
        titles.addWidget(title)
        titles.addWidget(self.eyebrow)
        layout.addLayout(titles)
        layout.addStretch()

        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _build_navigation(self) -> QFrame:
        navigation = QFrame()
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(180)
        layout = QVBoxLayout(navigation)
        layout.setContentsMargins(12, 20, 12, 14)
        layout.setSpacing(6)

        brand = QLabel("AUTOMATION")
        brand.setObjectName("navigationBrand")
        layout.addWidget(brand)
        meta = QLabel("CONTROL PANEL")
        meta.setObjectName("navigationMeta")
        layout.addWidget(meta)
        layout.addSpacing(22)

        group = QButtonGroup(navigation)
        group.setExclusive(True)
        for index, label in enumerate(("创建账号", "锦标赛数据", "参数配置")):
            button = QPushButton(label)
            button.setObjectName("navigationButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(
                lambda checked, selected=index: (
                    self._switch_section(selected) if checked else None
                )
            )
            group.addButton(button)
            self.navigation_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch()

        version = QLabel("LOCAL  ·  v2.1")
        version.setObjectName("navigationMeta")
        layout.addWidget(version)
        return navigation

    def _build_task_workspace(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_settings_panel())
        layout.addWidget(self._build_terminal_panel(), 1)
        return page

    def _build_config_workspace(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(26, 24, 26, 24)
        panel_layout.setSpacing(14)
        title = QLabel("参数配置")
        title.setObjectName("sectionTitle")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._build_config_tab(), 1)
        layout.addWidget(panel)
        return page

    def _build_settings_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel.setFixedWidth(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(16)

        self.settings_title = QLabel("创建账号")
        self.settings_title.setObjectName("sectionTitle")
        layout.addWidget(self.settings_title)

        self.settings_stack = QStackedWidget()
        self.settings_stack.addWidget(self._build_account_tab())
        self.settings_stack.addWidget(self._build_tournament_tab())
        layout.addWidget(self.settings_stack, 1)

        self.mode_hint = QLabel("只注册账号并导出账号信息，不执行加钱或下注。")
        self.mode_hint.setObjectName("fieldHint")
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)

        self.action_bar = QWidget()
        buttons = QHBoxLayout(self.action_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(self.action_bar)

        self.config_widgets.append(self.settings_stack)
        return panel

    def _build_account_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 8, 8)
        layout.setSpacing(10)
        form = self._form_layout()

        self.account_environment = QComboBox()
        self.account_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self._add_form_row(form, 0, "运行环境", self.account_environment)

        self.account_platform = self._platform_combo()
        self._add_form_row(form, 1, "注册平台", self.account_platform)

        self.account_channel_code = self._channel_code_combo(
            self.account_environment.currentText()
        )
        self.account_environment.currentTextChanged.connect(
            lambda environment: self._refresh_channel_code_combo(
                self.account_channel_code,
                environment,
            )
        )
        self._add_form_row(form, 2, "Channel Code", self.account_channel_code)

        self.account_count = self._spin_box(DEFAULT_ACCOUNT_COUNT, maximum=100_000)
        self._add_form_row(form, 3, "账号数量", self.account_count)

        self.account_max_workers = self._spin_box(DEFAULT_MAX_WORKERS, maximum=100)
        (
            account_execution_mode,
            self.account_serial_button,
            self.account_parallel_button,
        ) = self._execution_mode_control(self.account_max_workers)
        self._add_form_row(form, 4, "执行方式", account_execution_mode)
        self._add_form_row(form, 5, "并行账号", self.account_max_workers)

        self.account_output_file = QLineEdit(
            str(PROJECT_ROOT / "accounts_created.txt")
        )
        account_output, self.account_browse_button = self._output_field(
            self.account_output_file
        )
        self._add_form_row(form, 6, "输出文件", account_output)
        layout.addLayout(form)

        self.account_verbose = QCheckBox("显示调试日志")
        layout.addWidget(self.account_verbose)
        layout.addStretch()

        self.config_widgets.extend(
            [
                self.account_environment,
                self.account_platform,
                self.account_channel_code,
                self.account_count,
                self.account_max_workers,
                self.account_serial_button,
                self.account_parallel_button,
                self.account_output_file,
                self.account_browse_button,
                self.account_verbose,
            ]
        )
        return self._scrollable_settings_page(page)

    def _build_config_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 8, 12)
        layout.setSpacing(14)

        environment_row = QHBoxLayout()
        environment_label = QLabel("配置环境")
        environment_label.setObjectName("fieldLabel")
        environment_label.setFixedWidth(52)
        environment_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        environment_row.addWidget(environment_label)
        self.config_environment = QComboBox()
        self.config_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self.config_environment.currentTextChanged.connect(
            self._on_config_environment_changed
        )
        environment_row.addWidget(
            self._environment_control(self.config_environment),
            1,
        )
        environment_row.addStretch(2)
        layout.addLayout(environment_row)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        cards.addWidget(self._build_channel_code_card(), 1)
        cards.addWidget(self._build_ssh_private_key_card(), 1)
        layout.addLayout(cards)
        layout.addStretch()

        return self._scrollable_settings_page(page)

    def _build_channel_code_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("configCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Channel Code")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        description = QLabel("各环境独立维护，保存后立即同步到任务页。")
        description.setObjectName("fieldHint")
        description.setWordWrap(True)
        layout.addWidget(description)

        add_row = QHBoxLayout()
        add_row.setSpacing(7)
        self.channel_code_input = QLineEdit()
        self.channel_code_input.setPlaceholderText("输入新的 Channel Code")
        self.channel_code_input.returnPressed.connect(self._add_channel_code)
        add_row.addWidget(self.channel_code_input, 1)
        self.add_channel_code_button = QPushButton("添加")
        self.add_channel_code_button.setObjectName("secondaryButton")
        self.add_channel_code_button.clicked.connect(self._add_channel_code)
        add_row.addWidget(self.add_channel_code_button)
        layout.addLayout(add_row)

        self.channel_code_list = QListWidget()
        self.channel_code_list.setObjectName("channelCodeList")
        self.channel_code_list.setWordWrap(True)
        self.channel_code_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.channel_code_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.channel_code_list.addItems(
            self.channel_codes_by_environment[self.config_environment.currentText()]
        )
        layout.addWidget(self.channel_code_list, 1)

        self.delete_channel_code_button = QPushButton("删除选中项")
        self.delete_channel_code_button.setObjectName("stopButton")
        self.delete_channel_code_button.clicked.connect(self._delete_channel_code)
        layout.addWidget(self.delete_channel_code_button)
        self.config_widgets.extend(
            [
                self.config_environment,
                self.channel_code_input,
                self.add_channel_code_button,
                self.channel_code_list,
                self.delete_channel_code_button,
            ]
        )
        return card

    def _build_ssh_private_key_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("configCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("SSH 私钥库")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        description = QLabel(
            "私钥只需导入一次；数据库连接从私钥库选择，不保存或复制私钥内容。"
        )
        description.setObjectName("fieldHint")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.ssh_private_key_list = QListWidget()
        self.ssh_private_key_list.setObjectName("channelCodeList")
        self.ssh_private_key_list.setWordWrap(True)
        self.ssh_private_key_list.setTextElideMode(
            Qt.TextElideMode.ElideNone
        )
        self.ssh_private_key_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self.ssh_private_key_list, 1)

        buttons = QHBoxLayout()
        self.import_ssh_private_key_button = QPushButton("导入私钥")
        self.import_ssh_private_key_button.setObjectName("secondaryButton")
        self.import_ssh_private_key_button.clicked.connect(
            self._import_ssh_private_key
        )
        buttons.addWidget(self.import_ssh_private_key_button)
        self.delete_ssh_private_key_button = QPushButton("删除选中项")
        self.delete_ssh_private_key_button.setObjectName("stopButton")
        self.delete_ssh_private_key_button.clicked.connect(
            self._delete_ssh_private_key
        )
        buttons.addWidget(self.delete_ssh_private_key_button)
        layout.addLayout(buttons)

        self.config_widgets.extend(
            [
                self.ssh_private_key_list,
                self.import_ssh_private_key_button,
                self.delete_ssh_private_key_button,
            ]
        )
        self._refresh_ssh_private_key_list()
        return card

    def _build_tournament_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 8, 8)
        layout.setSpacing(10)
        form = self._form_layout()

        self.environment = QComboBox()
        self.environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self._add_form_row(form, 0, "运行环境", self.environment)

        self.platform = self._platform_combo()
        self._add_form_row(form, 1, "注册平台", self.platform)

        self.channel_code = self._channel_code_combo(self.environment.currentText())
        self.environment.currentTextChanged.connect(
            lambda environment: self._refresh_channel_code_combo(
                self.channel_code,
                environment,
            )
        )
        self._add_form_row(form, 2, "Channel Code", self.channel_code)

        self.count = self._spin_box(DEFAULT_ACCOUNT_COUNT, maximum=100_000)
        self._add_form_row(form, 3, "账号数量", self.count)

        self.max_workers = self._spin_box(DEFAULT_MAX_WORKERS, maximum=100)
        (
            tournament_execution_mode,
            self.serial_button,
            self.parallel_button,
        ) = self._execution_mode_control(self.max_workers)
        self._add_form_row(form, 4, "执行方式", tournament_execution_mode)
        self._add_form_row(form, 5, "并行账号", self.max_workers)

        self.balance = self._spin_box(INITIAL_BALANCE)
        self._add_form_row(form, 6, "加钱金额", self.balance)

        self.spin_count = self._spin_box(INITIAL_SPIN_COUNT, maximum=100_000)
        self._add_form_row(form, 7, "下注次数", self.spin_count)

        self.bet_amount = self._spin_box(spin.DEFAULT_BET_CENTS)
        self._add_form_row(form, 8, "下注金额", self.bet_amount, "美分")

        self.output_file = QLineEdit(str(PROJECT_ROOT / "accounts.txt"))
        tournament_output, self.browse_button = self._output_field(self.output_file)
        self._add_form_row(form, 9, "输出文件", tournament_output)
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
        self.spin_min.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.spin_min.setEnabled(False)
        random_row.addWidget(self.spin_min)
        max_label = QLabel("MAX")
        max_label.setObjectName("fieldHint")
        random_row.addWidget(max_label)
        self.spin_max = self._spin_box(INITIAL_SPIN_COUNT, maximum=100_000)
        self.spin_max.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.spin_max.setEnabled(False)
        random_row.addWidget(self.spin_max)
        layout.addLayout(random_row)

        self.verbose = QCheckBox("显示调试日志")
        layout.addWidget(self.verbose)
        layout.addStretch()

        self.config_widgets.extend(
            [
                self.environment,
                self.platform,
                self.channel_code,
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
        return self._scrollable_settings_page(page)

    # 通用表单组件
    @staticmethod
    def _scrollable_settings_page(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _form_layout() -> QGridLayout:
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        form.setColumnMinimumWidth(0, 100)
        form.setColumnStretch(1, 1)
        return form

    def _environment_control(self, combo: QComboBox) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        row.addWidget(combo, 1)

        status_button = QPushButton()
        status_button.setFixedWidth(132)
        status_button.setCursor(Qt.CursorShape.PointingHandCursor)
        status_button.clicked.connect(
            lambda: self._open_database_connection_dialog(combo)
        )
        combo.currentTextChanged.connect(self._update_database_status_button)
        row.addWidget(status_button)
        self.database_status_button = status_button
        self.config_widgets.append(status_button)
        self._update_database_status_button()
        return holder

    def _update_database_status_button(
        self,
        _environment: str = "",
    ) -> None:
        button = self.database_status_button
        if button is None:
            return
        connection = self.database_connections_by_environment[
            self.config_environment.currentText()
        ]
        configured = is_database_connection_configured(connection)
        if configured:
            button.setText("●  已配置 · 编辑")
            color = "#79d59a" if self.database_breath_bright else "#4f9568"
            background = "#17251d"
            border = "#315f40"
        else:
            button.setText("●  未配置 · 配置")
            color = "#e27d84" if self.database_breath_bright else "#954f55"
            background = "#27191b"
            border = "#65373b"
        button.setStyleSheet(
            "QPushButton {"
            f"color: {color}; background: {background}; border: 1px solid {border};"
            "border-radius: 7px; padding: 0 10px; font-weight: 650;"
            "} QPushButton:hover { color: #ffffff; border-color: #7b828e; }"
            "QPushButton:disabled { color: #555a63; background: #191b20; "
            "border-color: #292c32; }"
        )

    @Slot()
    def _animate_database_status(self) -> None:
        self.database_breath_bright = not self.database_breath_bright
        self._update_database_status_button()

    def _open_database_connection_dialog(self, combo: QComboBox) -> None:
        environment = combo.currentText()
        dialog = DatabaseConnectionDialog(
            environment,
            self.database_connections_by_environment[environment],
            self.ssh_private_keys,
            self,
        )
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_connection is not None
        ):
            self.database_connections_by_environment[environment] = (
                dialog.saved_connection
            )
            self._update_database_status_button()
            self._append_log(
                f"[config:{environment}] database connection saved\n"
            )

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
        widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        widget.setRange(1, maximum)
        widget.setValue(value)
        widget.setGroupSeparatorShown(True)
        widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        return widget

    @staticmethod
    def _platform_combo() -> QComboBox:
        widget = QComboBox()
        widget.addItem("Android", Platform.android.value)
        widget.addItem("iOS", Platform.ios.value)
        widget.setCurrentIndex(1)
        return widget

    def _channel_code_combo(self, environment: str) -> QComboBox:
        widget = QComboBox()
        widget.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        widget.setMinimumContentsLength(10)
        widget.setMinimumWidth(0)
        widget.addItems(self.channel_codes_by_environment[environment])
        return widget

    def _refresh_channel_code_combo(
        self,
        combo: QComboBox,
        environment: str,
    ) -> None:
        selected = combo.currentText()
        combo.clear()
        combo.addItems(self.channel_codes_by_environment[environment])
        selected_index = combo.findText(selected)
        combo.setCurrentIndex(max(0, selected_index))

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
        label.setFixedWidth(100)
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
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

    # 参数维护
    def _switch_section(self, index: int) -> None:
        self.current_section = index
        if index < len(self.navigation_buttons):
            self.navigation_buttons[index].setChecked(True)
        if index == 0:
            self.content_stack.setCurrentIndex(0)
            self.settings_stack.setCurrentIndex(0)
            self.settings_title.setText("创建账号")
            self.mode_hint.setText("只注册账号并导出账号信息，不执行加钱或下注。")
            self.start_button.setText("创建账号")
            self.session_title.setText("ACCOUNT CREATE")
            self.eyebrow.setText("$ account / create")
        elif index == 1:
            self.content_stack.setCurrentIndex(0)
            self.settings_stack.setCurrentIndex(1)
            self.settings_title.setText("锦标赛数据")
            self.mode_hint.setText("注册账号、加钱并连续下注，生成锦标赛测试数据。")
            self.start_button.setText("生成锦标赛数据")
            self.session_title.setText("TOURNAMENT DATA")
            self.eyebrow.setText("$ tournament / generate")
        else:
            self.content_stack.setCurrentIndex(1)
            self.eyebrow.setText("$ settings / parameters")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_text.setText("0 / 0")

    def _refresh_ssh_private_key_list(self) -> None:
        self.ssh_private_key_list.clear()
        for key in self.ssh_private_keys.values():
            item = QListWidgetItem(f"{key.name}\n{key.path}")
            item.setData(Qt.ItemDataRole.UserRole, key.key_id)
            item.setToolTip(key.path)
            item.setSizeHint(QSize(0, 52))
            self.ssh_private_key_list.addItem(item)

    @Slot()
    def _import_ssh_private_key(self) -> None:
        """导入一个可复用的 SSH 私钥文件。"""
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "导入 SSH 私钥到私钥库",
            "",
            "私钥文件 (*.pem *.key id_*);;所有文件 (*)",
        )
        if not selected:
            return
        try:
            imported = import_ssh_private_key(selected)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "导入失败", str(error))
            return
        self.ssh_private_keys = load_ssh_private_keys()
        self._refresh_ssh_private_key_list()
        for row in range(self.ssh_private_key_list.count()):
            item = self.ssh_private_key_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == imported.key_id:
                self.ssh_private_key_list.setCurrentRow(row)
                break
        self._append_log(f"[config] SSH private key registered: {imported.name}\n")

    @Slot()
    def _delete_ssh_private_key(self) -> None:
        """移除未使用的私钥记录，不删除原文件。"""
        item = self.ssh_private_key_list.currentItem()
        if item is None:
            QMessageBox.information(self, "选择私钥", "请先选择要删除的 SSH 私钥")
            return
        key_id = item.data(Qt.ItemDataRole.UserRole)
        key = self.ssh_private_keys.get(key_id)
        if key is None:
            return
        referenced_environments = [
            environment
            for environment, connection in self.database_connections_by_environment.items()
            if connection.ssh_private_key_id == key_id
        ]
        if referenced_environments:
            QMessageBox.warning(
                self,
                "私钥正在使用",
                "该私钥仍被以下环境引用："
                + "、".join(referenced_environments)
                + "。请先编辑这些数据库连接。",
            )
            return
        try:
            remove_ssh_private_key(key_id)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "删除失败", str(error))
            return
        self.ssh_private_keys = load_ssh_private_keys()
        self._refresh_ssh_private_key_list()
        self._update_database_status_button()
        self._append_log(f"[config] SSH private key removed: {key.name}\n")

    @Slot()
    def _add_channel_code(self) -> None:
        environment = self.config_environment.currentText()
        configured_codes = self.channel_codes_by_environment[environment]
        channel_code = self.channel_code_input.text().strip()
        if not channel_code:
            QMessageBox.warning(self, "参数错误", "Channel Code 不能为空")
            return
        if channel_code in configured_codes:
            QMessageBox.information(self, "无需添加", "该 Channel Code 已存在")
            return
        if self._persist_channel_codes(
            environment,
            [*configured_codes, channel_code],
        ):
            self.channel_code_input.clear()
            self.channel_code_list.setCurrentRow(len(configured_codes))
            self._append_log(
                f"[config:{environment}] channel code added: {channel_code}\n"
            )

    @Slot()
    def _delete_channel_code(self) -> None:
        environment = self.config_environment.currentText()
        configured_codes = self.channel_codes_by_environment[environment]
        selected_row = self.channel_code_list.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "选择配置", "请先选择要删除的 Channel Code")
            return
        if len(configured_codes) <= 1:
            QMessageBox.warning(self, "无法删除", "至少保留一个 Channel Code")
            return

        removed = configured_codes[selected_row]
        remaining = [
            code for index, code in enumerate(configured_codes) if index != selected_row
        ]
        if self._persist_channel_codes(environment, remaining):
            self._append_log(
                f"[config:{environment}] channel code removed: {removed}\n"
            )

    @Slot(str)
    def _on_config_environment_changed(self, environment: str) -> None:
        self.channel_code_list.clear()
        self.channel_code_list.addItems(
            self.channel_codes_by_environment[environment]
        )

    def _persist_channel_codes(
        self,
        environment: str,
        channel_codes: list[str],
    ) -> bool:
        """保存 Channel Code 并同步两个任务页。"""
        try:
            saved_codes = save_channel_codes(environment, channel_codes)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return False

        self.channel_codes_by_environment[environment] = saved_codes
        self.channel_code_list.clear()
        self.channel_code_list.addItems(saved_codes)
        if self.account_environment.currentText() == environment:
            self._refresh_channel_code_combo(
                self.account_channel_code,
                environment,
            )
        if self.environment.currentText() == environment:
            self._refresh_channel_code_combo(self.channel_code, environment)
        return True

    def _browse_output(self, line_edit: QLineEdit) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "选择账号输出文件",
            line_edit.text(),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if selected:
            line_edit.setText(selected)

    # 任务生命周期
    def _parameters(self) -> tuple[Callable[..., int], dict, str]:
        """校验当前页面并生成任务参数。"""
        if self.current_section == 0:
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
                    "platform": self.account_platform.currentData(),
                    "channel_code": self.account_channel_code.currentText(),
                    "output_file": output_path,
                    "verbose": self.account_verbose.isChecked(),
                },
                "create-accounts",
            )

        if self.current_section != 1:
            raise ValueError("参数配置页不能执行任务")

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
            "platform": self.platform.currentData(),
            "channel_code": self.channel_code.currentText(),
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
        """在工作线程中启动当前任务。"""
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
        """请求安全停止当前任务。"""
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
        for button in self.navigation_buttons:
            button.setEnabled(not running)
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
        """任务运行时确认停止后再关闭窗口。"""
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
    """创建并运行 Qt 桌面应用。"""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Automation Console")
    app.setStyle("Fusion")
    window = WorkflowWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
