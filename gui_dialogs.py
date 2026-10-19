"""主窗口使用的编辑弹窗和文件拖放控件。

弹窗负责输入、验证与保存；主窗口负责刷新列表和启动业务动作。
"""

import re
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from base.api_request import ApiTemplate, save_api_template
from base.apk_manager import CachedApk
from base.channel_source import log_database_name_for_environment
from base.database_config import (
    DatabaseConnectionConfig,
    SshPrivateKey,
    save_database_connection,
    validate_database_connection,
)
from base.feature_scenario import (
    ASSERT_OPERATORS,
    FeatureScenario,
    ScenarioStep,
    new_step,
    save_feature_scenario,
)
from base.ipa_manager import CachedIpa
from base.sql_data import (
    SqlTemplate,
    save_sql_template,
    template_parameter_names as sql_template_parameter_names,
)
from gui_widgets import NumberInput, SearchableComboBox, add_form_row
from gui_workers import DatabaseTestWorker

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

        parameter_label = QLabel("添加参数")
        parameter_label.setObjectName("fieldLabel")
        layout.addWidget(parameter_label)
        parameter_row = QHBoxLayout()
        self.parameter_name_input = QLineEdit()
        self.parameter_name_input.setPlaceholderText("例如：viplevel")
        self.parameter_name_input.returnPressed.connect(self._add_parameter)
        parameter_row.addWidget(self.parameter_name_input, 1)
        add_parameter_button = QPushButton("添加声明")
        add_parameter_button.setObjectName("secondaryButton")
        add_parameter_button.clicked.connect(self._add_parameter)
        parameter_row.addWidget(add_parameter_button)
        layout.addLayout(parameter_row)

        sql_label = QLabel("SQL（使用 @参数名=xxx; 声明运行参数）")
        sql_label.setObjectName("fieldLabel")
        layout.addWidget(sql_label)
        self.sql_input = QPlainTextEdit()
        self.sql_input.setPlaceholderText(
            "@userid=xxx;\n"
            "@viplevel=xxx;\n"
            "UPDATE user SET vip_level=@viplevel WHERE id=@userid;"
        )
        self.sql_input.setPlainText(template.sql if template else "@userid=xxx;\n")
        layout.addWidget(self.sql_input, 1)

        hint = QLabel(
            "参数名只能包含字母、数字和下划线，且不能以数字开头。"
            "单次执行时会自动生成参数输入框；正文可直接引用 @参数名。"
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
    def _add_parameter(self) -> None:
        name = self.parameter_name_input.text().strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            QMessageBox.information(
                self,
                "参数名无效",
                "参数名只能包含字母、数字和下划线，且不能以数字开头。",
            )
            return
        existing = sql_template_parameter_names(
            SqlTemplate("preview", "preview", self.sql_input.toPlainText())
        )
        if name.casefold() in {value.casefold() for value in existing}:
            QMessageBox.information(self, "参数已存在", f"@{name} 已在 SQL 中声明。")
            return
        cursor = self.sql_input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.insertText(f"@{name}=xxx;\n")
        self.sql_input.setTextCursor(cursor)
        self.parameter_name_input.clear()
        self.sql_input.setFocus()

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


class ApkDropZone(QFrame):
    """接收单个本地 APK，并把文件路径交给现有缓存流程。"""

    fileDropped = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("apkDropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self.setMinimumHeight(44)
        self.setMaximumHeight(52)
        self.setToolTip("仅支持拖入一个本地 APK 文件")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        self.hint = QLabel("拖拽 APK 到这里")
        self.hint.setObjectName("apkDropHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)

    @staticmethod
    def apk_path_from_mime_data(mime_data: object) -> str:
        """从拖拽数据中提取唯一且存在的本地 APK 路径。"""
        if not mime_data or not mime_data.hasUrls():
            return ""
        urls = mime_data.urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return ""
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() != ".apk" or not path.is_file():
            return ""
        return str(path)

    def _set_drag_active(self, active: bool) -> None:
        if self.property("dragActive") == active:
            return
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_selected_path(self, path: str) -> None:
        self.hint.setText(
            f"已选择 · {Path(path).name}" if path else "拖拽 APK 到这里"
        )

    def dragEnterEvent(self, event) -> None:
        if self.apk_path_from_mime_data(event.mimeData()):
            self._set_drag_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event) -> None:
        path = self.apk_path_from_mime_data(event.mimeData())
        self._set_drag_active(False)
        if not path:
            event.ignore()
            return
        self.fileDropped.emit(path)
        event.acceptProposedAction()


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
        add_form_row(form, 0, "安装包名称", self.name_input)
        add_form_row(form, 1, "归因链接", self.attribution_input)
        add_form_row(form, 2, "备注", self.note_input)
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
