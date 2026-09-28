"""自动化测试数据桌面控制台。"""

import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
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
from base.account_batch import (
    create_accounts,
    create_custom_account,
    validate_custom_email,
)
from base.app_config import load_channel_code_config, save_channel_codes
from base.channel_source import (
    ChannelSource,
    fetch_channel_sources,
    load_channel_source_config,
    log_database_name_for_environment,
    requires_manual_channel_code,
    resolve_registration_channel,
    save_channel_sources,
)
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
from base.sql_data import (
    SqlTemplate,
    delete_sql_template,
    generate_feature_data,
    load_sql_templates,
    save_sql_template,
)
from base.tournment_test import (
    DEFAULT_ACCOUNT_COUNT,
    DEFAULT_MAX_WORKERS,
    DEFAULT_SPIN_WORKERS,
    INITIAL_BALANCE,
    INITIAL_SPIN_COUNT,
    create_accounts_and_bet,
)
from base.user import SUPPORTED_ENVIRONMENTS


PROJECT_ROOT = Path(__file__).resolve().parent


APP_STYLESHEET = """
QWidget {
    color: #20242a;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QWidget#root { background: #f4f5f7; }
QDialog, QMessageBox { background: #ffffff; }
QFrame#topBar {
    background: #f4f5f7;
    border-bottom: 1px solid #dfe3e8;
}

QLabel#title { color: #17191d; font-size: 24px; font-weight: 700; }
QLabel#sectionTitle { color: #20242a; font-size: 15px; font-weight: 650; }
QLabel#fieldLabel { color: #5d6470; font-size: 12px; }
QLabel#eyebrow, QLabel#terminalMeta, QLabel#fieldHint,
QLabel#navigationMeta {
    color: #808792;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}
QLabel#navigationBrand, QLabel#sessionTitle {
    color: #17191d;
    font-family: "Cascadia Mono", "Consolas";
    font-weight: 700;
}
QLabel#navigationBrand { font-size: 15px; }
QLabel#sessionTitle { font-size: 13px; }
QLabel#online { color: #228653; font-weight: 700; }
QLabel#statusPill, QLabel#connectionStatus {
    background: #ffffff;
    border: 1px solid #d9dde3;
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
    background: #ffffff;
    border: 1px solid #dfe3e8;
    border-radius: 10px;
}
QFrame#terminalPanel, QFrame#configCard, QFrame#navigation { background: #ffffff; }

QPushButton {
    min-height: 36px;
    border-radius: 7px;
    padding: 0 14px;
    font-weight: 600;
}
QPushButton#navigationButton {
    min-height: 42px;
    color: #656c76;
    background: transparent;
    border: 0;
    padding: 0 14px;
    text-align: left;
}
QPushButton#navigationButton:hover, QPushButton#navigationButton:checked {
    color: #17191d;
    background: #eceff2;
}
QPushButton#primaryButton, QPushButton#modeButton:checked {
    color: #ffffff;
    background: #20242a;
    border: 1px solid #20242a;
}
QPushButton#primaryButton:hover, QPushButton#modeButton:checked:hover {
    background: #000000;
    border-color: #000000;
}
QPushButton#secondaryButton, QPushButton#stopButton,
QPushButton#browseButton, QPushButton#modeButton {
    color: #3f4650;
    background: #ffffff;
    border: 1px solid #cfd4db;
}
QPushButton#modeButton { color: #737b86; background: #f7f8f9; }
QPushButton#secondaryButton:hover, QPushButton#stopButton:hover,
QPushButton#browseButton:hover, QPushButton#modeButton:hover {
    color: #17191d;
    background: #f0f2f4;
    border-color: #aeb5bf;
}
QPushButton:disabled, QPushButton#navigationButton:disabled {
    color: #abb1ba;
    background: #f1f3f5;
    border-color: #e2e5e9;
}

QLineEdit, QSpinBox, QComboBox {
    min-height: 36px;
    color: #20242a;
    background: #ffffff;
    border: 1px solid #cfd4db;
    border-radius: 7px;
    padding: 0 10px;
    selection-color: #ffffff;
    selection-background-color: #343a42;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover { border-color: #9fa7b2; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #343a42; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: #a2a8b1;
    background: #f0f2f4;
    border-color: #e2e5e9;
}
QComboBox::drop-down {
    width: 24px;
    background: #f3f5f7;
    border: 0;
}
QComboBox QAbstractItemView {
    color: #20242a;
    background: #ffffff;
    border: 1px solid #cfd4db;
    selection-color: #17191d;
    selection-background-color: #e9edf1;
}

QListWidget#channelCodeList, QPlainTextEdit#terminal {
    color: #30363d;
    background: #fbfcfd;
    border: 1px solid #d6dbe1;
    border-radius: 7px;
    padding: 6px;
}
QListWidget#channelCodeList::item { min-height: 32px; padding: 4px 8px; }
QListWidget#channelCodeList::item:selected { color: #17191d; background: #e8ebef; }
QPlainTextEdit#terminal {
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
}

QCheckBox { color: #4d545e; spacing: 8px; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #ffffff;
    border: 1px solid #b9c0c9;
    border-radius: 4px;
}
QCheckBox::indicator:checked { background: #20242a; border-color: #20242a; }

QProgressBar {
    min-height: 5px;
    max-height: 5px;
    background: #e4e7eb;
    border: 0;
    border-radius: 2px;
}
QProgressBar::chunk { background: #20242a; border-radius: 2px; }

QScrollArea#settingsScroll, QWidget#settingsPage { background: transparent; border: 0; }
QScrollBar:vertical { width: 9px; margin: 4px 2px; background: transparent; }
QScrollBar::handle:vertical {
    min-height: 28px;
    background: #c7ccd3;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #9da5af; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class NumberInput(QSpinBox):
    """仅允许直接输入数字，不提供步进按钮或滚轮调节。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def wheelEvent(self, event) -> None:
        event.ignore()


class SearchableComboBox(QComboBox):
    """可按标题模糊检索的下拉选择框。"""

    def __init__(self) -> None:
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("输入标题检索")


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

        self.log_database_name = QLineEdit(
            connection.log_database_name
            or log_database_name_for_environment(environment, connection)
        )
        self.log_database_name.setPlaceholderText("渠道参数所在的日志库")
        self._add_row(form, 7, "日志库名称", self.log_database_name)

        self.database_username = QLineEdit(connection.database_username)
        self._add_row(form, 8, "数据库用户", self.database_username)

        self.database_password = QLineEdit(connection.database_password)
        self.database_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_row(form, 9, "数据库密码", self.database_password)
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
            self.log_database_name,
            self.database_username,
            self.database_password,
            self.cancel_button,
            self.test_button,
            self.save_button,
        ]

    @staticmethod
    def _port_spin(value: int) -> QSpinBox:
        widget = NumberInput()
        widget.setRange(1, 65535)
        widget.setValue(value)
        widget.setGroupSeparatorShown(True)
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
            log_database_name=self.log_database_name.text().strip(),
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


class SqlTemplateDialog(QDialog):
    """新增或编辑一条可复用 SQL 模板。"""

    def __init__(
        self,
        parent: QWidget,
        template: Optional[SqlTemplate] = None,
    ) -> None:
        super().__init__(parent)
        self.template = template
        self.saved_template: Optional[SqlTemplate] = None
        self.setWindowTitle("编辑 SQL 模板" if template else "新增 SQL 模板")
        self.resize(760, 560)
        self.setMinimumSize(620, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title_label = QLabel("标题")
        title_label.setObjectName("fieldLabel")
        layout.addWidget(title_label)
        self.title_input = QLineEdit(template.title if template else "")
        self.title_input.setPlaceholderText("例如：开通 VIP 测试数据")
        layout.addWidget(self.title_input)

        sql_label = QLabel("SQL（使用 @userid=xxx; 声明 UID）")
        sql_label.setObjectName("fieldLabel")
        layout.addWidget(sql_label)
        self.sql_input = QPlainTextEdit()
        self.sql_input.setPlaceholderText(
            "@userid=xxx;\n"
            "UPDATE user SET vip_level=1 WHERE id=@userid;"
        )
        self.sql_input.setPlainText(template.sql if template else "@userid=xxx;\n")
        layout.addWidget(self.sql_input, 1)

        hint = QLabel(
            "执行时会自动转换为 SET @userid=<UID>;，后续 SQL 可使用 @userid。"
        )
        hint.setObjectName("fieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        save_button = QPushButton("保存")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    @Slot()
    def _save(self) -> None:
        try:
            self.saved_template = save_sql_template(
                self.title_input.text(),
                self.sql_input.toPlainText(),
                template_id=self.template.template_id if self.template else None,
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.accept()


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
        self.channel_source_thread: Optional[QThread] = None
        self.channel_source_worker: Optional[ChannelSourceUpdateWorker] = None
        self.close_after_stop = False
        self.current_section = 0
        self.config_widgets: list[QWidget] = []
        self.navigation_buttons: list[QPushButton] = []
        self.database_status_button: Optional[QPushButton] = None
        self.database_breath_bright = True
        self.channel_codes_by_environment = load_channel_code_config()
        self.channel_sources_by_environment = load_channel_source_config()
        self.database_connections_by_environment = load_database_connections()
        self.ssh_private_keys = load_ssh_private_keys()
        self.sql_templates = load_sql_templates()

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
        self.content_stack.addWidget(self._build_feature_workspace())
        workspace.addWidget(self.content_stack, 1)
        page.addLayout(workspace, 1)

        self._set_status("●  READY", "#228653")
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
        self.eyebrow = QLabel("$ account / create-batch")
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
        for index, label in enumerate(
            ("创建账号", "锦标赛数据", "功能数据", "参数配置")
        ):
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

        self.mode_hint = QLabel("按原有逻辑批量注册随机邮箱账号，并导出账号信息。")
        self.mode_hint.setObjectName("fieldHint")
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)

        self.action_bar = QWidget()
        buttons = QHBoxLayout(self.action_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        self.start_button = QPushButton("批量创建账号")
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

        (
            account_creation_mode,
            self.account_batch_mode_button,
            self.account_custom_mode_button,
        ) = self._account_creation_mode_control()
        self._add_form_row(form, 0, "创建方式", account_creation_mode)

        self.account_environment = QComboBox()
        self.account_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self.account_environment.currentTextChanged.connect(
            self._sync_account_channel_options
        )
        self._add_form_row(form, 1, "运行环境", self.account_environment)

        self.account_platform = self._platform_combo()
        self._add_form_row(form, 2, "注册平台", self.account_platform)

        (
            self.account_enter_b_control,
            self.account_enter_b_no_button,
            self.account_enter_b_yes_button,
        ) = self._boolean_choice_control(default=True)
        self.account_enter_b_label = self._add_form_row(
            form,
            3,
            "进入 B 面",
            self.account_enter_b_control,
        )

        (
            self.account_new_user_control,
            self.account_new_user_no_button,
            self.account_new_user_yes_button,
        ) = self._boolean_choice_control(default=False)
        self.account_new_user_label = self._add_form_row(
            form,
            4,
            "新手套路",
            self.account_new_user_control,
        )

        self.account_channel_source = QLineEdit()
        self.account_channel_source.setReadOnly(True)
        self.account_channel_source.setPlaceholderText("请先更新渠道参数")
        self.account_channel_code = self._prod_channel_code_combo()
        (
            account_channel_source_field,
            self.account_update_parameters_button,
        ) = self._channel_source_field(
            self.account_channel_source,
            "account",
            self.account_channel_code,
        )
        self.account_channel_source_label = self._add_form_row(
            form,
            5,
            "匹配渠道源",
            account_channel_source_field,
        )

        self.account_enter_b_no_button.toggled.connect(
            lambda checked: self._sync_account_channel_options() if checked else None
        )
        self.account_enter_b_yes_button.toggled.connect(
            lambda checked: self._sync_account_channel_options() if checked else None
        )
        self.account_new_user_no_button.toggled.connect(
            lambda checked: self._refresh_account_channel_source() if checked else None
        )
        self.account_new_user_yes_button.toggled.connect(
            lambda checked: self._refresh_account_channel_source() if checked else None
        )

        self.account_count = self._spin_box(DEFAULT_ACCOUNT_COUNT, maximum=100_000)
        self.account_count_label = self._add_form_row(
            form,
            6,
            "账号数量",
            self.account_count,
        )

        self.account_custom_email = QLineEdit()
        self.account_custom_email.setPlaceholderText("例如：tester@example.com")
        self.account_custom_email_label = self._add_form_row(
            form,
            7,
            "自定义邮箱",
            self.account_custom_email,
        )

        self.account_max_workers = self._spin_box(DEFAULT_MAX_WORKERS, maximum=100)
        (
            self.account_execution_mode,
            self.account_serial_button,
            self.account_parallel_button,
        ) = self._execution_mode_control(self.account_max_workers)
        self.account_execution_mode_label = self._add_form_row(
            form,
            8,
            "执行方式",
            self.account_execution_mode,
        )
        self.account_max_workers_label = self._add_form_row(
            form,
            9,
            "并行账号",
            self.account_max_workers,
        )

        self.account_output_file = QLineEdit(
            str(PROJECT_ROOT / "accounts_created.txt")
        )
        account_output, self.account_browse_button = self._output_field(
            self.account_output_file
        )
        self._add_form_row(form, 10, "输出文件", account_output)
        self.account_sql_template = self._sql_binding_combo()
        self._add_form_row(form, 11, "绑定 SQL", self.account_sql_template)
        layout.addLayout(form)

        self.account_verbose = QCheckBox("显示调试日志")
        layout.addWidget(self.account_verbose)
        layout.addStretch()

        self.config_widgets.extend(
            [
                self.account_environment,
                self.account_platform,
                self.account_enter_b_no_button,
                self.account_enter_b_yes_button,
                self.account_new_user_no_button,
                self.account_new_user_yes_button,
                self.account_update_parameters_button,
                self.account_batch_mode_button,
                self.account_custom_mode_button,
                self.account_count,
                self.account_custom_email,
                self.account_max_workers,
                self.account_serial_button,
                self.account_parallel_button,
                self.account_output_file,
                self.account_browse_button,
                self.account_sql_template,
                self.account_verbose,
            ]
        )
        self._sync_account_creation_mode_inputs()
        self._sync_account_channel_options()
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
        description = QLabel(
            "各环境独立维护；供锦标赛任务和创建账号的渠道匹配优先级使用。"
        )
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
        self.environment.currentTextChanged.connect(
            self._sync_tournament_channel_options
        )
        self._add_form_row(form, 0, "运行环境", self.environment)

        self.platform = self._platform_combo()
        self._add_form_row(form, 1, "注册平台", self.platform)

        (
            self.tournament_enter_b_control,
            self.tournament_enter_b_no_button,
            self.tournament_enter_b_yes_button,
        ) = self._boolean_choice_control(default=True)
        self.tournament_enter_b_label = self._add_form_row(
            form,
            2,
            "进入 B 面",
            self.tournament_enter_b_control,
        )

        (
            self.tournament_new_user_control,
            self.tournament_new_user_no_button,
            self.tournament_new_user_yes_button,
        ) = self._boolean_choice_control(default=False)
        self.tournament_new_user_label = self._add_form_row(
            form,
            3,
            "新手套路",
            self.tournament_new_user_control,
        )

        self.tournament_channel_source = QLineEdit()
        self.tournament_channel_source.setReadOnly(True)
        self.tournament_channel_source.setPlaceholderText("请先更新渠道参数")
        self.tournament_channel_code = self._prod_channel_code_combo()
        (
            tournament_channel_source_field,
            self.tournament_update_parameters_button,
        ) = self._channel_source_field(
            self.tournament_channel_source,
            "tournament",
            self.tournament_channel_code,
        )
        self.tournament_channel_source_label = self._add_form_row(
            form,
            4,
            "匹配渠道源",
            tournament_channel_source_field,
        )
        self.tournament_enter_b_no_button.toggled.connect(
            lambda checked: self._sync_tournament_channel_options()
            if checked
            else None
        )
        self.tournament_enter_b_yes_button.toggled.connect(
            lambda checked: self._sync_tournament_channel_options()
            if checked
            else None
        )
        self.tournament_new_user_no_button.toggled.connect(
            lambda checked: self._refresh_tournament_channel_source()
            if checked
            else None
        )
        self.tournament_new_user_yes_button.toggled.connect(
            lambda checked: self._refresh_tournament_channel_source()
            if checked
            else None
        )

        self.count = self._spin_box(DEFAULT_ACCOUNT_COUNT, maximum=100_000)
        self._add_form_row(form, 5, "账号数量", self.count)

        self.max_workers = self._spin_box(DEFAULT_MAX_WORKERS, maximum=100)
        (
            tournament_execution_mode,
            self.serial_button,
            self.parallel_button,
        ) = self._execution_mode_control(self.max_workers)
        self._add_form_row(form, 6, "执行方式", tournament_execution_mode)
        self._add_form_row(form, 7, "并行账号", self.max_workers)

        self.spin_workers = self._spin_box(DEFAULT_SPIN_WORKERS, maximum=100)
        (
            spin_execution_mode,
            self.spin_serial_button,
            self.spin_parallel_button,
        ) = self._execution_mode_control(self.spin_workers)
        self._add_form_row(form, 8, "下注方式", spin_execution_mode)
        self._add_form_row(form, 9, "下注并发", self.spin_workers)

        self.balance = self._spin_box(INITIAL_BALANCE)
        self._add_form_row(form, 10, "加钱金额", self.balance)

        self.spin_count = self._spin_box(INITIAL_SPIN_COUNT, maximum=100_000)
        self._add_form_row(form, 11, "下注次数", self.spin_count)

        self.bet_amount = self._spin_box(spin.DEFAULT_BET_CENTS)
        self._add_form_row(form, 12, "下注金额", self.bet_amount, "美分")

        self.output_file = QLineEdit(str(PROJECT_ROOT / "accounts.txt"))
        tournament_output, self.browse_button = self._output_field(self.output_file)
        self._add_form_row(form, 13, "输出文件", tournament_output)
        self.tournament_sql_template = self._sql_binding_combo()
        self._add_form_row(form, 14, "绑定 SQL", self.tournament_sql_template)
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
                self.tournament_enter_b_no_button,
                self.tournament_enter_b_yes_button,
                self.tournament_new_user_no_button,
                self.tournament_new_user_yes_button,
                self.tournament_update_parameters_button,
                self.count,
                self.max_workers,
                self.serial_button,
                self.parallel_button,
                self.spin_workers,
                self.spin_serial_button,
                self.spin_parallel_button,
                self.balance,
                self.spin_count,
                self.bet_amount,
                self.output_file,
                self.browse_button,
                self.tournament_sql_template,
                self.random_spins,
                self.spin_min,
                self.spin_max,
                self.verbose,
            ]
        )
        self._sync_tournament_channel_options()
        return self._scrollable_settings_page(page)

    def _build_feature_workspace(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        main = QHBoxLayout()
        main.setSpacing(12)

        list_panel = QFrame()
        list_panel.setObjectName("settingsPanel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(22, 20, 22, 20)
        list_layout.setSpacing(10)
        list_title = QLabel("SQL 模板")
        list_title.setObjectName("sectionTitle")
        list_layout.addWidget(list_title)
        list_hint = QLabel("按命名标题管理和检索功能数据 SQL。")
        list_hint.setObjectName("fieldHint")
        list_layout.addWidget(list_hint)

        self.feature_sql_search = QLineEdit()
        self.feature_sql_search.setPlaceholderText("输入标题检索…")
        self.feature_sql_search.textChanged.connect(
            self._filter_feature_sql_templates
        )
        list_layout.addWidget(self.feature_sql_search)

        self.feature_sql_list = QListWidget()
        self.feature_sql_list.setObjectName("channelCodeList")
        self.feature_sql_list.currentItemChanged.connect(
            self._on_feature_sql_selection_changed
        )
        self.feature_sql_list.itemDoubleClicked.connect(
            lambda _item: self._edit_sql_template()
        )
        list_layout.addWidget(self.feature_sql_list, 1)

        manage_buttons = QHBoxLayout()
        manage_buttons.setSpacing(7)
        self.new_sql_template_button = QPushButton("新增 SQL")
        self.new_sql_template_button.setObjectName("secondaryButton")
        self.new_sql_template_button.clicked.connect(self._new_sql_template)
        manage_buttons.addWidget(self.new_sql_template_button)
        self.edit_sql_template_button = QPushButton("编辑")
        self.edit_sql_template_button.setObjectName("secondaryButton")
        self.edit_sql_template_button.clicked.connect(self._edit_sql_template)
        manage_buttons.addWidget(self.edit_sql_template_button)
        self.delete_sql_template_button = QPushButton("删除")
        self.delete_sql_template_button.setObjectName("stopButton")
        self.delete_sql_template_button.clicked.connect(self._delete_sql_template)
        manage_buttons.addWidget(self.delete_sql_template_button)
        list_layout.addLayout(manage_buttons)
        main.addWidget(list_panel, 2)

        execute_panel = QFrame()
        execute_panel.setObjectName("settingsPanel")
        execute_panel.setFixedWidth(360)
        execute_layout = QVBoxLayout(execute_panel)
        execute_layout.setContentsMargins(22, 20, 22, 20)
        execute_layout.setSpacing(12)
        execute_title = QLabel("执行功能数据")
        execute_title.setObjectName("sectionTitle")
        execute_layout.addWidget(execute_title)

        selected_caption = QLabel("已选模板")
        selected_caption.setObjectName("fieldLabel")
        execute_layout.addWidget(selected_caption)
        self.feature_selected_title = QLabel("未选择")
        self.feature_selected_title.setObjectName("fieldHint")
        self.feature_selected_title.setWordWrap(True)
        execute_layout.addWidget(self.feature_selected_title)

        environment_label = QLabel("运行环境")
        environment_label.setObjectName("fieldLabel")
        execute_layout.addWidget(environment_label)
        self.feature_environment = QComboBox()
        self.feature_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        execute_layout.addWidget(self.feature_environment)

        user_id_label = QLabel("User ID")
        user_id_label.setObjectName("fieldLabel")
        execute_layout.addWidget(user_id_label)
        self.feature_user_id = self._spin_box(1, maximum=2_147_483_647)
        self.feature_user_id.setMinimum(1)
        execute_layout.addWidget(self.feature_user_id)

        parameter_hint = QLabel(
            "@userid=xxx 会自动替换为上方 User ID。"
        )
        parameter_hint.setObjectName("fieldHint")
        parameter_hint.setWordWrap(True)
        execute_layout.addWidget(parameter_hint)
        execute_layout.addStretch()

        execute_buttons = QHBoxLayout()
        self.feature_execute_button = QPushButton("执行")
        self.feature_execute_button.setObjectName("primaryButton")
        self.feature_execute_button.clicked.connect(self._start)
        execute_buttons.addWidget(self.feature_execute_button, 1)
        self.feature_stop_button = QPushButton("停止")
        self.feature_stop_button.setObjectName("stopButton")
        self.feature_stop_button.setEnabled(False)
        self.feature_stop_button.clicked.connect(self._stop)
        execute_buttons.addWidget(self.feature_stop_button)
        execute_layout.addLayout(execute_buttons)
        main.addWidget(execute_panel)
        layout.addLayout(main, 1)

        log_panel = QFrame()
        log_panel.setObjectName("terminalPanel")
        log_panel.setFixedHeight(150)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(16, 10, 16, 12)
        log_layout.setSpacing(6)
        log_header = QHBoxLayout()
        log_title = QLabel("执行日志")
        log_title.setObjectName("sessionTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        clear_log_button = QPushButton("清空")
        clear_log_button.setObjectName("secondaryButton")
        clear_log_button.clicked.connect(lambda: self.feature_log.clear())
        log_header.addWidget(clear_log_button)
        log_layout.addLayout(log_header)
        self.feature_log = QPlainTextEdit()
        self.feature_log.setObjectName("terminal")
        self.feature_log.setReadOnly(True)
        self.feature_log.setUndoRedoEnabled(False)
        self.feature_log.document().setMaximumBlockCount(500)
        compact_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        compact_font.setPointSize(9)
        self.feature_log.setFont(compact_font)
        log_layout.addWidget(self.feature_log, 1)
        layout.addWidget(log_panel)

        self.config_widgets.extend(
            [
                self.feature_sql_search,
                self.feature_sql_list,
                self.feature_environment,
                self.feature_user_id,
                self.new_sql_template_button,
                self.edit_sql_template_button,
                self.delete_sql_template_button,
                self.feature_execute_button,
            ]
        )
        self._refresh_sql_template_combos()
        return page

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
            color = "#208653" if self.database_breath_bright else "#5b9b76"
            background = "#f0faf4"
            border = "#a9d8ba"
        else:
            button.setText("●  未配置 · 配置")
            color = "#c43d47" if self.database_breath_bright else "#b06b71"
            background = "#fff4f4"
            border = "#e7b8bc"
        button.setStyleSheet(
            "QPushButton {"
            f"color: {color}; background: {background}; border: 1px solid {border};"
            "border-radius: 7px; padding: 0 10px; font-weight: 650;"
            "} QPushButton:hover { color: #17191d; border-color: #8f98a4; }"
            "QPushButton:disabled { color: #abb1ba; background: #f1f3f5; "
            "border-color: #e2e5e9; }"
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

    def _account_creation_mode_control(
        self,
    ) -> tuple[QWidget, QPushButton, QPushButton]:
        """创建批量与定制单账号的互斥选择控件。"""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        batch = QPushButton("批量创建")
        batch.setObjectName("modeButton")
        batch.setCheckable(True)
        batch.setChecked(True)
        custom = QPushButton("定制单账号")
        custom.setObjectName("modeButton")
        custom.setCheckable(True)

        group = QButtonGroup(holder)
        group.setExclusive(True)
        group.addButton(batch)
        group.addButton(custom)
        batch.toggled.connect(
            lambda checked: self._on_account_creation_mode_changed() if checked else None
        )
        custom.toggled.connect(
            lambda checked: self._on_account_creation_mode_changed() if checked else None
        )
        row.addWidget(batch, 1)
        row.addWidget(custom, 1)
        return holder, batch, custom

    @staticmethod
    def _boolean_choice_control(
        *,
        default: bool,
    ) -> tuple[QWidget, QPushButton, QPushButton]:
        """创建“否 / 是”互斥选择控件。"""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        no_button = QPushButton("否")
        yes_button = QPushButton("是")
        for button in (no_button, yes_button):
            button.setObjectName("modeButton")
            button.setCheckable(True)
            row.addWidget(button, 1)
        group = QButtonGroup(holder)
        group.setExclusive(True)
        group.addButton(no_button)
        group.addButton(yes_button)
        yes_button.setChecked(default)
        no_button.setChecked(not default)
        return holder, no_button, yes_button

    def _channel_source_field(
        self,
        line_edit: QLineEdit,
        context: str,
        manual_combo: Optional[QComboBox] = None,
    ) -> tuple[QWidget, QPushButton]:
        """创建自动渠道预览和生产 Channel Code 选择器。"""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        if manual_combo is not None:
            manual_combo.hide()
            row.addWidget(manual_combo, 1)
        row.addWidget(line_edit, 1)
        update_button = QPushButton("更新参数")
        update_button.setObjectName("secondaryButton")
        update_button.clicked.connect(
            lambda: self._update_channel_source_parameters(context)
        )
        row.addWidget(update_button)
        return holder, update_button

    def _prod_channel_code_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(10)
        combo.addItems(self.channel_codes_by_environment["prod"])
        return combo

    def _refresh_prod_channel_code_combo(self, combo: QComboBox) -> None:
        selected = combo.currentText()
        combo.clear()
        combo.addItems(self.channel_codes_by_environment["prod"])
        selected_index = combo.findText(selected)
        combo.setCurrentIndex(max(0, selected_index))

    def _sql_binding_combo(self) -> QComboBox:
        combo = SearchableComboBox()
        combo.addItem("不绑定 SQL", None)
        for template in self.sql_templates:
            combo.addItem(template.title, template.template_id)
        return combo

    def _template_by_id(self, template_id: object) -> Optional[SqlTemplate]:
        return next(
            (
                template
                for template in self.sql_templates
                if template.template_id == template_id
            ),
            None,
        )

    def _selected_sql_template(
        self,
        combo: QComboBox,
        *,
        required: bool = False,
    ) -> Optional[SqlTemplate]:
        selected_text = combo.currentText().strip()
        if not selected_text or selected_text in ("不绑定 SQL", "请先新增 SQL"):
            template = None
        else:
            template = next(
                (
                    candidate
                    for candidate in self.sql_templates
                    if candidate.title.casefold() == selected_text.casefold()
                ),
                None,
            )
            if template is None:
                raise ValueError("请从检索结果中选择完整的 SQL 模板标题")
        if required and template is None:
            raise ValueError("请先选择 SQL 模板")
        return template

    @staticmethod
    def _restore_combo_selection(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _refresh_sql_template_combos(
        self,
        selected_template_id: Optional[str] = None,
    ) -> None:
        account_selected = (
            self.account_sql_template.currentData()
            if hasattr(self, "account_sql_template")
            else None
        )
        tournament_selected = (
            self.tournament_sql_template.currentData()
            if hasattr(self, "tournament_sql_template")
            else None
        )
        current_feature = (
            self.feature_sql_list.currentItem()
            if hasattr(self, "feature_sql_list")
            else None
        )
        feature_selected = selected_template_id or (
            current_feature.data(Qt.ItemDataRole.UserRole)
            if current_feature is not None
            else None
        )

        for combo, selected in (
            (getattr(self, "account_sql_template", None), account_selected),
            (getattr(self, "tournament_sql_template", None), tournament_selected),
        ):
            if combo is None:
                continue
            combo.clear()
            combo.addItem("不绑定 SQL", None)
            for template in self.sql_templates:
                combo.addItem(template.title, template.template_id)
            self._restore_combo_selection(combo, selected)

        if hasattr(self, "feature_sql_list"):
            self.feature_sql_list.blockSignals(True)
            self.feature_sql_list.clear()
            selected_row = -1
            for row, template in enumerate(self.sql_templates):
                item = QListWidgetItem(template.title)
                item.setData(Qt.ItemDataRole.UserRole, template.template_id)
                item.setToolTip(template.title)
                self.feature_sql_list.addItem(item)
                if template.template_id == feature_selected:
                    selected_row = row
            self.feature_sql_list.blockSignals(False)
            if self.feature_sql_list.count():
                self.feature_sql_list.setCurrentRow(max(0, selected_row))
            self._filter_feature_sql_templates(self.feature_sql_search.text())
            self._on_feature_sql_selection_changed()

    def _selected_feature_sql_template(self) -> Optional[SqlTemplate]:
        if not hasattr(self, "feature_sql_list"):
            return None
        item = self.feature_sql_list.currentItem()
        if item is None or item.isHidden():
            return None
        return self._template_by_id(item.data(Qt.ItemDataRole.UserRole))

    @Slot(str)
    def _filter_feature_sql_templates(self, query: str) -> None:
        if not hasattr(self, "feature_sql_list"):
            return
        normalized = query.strip().casefold()
        first_visible = None
        for row in range(self.feature_sql_list.count()):
            item = self.feature_sql_list.item(row)
            visible = not normalized or normalized in item.text().casefold()
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = item
        current = self.feature_sql_list.currentItem()
        if current is None or current.isHidden():
            self.feature_sql_list.setCurrentItem(first_visible)
        self._on_feature_sql_selection_changed()

    def _on_feature_sql_selection_changed(self, *_args) -> None:
        if not hasattr(self, "feature_selected_title"):
            return
        template = self._selected_feature_sql_template()
        self.feature_selected_title.setText(template.title if template else "未选择")
        has_template = template is not None
        self.edit_sql_template_button.setEnabled(has_template)
        self.delete_sql_template_button.setEnabled(has_template)
        self.feature_execute_button.setEnabled(has_template and not self._is_running())

    @Slot()
    def _new_sql_template(self) -> None:
        dialog = SqlTemplateDialog(self)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_template is not None
        ):
            self.sql_templates = load_sql_templates()
            self._refresh_sql_template_combos(dialog.saved_template.template_id)
            self._append_log(
                f"[sql-config] created: {dialog.saved_template.title}\n"
            )

    @Slot()
    def _edit_sql_template(self) -> None:
        template = self._selected_feature_sql_template()
        if template is None:
            QMessageBox.information(self, "选择 SQL", "请先选择要编辑的 SQL 模板")
            return
        dialog = SqlTemplateDialog(self, template)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_template is not None
        ):
            self.sql_templates = load_sql_templates()
            self._refresh_sql_template_combos(dialog.saved_template.template_id)
            self._append_log(
                f"[sql-config] updated: {dialog.saved_template.title}\n"
            )

    @Slot()
    def _delete_sql_template(self) -> None:
        template = self._selected_feature_sql_template()
        if template is None:
            QMessageBox.information(self, "选择 SQL", "请先选择要删除的 SQL 模板")
            return
        answer = QMessageBox.question(
            self,
            "删除 SQL 模板",
            f"确定删除「{template.title}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_sql_template(template.template_id)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "删除失败", str(error))
            return
        self.sql_templates = load_sql_templates()
        self._refresh_sql_template_combos()
        self._append_log(f"[sql-config] deleted: {template.title}\n")

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
        self.session_title = QLabel("ACCOUNT BATCH CREATE")
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
        widget = NumberInput()
        widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        widget.setRange(1, maximum)
        widget.setValue(value)
        widget.setGroupSeparatorShown(True)
        return widget

    @staticmethod
    def _platform_combo() -> QComboBox:
        widget = QComboBox()
        widget.addItem("Android", Platform.android.value)
        widget.addItem("iOS", Platform.ios.value)
        widget.setCurrentIndex(1)
        return widget

    @staticmethod
    def _add_form_row(
        layout: QGridLayout,
        row: int,
        label_text: str,
        widget: QWidget,
        suffix: str = "",
    ) -> QLabel:
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
        return label

    @Slot(bool)
    def _toggle_random_inputs(self, enabled: bool) -> None:
        self.spin_count.setEnabled(not enabled and not self._is_running())
        self.spin_min.setEnabled(enabled and not self._is_running())
        self.spin_max.setEnabled(enabled and not self._is_running())

    def _sync_execution_mode_inputs(self) -> None:
        if hasattr(self, "account_max_workers"):
            self.account_max_workers.setEnabled(
                not self._is_running()
                and self.account_batch_mode_button.isChecked()
                and self.account_parallel_button.isChecked()
            )
        if hasattr(self, "max_workers"):
            self.max_workers.setEnabled(
                not self._is_running() and self.parallel_button.isChecked()
            )
        if hasattr(self, "spin_workers"):
            self.spin_workers.setEnabled(
                not self._is_running() and self.spin_parallel_button.isChecked()
            )

    def _sync_account_creation_mode_inputs(self) -> None:
        """仅启用当前创建方式需要的账号参数。"""
        if not hasattr(self, "account_custom_email"):
            return
        editable = not self._is_running()
        is_batch = self.account_batch_mode_button.isChecked()
        self.account_count_label.setVisible(is_batch)
        self.account_count.setVisible(is_batch)
        self.account_execution_mode_label.setVisible(is_batch)
        self.account_execution_mode.setVisible(is_batch)
        self.account_max_workers_label.setVisible(is_batch)
        self.account_max_workers.setVisible(is_batch)
        self.account_custom_email_label.setVisible(not is_batch)
        self.account_custom_email.setVisible(not is_batch)
        self.account_count.setEnabled(editable)
        self.account_serial_button.setEnabled(editable)
        self.account_parallel_button.setEnabled(editable)
        self.account_custom_email.setEnabled(editable)
        self._sync_execution_mode_inputs()

    def _sync_account_channel_options(self, _environment: str = "") -> None:
        """生产环境改为手动输入，其他环境自动匹配。"""
        if not hasattr(self, "account_new_user_control"):
            return
        environment = self.account_environment.currentText()
        manual = requires_manual_channel_code(environment)
        can_enter_b = self.account_enter_b_yes_button.isChecked() and not manual
        self.account_enter_b_label.setVisible(not manual)
        self.account_enter_b_control.setVisible(not manual)
        self.account_new_user_label.setVisible(can_enter_b)
        self.account_new_user_control.setVisible(can_enter_b)
        self.account_channel_source_label.setText(
            "Channel Code" if manual else "匹配渠道源"
        )
        self.account_channel_source.setVisible(not manual)
        self.account_channel_code.setVisible(manual)
        self.account_update_parameters_button.setVisible(not manual)
        self._refresh_account_channel_source()

    def _resolve_account_channel_source(self) -> str:
        environment = self.account_environment.currentText()
        return resolve_registration_channel(
            environment,
            self.channel_sources_by_environment[environment],
            can_enter_b=self.account_enter_b_yes_button.isChecked(),
            has_new_user_offer=self.account_new_user_yes_button.isChecked(),
            preferred_sources=self.channel_codes_by_environment[environment],
            manual_channel_code=self.account_channel_code.currentText(),
        )

    @Slot()
    @Slot(str)
    def _refresh_account_channel_source(self, _value: str = "") -> None:
        """预览当前业务选项自动匹配出的渠道源。"""
        if not hasattr(self, "account_channel_source"):
            return
        if requires_manual_channel_code(self.account_environment.currentText()):
            return
        try:
            channel_source = self._resolve_account_channel_source()
        except ValueError:
            self.account_channel_source.clear()
            self.account_channel_source.setPlaceholderText("请先更新渠道参数")
        else:
            self.account_channel_source.setText(channel_source)

    def _sync_tournament_channel_options(self, _environment: str = "") -> None:
        """生产环境改为手动输入，其他环境自动匹配。"""
        if not hasattr(self, "tournament_new_user_control"):
            return
        environment = self.environment.currentText()
        manual = requires_manual_channel_code(environment)
        can_enter_b = self.tournament_enter_b_yes_button.isChecked() and not manual
        self.tournament_enter_b_label.setVisible(not manual)
        self.tournament_enter_b_control.setVisible(not manual)
        self.tournament_new_user_label.setVisible(can_enter_b)
        self.tournament_new_user_control.setVisible(can_enter_b)
        self.tournament_channel_source_label.setText(
            "Channel Code" if manual else "匹配渠道源"
        )
        self.tournament_channel_source.setVisible(not manual)
        self.tournament_channel_code.setVisible(manual)
        self.tournament_update_parameters_button.setVisible(not manual)
        self._refresh_tournament_channel_source()

    def _resolve_tournament_channel_source(self) -> str:
        environment = self.environment.currentText()
        return resolve_registration_channel(
            environment,
            self.channel_sources_by_environment[environment],
            can_enter_b=self.tournament_enter_b_yes_button.isChecked(),
            has_new_user_offer=self.tournament_new_user_yes_button.isChecked(),
            preferred_sources=self.channel_codes_by_environment[environment],
            manual_channel_code=self.tournament_channel_code.currentText(),
        )

    @Slot()
    @Slot(str)
    def _refresh_tournament_channel_source(self, _value: str = "") -> None:
        """预览锦标赛任务自动匹配出的渠道源。"""
        if not hasattr(self, "tournament_channel_source"):
            return
        if requires_manual_channel_code(self.environment.currentText()):
            return
        try:
            channel_source = self._resolve_tournament_channel_source()
        except ValueError:
            self.tournament_channel_source.clear()
            self.tournament_channel_source.setPlaceholderText("请先更新渠道参数")
        else:
            self.tournament_channel_source.setText(channel_source)

    def _update_channel_source_parameters(self, context: str = "account") -> None:
        """从当前环境日志库更新渠道源缓存。"""
        if self._is_channel_source_updating():
            return
        if context == "tournament":
            environment = self.environment.currentText()
            update_button = self.tournament_update_parameters_button
        else:
            environment = self.account_environment.currentText()
            update_button = self.account_update_parameters_button
        connection = self.database_connections_by_environment[environment]
        if not is_database_connection_configured(connection):
            QMessageBox.warning(
                self,
                "数据库未配置",
                f"请先在参数配置页完成 {environment} 环境的数据库连接配置。",
            )
            return

        self.start_button.setEnabled(False)
        self.account_update_parameters_button.setEnabled(False)
        self.tournament_update_parameters_button.setEnabled(False)
        update_button.setText("更新中…")
        self._append_log(
            f"\n[channel-source:{environment}] updating parameters\n"
        )
        self.channel_source_thread = QThread(self)
        self.channel_source_worker = ChannelSourceUpdateWorker(
            environment,
            connection,
        )
        self.channel_source_worker.moveToThread(self.channel_source_thread)
        self.channel_source_thread.started.connect(self.channel_source_worker.run)
        self.channel_source_worker.succeeded.connect(
            self._on_channel_source_update_succeeded
        )
        self.channel_source_worker.failed.connect(self._on_channel_source_update_failed)
        self.channel_source_worker.done.connect(self.channel_source_thread.quit)
        self.channel_source_worker.done.connect(self.channel_source_worker.deleteLater)
        self.channel_source_thread.finished.connect(
            self._on_channel_source_update_finished
        )
        self.channel_source_thread.finished.connect(
            self.channel_source_thread.deleteLater
        )
        self.channel_source_thread.start()

    @Slot(str, object)
    def _on_channel_source_update_succeeded(
        self,
        environment: str,
        sources: object,
    ) -> None:
        if not isinstance(sources, list):
            return
        self.channel_sources_by_environment[environment] = [
            source for source in sources if isinstance(source, ChannelSource)
        ]
        if self.account_environment.currentText() == environment:
            self._refresh_account_channel_source()
        if self.environment.currentText() == environment:
            self._refresh_tournament_channel_source()
        self._append_log(
            f"[channel-source:{environment}] cached {len(sources)} sources\n"
        )

    @Slot(str, str)
    def _on_channel_source_update_failed(
        self,
        environment: str,
        message: str,
    ) -> None:
        self._append_log(f"[channel-source:{environment}] update failed: {message}\n")
        QMessageBox.critical(self, "参数更新失败", message)

    @Slot()
    def _on_channel_source_update_finished(self) -> None:
        self.channel_source_worker = None
        self.channel_source_thread = None
        self.account_update_parameters_button.setText("更新参数")
        self.tournament_update_parameters_button.setText("更新参数")
        self.account_update_parameters_button.setEnabled(not self._is_running())
        self.tournament_update_parameters_button.setEnabled(not self._is_running())
        self.start_button.setEnabled(not self._is_running())

    def _is_channel_source_updating(self) -> bool:
        return bool(
            self.channel_source_thread and self.channel_source_thread.isRunning()
        )

    @Slot()
    def _on_account_creation_mode_changed(self) -> None:
        """切换账号创建方式并同步界面说明。"""
        self._sync_account_creation_mode_inputs()
        if not hasattr(self, "mode_hint") or self.current_section != 0:
            return
        if self.account_custom_mode_button.isChecked():
            self.mode_hint.setText("使用指定邮箱创建一个账号，并导出账号信息。")
            self.start_button.setText("创建指定账号")
            self.session_title.setText("CUSTOM ACCOUNT CREATE")
            self.eyebrow.setText("$ account / create-custom")
        else:
            self.mode_hint.setText("按原有逻辑批量注册随机邮箱账号，并导出账号信息。")
            self.start_button.setText("批量创建账号")
            self.session_title.setText("ACCOUNT BATCH CREATE")
            self.eyebrow.setText("$ account / create-batch")

    # 参数维护
    def _switch_section(self, index: int) -> None:
        self.current_section = index
        if index < len(self.navigation_buttons):
            self.navigation_buttons[index].setChecked(True)
        if index == 0:
            self.content_stack.setCurrentIndex(0)
            self.settings_stack.setCurrentIndex(0)
            self.settings_title.setText("创建账号")
            self._on_account_creation_mode_changed()
        elif index == 1:
            self.content_stack.setCurrentIndex(0)
            self.settings_stack.setCurrentIndex(1)
            self.settings_title.setText("锦标赛数据")
            self.mode_hint.setText(
                "账号和下注可分别设置串行或并行；并行下注使用独立 session。"
            )
            self.start_button.setText("生成锦标赛数据")
            self.session_title.setText("TOURNAMENT DATA")
            self.eyebrow.setText("$ tournament / generate")
        elif index == 2:
            self.content_stack.setCurrentIndex(2)
            self.eyebrow.setText("$ sql-data / generate")
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
        if environment == "prod":
            self._refresh_prod_channel_code_combo(self.account_channel_code)
            self._refresh_prod_channel_code_combo(self.tournament_channel_code)
        if self.environment.currentText() == environment:
            self._refresh_tournament_channel_source()
        if self.account_environment.currentText() == environment:
            self._refresh_account_channel_source()
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
    def _sql_binding_parameters(
        self,
        environment: str,
        combo: QComboBox,
    ) -> dict:
        template = self._selected_sql_template(combo)
        if template is None:
            return {}
        connection = self.database_connections_by_environment[environment]
        if not is_database_connection_configured(connection):
            raise ValueError(
                f"绑定 SQL 前请先完成 {environment} 环境的数据库配置"
            )
        return {
            "sql_template": template,
            "database_connection": connection,
        }

    def _parameters(self) -> tuple[Callable[..., int], dict, str]:
        """校验当前页面并生成任务参数。"""
        if self.current_section == 0:
            output_path = Path(self.account_output_file.text()).expanduser()
            if not output_path.name:
                raise ValueError("请选择输出文件")
            common_parameters = {
                "environment": self.account_environment.currentText(),
                "platform": self.account_platform.currentData(),
                "channel_code": self._resolve_account_channel_source(),
                "output_file": output_path,
                "verbose": self.account_verbose.isChecked(),
                **self._sql_binding_parameters(
                    self.account_environment.currentText(),
                    self.account_sql_template,
                ),
            }
            if self.account_custom_mode_button.isChecked():
                return (
                    create_custom_account,
                    {
                        **common_parameters,
                        "email": validate_custom_email(
                            self.account_custom_email.text()
                        ),
                    },
                    "create-custom-account",
                )
            return (
                create_accounts,
                {
                    **common_parameters,
                    "count": self.account_count.value(),
                    "max_workers": (
                        self.account_max_workers.value()
                        if self.account_parallel_button.isChecked()
                        else 1
                    ),
                },
                "create-accounts-batch",
            )

        if self.current_section == 2:
            environment = self.feature_environment.currentText()
            template = self._selected_feature_sql_template()
            if template is None:
                raise ValueError("请先从列表选择 SQL 模板")
            connection = self.database_connections_by_environment[environment]
            if not is_database_connection_configured(connection):
                raise ValueError(
                    f"请先完成 {environment} 环境的数据库配置"
                )
            return (
                generate_feature_data,
                {
                    "template": template,
                    "user_id": self.feature_user_id.value(),
                    "connection": connection,
                },
                "generate-feature-data",
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
            "max_workers": (
                self.max_workers.value() if self.parallel_button.isChecked() else 1
            ),
            "spin_workers": (
                self.spin_workers.value()
                if self.spin_parallel_button.isChecked()
                else 1
            ),
            "spin_count": self.spin_count.value(),
            "spin_count_range": None,
            "environment": self.environment.currentText(),
            "platform": self.platform.currentData(),
            "channel_code": self._resolve_tournament_channel_source(),
            "output_file": output_path,
            "verbose": self.verbose.isChecked(),
            **self._sql_binding_parameters(
                self.environment.currentText(),
                self.tournament_sql_template,
            ),
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

        output_file = parameters.get("output_file")
        if output_file is not None and output_file.exists():
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
        self._set_status("●  RUNNING", "#228653")
        total_count = parameters.get("count", 1)
        self.progress.setRange(0, total_count)
        self.progress.setValue(0)
        self.progress_text.setText(f"0 / {total_count}  ·  OK 0")
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
        self.feature_stop_button.setEnabled(False)
        self._set_status("●  STOPPING", "#a66b13")
        self._append_log("\n[signal] stop requested; waiting for active requests\n")

    @Slot(int, int, int)
    def _on_progress(self, completed: int, total: int, successful: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(completed)
        self.progress_text.setText(f"{completed} / {total}  ·  OK {successful}")
        self._set_status(
            f"●  RUNNING  {completed}/{total}  OK {successful}",
            "#228653",
        )

    @Slot(int, bool)
    def _on_completed(self, successful: int, cancelled: bool) -> None:
        if cancelled:
            self._set_status(f"●  STOPPED  OK {successful}", "#a66b13")
            self._append_log("[stopped] workflow cancelled\n")
        else:
            self._set_status(f"●  DONE  OK {successful}", "#228653")
            self._append_log("[done] workflow completed\n")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_status("●  FAILED", "#c43d47")
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
        target = self.feature_log if self.current_section == 2 else self.log
        cursor = target.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        target.setTextCursor(cursor)
        target.ensureCursorVisible()

    @Slot()
    def _clear_log(self) -> None:
        if self.current_section == 2:
            self.feature_log.clear()
        else:
            self.log.clear()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.feature_stop_button.setEnabled(running)
        for button in self.navigation_buttons:
            button.setEnabled(not running)
        for widget in self.config_widgets:
            widget.setEnabled(not running)
        if not running:
            self._on_feature_sql_selection_changed()
            self._toggle_random_inputs(self.random_spins.isChecked())
            self._sync_account_creation_mode_inputs()
            self._sync_execution_mode_inputs()

    def _is_running(self) -> bool:
        return bool(self.worker_thread and self.worker_thread.isRunning())

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def closeEvent(self, event: QCloseEvent) -> None:
        """任务运行时确认停止后再关闭窗口。"""
        if self._is_channel_source_updating():
            QMessageBox.information(
                self,
                "正在更新参数",
                "渠道参数更新结束后才能退出。",
            )
            event.ignore()
            return
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
