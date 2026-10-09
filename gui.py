"""自动化测试数据桌面控制台。"""

import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from base import spin
from base.account_batch import (
    create_accounts,
    create_custom_account,
    validate_custom_email,
)
from base.apk_manager import (
    AndroidDevice,
    ApkInstallResult,
    CachedApk,
    attribute_and_install,
    cache_apk,
    install_apk,
    list_android_devices,
    load_cached_apks,
    open_attribution_url,
    reinstall_apk,
    remove_cached_apk,
    update_cached_apk,
)
from base.android_log import (
    AndroidLogCapture,
    LogcatCaptureConfig,
    list_installed_packages,
)
from base.ipa_manager import (
    CachedIpa,
    IosDevice,
    IpaInstallResult,
    attribute_and_install_ipa,
    cache_ipa,
    download_and_cache_ipa,
    install_ipa,
    list_ios_devices,
    load_cached_ipas,
    open_ios_attribution_url,
    remove_cached_ipa,
    update_cached_ipa,
)
from base.api_request import (
    ApiTemplate,
    delete_api_template,
    load_environment_api_base_url,
    load_api_templates,
    parse_runtime_parameters,
    save_api_template,
    send_api_request,
    template_parameter_names,
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
from base.feature_scenario import (
    ASSERT_OPERATORS,
    FeatureScenario,
    ScenarioStep,
    delete_feature_scenario,
    load_feature_scenarios,
    new_step,
    run_feature_scenario,
    save_feature_scenario,
    scenario_needs_database,
)
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


SECTION_INFO = (
    ("数据准备", "账号生成", "批量生成测试账号，或使用指定邮箱创建单个账号。"),
    ("数据准备", "锦标赛造数", "创建参赛账号并完成充值、下注等锦标赛数据准备。"),
    ("接口与流程", "SQL 数据模板", "维护并执行可复用 SQL，用于快速准备业务测试数据。"),
    ("接口与流程", "API 请求模板", "保存、调试并复用环境化的 HTTP 请求。"),
    ("接口与流程", "自动化场景", "把 SQL、API、变量提取和断言编排为完整流程。"),
    ("设备工具", "Android 安装", "管理 APK 缓存，并对 Android 设备执行归因与安装。"),
    ("设备工具", "iOS 安装", "管理 IPA 缓存，并对 iPhone 执行归因与安装。"),
    ("设备工具", "Android 日志", "按应用、级别和关键词抓取并导出设备日志。"),
    ("系统", "环境与参数", "维护环境渠道参数、数据库连接和 SSH 私钥。"),
)


APP_STYLESHEET = """
QWidget {
    color: #20242a;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QWidget#root { background: #f3f5f8; }
QDialog, QMessageBox { background: #ffffff; }
QFrame#topBar {
    background: #ffffff;
    border: 1px solid #dfe3e8;
    border-radius: 12px;
}

QLabel#title { color: #17191d; font-size: 23px; font-weight: 700; }
QLabel#sectionTitle { color: #20242a; font-size: 15px; font-weight: 650; }
QLabel#fieldLabel { color: #5d6470; font-size: 12px; }
QLabel#pageDescription, QLabel#terminalMeta, QLabel#fieldHint,
QLabel#navigationMeta {
    color: #808792;
    font-size: 11px;
}
QLabel#pageDescription { font-size: 12px; }
QLabel#navigationMeta, QLabel#terminalMeta {
    font-family: "Cascadia Mono", "Consolas";
}
QLabel#navigationBrand, QLabel#sessionTitle {
    color: #17191d;
    font-weight: 700;
}
QLabel#navigationBrand { font-size: 17px; }
QLabel#sessionTitle { font-family: "Cascadia Mono", "Consolas"; font-size: 13px; }
QLabel#navigationGroup {
    color: #8a919c;
    font-size: 10px;
    font-weight: 700;
    padding: 10px 10px 3px 10px;
}
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
    min-height: 38px;
    color: #656c76;
    background: transparent;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 6px;
    padding: 0 12px;
    text-align: left;
}
QPushButton#navigationButton:hover {
    color: #17191d;
    background: #f2f4f7;
}
QPushButton#navigationButton:checked {
    color: #2846a6;
    background: #edf1ff;
    border-left: 3px solid #4b67d1;
    font-weight: 700;
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
QPlainTextEdit#longTextInput {
    color: #20242a;
    background: #ffffff;
    border: 1px solid #cfd4db;
    border-radius: 7px;
    padding: 8px 10px;
    selection-color: #ffffff;
    selection-background-color: #343a42;
}
QPlainTextEdit#longTextInput:hover { border-color: #9fa7b2; }
QPlainTextEdit#longTextInput:focus { border-color: #343a42; }
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
QTableWidget#apkTable {
    color: #30363d;
    background: #ffffff;
    alternate-background-color: #f8f9fa;
    border: 1px solid #d6dbe1;
    border-radius: 7px;
    gridline-color: #e4e7eb;
}
QTableWidget#apkTable::item { padding: 6px; }
QTableWidget#apkTable QHeaderView::section {
    color: #5d6470;
    background: #f3f5f7;
    border: 0;
    border-bottom: 1px solid #d6dbe1;
    padding: 8px;
    font-size: 12px;
    font-weight: 600;
}
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


class ApkActionWorker(QObject):
    """在后台执行单个移动设备操作，避免阻塞界面。"""

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
            self.ssh_private_key.addItem("请先在“环境与参数”中导入私钥", None)
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


class ApiTemplateDialog(QDialog):
    """新增或编辑一条可复用 API 请求模板。"""

    def __init__(
        self,
        parent: QWidget,
        template: Optional[ApiTemplate] = None,
    ) -> None:
        super().__init__(parent)
        self.template = template
        self.saved_template: Optional[ApiTemplate] = None
        self.setWindowTitle("编辑 API 模板" if template else "新增 API 模板")
        self.resize(780, 680)
        self.setMinimumSize(640, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        title_label = QLabel("标题")
        title_label.setObjectName("fieldLabel")
        layout.addWidget(title_label)
        self.title_input = QLineEdit(template.title if template else "")
        self.title_input.setPlaceholderText("例如：查询用户信息")
        layout.addWidget(self.title_input)

        request_row = QHBoxLayout()
        self.method_input = QComboBox()
        self.method_input.addItems(["GET", "POST", "PUT", "PATCH", "DELETE"])
        if template:
            self.method_input.setCurrentText(template.method)
        self.method_input.setFixedWidth(110)
        request_row.addWidget(self.method_input)
        self.url_input = QLineEdit(template.url if template else "")
        self.url_input.setPlaceholderText("/v1/user/{{userid}}")
        request_row.addWidget(self.url_input, 1)
        layout.addLayout(request_row)

        headers_label = QLabel("Headers（JSON 对象）")
        headers_label.setObjectName("fieldLabel")
        layout.addWidget(headers_label)
        self.headers_input = QPlainTextEdit()
        self.headers_input.setPlaceholderText(
            '{"Content-Type":"application/json","Authorization":"Bearer {{token}}"}'
        )
        self.headers_input.setPlainText(template.headers if template else "{}")
        self.headers_input.setMaximumHeight(130)
        layout.addWidget(self.headers_input)

        body_label = QLabel("Body（可留空）")
        body_label.setObjectName("fieldLabel")
        layout.addWidget(body_label)
        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText('{"user_id":{{userid}}}')
        self.body_input.setPlainText(template.body if template else "")
        layout.addWidget(self.body_input, 1)

        timeout_row = QHBoxLayout()
        timeout_label = QLabel("超时时间（秒）")
        timeout_label.setObjectName("fieldLabel")
        timeout_row.addWidget(timeout_label)
        self.timeout_input = NumberInput()
        self.timeout_input.setRange(1, 300)
        self.timeout_input.setValue(template.timeout if template else 30)
        self.timeout_input.setFixedWidth(110)
        timeout_row.addWidget(self.timeout_input)
        timeout_row.addStretch()
        layout.addLayout(timeout_row)

        hint = QLabel(
            "接口路径以 / 开头时会自动使用发送页所选环境的 domain；完整 URL 固定域名。"
            "路径、Headers 和 Body 均可使用 {{参数名}}。"
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
            self.saved_template = save_api_template(
                self.title_input.text(),
                self.method_input.currentText(),
                self.url_input.text(),
                self.headers_input.toPlainText(),
                self.body_input.toPlainText(),
                self.timeout_input.value(),
                template_id=self.template.template_id if self.template else None,
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.accept()


STEP_TYPE_LABELS = {
    "sql": "SQL",
    "api": "API",
    "extract": "提取变量",
    "assert": "断言",
}
ASSERT_OPERATOR_LABELS = {
    "equals": "等于",
    "not_equals": "不等于",
    "exists": "字段存在",
    "not_exists": "字段不存在",
    "contains": "包含",
    "greater_than": "大于",
    "less_than": "小于",
}


class ScenarioStepDialog(QDialog):
    """新增或编辑一个场景步骤。"""

    def __init__(
        self,
        parent: QWidget,
        step_type: str,
        sql_templates: list[SqlTemplate],
        api_templates: list[ApiTemplate],
        step: Optional[ScenarioStep] = None,
    ) -> None:
        super().__init__(parent)
        self.step_type = step_type
        self.original_step = step
        self.saved_step: Optional[ScenarioStep] = None
        self.setWindowTitle(
            f"{'编辑' if step else '新增'}{STEP_TYPE_LABELS[step_type]}步骤"
        )
        self.resize(540, 330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(11)

        title_label = QLabel("步骤标题")
        title_label.setObjectName("fieldLabel")
        layout.addWidget(title_label)
        default_title = STEP_TYPE_LABELS[step_type]
        self.title_input = QLineEdit(step.title if step else default_title)
        layout.addWidget(self.title_input)

        config = step.config if step else {}
        if step_type == "sql":
            label = QLabel("SQL 模板")
            label.setObjectName("fieldLabel")
            layout.addWidget(label)
            self.template_input = SearchableComboBox()
            for template in sql_templates:
                self.template_input.addItem(template.title, template.template_id)
            selected = self.template_input.findData(config.get("template_id"))
            if selected >= 0:
                self.template_input.setCurrentIndex(selected)
            layout.addWidget(self.template_input)
        elif step_type == "api":
            label = QLabel("API 模板")
            label.setObjectName("fieldLabel")
            layout.addWidget(label)
            self.template_input = SearchableComboBox()
            for template in api_templates:
                self.template_input.addItem(
                    f"{template.method} · {template.title}",
                    template.template_id,
                )
            selected = self.template_input.findData(config.get("template_id"))
            if selected >= 0:
                self.template_input.setCurrentIndex(selected)
            layout.addWidget(self.template_input)
        elif step_type == "extract":
            path_label = QLabel("来源字段路径")
            path_label.setObjectName("fieldLabel")
            layout.addWidget(path_label)
            self.path_input = QLineEdit(str(config.get("path", "")))
            self.path_input.setPlaceholderText("例如：response.data.order_id")
            layout.addWidget(self.path_input)
            variable_label = QLabel("保存为变量")
            variable_label.setObjectName("fieldLabel")
            layout.addWidget(variable_label)
            self.variable_input = QLineEdit(str(config.get("variable", "")))
            self.variable_input.setPlaceholderText("例如：order_id")
            layout.addWidget(self.variable_input)
        else:
            path_label = QLabel("实际值字段路径")
            path_label.setObjectName("fieldLabel")
            layout.addWidget(path_label)
            self.path_input = QLineEdit(str(config.get("path", "")))
            self.path_input.setPlaceholderText("例如：response.code")
            layout.addWidget(self.path_input)
            assertion_row = QHBoxLayout()
            self.operator_input = QComboBox()
            for operator in ASSERT_OPERATORS:
                self.operator_input.addItem(
                    ASSERT_OPERATOR_LABELS[operator],
                    operator,
                )
            selected = self.operator_input.findData(config.get("operator"))
            if selected >= 0:
                self.operator_input.setCurrentIndex(selected)
            assertion_row.addWidget(self.operator_input)
            self.expected_input = QLineEdit(
                "" if config.get("expected") is None else str(config.get("expected"))
            )
            self.expected_input.setPlaceholderText("期望值，可使用 {{变量名}}")
            assertion_row.addWidget(self.expected_input, 1)
            layout.addLayout(assertion_row)
            self.operator_input.currentIndexChanged.connect(
                self._sync_expected_input
            )
            self._sync_expected_input()

        self.cleanup_input = QCheckBox("作为清理步骤（前面失败后仍会执行）")
        self.cleanup_input.setChecked(step.cleanup if step else False)
        layout.addWidget(self.cleanup_input)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        save_button = QPushButton("保存步骤")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def _sync_expected_input(self) -> None:
        if not hasattr(self, "expected_input"):
            return
        self.expected_input.setEnabled(
            self.operator_input.currentData() not in ("exists", "not_exists")
        )

    @Slot()
    def _save(self) -> None:
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.critical(self, "参数错误", "步骤标题不能为空")
            return
        if self.step_type in ("sql", "api"):
            template_id = self.template_input.currentData()
            if not template_id:
                QMessageBox.critical(self, "参数错误", "请先创建并选择模板")
                return
            config = {"template_id": template_id}
        elif self.step_type == "extract":
            path = self.path_input.text().strip()
            variable = self.variable_input.text().strip()
            if not path or not variable:
                QMessageBox.critical(self, "参数错误", "字段路径和变量名不能为空")
                return
            config = {"path": path, "variable": variable}
        else:
            path = self.path_input.text().strip()
            if not path:
                QMessageBox.critical(self, "参数错误", "字段路径不能为空")
                return
            config = {
                "path": path,
                "operator": self.operator_input.currentData(),
                "expected": self.expected_input.text(),
            }
        created = new_step(
            self.step_type,
            title,
            config,
            cleanup=self.cleanup_input.isChecked(),
        )
        self.saved_step = (
            ScenarioStep(
                self.original_step.step_id,
                created.step_type,
                created.title,
                created.config,
                created.cleanup,
            )
            if self.original_step
            else created
        )
        self.accept()


class FeatureScenarioDialog(QDialog):
    """通过有序步骤列表新增或编辑功能场景。"""

    def __init__(
        self,
        parent: QWidget,
        sql_templates: list[SqlTemplate],
        api_templates: list[ApiTemplate],
        scenario: Optional[FeatureScenario] = None,
    ) -> None:
        super().__init__(parent)
        self.scenario = scenario
        self.sql_templates = sql_templates
        self.api_templates = api_templates
        self.steps = list(scenario.steps) if scenario else []
        self.saved_scenario: Optional[FeatureScenario] = None
        self.setWindowTitle("编辑自动化场景" if scenario else "新增自动化场景")
        self.resize(760, 610)
        self.setMinimumSize(650, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        title_label = QLabel("场景标题")
        title_label.setObjectName("fieldLabel")
        layout.addWidget(title_label)
        self.title_input = QLineEdit(scenario.title if scenario else "")
        self.title_input.setPlaceholderText("例如：广告触发与状态校验")
        layout.addWidget(self.title_input)

        step_label = QLabel("执行步骤（按列表顺序运行）")
        step_label.setObjectName("fieldLabel")
        layout.addWidget(step_label)
        self.step_list = QListWidget()
        self.step_list.setObjectName("channelCodeList")
        self.step_list.itemDoubleClicked.connect(lambda _item: self._edit_step())
        layout.addWidget(self.step_list, 1)

        add_buttons = QHBoxLayout()
        for label, step_type in (
            ("+ SQL", "sql"),
            ("+ API", "api"),
            ("+ 提取", "extract"),
            ("+ 断言", "assert"),
        ):
            button = QPushButton(label)
            button.setObjectName("secondaryButton")
            button.clicked.connect(
                lambda _checked=False, selected=step_type: self._add_step(selected)
            )
            add_buttons.addWidget(button)
        add_buttons.addStretch()
        layout.addLayout(add_buttons)

        manage_buttons = QHBoxLayout()
        edit_button = QPushButton("编辑步骤")
        edit_button.setObjectName("secondaryButton")
        edit_button.clicked.connect(self._edit_step)
        manage_buttons.addWidget(edit_button)
        delete_button = QPushButton("删除步骤")
        delete_button.setObjectName("stopButton")
        delete_button.clicked.connect(self._delete_step)
        manage_buttons.addWidget(delete_button)
        up_button = QPushButton("上移")
        up_button.setObjectName("secondaryButton")
        up_button.clicked.connect(lambda: self._move_step(-1))
        manage_buttons.addWidget(up_button)
        down_button = QPushButton("下移")
        down_button.setObjectName("secondaryButton")
        down_button.clicked.connect(lambda: self._move_step(1))
        manage_buttons.addWidget(down_button)
        manage_buttons.addStretch()
        layout.addLayout(manage_buttons)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        save_button = QPushButton("保存场景")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)
        self._refresh_steps()

    def _refresh_steps(self, selected: int = -1) -> None:
        self.step_list.clear()
        for index, step in enumerate(self.steps, 1):
            cleanup = "清理 · " if step.cleanup else ""
            self.step_list.addItem(
                f"{index}. {cleanup}{STEP_TYPE_LABELS[step.step_type]} · {step.title}"
            )
        if self.steps:
            self.step_list.setCurrentRow(
                min(max(0, selected), len(self.steps) - 1)
            )

    def _add_step(self, step_type: str) -> None:
        dialog = ScenarioStepDialog(
            self,
            step_type,
            self.sql_templates,
            self.api_templates,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_step:
            self.steps.append(dialog.saved_step)
            self._refresh_steps(len(self.steps) - 1)

    def _edit_step(self) -> None:
        row = self.step_list.currentRow()
        if row < 0:
            return
        step = self.steps[row]
        dialog = ScenarioStepDialog(
            self,
            step.step_type,
            self.sql_templates,
            self.api_templates,
            step,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_step:
            self.steps[row] = dialog.saved_step
            self._refresh_steps(row)

    def _delete_step(self) -> None:
        row = self.step_list.currentRow()
        if row < 0:
            return
        self.steps.pop(row)
        self._refresh_steps(row)

    def _move_step(self, offset: int) -> None:
        row = self.step_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= len(self.steps):
            return
        self.steps[row], self.steps[target] = self.steps[target], self.steps[row]
        self._refresh_steps(target)

    @Slot()
    def _save(self) -> None:
        try:
            self.saved_scenario = save_feature_scenario(
                self.title_input.text(),
                self.steps,
                scenario_id=self.scenario.scenario_id if self.scenario else None,
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.accept()


class CachedApkDialog(QDialog):
    """编辑缓存安装包的名称、归因链接和备注。"""

    def __init__(self, package: CachedApk | CachedIpa, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑缓存安装包")
        self.setModal(True)
        self.resize(560, 330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("编辑缓存安装包")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.name_input = QLineEdit(package.name)
        self.attribution_input = QPlainTextEdit(package.attribution)
        self.attribution_input.setObjectName("longTextInput")
        self.attribution_input.setFixedHeight(90)
        self.attribution_input.setPlaceholderText("https://...")
        self.note_input = QLineEdit(package.note)
        self.note_input.setPlaceholderText("例如：渠道、环境或版本说明")
        WorkflowWindow._add_form_row(form, 0, "安装包名称", self.name_input)
        WorkflowWindow._add_form_row(form, 1, "归因链接", self.attribution_input)
        WorkflowWindow._add_form_row(form, 2, "备注", self.note_input)
        layout.addLayout(form)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("保存修改")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def values(self) -> tuple[str, str, str]:
        return (
            self.name_input.text().strip(),
            self.attribution_input.toPlainText().strip(),
            self.note_input.text().strip(),
        )


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
        self.apk_action_thread: Optional[QThread] = None
        self.apk_action_worker: Optional[ApkActionWorker] = None
        self.pending_apk_action: Optional[
            tuple[str, Callable[[], object], Callable[[object], None]]
        ] = None
        self.ios_action_thread: Optional[QThread] = None
        self.ios_action_worker: Optional[ApkActionWorker] = None
        self.app_log_query_thread: Optional[QThread] = None
        self.app_log_query_worker: Optional[ApkActionWorker] = None
        self.app_log_thread: Optional[QThread] = None
        self.app_log_worker: Optional[AndroidLogWorker] = None
        self.app_log_stop_requested = False
        self.app_log_capture_failed = False
        self.close_after_log_stop = False
        self.close_after_stop = False
        self.exit_after_workers_stop = False
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
        self.api_templates = load_api_templates()
        self.feature_scenarios = load_feature_scenarios()
        self.cached_apks = load_cached_apks()
        self.android_devices: Dict[str, AndroidDevice] = {}
        self.last_apk_device_error = ""
        self.cached_ipas = load_cached_ipas()
        self.ios_devices: Dict[str, IosDevice] = {}
        self.last_ios_device_error = ""
        self.app_log_devices: Dict[str, AndroidDevice] = {}

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.setStyleSheet(APP_STYLESHEET)

        page = QHBoxLayout(root)
        page.setContentsMargins(18, 18, 18, 18)
        page.setSpacing(18)
        page.addWidget(self._build_navigation())

        workspace = QVBoxLayout()
        workspace.setSpacing(14)
        workspace.addWidget(self._build_top_bar())
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_task_workspace())
        self.content_stack.addWidget(self._build_config_workspace())
        self.content_stack.addWidget(self._build_feature_workspace())
        self.content_stack.addWidget(self._build_api_workspace())
        self.content_stack.addWidget(self._build_scenario_workspace())
        self.content_stack.addWidget(self._build_apk_workspace())
        self.content_stack.addWidget(self._build_ipa_workspace())
        self.content_stack.addWidget(self._build_app_log_workspace())
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
        bar.setFixedHeight(94)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 15, 20, 15)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.page_title = QLabel(SECTION_INFO[0][1])
        self.page_title.setObjectName("title")
        self.page_description = QLabel(SECTION_INFO[0][2])
        self.page_description.setObjectName("pageDescription")
        self.page_description.setWordWrap(True)
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_description)
        layout.addLayout(titles)
        layout.addStretch()

        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _build_navigation(self) -> QFrame:
        navigation = QFrame()
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(214)
        layout = QVBoxLayout(navigation)
        layout.setContentsMargins(12, 22, 12, 14)
        layout.setSpacing(3)

        brand = QLabel("自动化控制台")
        brand.setObjectName("navigationBrand")
        layout.addWidget(brand)
        meta = QLabel("TEST OPERATIONS")
        meta.setObjectName("navigationMeta")
        layout.addWidget(meta)
        layout.addSpacing(12)

        group = QButtonGroup(navigation)
        group.setExclusive(True)
        current_group = None
        for index, (group_name, label, _description) in enumerate(SECTION_INFO):
            if group_name != current_group:
                group_label = QLabel(group_name)
                group_label.setObjectName("navigationGroup")
                layout.addWidget(group_label)
                current_group = group_name
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

        version = QLabel("LOCAL  ·  v2.3")
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
        title = QLabel("环境参数")
        title.setObjectName("sectionTitle")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._build_config_tab(), 1)
        layout.addWidget(panel)
        return page

    def _build_apk_workspace(self) -> QWidget:
        """构建设备检测、APK 缓存、归因和安装页面。"""
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        device_card = QFrame()
        device_card.setObjectName("configCard")
        device_layout = QVBoxLayout(device_card)
        device_layout.setContentsMargins(20, 18, 20, 18)
        device_title = QLabel("Android 设备")
        device_title.setObjectName("sectionTitle")
        device_layout.addWidget(device_title)
        device_row = QHBoxLayout()
        self.apk_device_combo = QComboBox()
        self.apk_device_combo.addItem("正在检测 ADB 设备…", "")
        device_row.addWidget(self.apk_device_combo, 1)
        self.apk_refresh_button = QPushButton("刷新")
        self.apk_refresh_button.setObjectName("secondaryButton")
        self.apk_refresh_button.clicked.connect(self._refresh_android_devices)
        device_row.addWidget(self.apk_refresh_button)
        device_layout.addLayout(device_row)
        self.apk_device_hint = QLabel("请开启 USB 调试并允许当前电脑调试。")
        self.apk_device_hint.setObjectName("fieldHint")
        self.apk_device_hint.setWordWrap(True)
        device_layout.addWidget(self.apk_device_hint)
        top_row.addWidget(device_card, 1)

        import_card = QFrame()
        import_card.setObjectName("configCard")
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(20, 18, 20, 18)
        import_title = QLabel("添加安装包缓存")
        import_title.setObjectName("sectionTitle")
        import_layout.addWidget(import_title)
        file_row = QHBoxLayout()
        self.apk_source_path = QLineEdit()
        self.apk_source_path.setReadOnly(True)
        self.apk_source_path.setPlaceholderText("选择一个 APK 文件")
        file_row.addWidget(self.apk_source_path, 1)
        self.apk_choose_button = QPushButton("选择 APK")
        self.apk_choose_button.setObjectName("secondaryButton")
        self.apk_choose_button.clicked.connect(self._choose_apk)
        file_row.addWidget(self.apk_choose_button)
        import_layout.addLayout(file_row)
        attribution_row = QHBoxLayout()
        self.apk_attribution_input = QPlainTextEdit()
        self.apk_attribution_input.setObjectName("longTextInput")
        self.apk_attribution_input.setFixedHeight(58)
        self.apk_attribution_input.setPlaceholderText("关联归因链接（可选）")
        attribution_row.addWidget(self.apk_attribution_input, 1)
        self.apk_cache_button = QPushButton("缓存并添加")
        self.apk_cache_button.setObjectName("primaryButton")
        self.apk_cache_button.clicked.connect(self._cache_selected_apk)
        attribution_row.addWidget(self.apk_cache_button)
        import_layout.addLayout(attribution_row)
        top_row.addWidget(import_card, 1)
        layout.addLayout(top_row)

        package_card = QFrame()
        package_card.setObjectName("configCard")
        package_layout = QVBoxLayout(package_card)
        package_layout.setContentsMargins(20, 18, 20, 18)
        package_header = QHBoxLayout()
        package_title = QLabel("已缓存安装包")
        package_title.setObjectName("sectionTitle")
        package_header.addWidget(package_title)
        package_header.addStretch()
        self.apk_package_count = QLabel("0 个")
        self.apk_package_count.setObjectName("fieldHint")
        package_header.addWidget(self.apk_package_count)
        package_layout.addLayout(package_header)

        self.apk_table = QTableWidget(0, 4)
        self.apk_table.setObjectName("apkTable")
        self.apk_table.setHorizontalHeaderLabels(
            ("安装包", "MD5 / 备注", "归因链接", "操作")
        )
        self.apk_table.setAlternatingRowColors(True)
        self.apk_table.setWordWrap(False)
        self.apk_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.apk_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.apk_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.apk_table.verticalHeader().setVisible(False)
        self.apk_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.apk_table.horizontalHeader().resizeSection(0, 195)
        self.apk_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.apk_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.apk_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.apk_table.setMinimumHeight(260)
        package_layout.addWidget(self.apk_table, 1)

        self.apk_log = QPlainTextEdit()
        self.apk_log.setObjectName("terminal")
        self.apk_log.setReadOnly(True)
        self.apk_log.setMaximumHeight(115)
        self.apk_log.document().setMaximumBlockCount(1000)
        self.apk_log.setPlainText("runner@local:~$ adb ready\n")
        package_layout.addWidget(self.apk_log)
        layout.addWidget(package_card, 1)

        self.apk_controls = (
            self.apk_device_combo,
            self.apk_refresh_button,
            self.apk_choose_button,
            self.apk_source_path,
            self.apk_attribution_input,
            self.apk_cache_button,
            self.apk_table,
        )
        self._refresh_apk_table()
        return page

    def _build_ipa_workspace(self) -> QWidget:
        """构建 IPA 下载、缓存、归因和真机安装页面。"""
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        device_card = QFrame()
        device_card.setObjectName("configCard")
        device_layout = QVBoxLayout(device_card)
        device_layout.setContentsMargins(20, 18, 20, 18)
        device_title = QLabel("iOS 设备")
        device_title.setObjectName("sectionTitle")
        device_layout.addWidget(device_title)
        device_row = QHBoxLayout()
        self.ios_device_combo = QComboBox()
        self.ios_device_combo.addItem("正在检测 iOS 设备…", "")
        device_row.addWidget(self.ios_device_combo, 1)
        self.ios_refresh_button = QPushButton("刷新")
        self.ios_refresh_button.setObjectName("secondaryButton")
        self.ios_refresh_button.clicked.connect(self._refresh_ios_devices)
        device_row.addWidget(self.ios_refresh_button)
        device_layout.addLayout(device_row)
        self.ios_device_hint = QLabel(
            "请连接并解锁 iPhone、信任此电脑；归因需开启 Safari 高级设置中的 Web 检查器，并打开普通网页标签页。"
        )
        self.ios_device_hint.setObjectName("fieldHint")
        self.ios_device_hint.setWordWrap(True)
        device_layout.addWidget(self.ios_device_hint)
        top_row.addWidget(device_card, 1)

        import_card = QFrame()
        import_card.setObjectName("configCard")
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(20, 18, 20, 18)
        import_title = QLabel("下载或导入 IPA")
        import_title.setObjectName("sectionTitle")
        import_layout.addWidget(import_title)
        file_row = QHBoxLayout()
        self.ipa_source_path = QLineEdit()
        self.ipa_source_path.setReadOnly(True)
        self.ipa_source_path.setPlaceholderText("选择本地 IPA，或在下方填写下载地址")
        file_row.addWidget(self.ipa_source_path, 1)
        self.ipa_choose_button = QPushButton("选择 IPA")
        self.ipa_choose_button.setObjectName("secondaryButton")
        self.ipa_choose_button.clicked.connect(self._choose_ipa)
        file_row.addWidget(self.ipa_choose_button)
        import_layout.addLayout(file_row)
        self.ipa_download_url = QLineEdit()
        self.ipa_download_url.setPlaceholderText("https://.../package.ipa（与本地文件二选一）")
        import_layout.addWidget(self.ipa_download_url)
        attribution_row = QHBoxLayout()
        self.ipa_attribution_input = QPlainTextEdit()
        self.ipa_attribution_input.setObjectName("longTextInput")
        self.ipa_attribution_input.setFixedHeight(52)
        self.ipa_attribution_input.setPlaceholderText("关联归因链接（可选）")
        attribution_row.addWidget(self.ipa_attribution_input, 1)
        self.ipa_cache_button = QPushButton("添加缓存")
        self.ipa_cache_button.setObjectName("primaryButton")
        self.ipa_cache_button.clicked.connect(self._cache_selected_ipa)
        attribution_row.addWidget(self.ipa_cache_button)
        import_layout.addLayout(attribution_row)
        top_row.addWidget(import_card, 1)
        layout.addLayout(top_row)

        package_card = QFrame()
        package_card.setObjectName("configCard")
        package_layout = QVBoxLayout(package_card)
        package_layout.setContentsMargins(20, 18, 20, 18)
        package_header = QHBoxLayout()
        package_title = QLabel("已缓存的 IPA")
        package_title.setObjectName("sectionTitle")
        package_header.addWidget(package_title)
        package_header.addStretch()
        self.ipa_package_count = QLabel("0 个")
        self.ipa_package_count.setObjectName("fieldHint")
        package_header.addWidget(self.ipa_package_count)
        package_layout.addLayout(package_header)

        self.ipa_table = QTableWidget(0, 4)
        self.ipa_table.setObjectName("apkTable")
        self.ipa_table.setHorizontalHeaderLabels(
            ("安装包", "包信息 / 备注", "归因链接", "操作")
        )
        self.ipa_table.setAlternatingRowColors(True)
        self.ipa_table.setWordWrap(False)
        self.ipa_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.ipa_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ipa_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.ipa_table.verticalHeader().setVisible(False)
        self.ipa_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.ipa_table.horizontalHeader().resizeSection(0, 195)
        self.ipa_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.ipa_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.ipa_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.ipa_table.setMinimumHeight(250)
        package_layout.addWidget(self.ipa_table, 1)

        self.ipa_log = QPlainTextEdit()
        self.ipa_log.setObjectName("terminal")
        self.ipa_log.setReadOnly(True)
        self.ipa_log.setMaximumHeight(115)
        self.ipa_log.document().setMaximumBlockCount(1000)
        self.ipa_log.setPlainText("runner@local:~$ tidevice ready\n")
        package_layout.addWidget(self.ipa_log)
        layout.addWidget(package_card, 1)

        self.ipa_controls = (
            self.ios_device_combo,
            self.ios_refresh_button,
            self.ipa_choose_button,
            self.ipa_source_path,
            self.ipa_download_url,
            self.ipa_attribution_input,
            self.ipa_cache_button,
            self.ipa_table,
        )
        self._refresh_ipa_table()
        return page

    def _build_app_log_workspace(self) -> QWidget:
        """构建 Android 设备与应用 Logcat 实时抓取页面。"""
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        settings_card = QFrame()
        settings_card.setObjectName("configCard")
        settings_layout = QGridLayout(settings_card)
        settings_layout.setContentsMargins(20, 18, 20, 18)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(10)

        title = QLabel("Android 应用日志")
        title.setObjectName("sectionTitle")
        settings_layout.addWidget(title, 0, 0, 1, 4)

        device_label = QLabel("设备")
        device_label.setObjectName("fieldLabel")
        settings_layout.addWidget(device_label, 1, 0)
        self.app_log_device_combo = QComboBox()
        self.app_log_device_combo.addItem("正在检测 ADB 设备…", "")
        settings_layout.addWidget(self.app_log_device_combo, 1, 1)
        self.app_log_refresh_button = QPushButton("刷新设备")
        self.app_log_refresh_button.setObjectName("secondaryButton")
        self.app_log_refresh_button.clicked.connect(self._refresh_app_log_devices)
        settings_layout.addWidget(self.app_log_refresh_button, 1, 2)
        self.app_log_load_packages_button = QPushButton("读取应用列表")
        self.app_log_load_packages_button.setObjectName("secondaryButton")
        self.app_log_load_packages_button.clicked.connect(
            self._load_app_log_packages
        )
        settings_layout.addWidget(self.app_log_load_packages_button, 1, 3)

        package_label = QLabel("应用")
        package_label.setObjectName("fieldLabel")
        settings_layout.addWidget(package_label, 2, 0)
        self.app_log_package_combo = QComboBox()
        self.app_log_package_combo.setEditable(True)
        self.app_log_package_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.app_log_package_combo.addItem("全部日志（不按应用过滤）", "")
        package_line_edit = self.app_log_package_combo.lineEdit()
        if package_line_edit is not None:
            package_line_edit.setPlaceholderText("选择应用，或输入 com.example.app")
        settings_layout.addWidget(self.app_log_package_combo, 2, 1, 1, 3)
        self.app_log_device_combo.currentIndexChanged.connect(
            self._on_app_log_device_changed
        )

        level_label = QLabel("最低级别")
        level_label.setObjectName("fieldLabel")
        settings_layout.addWidget(level_label, 3, 0)
        self.app_log_level_combo = QComboBox()
        for label, value in (
            ("Verbose", "V"),
            ("Debug", "D"),
            ("Info", "I"),
            ("Warning", "W"),
            ("Error", "E"),
            ("Fatal", "F"),
        ):
            self.app_log_level_combo.addItem(label, value)
        self.app_log_level_combo.setCurrentIndex(2)
        settings_layout.addWidget(self.app_log_level_combo, 3, 1)

        keyword_label = QLabel("关键字")
        keyword_label.setObjectName("fieldLabel")
        settings_layout.addWidget(keyword_label, 3, 2)
        self.app_log_keyword = QLineEdit()
        self.app_log_keyword.setPlaceholderText("可选，不区分大小写")
        settings_layout.addWidget(self.app_log_keyword, 3, 3)

        output_label = QLabel("完整日志")
        output_label.setObjectName("fieldLabel")
        settings_layout.addWidget(output_label, 4, 0)
        self.app_log_output_path = QLineEdit()
        self.app_log_output_path.setPlaceholderText("可选：抓取时同步保存完整 .log 文件")
        settings_layout.addWidget(self.app_log_output_path, 4, 1, 1, 2)
        self.app_log_choose_output_button = QPushButton("选择文件")
        self.app_log_choose_output_button.setObjectName("secondaryButton")
        self.app_log_choose_output_button.clicked.connect(
            self._choose_app_log_output
        )
        settings_layout.addWidget(self.app_log_choose_output_button, 4, 3)

        self.app_log_clear_device = QCheckBox("开始前清空手机 Logcat 缓冲区")
        self.app_log_clear_device.setToolTip(
            "会删除设备当前 Logcat 历史；默认不勾选。"
        )
        settings_layout.addWidget(self.app_log_clear_device, 5, 1, 1, 2)
        settings_layout.setColumnStretch(1, 1)
        settings_layout.setColumnStretch(3, 1)
        layout.addWidget(settings_card)

        output_card = QFrame()
        output_card.setObjectName("configCard")
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(20, 18, 20, 18)
        output_header = QHBoxLayout()
        output_title = QLabel("实时日志")
        output_title.setObjectName("sectionTitle")
        output_header.addWidget(output_title)
        self.app_log_state = QLabel("等待开始")
        self.app_log_state.setObjectName("fieldHint")
        output_header.addWidget(self.app_log_state)
        output_header.addStretch()
        self.app_log_clear_button = QPushButton("清空显示")
        self.app_log_clear_button.setObjectName("secondaryButton")
        self.app_log_clear_button.clicked.connect(self._clear_app_log_output)
        output_header.addWidget(self.app_log_clear_button)
        self.app_log_export_button = QPushButton("导出当前显示")
        self.app_log_export_button.setObjectName("secondaryButton")
        self.app_log_export_button.clicked.connect(self._export_app_log_output)
        output_header.addWidget(self.app_log_export_button)
        self.app_log_start_button = QPushButton("开始抓取")
        self.app_log_start_button.setObjectName("primaryButton")
        self.app_log_start_button.clicked.connect(self._start_app_log_capture)
        output_header.addWidget(self.app_log_start_button)
        self.app_log_stop_button = QPushButton("停止")
        self.app_log_stop_button.setObjectName("stopButton")
        self.app_log_stop_button.setEnabled(False)
        self.app_log_stop_button.clicked.connect(self._stop_app_log_capture)
        output_header.addWidget(self.app_log_stop_button)
        output_layout.addLayout(output_header)

        self.app_log_output = QPlainTextEdit()
        self.app_log_output.setObjectName("terminal")
        self.app_log_output.setReadOnly(True)
        self.app_log_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.app_log_output.document().setMaximumBlockCount(20_000)
        self.app_log_output.setPlainText(
            "runner@local:~$ adb logcat ready\n"
            "# 选择设备后可读取第三方应用列表；留空应用将抓取整机日志。\n"
        )
        output_layout.addWidget(self.app_log_output, 1)
        layout.addWidget(output_card, 1)

        self.app_log_capture_controls = (
            self.app_log_device_combo,
            self.app_log_refresh_button,
            self.app_log_load_packages_button,
            self.app_log_package_combo,
            self.app_log_level_combo,
            self.app_log_keyword,
            self.app_log_output_path,
            self.app_log_choose_output_button,
            self.app_log_clear_device,
        )
        return page

    def _build_settings_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel.setFixedWidth(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(16)

        self.settings_title = QLabel("账号生成设置")
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
        self.account_scenario = self._scenario_binding_combo()
        self._add_form_row(form, 12, "绑定场景", self.account_scenario)
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
                self.account_scenario,
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
        self.tournament_scenario = self._scenario_binding_combo()
        self._add_form_row(form, 15, "绑定场景", self.tournament_scenario)
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
                self.tournament_scenario,
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
        list_title = QLabel("SQL 数据模板")
        list_title.setObjectName("sectionTitle")
        list_layout.addWidget(list_title)
        list_hint = QLabel("保存可复用 SQL；可单独执行，也可绑定到账号任务或自动化场景。")
        list_hint.setObjectName("fieldHint")
        list_hint.setWordWrap(True)
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
        execute_title = QLabel("单次执行")
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

    def _build_api_workspace(self) -> QWidget:
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
        list_title = QLabel("API 请求模板")
        list_title.setObjectName("sectionTitle")
        list_layout.addWidget(list_title)
        list_hint = QLabel("保存可复用 HTTP 请求；可单独调试，也可加入自动化场景。")
        list_hint.setObjectName("fieldHint")
        list_hint.setWordWrap(True)
        list_layout.addWidget(list_hint)

        self.api_search = QLineEdit()
        self.api_search.setPlaceholderText("输入标题检索…")
        self.api_search.textChanged.connect(self._filter_api_templates)
        list_layout.addWidget(self.api_search)

        self.api_list = QListWidget()
        self.api_list.setObjectName("channelCodeList")
        self.api_list.currentItemChanged.connect(
            self._on_api_selection_changed
        )
        self.api_list.itemDoubleClicked.connect(
            lambda _item: self._edit_api_template()
        )
        list_layout.addWidget(self.api_list, 1)

        manage_buttons = QHBoxLayout()
        manage_buttons.setSpacing(7)
        self.new_api_button = QPushButton("新增 API")
        self.new_api_button.setObjectName("secondaryButton")
        self.new_api_button.clicked.connect(self._new_api_template)
        manage_buttons.addWidget(self.new_api_button)
        self.edit_api_button = QPushButton("编辑")
        self.edit_api_button.setObjectName("secondaryButton")
        self.edit_api_button.clicked.connect(self._edit_api_template)
        manage_buttons.addWidget(self.edit_api_button)
        self.delete_api_button = QPushButton("删除")
        self.delete_api_button.setObjectName("stopButton")
        self.delete_api_button.clicked.connect(self._delete_api_template)
        manage_buttons.addWidget(self.delete_api_button)
        list_layout.addLayout(manage_buttons)
        main.addWidget(list_panel, 2)

        execute_panel = QFrame()
        execute_panel.setObjectName("settingsPanel")
        execute_panel.setFixedWidth(390)
        execute_layout = QVBoxLayout(execute_panel)
        execute_layout.setContentsMargins(22, 20, 22, 20)
        execute_layout.setSpacing(10)
        execute_title = QLabel("发送请求")
        execute_title.setObjectName("sectionTitle")
        execute_layout.addWidget(execute_title)

        selected_caption = QLabel("已选模板")
        selected_caption.setObjectName("fieldLabel")
        execute_layout.addWidget(selected_caption)
        self.api_selected_title = QLabel("未选择")
        self.api_selected_title.setObjectName("fieldHint")
        self.api_selected_title.setWordWrap(True)
        execute_layout.addWidget(self.api_selected_title)

        environment_label = QLabel("运行环境")
        environment_label.setObjectName("fieldLabel")
        execute_layout.addWidget(environment_label)
        self.api_environment = QComboBox()
        self.api_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        self.api_environment.currentTextChanged.connect(
            self._on_api_environment_changed
        )
        execute_layout.addWidget(self.api_environment)
        self.api_domain_hint = QLabel()
        self.api_domain_hint.setObjectName("fieldHint")
        self.api_domain_hint.setWordWrap(True)
        execute_layout.addWidget(self.api_domain_hint)

        parameters_label = QLabel("运行参数（JSON 对象）")
        parameters_label.setObjectName("fieldLabel")
        execute_layout.addWidget(parameters_label)
        self.api_parameters = QPlainTextEdit()
        self.api_parameters.setPlaceholderText('{"userid": 123, "token": "xxx"}')
        self.api_parameters.setPlainText("{}")
        self.api_parameters.setMaximumHeight(150)
        execute_layout.addWidget(self.api_parameters)
        self.api_parameter_hint = QLabel("当前模板无需运行参数")
        self.api_parameter_hint.setObjectName("fieldHint")
        self.api_parameter_hint.setWordWrap(True)
        execute_layout.addWidget(self.api_parameter_hint)
        execute_layout.addStretch()

        execute_buttons = QHBoxLayout()
        self.api_send_button = QPushButton("发送")
        self.api_send_button.setObjectName("primaryButton")
        self.api_send_button.clicked.connect(self._start)
        execute_buttons.addWidget(self.api_send_button, 1)
        self.api_stop_button = QPushButton("停止")
        self.api_stop_button.setObjectName("stopButton")
        self.api_stop_button.setEnabled(False)
        self.api_stop_button.clicked.connect(self._stop)
        execute_buttons.addWidget(self.api_stop_button)
        execute_layout.addLayout(execute_buttons)
        main.addWidget(execute_panel)
        layout.addLayout(main, 1)

        log_panel = QFrame()
        log_panel.setObjectName("terminalPanel")
        log_panel.setFixedHeight(160)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(16, 10, 16, 12)
        log_layout.setSpacing(6)
        log_header = QHBoxLayout()
        log_title = QLabel("响应日志")
        log_title.setObjectName("sessionTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        clear_log_button = QPushButton("清空")
        clear_log_button.setObjectName("secondaryButton")
        clear_log_button.clicked.connect(lambda: self.api_log.clear())
        log_header.addWidget(clear_log_button)
        log_layout.addLayout(log_header)
        self.api_log = QPlainTextEdit()
        self.api_log.setObjectName("terminal")
        self.api_log.setReadOnly(True)
        self.api_log.setUndoRedoEnabled(False)
        self.api_log.document().setMaximumBlockCount(500)
        compact_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        compact_font.setPointSize(9)
        self.api_log.setFont(compact_font)
        log_layout.addWidget(self.api_log, 1)
        layout.addWidget(log_panel)

        self.config_widgets.extend(
            [
                self.api_search,
                self.api_list,
                self.api_environment,
                self.api_parameters,
                self.new_api_button,
                self.edit_api_button,
                self.delete_api_button,
                self.api_send_button,
            ]
        )
        self._refresh_api_templates()
        self._on_api_environment_changed(self.api_environment.currentText())
        return page

    def _build_scenario_workspace(self) -> QWidget:
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
        list_title = QLabel("自动化场景")
        list_title.setObjectName("sectionTitle")
        list_layout.addWidget(list_title)
        list_hint = QLabel("将 SQL、API、变量提取和断言编排成可复用流程。")
        list_hint.setObjectName("fieldHint")
        list_hint.setWordWrap(True)
        list_layout.addWidget(list_hint)
        self.scenario_search = QLineEdit()
        self.scenario_search.setPlaceholderText("输入场景标题检索…")
        self.scenario_search.textChanged.connect(self._filter_scenarios)
        list_layout.addWidget(self.scenario_search)
        self.scenario_list = QListWidget()
        self.scenario_list.setObjectName("channelCodeList")
        self.scenario_list.currentItemChanged.connect(
            self._on_scenario_selection_changed
        )
        self.scenario_list.itemDoubleClicked.connect(
            lambda _item: self._edit_scenario()
        )
        list_layout.addWidget(self.scenario_list, 1)
        manage_buttons = QHBoxLayout()
        self.new_scenario_button = QPushButton("新增场景")
        self.new_scenario_button.setObjectName("secondaryButton")
        self.new_scenario_button.clicked.connect(self._new_scenario)
        manage_buttons.addWidget(self.new_scenario_button)
        self.edit_scenario_button = QPushButton("编辑")
        self.edit_scenario_button.setObjectName("secondaryButton")
        self.edit_scenario_button.clicked.connect(self._edit_scenario)
        manage_buttons.addWidget(self.edit_scenario_button)
        self.delete_scenario_button = QPushButton("删除")
        self.delete_scenario_button.setObjectName("stopButton")
        self.delete_scenario_button.clicked.connect(self._delete_scenario)
        manage_buttons.addWidget(self.delete_scenario_button)
        list_layout.addLayout(manage_buttons)
        main.addWidget(list_panel, 2)

        execute_panel = QFrame()
        execute_panel.setObjectName("settingsPanel")
        execute_panel.setFixedWidth(390)
        execute_layout = QVBoxLayout(execute_panel)
        execute_layout.setContentsMargins(22, 20, 22, 20)
        execute_layout.setSpacing(10)
        execute_title = QLabel("运行场景")
        execute_title.setObjectName("sectionTitle")
        execute_layout.addWidget(execute_title)
        selected_caption = QLabel("已选场景")
        selected_caption.setObjectName("fieldLabel")
        execute_layout.addWidget(selected_caption)
        self.scenario_selected_title = QLabel("未选择")
        self.scenario_selected_title.setObjectName("fieldHint")
        self.scenario_selected_title.setWordWrap(True)
        execute_layout.addWidget(self.scenario_selected_title)

        environment_label = QLabel("运行环境")
        environment_label.setObjectName("fieldLabel")
        execute_layout.addWidget(environment_label)
        self.scenario_environment = QComboBox()
        self.scenario_environment.addItems(list(SUPPORTED_ENVIRONMENTS))
        execute_layout.addWidget(self.scenario_environment)

        parameters_label = QLabel("初始变量（JSON 对象）")
        parameters_label.setObjectName("fieldLabel")
        execute_layout.addWidget(parameters_label)
        self.scenario_parameters = QPlainTextEdit()
        self.scenario_parameters.setPlaceholderText(
            '{"userid":123,"token":"xxx","email":"test@cc.cc"}'
        )
        self.scenario_parameters.setPlainText("{}")
        self.scenario_parameters.setMaximumHeight(150)
        execute_layout.addWidget(self.scenario_parameters)
        context_hint = QLabel(
            "账号绑定运行时会自动提供 userid、token、email；独立运行需手动填写。"
        )
        context_hint.setObjectName("fieldHint")
        context_hint.setWordWrap(True)
        execute_layout.addWidget(context_hint)
        execute_layout.addStretch()

        execute_buttons = QHBoxLayout()
        self.scenario_execute_button = QPushButton("运行场景")
        self.scenario_execute_button.setObjectName("primaryButton")
        self.scenario_execute_button.clicked.connect(self._start)
        execute_buttons.addWidget(self.scenario_execute_button, 1)
        self.scenario_stop_button = QPushButton("停止")
        self.scenario_stop_button.setObjectName("stopButton")
        self.scenario_stop_button.setEnabled(False)
        self.scenario_stop_button.clicked.connect(self._stop)
        execute_buttons.addWidget(self.scenario_stop_button)
        execute_layout.addLayout(execute_buttons)
        main.addWidget(execute_panel)
        layout.addLayout(main, 1)

        log_panel = QFrame()
        log_panel.setObjectName("terminalPanel")
        log_panel.setFixedHeight(170)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(16, 10, 16, 12)
        log_layout.setSpacing(6)
        log_header = QHBoxLayout()
        log_title = QLabel("场景结果")
        log_title.setObjectName("sessionTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        clear_log_button = QPushButton("清空")
        clear_log_button.setObjectName("secondaryButton")
        clear_log_button.clicked.connect(lambda: self.scenario_log.clear())
        log_header.addWidget(clear_log_button)
        log_layout.addLayout(log_header)
        self.scenario_log = QPlainTextEdit()
        self.scenario_log.setObjectName("terminal")
        self.scenario_log.setReadOnly(True)
        self.scenario_log.setUndoRedoEnabled(False)
        self.scenario_log.document().setMaximumBlockCount(800)
        compact_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        compact_font.setPointSize(9)
        self.scenario_log.setFont(compact_font)
        log_layout.addWidget(self.scenario_log, 1)
        layout.addWidget(log_panel)

        self.config_widgets.extend(
            [
                self.scenario_search,
                self.scenario_list,
                self.scenario_environment,
                self.scenario_parameters,
                self.new_scenario_button,
                self.edit_scenario_button,
                self.delete_scenario_button,
                self.scenario_execute_button,
            ]
        )
        self._refresh_scenario_views()
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

    def _scenario_binding_combo(self) -> QComboBox:
        combo = SearchableComboBox()
        combo.addItem("不绑定场景", None)
        for scenario in self.feature_scenarios:
            combo.addItem(scenario.title, scenario.scenario_id)
        return combo

    def _scenario_by_id(self, scenario_id: object) -> Optional[FeatureScenario]:
        return next(
            (
                scenario
                for scenario in self.feature_scenarios
                if scenario.scenario_id == scenario_id
            ),
            None,
        )

    def _selected_scenario_from_combo(
        self,
        combo: QComboBox,
    ) -> Optional[FeatureScenario]:
        selected_text = combo.currentText().strip()
        if not selected_text or selected_text == "不绑定场景":
            return None
        scenario = next(
            (
                candidate
                for candidate in self.feature_scenarios
                if candidate.title.casefold() == selected_text.casefold()
            ),
            None,
        )
        if scenario is None:
            raise ValueError("请从检索结果中选择完整的自动化场景标题")
        return scenario

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
        used_by = self._scenarios_using_template("sql", template.template_id)
        if used_by:
            QMessageBox.warning(
                self,
                "模板正在使用",
                f"该 SQL 被以下场景引用，需先移除对应步骤：{', '.join(used_by)}",
            )
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

    def _api_template_by_id(self, template_id: object) -> Optional[ApiTemplate]:
        return next(
            (
                template
                for template in self.api_templates
                if template.template_id == template_id
            ),
            None,
        )

    def _selected_api_template(self) -> Optional[ApiTemplate]:
        if not hasattr(self, "api_list"):
            return None
        item = self.api_list.currentItem()
        if item is None or item.isHidden():
            return None
        return self._api_template_by_id(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_api_templates(
        self,
        selected_template_id: Optional[str] = None,
    ) -> None:
        if not hasattr(self, "api_list"):
            return
        current = self.api_list.currentItem()
        selected_id = selected_template_id or (
            current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        )
        self.api_list.blockSignals(True)
        self.api_list.clear()
        selected_row = -1
        for row, template in enumerate(self.api_templates):
            item = QListWidgetItem(f"{template.method}  ·  {template.title}")
            item.setData(Qt.ItemDataRole.UserRole, template.template_id)
            item.setToolTip(template.url)
            self.api_list.addItem(item)
            if template.template_id == selected_id:
                selected_row = row
        self.api_list.blockSignals(False)
        if self.api_list.count():
            self.api_list.setCurrentRow(max(0, selected_row))
        self._filter_api_templates(self.api_search.text())
        self._on_api_selection_changed()

    @Slot(str)
    def _filter_api_templates(self, query: str) -> None:
        if not hasattr(self, "api_list"):
            return
        normalized = query.strip().casefold()
        first_visible = None
        for row in range(self.api_list.count()):
            item = self.api_list.item(row)
            template = self._api_template_by_id(
                item.data(Qt.ItemDataRole.UserRole)
            )
            search_value = (
                f"{item.text()} {template.url}" if template else item.text()
            ).casefold()
            visible = not normalized or normalized in search_value
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = item
        current = self.api_list.currentItem()
        if current is None or current.isHidden():
            self.api_list.setCurrentItem(first_visible)
        self._on_api_selection_changed()

    def _on_api_selection_changed(self, *_args) -> None:
        if not hasattr(self, "api_selected_title"):
            return
        template = self._selected_api_template()
        has_template = template is not None
        if template is None:
            self.api_selected_title.setText("未选择")
            self.api_parameter_hint.setText("当前模板无需运行参数")
        else:
            self.api_selected_title.setText(
                f"{template.method} · {template.title}"
            )
            names = template_parameter_names(template)
            self.api_parameter_hint.setText(
                f"需要参数：{', '.join(names)}"
                if names
                else "当前模板无需运行参数"
            )
        self._on_api_environment_changed(self.api_environment.currentText())
        self.edit_api_button.setEnabled(has_template and not self._is_running())
        self.delete_api_button.setEnabled(has_template and not self._is_running())
        self.api_send_button.setEnabled(has_template and not self._is_running())

    @Slot(str)
    def _on_api_environment_changed(self, environment: str) -> None:
        if not hasattr(self, "api_domain_hint"):
            return
        template = self._selected_api_template()
        if template and template.url.startswith(("http://", "https://")):
            self.api_domain_hint.setText(
                f"固定 URL：{template.url}（不随环境切换）"
            )
            return
        try:
            base_url = load_environment_api_base_url(environment)
        except ValueError as error:
            self.api_domain_hint.setText(str(error))
            return
        path = template.url if template else ""
        self.api_domain_hint.setText(f"域名：{base_url}    路径：{path}")

    @Slot()
    def _new_api_template(self) -> None:
        dialog = ApiTemplateDialog(self)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_template is not None
        ):
            self.api_templates = load_api_templates()
            self._refresh_api_templates(dialog.saved_template.template_id)
            self._append_log(
                f"[api-config] created: {dialog.saved_template.title}\n"
            )

    @Slot()
    def _edit_api_template(self) -> None:
        template = self._selected_api_template()
        if template is None:
            QMessageBox.information(self, "选择 API", "请先选择要编辑的 API 模板")
            return
        dialog = ApiTemplateDialog(self, template)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_template is not None
        ):
            self.api_templates = load_api_templates()
            self._refresh_api_templates(dialog.saved_template.template_id)
            self._append_log(
                f"[api-config] updated: {dialog.saved_template.title}\n"
            )

    @Slot()
    def _delete_api_template(self) -> None:
        template = self._selected_api_template()
        if template is None:
            QMessageBox.information(self, "选择 API", "请先选择要删除的 API 模板")
            return
        used_by = self._scenarios_using_template("api", template.template_id)
        if used_by:
            QMessageBox.warning(
                self,
                "模板正在使用",
                f"该 API 被以下场景引用，需先移除对应步骤：{', '.join(used_by)}",
            )
            return
        answer = QMessageBox.question(
            self,
            "删除 API 模板",
            f"确定删除「{template.title}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_api_template(template.template_id)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "删除失败", str(error))
            return
        self.api_templates = load_api_templates()
        self._refresh_api_templates()
        self._append_log(f"[api-config] deleted: {template.title}\n")

    def _scenarios_using_template(
        self,
        step_type: str,
        template_id: str,
    ) -> list[str]:
        return [
            scenario.title
            for scenario in self.feature_scenarios
            if any(
                step.step_type == step_type
                and step.config.get("template_id") == template_id
                for step in scenario.steps
            )
        ]

    def _selected_feature_scenario(self) -> Optional[FeatureScenario]:
        if not hasattr(self, "scenario_list"):
            return None
        item = self.scenario_list.currentItem()
        if item is None or item.isHidden():
            return None
        return self._scenario_by_id(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_scenario_views(
        self,
        selected_scenario_id: Optional[str] = None,
    ) -> None:
        for combo in (
            getattr(self, "account_scenario", None),
            getattr(self, "tournament_scenario", None),
        ):
            if combo is None:
                continue
            selected = combo.currentData()
            combo.clear()
            combo.addItem("不绑定场景", None)
            for scenario in self.feature_scenarios:
                combo.addItem(scenario.title, scenario.scenario_id)
            self._restore_combo_selection(combo, selected)

        if not hasattr(self, "scenario_list"):
            return
        current = self.scenario_list.currentItem()
        selected_id = selected_scenario_id or (
            current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        )
        self.scenario_list.blockSignals(True)
        self.scenario_list.clear()
        selected_row = -1
        for row, scenario in enumerate(self.feature_scenarios):
            item = QListWidgetItem(
                f"{scenario.title}  ·  {len(scenario.steps)} 步"
            )
            item.setData(Qt.ItemDataRole.UserRole, scenario.scenario_id)
            self.scenario_list.addItem(item)
            if scenario.scenario_id == selected_id:
                selected_row = row
        self.scenario_list.blockSignals(False)
        if self.scenario_list.count():
            self.scenario_list.setCurrentRow(max(0, selected_row))
        self._filter_scenarios(self.scenario_search.text())
        self._on_scenario_selection_changed()

    @Slot(str)
    def _filter_scenarios(self, query: str) -> None:
        if not hasattr(self, "scenario_list"):
            return
        normalized = query.strip().casefold()
        first_visible = None
        for row in range(self.scenario_list.count()):
            item = self.scenario_list.item(row)
            visible = not normalized or normalized in item.text().casefold()
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = item
        current = self.scenario_list.currentItem()
        if current is None or current.isHidden():
            self.scenario_list.setCurrentItem(first_visible)
        self._on_scenario_selection_changed()

    def _on_scenario_selection_changed(self, *_args) -> None:
        if not hasattr(self, "scenario_selected_title"):
            return
        scenario = self._selected_feature_scenario()
        has_scenario = scenario is not None
        if scenario is None:
            self.scenario_selected_title.setText("未选择")
        else:
            sql_count = sum(
                step.step_type == "sql" for step in scenario.steps
            )
            api_count = sum(
                step.step_type == "api" for step in scenario.steps
            )
            assertion_count = sum(
                step.step_type == "assert" for step in scenario.steps
            )
            self.scenario_selected_title.setText(
                f"{scenario.title} · {len(scenario.steps)} 步 "
                f"(SQL {sql_count} / API {api_count} / 断言 {assertion_count})"
            )
        self.edit_scenario_button.setEnabled(
            has_scenario and not self._is_running()
        )
        self.delete_scenario_button.setEnabled(
            has_scenario and not self._is_running()
        )
        self.scenario_execute_button.setEnabled(
            has_scenario and not self._is_running()
        )

    @Slot()
    def _new_scenario(self) -> None:
        dialog = FeatureScenarioDialog(
            self,
            self.sql_templates,
            self.api_templates,
        )
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_scenario is not None
        ):
            self.feature_scenarios = load_feature_scenarios()
            self._refresh_scenario_views(dialog.saved_scenario.scenario_id)
            self._append_log(
                f"[scenario-config] created: {dialog.saved_scenario.title}\n"
            )

    @Slot()
    def _edit_scenario(self) -> None:
        scenario = self._selected_feature_scenario()
        if scenario is None:
            QMessageBox.information(self, "选择场景", "请先选择要编辑的自动化场景")
            return
        dialog = FeatureScenarioDialog(
            self,
            self.sql_templates,
            self.api_templates,
            scenario,
        )
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved_scenario is not None
        ):
            self.feature_scenarios = load_feature_scenarios()
            self._refresh_scenario_views(dialog.saved_scenario.scenario_id)
            self._append_log(
                f"[scenario-config] updated: {dialog.saved_scenario.title}\n"
            )

    @Slot()
    def _delete_scenario(self) -> None:
        scenario = self._selected_feature_scenario()
        if scenario is None:
            QMessageBox.information(self, "选择场景", "请先选择要删除的自动化场景")
            return
        answer = QMessageBox.question(
            self,
            "删除自动化场景",
            f"确定删除「{scenario.title}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_feature_scenario(scenario.scenario_id)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "删除失败", str(error))
            return
        self.feature_scenarios = load_feature_scenarios()
        self._refresh_scenario_views()
        self._append_log(f"[scenario-config] deleted: {scenario.title}\n")

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
                f"请先在“环境与参数”页完成 {environment} 环境的数据库连接配置。",
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
            self.page_description.setText("使用指定邮箱创建单个测试账号，并导出账号信息。")
        else:
            self.mode_hint.setText("按原有逻辑批量注册随机邮箱账号，并导出账号信息。")
            self.start_button.setText("批量创建账号")
            self.session_title.setText("ACCOUNT BATCH CREATE")
            self.page_description.setText(SECTION_INFO[0][2])

    # Android 设备、APK 缓存和归因安装
    def _append_apk_log(self, text: str) -> None:
        cursor = self.apk_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text.rstrip() + "\n")
        self.apk_log.setTextCursor(cursor)
        self.apk_log.ensureCursorVisible()

    def _choose_apk(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "选择 Android 安装包", "", "Android 安装包 (*.apk)"
        )
        if selected:
            self.apk_source_path.setText(selected)

    def _cache_selected_apk(self) -> None:
        source = self.apk_source_path.text().strip()
        if not source:
            QMessageBox.information(self, "选择安装包", "请先选择 APK 文件。")
            return
        attribution = self.apk_attribution_input.toPlainText().strip()
        self._run_apk_action(
            "缓存安装包",
            lambda: cache_apk(source, attribution),
            self._on_apk_cached,
        )

    def _on_apk_cached(self, value: object) -> None:
        self.cached_apks = load_cached_apks()
        self._refresh_apk_table()
        self.apk_source_path.clear()
        self.apk_attribution_input.clear()
        if getattr(value, "duplicate", False):
            self._append_apk_log("[cache] 相同 MD5 已存在，已复用缓存并更新归因链接")
        else:
            package = getattr(value, "package", None)
            self._append_apk_log(f"[cache] 已缓存：{getattr(package, 'name', 'APK')}")

    def _refresh_apk_table(self) -> None:
        if not hasattr(self, "apk_table"):
            return
        self.apk_table.setRowCount(len(self.cached_apks))
        self.apk_package_count.setText(f"{len(self.cached_apks)} 个")
        for row, package in enumerate(self.cached_apks):
            name_item = QTableWidgetItem(package.name)
            name_item.setToolTip(package.path)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.apk_table.setItem(row, 0, name_item)
            detail = package.md5 + (f" · {package.note}" if package.note else "")
            detail_item = QTableWidgetItem(detail)
            detail_tooltip = f"文件：{package.path}\nMD5：{package.md5}"
            if package.note:
                detail_tooltip += f"\n备注：{package.note}"
            detail_item.setToolTip(detail_tooltip)
            detail_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.apk_table.setItem(row, 1, detail_item)
            attribution_item = QTableWidgetItem(package.attribution or "—")
            attribution_item.setToolTip(package.attribution)
            attribution_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.apk_table.setItem(row, 2, attribution_item)

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 3, 4, 3)
            action_layout.setSpacing(5)
            specs = (
                ("安装", lambda pid=package.package_id: self._install_cached_apk(pid, False), True),
                ("归因", lambda pid=package.package_id: self._attribute_cached_apk(pid), bool(package.attribution)),
                ("归因+安装", lambda pid=package.package_id: self._install_cached_apk(pid, True), bool(package.attribution)),
                ("编辑", lambda pid=package.package_id: self._edit_cached_apk(pid), True),
                ("移除", lambda pid=package.package_id: self._remove_cached_apk(pid), True),
            )
            for label, callback, enabled in specs:
                button = QPushButton(label)
                button.setObjectName(
                    "primaryButton" if label == "归因+安装" else "secondaryButton"
                )
                button.setEnabled(enabled)
                button.clicked.connect(lambda _checked=False, fn=callback: fn())
                action_layout.addWidget(button)
            self.apk_table.setCellWidget(row, 3, actions)
            self.apk_table.setRowHeight(row, 54)

    def _cached_apk_by_id(self, package_id: str) -> Optional[CachedApk]:
        return next(
            (item for item in self.cached_apks if item.package_id == package_id),
            None,
        )

    def _edit_cached_apk(self, package_id: str) -> None:
        package = self._cached_apk_by_id(package_id)
        if package is None:
            QMessageBox.critical(self, "编辑失败", "未找到缓存安装包。")
            return
        dialog = CachedApkDialog(package, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            name, attribution, note = dialog.values()
            update_cached_apk(
                package.package_id,
                name=name,
                attribution=attribution,
                note=note,
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.cached_apks = load_cached_apks()
        self._refresh_apk_table()
        self._append_apk_log(f"[cache] 已更新：{name or package.name}")

    def _remove_cached_apk(self, package_id: str) -> None:
        package = self._cached_apk_by_id(package_id)
        if package is None:
            return
        answer = QMessageBox.question(
            self,
            "移除缓存记录",
            f"确定从列表移除「{package.name}」？\n\n缓存 APK 文件将保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_cached_apk(package.package_id)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "移除失败", str(error))
            return
        self.cached_apks = load_cached_apks()
        self._refresh_apk_table()
        self._append_apk_log(f"[cache] 已移除记录：{package.name}（文件保留）")

    def _selected_android_serial(self) -> str:
        serial = str(self.apk_device_combo.currentData() or "").strip()
        device = self.android_devices.get(serial)
        if not serial or device is None:
            raise ValueError("请先连接并选择 Android 设备")
        if device.status != "device":
            raise ValueError(
                f"设备 {serial} 当前状态为 {device.status}，请先完成 USB 调试授权"
            )
        return serial

    @Slot()
    def _refresh_android_devices(self) -> None:
        if self.current_section != 5 or self._is_apk_busy():
            return
        current_serial = str(self.apk_device_combo.currentData() or "")
        self._run_apk_action(
            "检测 Android 设备",
            list_android_devices,
            lambda value: self._on_android_devices_refreshed(value, current_serial),
            quiet=True,
        )

    def _on_android_devices_refreshed(
        self, value: object, preferred_serial: str
    ) -> None:
        devices = [item for item in value if isinstance(item, AndroidDevice)]
        self.android_devices = {device.serial: device for device in devices}
        self.apk_device_combo.clear()
        if not devices:
            self.apk_device_combo.addItem("未检测到设备", "")
            self.apk_device_hint.setText("未检测到设备，请检查数据线和 USB 调试设置。")
        else:
            for device in devices:
                detail = f" · {device.detail}" if device.detail else ""
                self.apk_device_combo.addItem(
                    f"{device.serial} · {device.status}{detail}", device.serial
                )
            preferred_index = self.apk_device_combo.findData(preferred_serial)
            if preferred_index >= 0:
                self.apk_device_combo.setCurrentIndex(preferred_index)
            ready_count = sum(device.status == "device" for device in devices)
            self.apk_device_hint.setText(
                f"ADB 已发现 {len(devices)} 台设备，其中 {ready_count} 台可安装。"
            )
        self.last_apk_device_error = ""

    def _install_cached_apk(self, package_id: str, with_attribution: bool) -> None:
        package = self._cached_apk_by_id(package_id)
        if package is None:
            QMessageBox.critical(self, "安装失败", "未找到缓存安装包。")
            return
        try:
            serial = self._selected_android_serial()
        except ValueError as error:
            QMessageBox.information(self, "选择设备", str(error))
            return
        if with_attribution and not package.attribution:
            QMessageBox.information(self, "缺少归因链接", "请先编辑并填写归因链接。")
            return
        if with_attribution:
            description = f"归因并安装 {package.name}"
            action = lambda: attribute_and_install(
                serial, package.attribution, package.path
            )
        else:
            description = f"安装 {package.name}"
            action = lambda: install_apk(serial, package.path)
        self._append_apk_log(f"[adb:{serial}] {description}…")
        self._run_apk_action(
            description,
            action,
            lambda value: self._on_apk_install_result(value, package, serial),
        )

    def _attribute_cached_apk(self, package_id: str) -> None:
        package = self._cached_apk_by_id(package_id)
        if package is None:
            return
        try:
            serial = self._selected_android_serial()
        except ValueError as error:
            QMessageBox.information(self, "选择设备", str(error))
            return
        if not package.attribution:
            QMessageBox.information(self, "缺少归因链接", "请先编辑并填写归因链接。")
            return
        self._run_apk_action(
            f"打开 {package.name} 的归因链接",
            lambda: open_attribution_url(serial, package.attribution),
            lambda _value: self._append_apk_log(
                f"[adb:{serial}] 已在设备浏览器打开归因链接"
            ),
        )

    def _on_apk_install_result(
        self, value: object, package: CachedApk, serial: str
    ) -> None:
        if not isinstance(value, ApkInstallResult):
            raise TypeError("ADB 返回了无法识别的安装结果")
        if value.status != "signature-conflict":
            self._append_apk_log(f"[adb:{serial}] 安装完成：{package.name}")
            return
        answer = QMessageBox.question(
            self,
            "检测到同包名旧应用",
            (
                f"设备上已存在「{value.package_name}」，但签名与当前 APK 不一致，"
                "无法直接覆盖。\n\n是否卸载旧应用后安装当前 APK？"
                "此操作会清空旧应用的本地数据。"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._append_apk_log(
                f"[adb:{serial}] 已取消替换；旧应用 {value.package_name} 未改动"
            )
            return
        self.pending_apk_action = (
            f"替换旧应用 {value.package_name}",
            lambda: reinstall_apk(serial, package.path, value.package_name),
            lambda _result: self._append_apk_log(
                f"[adb:{serial}] 替换完成：旧应用已卸载，{package.name} 已安装"
            ),
        )

    def _run_apk_action(
        self,
        description: str,
        action: Callable[[], object],
        on_success: Callable[[object], None],
        *,
        quiet: bool = False,
    ) -> None:
        if self._is_apk_busy() or self._is_ios_busy():
            return
        self.apk_action_description = description
        self.apk_action_quiet = quiet
        if quiet:
            self._set_apk_refreshing(True)
        else:
            self._set_apk_busy(True)
        self._set_status("●  ADB RUNNING", "#228653")
        self.apk_action_thread = QThread(self)
        self.apk_action_worker = ApkActionWorker(action)
        self.apk_action_worker.moveToThread(self.apk_action_thread)
        self.apk_action_thread.started.connect(self.apk_action_worker.run)
        self.apk_action_worker.succeeded.connect(on_success)
        self.apk_action_worker.failed.connect(self._on_apk_action_failed)
        self.apk_action_worker.done.connect(self.apk_action_thread.quit)
        self.apk_action_worker.done.connect(self.apk_action_worker.deleteLater)
        self.apk_action_thread.finished.connect(self._on_apk_action_finished)
        self.apk_action_thread.finished.connect(self.apk_action_thread.deleteLater)
        self.apk_action_thread.start()

    @Slot(str)
    def _on_apk_action_failed(self, message: str) -> None:
        if self.apk_action_quiet:
            self.apk_device_combo.clear()
            self.apk_device_combo.addItem("ADB 不可用", "")
            self.apk_device_hint.setText(message)
            if message != self.last_apk_device_error:
                self._append_apk_log(f"[adb] 设备检测失败：{message}")
                self.last_apk_device_error = message
        else:
            self._append_apk_log(
                f"[adb] {self.apk_action_description}失败：{message}"
            )
            QMessageBox.critical(self, "ADB 操作失败", message)

    @Slot()
    def _on_apk_action_finished(self) -> None:
        pending = self.pending_apk_action
        was_quiet = self.apk_action_quiet
        self.pending_apk_action = None
        self.apk_action_worker = None
        self.apk_action_thread = None
        if was_quiet:
            self._set_apk_refreshing(False)
        else:
            self._set_apk_busy(False)
        if self._is_app_log_running():
            self._set_status("●  LOGCAT RUNNING", "#228653")
        else:
            self._set_status("●  READY", "#228653")
        if pending is not None:
            description, action, on_success = pending
            QTimer.singleShot(
                0, lambda: self._run_apk_action(description, action, on_success)
            )

    def _set_apk_busy(self, busy: bool) -> None:
        for control in self.apk_controls:
            control.setEnabled(not busy)
        for button in self.navigation_buttons:
            button.setEnabled(not busy)

    def _set_apk_refreshing(self, refreshing: bool) -> None:
        """设备检测只锁定会发起其他后台操作的控件，不刷新整个页面。"""
        self.apk_device_combo.setEnabled(not refreshing)
        self.apk_refresh_button.setEnabled(not refreshing)
        self.apk_cache_button.setEnabled(not refreshing)
        self.apk_table.setEnabled(not refreshing)

    def _is_apk_busy(self) -> bool:
        return bool(self.apk_action_thread and self.apk_action_thread.isRunning())

    # iOS 设备、IPA 下载、缓存和归因安装
    def _append_ipa_log(self, text: str) -> None:
        cursor = self.ipa_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text.rstrip() + "\n")
        self.ipa_log.setTextCursor(cursor)
        self.ipa_log.ensureCursorVisible()

    def _choose_ipa(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "选择 iOS 安装包", "", "iOS 安装包 (*.ipa)"
        )
        if selected:
            self.ipa_source_path.setText(selected)
            self.ipa_download_url.clear()

    def _cache_selected_ipa(self) -> None:
        source = self.ipa_source_path.text().strip()
        download_url = self.ipa_download_url.text().strip()
        if bool(source) == bool(download_url):
            QMessageBox.information(
                self,
                "选择安装包",
                "请选择一个本地 IPA，或填写一个 IPA 下载地址（两者只能选一个）。",
            )
            return
        attribution = self.ipa_attribution_input.toPlainText().strip()
        if source:
            description = "缓存 IPA"
            action = lambda: cache_ipa(source, attribution)
        else:
            description = "下载并缓存 IPA"
            action = lambda: download_and_cache_ipa(download_url, attribution)
        self._append_ipa_log(f"[ipa] {description}…")
        self._run_ios_action(description, action, self._on_ipa_cached)

    def _on_ipa_cached(self, value: object) -> None:
        self.cached_ipas = load_cached_ipas()
        self._refresh_ipa_table()
        self.ipa_source_path.clear()
        self.ipa_download_url.clear()
        self.ipa_attribution_input.clear()
        package = getattr(value, "package", None)
        prefix = "相同 MD5 已存在，已复用" if getattr(value, "duplicate", False) else "已缓存"
        self._append_ipa_log(
            f"[cache] {prefix}：{getattr(package, 'name', 'IPA')} · "
            f"{getattr(package, 'bundle_id', '')}"
        )

    def _refresh_ipa_table(self) -> None:
        if not hasattr(self, "ipa_table"):
            return
        self.ipa_table.setRowCount(len(self.cached_ipas))
        self.ipa_package_count.setText(f"{len(self.cached_ipas)} 个")
        for row, package in enumerate(self.cached_ipas):
            name_item = QTableWidgetItem(package.name)
            name_item.setToolTip(package.path)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.ipa_table.setItem(row, 0, name_item)
            expiration = package.expires_at[:10] if package.expires_at else "未知期限"
            detail = f"{package.bundle_id} · {package.profile_name} · {expiration}"
            if package.note:
                detail += f" · {package.note}"
            detail_item = QTableWidgetItem(detail)
            detail_item.setToolTip(
                f"文件：{package.path}\nMD5：{package.md5}\nBundle ID：{package.bundle_id}"
                f"\n描述文件：{package.profile_name}\n到期：{package.expires_at}"
                + (f"\n备注：{package.note}" if package.note else "")
            )
            detail_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.ipa_table.setItem(row, 1, detail_item)
            attribution_item = QTableWidgetItem(package.attribution or "—")
            attribution_item.setToolTip(package.attribution)
            attribution_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.ipa_table.setItem(row, 2, attribution_item)

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 3, 4, 3)
            action_layout.setSpacing(5)
            specs = (
                ("安装", lambda pid=package.package_id: self._install_cached_ipa(pid, False), True),
                ("归因", lambda pid=package.package_id: self._attribute_cached_ipa(pid), bool(package.attribution)),
                ("归因+安装", lambda pid=package.package_id: self._install_cached_ipa(pid, True), bool(package.attribution)),
                ("编辑", lambda pid=package.package_id: self._edit_cached_ipa(pid), True),
                ("移除", lambda pid=package.package_id: self._remove_cached_ipa(pid), True),
            )
            for label, callback, enabled in specs:
                button = QPushButton(label)
                button.setObjectName(
                    "primaryButton" if label == "归因+安装" else "secondaryButton"
                )
                button.setEnabled(enabled)
                button.clicked.connect(lambda _checked=False, fn=callback: fn())
                action_layout.addWidget(button)
            self.ipa_table.setCellWidget(row, 3, actions)
            self.ipa_table.setRowHeight(row, 54)

    def _cached_ipa_by_id(self, package_id: str) -> Optional[CachedIpa]:
        return next(
            (item for item in self.cached_ipas if item.package_id == package_id),
            None,
        )

    def _edit_cached_ipa(self, package_id: str) -> None:
        package = self._cached_ipa_by_id(package_id)
        if package is None:
            QMessageBox.critical(self, "编辑失败", "未找到缓存 IPA。")
            return
        dialog = CachedApkDialog(package, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            name, attribution, note = dialog.values()
            update_cached_ipa(
                package.package_id,
                name=name,
                attribution=attribution,
                note=note,
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.cached_ipas = load_cached_ipas()
        self._refresh_ipa_table()
        self._append_ipa_log(f"[cache] 已更新：{name or package.name}")

    def _remove_cached_ipa(self, package_id: str) -> None:
        package = self._cached_ipa_by_id(package_id)
        if package is None:
            return
        answer = QMessageBox.question(
            self,
            "移除缓存记录",
            f"确定从列表移除「{package.name}」？\n\n缓存 IPA 文件将保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_cached_ipa(package.package_id)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "移除失败", str(error))
            return
        self.cached_ipas = load_cached_ipas()
        self._refresh_ipa_table()
        self._append_ipa_log(f"[cache] 已移除记录：{package.name}（文件保留）")

    def _selected_ios_udid(self) -> str:
        udid = str(self.ios_device_combo.currentData() or "").strip()
        if not udid or udid not in self.ios_devices:
            raise ValueError("请先连接并选择 iOS 设备")
        return udid

    @Slot()
    def _refresh_ios_devices(self) -> None:
        if self.current_section != 6 or self._is_ios_busy():
            return
        current_udid = str(self.ios_device_combo.currentData() or "")
        self._run_ios_action(
            "检测 iOS 设备",
            list_ios_devices,
            lambda value: self._on_ios_devices_refreshed(value, current_udid),
            quiet=True,
        )

    def _on_ios_devices_refreshed(self, value: object, preferred_udid: str) -> None:
        devices = [item for item in value if isinstance(item, IosDevice)]
        self.ios_devices = {device.udid: device for device in devices}
        self.ios_device_combo.clear()
        if not devices:
            self.ios_device_combo.addItem("未检测到设备", "")
            self.ios_device_hint.setText(
                "未检测到设备，请检查数据线、设备信任状态和 Apple Mobile Device 服务。"
            )
        else:
            for device in devices:
                details = " · ".join(
                    value
                    for value in (device.product_version, device.connection_type)
                    if value
                )
                suffix = f" · {details}" if details else ""
                self.ios_device_combo.addItem(
                    f"{device.name or 'iPhone'} · {device.udid}{suffix}", device.udid
                )
            preferred_index = self.ios_device_combo.findData(preferred_udid)
            if preferred_index >= 0:
                self.ios_device_combo.setCurrentIndex(preferred_index)
            self.ios_device_hint.setText(
                f"已发现 {len(devices)} 台设备；归因需开启 Safari 的 Web 检查器，并打开普通网页标签页。"
            )
        self.last_ios_device_error = ""

    def _install_cached_ipa(self, package_id: str, with_attribution: bool) -> None:
        package = self._cached_ipa_by_id(package_id)
        if package is None:
            QMessageBox.critical(self, "安装失败", "未找到缓存 IPA。")
            return
        try:
            udid = self._selected_ios_udid()
        except ValueError as error:
            QMessageBox.information(self, "选择设备", str(error))
            return
        if with_attribution and not package.attribution:
            QMessageBox.information(self, "缺少归因链接", "请先编辑并填写归因链接。")
            return
        if with_attribution:
            description = f"归因并安装 {package.name}"
            action = lambda: attribute_and_install_ipa(
                udid, package.attribution, package.path
            )
        else:
            description = f"安装 {package.name}"
            action = lambda: install_ipa(udid, package.path)
        self._append_ipa_log(
            f"[tidevice:{udid}] {description}…"
        )
        self._run_ios_action(
            description,
            action,
            lambda value: self._on_ipa_install_result(value, package, udid),
        )

    def _attribute_cached_ipa(self, package_id: str) -> None:
        package = self._cached_ipa_by_id(package_id)
        if package is None:
            return
        try:
            udid = self._selected_ios_udid()
        except ValueError as error:
            QMessageBox.information(self, "选择设备", str(error))
            return
        if not package.attribution:
            QMessageBox.information(self, "缺少归因链接", "请先编辑并填写归因链接。")
            return
        self._run_ios_action(
            f"打开 {package.name} 的归因链接",
            lambda: open_ios_attribution_url(udid, package.attribution),
            lambda _value: self._append_ipa_log(
                f"[tidevice:{udid}] 已在 Safari 打开归因链接"
            ),
        )

    def _on_ipa_install_result(
        self, value: object, package: CachedIpa, udid: str
    ) -> None:
        if not isinstance(value, IpaInstallResult):
            raise TypeError("tidevice 返回了无法识别的安装结果")
        self._append_ipa_log(
            f"[tidevice:{udid}] 安装完成：{package.name}（{value.bundle_id}）"
        )

    def _run_ios_action(
        self,
        description: str,
        action: Callable[[], object],
        on_success: Callable[[object], None],
        *,
        quiet: bool = False,
    ) -> None:
        if self._is_ios_busy() or self._is_apk_busy():
            return
        self.ios_action_description = description
        self.ios_action_quiet = quiet
        if quiet:
            self._set_ios_refreshing(True)
        else:
            self._set_ios_busy(True)
        self._set_status("●  IOS RUNNING", "#228653")
        self.ios_action_thread = QThread(self)
        self.ios_action_worker = ApkActionWorker(action)
        self.ios_action_worker.moveToThread(self.ios_action_thread)
        self.ios_action_thread.started.connect(self.ios_action_worker.run)
        self.ios_action_worker.succeeded.connect(on_success)
        self.ios_action_worker.failed.connect(self._on_ios_action_failed)
        self.ios_action_worker.done.connect(self.ios_action_thread.quit)
        self.ios_action_worker.done.connect(self.ios_action_worker.deleteLater)
        self.ios_action_thread.finished.connect(self._on_ios_action_finished)
        self.ios_action_thread.finished.connect(self.ios_action_thread.deleteLater)
        self.ios_action_thread.start()

    @Slot(str)
    def _on_ios_action_failed(self, message: str) -> None:
        if self.ios_action_quiet:
            self.ios_device_combo.clear()
            self.ios_device_combo.addItem("tidevice 不可用", "")
            self.ios_device_hint.setText(message)
            if message != self.last_ios_device_error:
                self._append_ipa_log(f"[tidevice] 设备检测失败：{message}")
                self.last_ios_device_error = message
        else:
            self._append_ipa_log(
                f"[tidevice] {self.ios_action_description}失败：{message}"
            )
            QMessageBox.critical(self, "iOS 操作失败", message)

    @Slot()
    def _on_ios_action_finished(self) -> None:
        was_quiet = self.ios_action_quiet
        self.ios_action_worker = None
        self.ios_action_thread = None
        if was_quiet:
            self._set_ios_refreshing(False)
        else:
            self._set_ios_busy(False)
        if self._is_app_log_running():
            self._set_status("●  LOGCAT RUNNING", "#228653")
        else:
            self._set_status("●  READY", "#228653")

    def _set_ios_busy(self, busy: bool) -> None:
        for control in self.ipa_controls:
            control.setEnabled(not busy)
        for button in self.navigation_buttons:
            button.setEnabled(not busy)

    def _set_ios_refreshing(self, refreshing: bool) -> None:
        self.ios_device_combo.setEnabled(not refreshing)
        self.ios_refresh_button.setEnabled(not refreshing)
        self.ipa_cache_button.setEnabled(not refreshing)
        self.ipa_table.setEnabled(not refreshing)

    def _is_ios_busy(self) -> bool:
        return bool(self.ios_action_thread and self.ios_action_thread.isRunning())

    # Android 应用日志
    def _append_app_log_output(self, text: str) -> None:
        cursor = self.app_log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.app_log_output.setTextCursor(cursor)
        self.app_log_output.ensureCursorVisible()

    def _append_app_log_message(self, text: str) -> None:
        self._append_app_log_output(text.rstrip() + "\n")

    def _clear_app_log_output(self) -> None:
        self.app_log_output.clear()

    def _choose_app_log_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "保存完整 Android 日志",
            "android-logcat.log",
            "日志文件 (*.log *.txt);;所有文件 (*)",
        )
        if selected:
            self.app_log_output_path.setText(selected)

    def _export_app_log_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前显示的日志",
            "android-logcat-visible.log",
            "日志文件 (*.log *.txt);;所有文件 (*)",
        )
        if not selected:
            return
        try:
            Path(selected).write_text(
                self.app_log_output.toPlainText(),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.critical(self, "导出失败", str(error))
            return
        self.app_log_state.setText(f"已导出：{selected}")

    def _selected_app_log_serial(self) -> str:
        serial = str(self.app_log_device_combo.currentData() or "").strip()
        device = self.app_log_devices.get(serial)
        if not serial or device is None:
            raise ValueError("请先连接并选择 Android 设备")
        if device.status != "device":
            raise ValueError(
                f"设备 {serial} 当前状态为 {device.status}，请先完成 USB 调试授权"
            )
        return serial

    def _selected_app_log_package(self) -> str:
        text = self.app_log_package_combo.currentText().strip()
        if text == "全部日志（不按应用过滤）":
            return ""
        return text

    @Slot()
    def _on_app_log_device_changed(self) -> None:
        """设备切换后丢弃旧设备的应用列表，避免抓错包名。"""
        self.app_log_package_combo.clear()
        self.app_log_package_combo.addItem("全部日志（不按应用过滤）", "")
        if (
            self.app_log_devices
            and not self._is_app_log_query_busy()
            and not self._is_app_log_running()
        ):
            self.app_log_state.setText("设备已切换，可重新读取应用列表")

    def _run_app_log_query(
        self,
        description: str,
        action: Callable[[], object],
        on_success: Callable[[object], None],
        *,
        quiet: bool = False,
    ) -> None:
        if self._is_app_log_query_busy() or self._is_app_log_running():
            return
        self.app_log_query_description = description
        self.app_log_query_quiet = quiet
        self._set_app_log_query_busy(True)
        self.app_log_query_thread = QThread(self)
        self.app_log_query_worker = ApkActionWorker(action)
        self.app_log_query_worker.moveToThread(self.app_log_query_thread)
        self.app_log_query_thread.started.connect(self.app_log_query_worker.run)
        self.app_log_query_worker.succeeded.connect(on_success)
        self.app_log_query_worker.failed.connect(self._on_app_log_query_failed)
        self.app_log_query_worker.done.connect(self.app_log_query_thread.quit)
        self.app_log_query_worker.done.connect(
            self.app_log_query_worker.deleteLater
        )
        self.app_log_query_thread.finished.connect(
            self._on_app_log_query_finished
        )
        self.app_log_query_thread.finished.connect(
            self.app_log_query_thread.deleteLater
        )
        self.app_log_query_thread.start()

    @Slot()
    def _refresh_app_log_devices(self) -> None:
        if (
            self.current_section != 7
            or self._is_app_log_query_busy()
            or self._is_app_log_running()
        ):
            return
        current_serial = str(self.app_log_device_combo.currentData() or "")
        self.app_log_state.setText("正在检测设备…")
        self._run_app_log_query(
            "检测 Android 设备",
            list_android_devices,
            lambda value: self._on_app_log_devices_refreshed(
                value,
                current_serial,
            ),
            quiet=True,
        )

    def _on_app_log_devices_refreshed(
        self,
        value: object,
        preferred_serial: str,
    ) -> None:
        devices = [item for item in value if isinstance(item, AndroidDevice)]
        self.app_log_devices = {device.serial: device for device in devices}
        self.app_log_device_combo.clear()
        if not devices:
            self.app_log_device_combo.addItem("未检测到设备", "")
            self.app_log_state.setText("未检测到设备，请检查 USB 调试设置")
            return
        for device in devices:
            detail = f" · {device.detail}" if device.detail else ""
            self.app_log_device_combo.addItem(
                f"{device.serial} · {device.status}{detail}",
                device.serial,
            )
        preferred_index = self.app_log_device_combo.findData(preferred_serial)
        if preferred_index < 0:
            preferred_index = next(
                (
                    index
                    for index, device in enumerate(devices)
                    if device.status == "device"
                ),
                0,
            )
        self.app_log_device_combo.setCurrentIndex(preferred_index)
        ready_count = sum(device.status == "device" for device in devices)
        self.app_log_state.setText(
            f"已发现 {len(devices)} 台设备，{ready_count} 台可抓取日志"
        )

    @Slot()
    def _load_app_log_packages(self) -> None:
        try:
            serial = self._selected_app_log_serial()
        except ValueError as error:
            QMessageBox.information(self, "选择设备", str(error))
            return
        current_package = self._selected_app_log_package()
        self.app_log_state.setText("正在读取第三方应用列表…")
        self._run_app_log_query(
            "读取应用列表",
            lambda: list_installed_packages(serial),
            lambda value: self._on_app_log_packages_loaded(value, current_package),
        )

    def _on_app_log_packages_loaded(
        self,
        value: object,
        preferred_package: str,
    ) -> None:
        packages = [item for item in value if isinstance(item, str)]
        self.app_log_package_combo.clear()
        self.app_log_package_combo.addItem("全部日志（不按应用过滤）", "")
        for package_name in packages:
            self.app_log_package_combo.addItem(package_name, package_name)
        if preferred_package:
            index = self.app_log_package_combo.findData(preferred_package)
            if index >= 0:
                self.app_log_package_combo.setCurrentIndex(index)
            else:
                self.app_log_package_combo.setCurrentText(preferred_package)
        self.app_log_state.setText(f"已读取 {len(packages)} 个第三方应用")

    @Slot(str)
    def _on_app_log_query_failed(self, message: str) -> None:
        self.app_log_state.setText(f"{self.app_log_query_description}失败")
        self._append_app_log_message(
            f"[adb] {self.app_log_query_description}失败：{message}"
        )
        if self.app_log_query_description == "检测 Android 设备":
            self.app_log_devices = {}
            self.app_log_device_combo.clear()
            self.app_log_device_combo.addItem("ADB 不可用", "")
        if not self.app_log_query_quiet:
            QMessageBox.critical(self, "ADB 操作失败", message)

    @Slot()
    def _on_app_log_query_finished(self) -> None:
        self.app_log_query_worker = None
        self.app_log_query_thread = None
        self._set_app_log_query_busy(False)

    def _set_app_log_query_busy(self, busy: bool) -> None:
        self.app_log_device_combo.setEnabled(not busy)
        self.app_log_refresh_button.setEnabled(not busy)
        self.app_log_load_packages_button.setEnabled(not busy)
        self.app_log_package_combo.setEnabled(not busy)
        self.app_log_start_button.setEnabled(not busy)

    def _is_app_log_query_busy(self) -> bool:
        return self.app_log_query_thread is not None

    @Slot()
    def _start_app_log_capture(self) -> None:
        if self._is_app_log_running() or self._is_app_log_query_busy():
            return
        try:
            serial = self._selected_app_log_serial()
            config = LogcatCaptureConfig(
                serial=serial,
                package_name=self._selected_app_log_package(),
                minimum_level=str(self.app_log_level_combo.currentData() or "I"),
                keyword=self.app_log_keyword.text(),
                clear_before_start=self.app_log_clear_device.isChecked(),
                output_path=self.app_log_output_path.text(),
            ).validated()
        except ValueError as error:
            QMessageBox.information(self, "日志参数", str(error))
            return

        output_file = (
            Path(config.output_path).expanduser() if config.output_path else None
        )
        if output_file is not None:
            if output_file.exists() and not output_file.is_file():
                QMessageBox.information(self, "日志文件", "输出路径不是普通文件")
                return
            if not output_file.parent.is_dir():
                QMessageBox.information(self, "日志文件", "输出文件夹不存在")
                return
            if output_file.exists():
                answer = QMessageBox.question(
                    self,
                    "覆盖日志文件",
                    f"{output_file}\n已存在，是否覆盖？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

        target = config.package_name or "全部进程"
        self._append_app_log_message(
            f"\n[logcat:{serial}] 开始抓取 · {target} · {config.minimum_level}+"
        )
        if config.keyword:
            self._append_app_log_message(f"[filter] 关键字：{config.keyword}")
        if config.output_path:
            self._append_app_log_message(f"[file] 完整日志：{config.output_path}")
        self.app_log_stop_requested = False
        self.app_log_capture_failed = False
        if config.clear_before_start:
            self.app_log_clear_device.setChecked(False)
        self._set_app_log_capture_running(True)
        self._set_status("●  LOGCAT RUNNING", "#228653")
        self.app_log_thread = QThread(self)
        self.app_log_worker = AndroidLogWorker(config)
        self.app_log_worker.moveToThread(self.app_log_thread)
        self.app_log_thread.started.connect(self.app_log_worker.run)
        self.app_log_worker.output.connect(self._append_app_log_output)
        self.app_log_worker.failed.connect(self._on_app_log_capture_failed)
        self.app_log_worker.done.connect(self.app_log_thread.quit)
        self.app_log_worker.done.connect(self.app_log_worker.deleteLater)
        self.app_log_thread.finished.connect(self._on_app_log_capture_finished)
        self.app_log_thread.finished.connect(self.app_log_thread.deleteLater)
        self.app_log_thread.start()

    @Slot()
    def _stop_app_log_capture(self) -> None:
        if self.app_log_worker is None or not self._is_app_log_running():
            return
        self.app_log_stop_requested = True
        self.app_log_state.setText("正在停止日志抓取…")
        self.app_log_stop_button.setEnabled(False)
        self.app_log_worker.request_stop()

    @Slot(str)
    def _on_app_log_capture_failed(self, message: str) -> None:
        self.app_log_capture_failed = True
        self._append_app_log_message(f"[logcat:error] {message}")
        self.app_log_state.setText("抓取失败")
        self._set_status("●  LOGCAT FAILED", "#c43d47")
        if not self.close_after_log_stop:
            QMessageBox.critical(self, "日志抓取失败", message)

    @Slot()
    def _on_app_log_capture_finished(self) -> None:
        was_stopped = self.app_log_stop_requested
        failed = self.app_log_capture_failed
        self.app_log_worker = None
        self.app_log_thread = None
        self.app_log_stop_requested = False
        self._set_app_log_capture_running(False)
        if was_stopped:
            self._append_app_log_message("[logcat] 日志抓取已停止")
            self.app_log_state.setText("已停止")
        elif failed:
            self.app_log_state.setText("抓取失败")
        else:
            self._append_app_log_message("[logcat] ADB 日志流已结束")
            self.app_log_state.setText("日志流已结束")
        if (
            not failed
            and not self._is_running()
            and not self._is_apk_busy()
            and not self._is_ios_busy()
        ):
            self._set_status("●  READY", "#228653")
        if self.close_after_log_stop:
            self.close_after_log_stop = False
        self._finish_deferred_close_if_idle()

    def _set_app_log_capture_running(self, running: bool) -> None:
        for control in self.app_log_capture_controls:
            control.setEnabled(not running)
        self.app_log_start_button.setEnabled(not running)
        self.app_log_stop_button.setEnabled(running)
        self.app_log_state.setText("正在抓取…" if running else "已停止")

    def _is_app_log_running(self) -> bool:
        return self.app_log_thread is not None

    def _finish_deferred_close_if_idle(self) -> None:
        if (
            self.exit_after_workers_stop
            and not self._is_running()
            and not self._is_app_log_running()
        ):
            self.exit_after_workers_stop = False
            QTimer.singleShot(0, self.close)

    # 参数维护
    def _switch_section(self, index: int) -> None:
        self.current_section = index
        if index < len(self.navigation_buttons):
            self.navigation_buttons[index].setChecked(True)
            _group, title, description = SECTION_INFO[index]
            self.page_title.setText(title)
            self.page_description.setText(description)
        if index == 0:
            self.content_stack.setCurrentIndex(0)
            self.settings_stack.setCurrentIndex(0)
            self.settings_title.setText("账号生成设置")
            self._on_account_creation_mode_changed()
        elif index == 1:
            self.content_stack.setCurrentIndex(0)
            self.settings_stack.setCurrentIndex(1)
            self.settings_title.setText("锦标赛造数设置")
            self.mode_hint.setText(
                "账号和下注可分别设置串行或并行；并行下注使用独立 session。"
            )
            self.start_button.setText("生成锦标赛数据")
            self.session_title.setText("TOURNAMENT DATA")
        elif index == 2:
            self.content_stack.setCurrentIndex(2)
        elif index == 3:
            self.content_stack.setCurrentIndex(3)
        elif index == 4:
            self.content_stack.setCurrentIndex(4)
        elif index == 5:
            self.content_stack.setCurrentIndex(5)
            QTimer.singleShot(0, self._refresh_android_devices)
        elif index == 6:
            self.content_stack.setCurrentIndex(6)
            QTimer.singleShot(0, self._refresh_ios_devices)
        elif index == 7:
            self.content_stack.setCurrentIndex(7)
            if not self.app_log_devices:
                QTimer.singleShot(0, self._refresh_app_log_devices)
        else:
            self.content_stack.setCurrentIndex(1)
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

    def _scenario_binding_parameters(
        self,
        environment: str,
        combo: QComboBox,
    ) -> dict:
        scenario = self._selected_scenario_from_combo(combo)
        if scenario is None:
            return {}
        connection = self.database_connections_by_environment[environment]
        if scenario_needs_database(scenario) and not is_database_connection_configured(
            connection
        ):
            raise ValueError(
                f"绑定场景包含 SQL，请先完成 {environment} 环境的数据库配置"
            )
        return {
            "feature_scenario": scenario,
            "scenario_database_connection": (
                connection if scenario_needs_database(scenario) else None
            ),
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
                **self._scenario_binding_parameters(
                    self.account_environment.currentText(),
                    self.account_scenario,
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

        if self.current_section == 3:
            template = self._selected_api_template()
            if template is None:
                raise ValueError("请先从列表选择 API 模板")
            return (
                send_api_request,
                {
                    "template": template,
                    "parameters": parse_runtime_parameters(
                        self.api_parameters.toPlainText()
                    ),
                    "environment": self.api_environment.currentText(),
                },
                "send-api-request",
            )

        if self.current_section == 4:
            scenario = self._selected_feature_scenario()
            if scenario is None:
                raise ValueError("请先从列表选择自动化场景")
            environment = self.scenario_environment.currentText()
            connection = self.database_connections_by_environment[environment]
            if scenario_needs_database(scenario) and not is_database_connection_configured(
                connection
            ):
                raise ValueError(
                    f"场景包含 SQL，请先完成 {environment} 环境的数据库配置"
                )
            runtime_parameters = parse_runtime_parameters(
                self.scenario_parameters.toPlainText()
            )
            if scenario_needs_database(scenario) and "userid" not in runtime_parameters:
                raise ValueError("场景包含 SQL，初始变量中必须填写 userid")
            return (
                run_feature_scenario,
                {
                    "scenario": scenario,
                    "environment": environment,
                    "runtime_parameters": runtime_parameters,
                    "database_connection": (
                        connection if scenario_needs_database(scenario) else None
                    ),
                },
                "run-feature-scenario",
            )

        if self.current_section != 1:
            raise ValueError("“环境与参数”页不能执行任务")

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
            **self._scenario_binding_parameters(
                self.environment.currentText(),
                self.tournament_scenario,
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
        if self._is_app_log_running():
            QMessageBox.information(
                self,
                "日志正在抓取",
                "请先在“Android 日志”页停止抓取，再启动数据任务。",
            )
            return
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
        self.api_stop_button.setEnabled(False)
        self.scenario_stop_button.setEnabled(False)
        self._set_status("●  STOPPING", "#a66b13")
        self._append_log(
            "\n[signal] stop requested; no new tasks will start; "
            "waiting only for active requests\n"
        )

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
        self._finish_deferred_close_if_idle()

    @Slot(str)
    def _append_log(self, text: str) -> None:
        if self.current_section == 2:
            target = self.feature_log
        elif self.current_section == 3:
            target = self.api_log
        elif self.current_section == 4:
            target = self.scenario_log
        else:
            target = self.log
        cursor = target.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        target.setTextCursor(cursor)
        target.ensureCursorVisible()

    @Slot()
    def _clear_log(self) -> None:
        if self.current_section == 2:
            self.feature_log.clear()
        elif self.current_section == 3:
            self.api_log.clear()
        elif self.current_section == 4:
            self.scenario_log.clear()
        else:
            self.log.clear()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.feature_stop_button.setEnabled(running)
        self.api_stop_button.setEnabled(running)
        self.scenario_stop_button.setEnabled(running)
        for button in self.navigation_buttons:
            button.setEnabled(not running)
        for widget in self.config_widgets:
            widget.setEnabled(not running)
        if not running:
            self._on_feature_sql_selection_changed()
            self._on_api_selection_changed()
            self._on_scenario_selection_changed()
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
        if (
            self._is_apk_busy()
            or self._is_ios_busy()
            or self._is_app_log_query_busy()
        ):
            QMessageBox.information(
                self,
                "设备操作进行中",
                "当前安装、设备检测或应用列表读取结束后才能退出。",
            )
            event.ignore()
            return
        if self._is_channel_source_updating():
            QMessageBox.information(
                self,
                "正在更新参数",
                "渠道参数更新结束后才能退出。",
            )
            event.ignore()
            return
        workflow_running = self._is_running()
        log_running = self._is_app_log_running()
        if workflow_running or log_running:
            if workflow_running and log_running:
                prompt = "任务和日志抓取仍在运行。停止它们并退出？"
            elif log_running:
                prompt = "手机日志仍在抓取。停止抓取并退出？"
            else:
                prompt = "任务仍在运行。停止任务并退出？"
            answer = QMessageBox.question(
                self,
                "退出",
                prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.exit_after_workers_stop = True
            if workflow_running:
                self.close_after_stop = True
                self._stop()
            if log_running:
                self.close_after_log_stop = True
                self._stop_app_log_capture()
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
