"""主窗口复用的轻量 Qt 控件。

本模块只负责输入体验和文本高亮，不接触业务数据或网络。
"""

import re
from typing import Callable, Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)


ACTION_TABLE_ROW_HEIGHT = 48


def add_form_row(
    layout: QGridLayout,
    row: int,
    label_text: str,
    widget: QWidget,
    suffix: str = "",
) -> QLabel:
    """向两列或三列表单添加统一样式的标签、控件和可选提示。"""
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


def action_button_row(
    actions: Iterable[tuple[str, Callable[[], None], bool]],
) -> QWidget:
    """创建表格中的操作按钮行，统一样式、间距与信号绑定。"""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(4, 3, 4, 3)
    layout.setSpacing(5)
    for label, callback, enabled in actions:
        button = QPushButton(label)
        button.setObjectName(
            "primaryButton" if label == "归因+安装" else "secondaryButton"
        )
        button.setEnabled(enabled)
        button.clicked.connect(lambda _checked=False, fn=callback: fn())
        layout.addWidget(button)
    return container

class NumberInput(QSpinBox):
    """仅允许直接输入数字，不提供步进按钮或滚轮调节。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def wheelEvent(self, event) -> None:
        event.ignore()


def _text_format(color: str, *, bold: bool = False) -> QTextCharFormat:
    text_format = QTextCharFormat()
    text_format.setForeground(QColor(color))
    if bold:
        text_format.setFontWeight(QFont.Weight.Bold)
    return text_format


class JsonSyntaxHighlighter(QSyntaxHighlighter):
    """为 JSON 编辑器和响应内容提供轻量语法高亮。"""

    STRING_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"')
    NUMBER_PATTERN = re.compile(
        r"(?<![\w.])-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])"
    )
    LITERAL_PATTERN = re.compile(r"\b(?:true|false|null)\b")
    PUNCTUATION_PATTERN = re.compile(r"[{}\[\],:]")

    def __init__(self, document) -> None:
        super().__init__(document)
        self.string_format = _text_format("#228653")
        self.key_format = _text_format("#2846a6", bold=True)
        self.number_format = _text_format("#a05a00")
        self.literal_format = _text_format("#7b3fb2", bold=True)
        self.punctuation_format = _text_format("#69717d")

    def highlightBlock(self, text: str) -> None:
        for match in self.PUNCTUATION_PATTERN.finditer(text):
            self.setFormat(match.start(), len(match.group()), self.punctuation_format)
        for match in self.NUMBER_PATTERN.finditer(text):
            self.setFormat(match.start(), len(match.group()), self.number_format)
        for match in self.LITERAL_PATTERN.finditer(text):
            self.setFormat(match.start(), len(match.group()), self.literal_format)
        for match in self.STRING_PATTERN.finditer(text):
            suffix = text[match.end():]
            text_format = (
                self.key_format
                if re.match(r"\s*:", suffix)
                else self.string_format
            )
            self.setFormat(match.start(), len(match.group()), text_format)


class ApiPreviewHighlighter(JsonSyntaxHighlighter):
    """在 JSON 之外强调请求方法、URL 和内容分区。"""

    REQUEST_PATTERN = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(.*)$")

    def __init__(self, document) -> None:
        super().__init__(document)
        self.method_format = _text_format("#ffffff", bold=True)
        self.method_format.setBackground(QColor("#2846a6"))
        self.url_format = _text_format("#1559a5")
        self.heading_format = _text_format("#20242a", bold=True)
        self.meta_format = _text_format("#808792")

    def highlightBlock(self, text: str) -> None:
        super().highlightBlock(text)
        request_match = self.REQUEST_PATTERN.match(text)
        if request_match:
            self.setFormat(
                request_match.start(1),
                len(request_match.group(1)),
                self.method_format,
            )
            self.setFormat(
                request_match.start(2),
                len(request_match.group(2)),
                self.url_format,
            )
        elif text in ("Headers", "Body"):
            self.setFormat(0, len(text), self.heading_format)
        elif text.startswith("Timeout:"):
            self.setFormat(0, len(text), self.meta_format)


class ApiLogHighlighter(JsonSyntaxHighlighter):
    """强调响应日志中的请求摘要、成功状态和失败状态。"""

    STATUS_PATTERN = re.compile(r"(?<!\d)([1-5]\d{2})(?!\d)")

    def __init__(self, document) -> None:
        super().__init__(document)
        self.label_format = _text_format("#2846a6", bold=True)
        self.success_format = _text_format("#228653", bold=True)
        self.error_format = _text_format("#c43d47", bold=True)

    def highlightBlock(self, text: str) -> None:
        super().highlightBlock(text)
        if text.startswith("[api]"):
            self.setFormat(0, 5, self.label_format)
        for match in self.STATUS_PATTERN.finditer(text):
            status = int(match.group(1))
            text_format = (
                self.success_format if 200 <= status < 400 else self.error_format
            )
            self.setFormat(match.start(1), len(match.group(1)), text_format)


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
