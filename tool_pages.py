"""时间戳、SSH 主机和快捷访问桌面页面。"""

from __future__ import annotations

from dataclasses import replace
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from base.database_config import import_ssh_private_key, load_ssh_private_keys
from base.quick_access import (
    QuickAccessField,
    QuickAccessLink,
    load_quick_access,
    quick_access_share_text,
    save_quick_access,
    validate_quick_access_link,
)
from base.ssh_host import (
    AUTH_KEY_ONLY,
    AUTH_KEY_PREFERRED,
    AUTH_PASSWORD_ONLY,
    SshCommandResult,
    SshHostConfig,
    SshHostTime,
    execute_ssh_command,
    get_ssh_host_time,
    load_ssh_hosts,
    save_ssh_hosts,
    set_ssh_host_time,
    test_ssh_host,
)
from tools.timestamp_tool import TimestampResult, offset_timestamp, parse_timestamp


def _section_card(title_text: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("settingsPanel")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    title = QLabel(title_text)
    title.setObjectName("sectionTitle")
    layout.addWidget(title)
    return card, layout


def _copy_text(parent: QWidget, value: object) -> None:
    QApplication.clipboard().setText(str(value))
    if hasattr(parent, "status_text"):
        parent.status_text.setText("已复制到剪贴板")


class TimestampPanel(QWidget):
    """可复用的时间戳输入和结果面板。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.result: Optional[TimestampResult] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "输入秒/毫秒时间戳或日期时间，如 2026-07-14 10:30:00"
        )
        self.input.textChanged.connect(self._parse_input)
        input_row.addWidget(self.input, 1)
        now_button = QPushButton("使用当前时间")
        now_button.setObjectName("secondaryButton")
        now_button.clicked.connect(self.use_now)
        input_row.addWidget(now_button)
        layout.addLayout(input_row)

        self.error = QLabel("")
        self.error.setObjectName("fieldHint")
        self.error.setStyleSheet("color: #c43d47;")
        layout.addWidget(self.error)

        result_grid = QGridLayout()
        result_grid.setHorizontalSpacing(12)
        result_grid.setVerticalSpacing(9)
        self.values: dict[str, QLabel] = {}
        fields = (
            ("本地时间", "local_time"),
            ("UTC 时间", "utc_time"),
            ("UTC+8（北京时间）", "utc_plus_8"),
            ("UTC-8", "utc_minus_8"),
            ("ISO 8601", "iso_8601"),
            ("相对时间", "relative"),
            ("时间戳（毫秒）", "epoch_milliseconds"),
            ("时间戳（秒）", "epoch_seconds"),
        )
        for row, (label_text, key) in enumerate(fields):
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            result_grid.addWidget(label, row, 0)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if key.startswith("epoch") or key == "iso_8601":
                value.setFont(QFont("Consolas", 10))
            result_grid.addWidget(value, row, 1, 1, 2)
            copy_button = QPushButton("复制")
            copy_button.setObjectName("secondaryButton")
            copy_button.clicked.connect(
                lambda _checked=False, field=key: self._copy_result(field)
            )
            result_grid.addWidget(copy_button, row, 3)
            self.values[key] = value
        result_grid.setColumnStretch(1, 1)
        layout.addLayout(result_grid)

        offset_row = QHBoxLayout()
        offset_label = QLabel("时间偏移")
        offset_label.setObjectName("fieldLabel")
        offset_row.addWidget(offset_label)
        self.offset_hours = QSpinBox()
        self.offset_hours.setRange(-100000, 100000)
        self.offset_hours.setSuffix(" 小时")
        offset_row.addWidget(self.offset_hours)
        apply_button = QPushButton("应用偏移")
        apply_button.setObjectName("primaryButton")
        apply_button.clicked.connect(self._apply_offset)
        offset_row.addWidget(apply_button)
        offset_row.addStretch()
        layout.addLayout(offset_row)
        self.offset_result = QLabel("偏移结果：—")
        self.offset_result.setObjectName("metricSummary")
        self.offset_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.offset_result)

    def use_now(self) -> None:
        from time import time

        self.input.setText(str(int(time())))

    def set_input(self, value: object) -> None:
        self.input.setText(str(value))

    def _parse_input(self, text: str) -> None:
        if not text.strip():
            self.result = None
            self.error.clear()
            self._render_result()
            return
        try:
            self.result = parse_timestamp(text)
            self.error.clear()
        except ValueError as error:
            self.result = None
            self.error.setText(str(error))
        self._render_result()

    def _render_result(self) -> None:
        for key, label in self.values.items():
            label.setText("—" if self.result is None else str(getattr(self.result, key)))
        self.offset_result.setText("偏移结果：—")

    def _copy_result(self, field: str) -> None:
        if self.result is not None:
            _copy_text(self, getattr(self.result, field))

    def _apply_offset(self) -> None:
        if self.result is None:
            self.error.setText("请先输入有效时间")
            return
        value = offset_timestamp(
            self.result.epoch_milliseconds,
            self.offset_hours.value(),
        )
        self.offset_result.setText(
            "偏移结果："
            f"{value.local_time}  ·  {value.utc_plus_8}\n"
            f"毫秒 {value.epoch_milliseconds}  ·  秒 {value.epoch_seconds}"
        )


class TimestampWorkspace(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card, card_layout = _section_card("时间戳解析与偏移")
        hint = QLabel("支持 Unix 秒/毫秒时间戳、ISO 8601 和本地日期时间字符串。")
        hint.setObjectName("fieldHint")
        card_layout.addWidget(hint)
        self.panel = TimestampPanel()
        card_layout.addWidget(self.panel, 1)
        layout.addWidget(card)
        self.panel.use_now()


class _ActionWorker(QObject):
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
        except Exception as error:  # noqa: BLE001 - UI boundary
            self.failed.emit(str(error))
        finally:
            self.done.emit()


class SshHostDialog(QDialog):
    def __init__(
        self,
        host: Optional[SshHostConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.original = host
        self.setWindowTitle("编辑 SSH 主机" if host else "新增 SSH 主机")
        self.resize(560, 500)
        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.name = QLineEdit(host.name if host else "")
        self.address = QLineEdit(host.host if host else "")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(host.port if host else 22)
        self.username = QLineEdit(host.username if host else "")
        self.password = QLineEdit(host.password if host else "")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.auth = QComboBox()
        self.auth.addItem("私钥优先（可回退密码）", AUTH_KEY_PREFERRED)
        self.auth.addItem("仅私钥", AUTH_KEY_ONLY)
        self.auth.addItem("仅密码", AUTH_PASSWORD_ONLY)
        if host:
            self.auth.setCurrentIndex(self.auth.findData(host.auth_type))
        self.private_key = QComboBox()
        self._reload_keys(host.private_key_id if host else "")
        self.passphrase = QLineEdit(host.passphrase if host else "")
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.remark = QLineEdit(host.remark if host else "")

        def add_row(row: int, label_text: str, widget: QWidget) -> None:
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            form.addWidget(label, row, 0)
            form.addWidget(widget, row, 1)

        add_row(0, "名称", self.name)
        address_row = QWidget()
        address_layout = QHBoxLayout(address_row)
        address_layout.setContentsMargins(0, 0, 0, 0)
        address_layout.addWidget(self.address, 1)
        address_layout.addWidget(self.port)
        add_row(1, "地址 / 端口", address_row)
        add_row(2, "用户名", self.username)
        add_row(3, "认证方式", self.auth)
        add_row(4, "登录密码", self.password)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.private_key, 1)
        import_button = QPushButton("导入私钥")
        import_button.clicked.connect(self._import_key)
        key_layout.addWidget(import_button)
        add_row(5, "私钥", key_row)
        add_row(6, "私钥口令", self.passphrase)
        add_row(7, "备注", self.remark)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        security = QLabel(
            "主机密码保存在本机 cache/ssh_hosts.json；私钥只登记文件路径，不复制私钥内容。"
        )
        security.setObjectName("fieldHint")
        security.setWordWrap(True)
        layout.addWidget(security)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._accept_validated)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.auth.currentIndexChanged.connect(self._sync_auth_fields)
        self._sync_auth_fields()

    def _reload_keys(self, selected_id: str = "") -> None:
        self.private_key.clear()
        self.private_key.addItem("不使用私钥", "")
        for key in load_ssh_private_keys().values():
            self.private_key.addItem(key.name, key.key_id)
        index = self.private_key.findData(selected_id)
        self.private_key.setCurrentIndex(max(0, index))

    def _import_key(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "导入 SSH 私钥",
            "",
            "SSH 私钥 (*.pem *.key id_rsa id_ed25519);;所有文件 (*)",
        )
        if not selected:
            return
        try:
            imported = import_ssh_private_key(selected)
        except ValueError as error:
            QMessageBox.critical(self, "导入失败", str(error))
            return
        self._reload_keys(imported.key_id)

    def _sync_auth_fields(self) -> None:
        auth_type = self.auth.currentData()
        self.private_key.setEnabled(auth_type != AUTH_PASSWORD_ONLY)
        self.passphrase.setEnabled(auth_type != AUTH_PASSWORD_ONLY)
        self.password.setEnabled(auth_type != AUTH_KEY_ONLY)

    def value(self) -> SshHostConfig:
        return SshHostConfig(
            host_id=self.original.host_id if self.original else "",
            name=self.name.text().strip(),
            host=self.address.text().strip(),
            port=self.port.value(),
            username=self.username.text().strip(),
            auth_type=str(self.auth.currentData()),
            private_key_id=str(self.private_key.currentData() or ""),
            password=self.password.text(),
            passphrase=self.passphrase.text(),
            remark=self.remark.text().strip(),
        )

    def _accept_validated(self) -> None:
        from base.ssh_host import validate_ssh_host

        try:
            validate_ssh_host(self.value())
        except ValueError as error:
            QMessageBox.warning(self, "配置不完整", str(error))
            return
        self.accept()


class SshHostWorkspace(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.hosts = load_ssh_hosts()
        self.action_thread: Optional[QThread] = None
        self.action_worker: Optional[_ActionWorker] = None
        self.success_callback: Optional[Callable[[object], None]] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._build_hosts_tab(), "SSH 主机")
        self.tabs.addTab(self._build_console_tab(), "命令与时间")
        self._refresh_hosts()

    def _build_hosts_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称、地址或备注")
        self.search.textChanged.connect(self._refresh_hosts)
        toolbar.addWidget(self.search, 1)
        add_button = QPushButton("+ 新增主机")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self._add_host)
        toolbar.addWidget(add_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("apkTable")
        self.table.setHorizontalHeaderLabels(
            ["名称", "地址", "认证", "私钥", "备注", "操作"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        self.status_text = QLabel("主机配置仅保存在本机")
        self.status_text.setObjectName("fieldHint")
        layout.addWidget(self.status_text)
        return page

    def _build_console_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("当前主机"))
        self.host_combo = QComboBox()
        host_row.addWidget(self.host_combo, 1)
        test_button = QPushButton("测试连接")
        test_button.clicked.connect(self._test_selected_host)
        host_row.addWidget(test_button)
        refresh_time = QPushButton("读取主机时间")
        refresh_time.clicked.connect(self._load_remote_time)
        host_row.addWidget(refresh_time)
        layout.addLayout(host_row)

        command_row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("输入远程命令，如 uname -a")
        self.command.returnPressed.connect(self._execute_selected_command)
        command_row.addWidget(self.command, 1)
        execute = QPushButton("执行命令")
        execute.setObjectName("primaryButton")
        execute.clicked.connect(self._execute_selected_command)
        command_row.addWidget(execute)
        layout.addLayout(command_row)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("连接测试、命令输出和时间操作结果会显示在这里。")
        layout.addWidget(self.output, 1)

        time_card = QFrame()
        time_card.setObjectName("configCard")
        time_layout = QVBoxLayout(time_card)
        self.remote_time = QLabel("远程时间：尚未读取")
        self.remote_time.setObjectName("metricSummary")
        time_layout.addWidget(self.remote_time)
        time_row = QHBoxLayout()
        self.remote_timestamp = QLineEdit()
        self.remote_timestamp.setPlaceholderText("输入秒/毫秒时间戳")
        time_row.addWidget(self.remote_timestamp, 1)
        now_button = QPushButton("填入当前")
        now_button.clicked.connect(
            lambda: self.remote_timestamp.setText(str(int(time.time())))
        )
        time_row.addWidget(now_button)
        set_button = QPushButton("修改主机时间")
        set_button.setObjectName("primaryButton")
        set_button.clicked.connect(self._set_remote_time)
        time_row.addWidget(set_button)
        time_layout.addLayout(time_row)
        warning = QLabel("修改时间通常需要远程用户拥有 root 或等效权限。")
        warning.setObjectName("fieldHint")
        time_layout.addWidget(warning)
        layout.addWidget(time_card)
        self.console_controls = [
            self.host_combo,
            test_button,
            refresh_time,
            self.command,
            execute,
            self.remote_timestamp,
            now_button,
            set_button,
        ]
        return page

    def _matching_hosts(self) -> list[SshHostConfig]:
        keyword = self.search.text().strip().casefold()
        if not keyword:
            return self.hosts
        return [
            host
            for host in self.hosts
            if keyword
            in " ".join((host.name, host.host, host.username, host.remark)).casefold()
        ]

    def _refresh_hosts(self) -> None:
        rows = self._matching_hosts()
        self.table.setRowCount(len(rows))
        keys = load_ssh_private_keys()
        auth_labels = {
            AUTH_KEY_PREFERRED: "私钥优先",
            AUTH_KEY_ONLY: "仅私钥",
            AUTH_PASSWORD_ONLY: "仅密码",
        }
        for row, host in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(host.name))
            self.table.setItem(
                row,
                1,
                QTableWidgetItem(f"{host.username}@{host.host}:{host.port}"),
            )
            self.table.setItem(row, 2, QTableWidgetItem(auth_labels[host.auth_type]))
            key_name = keys.get(host.private_key_id)
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(key_name.name if key_name else "—"),
            )
            self.table.setItem(row, 4, QTableWidgetItem(host.remark or "—"))
            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(3, 1, 3, 1)
            action_layout.setSpacing(4)
            for label, callback in (
                ("测试", lambda _c=False, item=host: self._test_host(item)),
                ("使用", lambda _c=False, item=host: self._use_host(item)),
                ("编辑", lambda _c=False, item=host: self._edit_host(item)),
                ("删除", lambda _c=False, item=host: self._delete_host(item)),
            ):
                button = QPushButton(label)
                button.clicked.connect(callback)
                action_layout.addWidget(button)
            self.table.setCellWidget(row, 5, actions)
        selected_id = self.host_combo.currentData() if self.host_combo.count() else ""
        self.host_combo.blockSignals(True)
        self.host_combo.clear()
        for host in self.hosts:
            self.host_combo.addItem(
                f"{host.name} · {host.username}@{host.host}:{host.port}",
                host.host_id,
            )
        index = self.host_combo.findData(selected_id)
        if index >= 0:
            self.host_combo.setCurrentIndex(index)
        self.host_combo.blockSignals(False)

    def _add_host(self) -> None:
        dialog = SshHostDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.hosts.append(dialog.value())
        self._save_and_refresh()

    def _edit_host(self, host: SshHostConfig) -> None:
        dialog = SshHostDialog(host, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.value()
        self.hosts = [updated if item.host_id == host.host_id else item for item in self.hosts]
        self._save_and_refresh()

    def _delete_host(self, host: SshHostConfig) -> None:
        answer = QMessageBox.question(
            self,
            "删除 SSH 主机",
            f"确定删除“{host.name}”吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.hosts = [item for item in self.hosts if item.host_id != host.host_id]
        self._save_and_refresh()

    def _save_and_refresh(self) -> None:
        try:
            save_ssh_hosts(self.hosts)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            self.hosts = load_ssh_hosts()
        self._refresh_hosts()

    def _use_host(self, host: SshHostConfig) -> None:
        index = self.host_combo.findData(host.host_id)
        if index >= 0:
            self.host_combo.setCurrentIndex(index)
        self.tabs.setCurrentIndex(1)

    def _selected_host(self) -> Optional[SshHostConfig]:
        host_id = self.host_combo.currentData()
        return next((host for host in self.hosts if host.host_id == host_id), None)

    def _test_host(self, host: SshHostConfig) -> None:
        self._run_action(
            lambda: test_ssh_host(host),
            lambda value: self._show_status(str(value)),
        )

    def _test_selected_host(self) -> None:
        host = self._selected_host()
        if host is None:
            QMessageBox.information(self, "选择主机", "请先新增并选择 SSH 主机")
            return
        self._test_host(host)

    def _execute_selected_command(self) -> None:
        host = self._selected_host()
        command = self.command.text().strip()
        if host is None or not command:
            QMessageBox.information(self, "命令未就绪", "请选择主机并输入远程命令")
            return
        self._append_output(f"$ {command}\n")
        self._run_action(
            lambda: execute_ssh_command(host, command),
            self._show_command_result,
        )

    def _load_remote_time(self) -> None:
        host = self._selected_host()
        if host is None:
            QMessageBox.information(self, "选择主机", "请先选择 SSH 主机")
            return
        self._run_action(lambda: get_ssh_host_time(host), self._show_remote_time)

    def _set_remote_time(self) -> None:
        host = self._selected_host()
        if host is None:
            QMessageBox.information(self, "选择主机", "请先选择 SSH 主机")
            return
        try:
            timestamp = parse_timestamp(self.remote_timestamp.text()).epoch_seconds
        except ValueError as error:
            QMessageBox.warning(self, "时间无效", str(error))
            return
        answer = QMessageBox.question(
            self,
            "确认修改主机时间",
            f"将“{host.name}”的系统时间修改为\n{parse_timestamp(timestamp).local_time}\n\n继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_action(
            lambda: set_ssh_host_time(host, timestamp),
            self._show_remote_time,
        )

    def _show_command_result(self, value: object) -> None:
        if not isinstance(value, SshCommandResult):
            return
        if value.stdout:
            self._append_output(value.stdout)
        if value.stderr:
            self._append_output(value.stderr)
        self._append_output(f"[exit {value.exit_status}]\n")

    def _show_remote_time(self, value: object) -> None:
        if not isinstance(value, SshHostTime):
            return
        self.remote_time.setText(
            f"远程时间：{value.date_text}\n"
            f"秒 {value.epoch_second}  ·  毫秒 {value.epoch_millisecond}"
        )
        self.remote_timestamp.setText(str(value.epoch_second))
        self._append_output(f"[time] {value.date_text} · {value.epoch_second}\n")

    def _show_status(self, message: str) -> None:
        self.status_text.setText(message)
        self._append_output(f"[ssh] {message}\n")

    def _append_output(self, text: str) -> None:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text if text.endswith("\n") else text + "\n")
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _run_action(
        self,
        action: Callable[[], object],
        on_success: Callable[[object], None],
    ) -> None:
        if self.is_busy():
            return
        self.success_callback = on_success
        self.table.setEnabled(False)
        for control in self.console_controls:
            control.setEnabled(False)
        self.status_text.setText("SSH 操作进行中…")
        self.action_thread = QThread(self)
        self.action_worker = _ActionWorker(action)
        self.action_worker.moveToThread(self.action_thread)
        self.action_thread.started.connect(self.action_worker.run)
        self.action_worker.succeeded.connect(self._action_succeeded)
        self.action_worker.failed.connect(self._action_failed)
        self.action_worker.done.connect(self.action_thread.quit)
        self.action_worker.done.connect(self.action_worker.deleteLater)
        self.action_thread.finished.connect(self._action_finished)
        self.action_thread.finished.connect(self.action_thread.deleteLater)
        self.action_thread.start()

    @Slot(object)
    def _action_succeeded(self, value: object) -> None:
        if self.success_callback:
            self.success_callback(value)

    @Slot(str)
    def _action_failed(self, message: str) -> None:
        self.status_text.setText(f"操作失败：{message}")
        self._append_output(f"[error] {message}\n")
        QMessageBox.critical(self, "SSH 操作失败", message)

    @Slot()
    def _action_finished(self) -> None:
        self.action_worker = None
        self.action_thread = None
        self.success_callback = None
        self.table.setEnabled(True)
        for control in self.console_controls:
            control.setEnabled(True)

    def is_busy(self) -> bool:
        return bool(self.action_thread and self.action_thread.isRunning())


class QuickAccessDialog(QDialog):
    def __init__(
        self,
        categories: list[str],
        link: Optional[QuickAccessLink] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.original = link
        self.setWindowTitle("编辑快捷访问" if link else "新增快捷访问")
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        form = QGridLayout()
        self.name = QLineEdit(link.name if link else "")
        self.url = QLineEdit(link.url if link else "")
        self.url.setPlaceholderText("https://...")
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(categories)
        self.category.setCurrentText(link.category if link else "")
        self.is_top = QCheckBox("置顶显示")
        self.is_top.setChecked(link.is_top if link else False)
        self.remark = QLineEdit(link.remark if link else "")
        for row, (label_text, widget) in enumerate(
            (
                ("名称", self.name),
                ("地址", self.url),
                ("分类", self.category),
                ("置顶", self.is_top),
                ("备注", self.remark),
            )
        ):
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            form.addWidget(label, row, 0)
            form.addWidget(widget, row, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)

        field_header = QHBoxLayout()
        field_title = QLabel("登录字段（账号、密码、AppKey 等）")
        field_title.setObjectName("sectionTitle")
        field_header.addWidget(field_title)
        field_header.addStretch()
        add_field = QPushButton("+ 添加字段")
        add_field.clicked.connect(self._add_field)
        field_header.addWidget(add_field)
        remove_field = QPushButton("删除选中字段")
        remove_field.clicked.connect(self._remove_fields)
        field_header.addWidget(remove_field)
        layout.addLayout(field_header)
        self.fields = QTableWidget(0, 2)
        self.fields.setObjectName("apkTable")
        self.fields.setHorizontalHeaderLabels(["字段名", "字段值"])
        self.fields.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.fields.verticalHeader().setVisible(False)
        layout.addWidget(self.fields, 1)
        for item in link.fields if link else []:
            self._add_field(item)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._accept_validated)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _add_field(self, field: Optional[QuickAccessField] = None) -> None:
        if isinstance(field, bool):
            field = None
        row = self.fields.rowCount()
        self.fields.insertRow(row)
        self.fields.setItem(row, 0, QTableWidgetItem(field.key if field else ""))
        self.fields.setItem(row, 1, QTableWidgetItem(field.value if field else ""))
        self.fields.setCurrentCell(row, 0)

    def _remove_fields(self) -> None:
        rows = sorted(
            {item.row() for item in self.fields.selectedItems()}, reverse=True
        )
        for row in rows:
            self.fields.removeRow(row)

    def value(self) -> QuickAccessLink:
        fields = []
        for row in range(self.fields.rowCount()):
            key_item = self.fields.item(row, 0)
            value_item = self.fields.item(row, 1)
            key = key_item.text().strip() if key_item else ""
            value = value_item.text() if value_item else ""
            if key or value:
                fields.append(QuickAccessField(key, value))
        return QuickAccessLink(
            link_id=self.original.link_id if self.original else "",
            name=self.name.text().strip(),
            url=self.url.text().strip(),
            category=self.category.currentText().strip(),
            remark=self.remark.text().strip(),
            is_top=self.is_top.isChecked(),
            fields=fields,
        )

    def _accept_validated(self) -> None:
        try:
            validate_quick_access_link(self.value())
        except ValueError as error:
            QMessageBox.warning(self, "内容不完整", str(error))
            return
        self.accept()


class CategoryDialog(QDialog):
    def __init__(self, categories: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.original = list(categories)
        self.renamed: dict[str, str] = {}
        self.deleted: set[str] = set()
        self.setWindowTitle("分类管理")
        self.resize(420, 430)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.addItems(categories)
        layout.addWidget(self.list, 1)
        actions = QHBoxLayout()
        for label, callback in (
            ("添加", self._add),
            ("重命名", self._rename),
            ("删除", self._delete),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        close = QPushButton("完成")
        close.setObjectName("primaryButton")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def categories(self) -> list[str]:
        return [self.list.item(index).text() for index in range(self.list.count())]

    def _add(self) -> None:
        value, ok = QInputDialog.getText(self, "添加分类", "分类名称")
        value = value.strip()
        if ok and value and value.casefold() not in {
            item.casefold() for item in self.categories()
        }:
            self.list.addItem(value)

    def _rename(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        old = item.text()
        value, ok = QInputDialog.getText(self, "重命名分类", "新名称", text=old)
        value = value.strip()
        if ok and value and value != old:
            item.setText(value)
            self.renamed[old] = value

    def _delete(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.deleted.add(item.text())
        self.list.takeItem(self.list.row(item))


class QuickAccessWorkspace(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.links, self.categories = load_quick_access()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card, card_layout = _section_card("快捷链接与登录信息")
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索链接名称、地址、分类或备注")
        self.search.textChanged.connect(self._refresh)
        toolbar.addWidget(self.search, 1)
        self.category_filter = QComboBox()
        self.category_filter.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self.category_filter)
        categories_button = QPushButton("分类管理")
        categories_button.clicked.connect(self._manage_categories)
        toolbar.addWidget(categories_button)
        add_button = QPushButton("+ 新增")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self._add_link)
        toolbar.addWidget(add_button)
        card_layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("apkTable")
        self.table.setHorizontalHeaderLabels(
            ["名称", "地址", "分类", "字段", "备注", "操作"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._open_from_row)
        card_layout.addWidget(self.table, 1)
        self.status_text = QLabel(
            "双击链接可在默认浏览器打开；字段值随链接保存在本机 cache。"
        )
        self.status_text.setObjectName("fieldHint")
        card_layout.addWidget(self.status_text)
        layout.addWidget(card)
        self._refresh_categories()
        self._refresh()

    def _refresh_categories(self) -> None:
        selected = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("全部分类")
        self.category_filter.addItems(self.categories)
        index = self.category_filter.findText(selected)
        self.category_filter.setCurrentIndex(max(0, index))
        self.category_filter.blockSignals(False)

    def _filtered(self) -> list[QuickAccessLink]:
        keyword = self.search.text().strip().casefold()
        category = self.category_filter.currentText()
        values = self.links
        if category and category != "全部分类":
            values = [item for item in values if item.category == category]
        if keyword:
            values = [
                item
                for item in values
                if keyword
                in " ".join((item.name, item.url, item.category, item.remark)).casefold()
            ]
        return sorted(values, key=lambda item: (not item.is_top, item.name.casefold()))

    def _refresh(self) -> None:
        rows = self._filtered()
        self.table.setRowCount(len(rows))
        for row, link in enumerate(rows):
            name = f"★ {link.name}" if link.is_top else link.name
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, link.link_id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(link.url))
            self.table.setItem(row, 2, QTableWidgetItem(link.category or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(str(len(link.fields))))
            self.table.setItem(row, 4, QTableWidgetItem(link.remark or "—"))
            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(3, 1, 3, 1)
            action_layout.setSpacing(4)
            for label, callback in (
                ("打开", lambda _c=False, item=link: self._open_link(item)),
                ("复制", lambda _c=False, item=link: self._copy_link(item)),
                ("编辑", lambda _c=False, item=link: self._edit_link(item)),
                ("删除", lambda _c=False, item=link: self._delete_link(item)),
            ):
                button = QPushButton(label)
                button.clicked.connect(callback)
                action_layout.addWidget(button)
            self.table.setCellWidget(row, 5, actions)

    def _link_for_row(self, row: int) -> Optional[QuickAccessLink]:
        item = self.table.item(row, 0)
        link_id = item.data(Qt.ItemDataRole.UserRole) if item else ""
        return next((link for link in self.links if link.link_id == link_id), None)

    def _open_from_row(self, row: int, _column: int) -> None:
        link = self._link_for_row(row)
        if link:
            self._open_link(link)

    def _open_link(self, link: QuickAccessLink) -> None:
        if not QDesktopServices.openUrl(QUrl(link.url)):
            QMessageBox.warning(self, "打开失败", "系统未能打开该链接")

    def _copy_link(self, link: QuickAccessLink) -> None:
        _copy_text(self, quick_access_share_text(link))
        self.status_text.setText(f"已复制“{link.name}”的链接和登录字段")

    def _add_link(self) -> None:
        dialog = QuickAccessDialog(self.categories, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.links.append(dialog.value())
        self._save_and_refresh()

    def _edit_link(self, link: QuickAccessLink) -> None:
        dialog = QuickAccessDialog(self.categories, link, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.value()
        self.links = [updated if item.link_id == link.link_id else item for item in self.links]
        self._save_and_refresh()

    def _delete_link(self, link: QuickAccessLink) -> None:
        answer = QMessageBox.question(
            self,
            "删除快捷访问",
            f"确定删除“{link.name}”及其登录字段吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.links = [item for item in self.links if item.link_id != link.link_id]
        self._save_and_refresh()

    def _manage_categories(self) -> None:
        dialog = CategoryDialog(self.categories, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for old, new in dialog.renamed.items():
            self.links = [
                replace(link, category=new) if link.category == old else link
                for link in self.links
            ]
        for deleted in dialog.deleted:
            self.links = [
                replace(link, category="") if link.category == deleted else link
                for link in self.links
            ]
        self.categories = dialog.categories()
        self._save_and_refresh()

    def _save_and_refresh(self) -> None:
        try:
            save_quick_access(self.links, self.categories)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", str(error))
            self.links, self.categories = load_quick_access()
        else:
            self.links, self.categories = load_quick_access()
        self._refresh_categories()
        self._refresh()
