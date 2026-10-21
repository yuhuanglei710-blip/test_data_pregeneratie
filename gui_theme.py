"""应用字体、导航元数据和 Qt 样式表。

视觉配置集中在这里，业务窗口只引用公开常量和字体辅助函数。
"""

import os
from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QComboBox, QWidget

WINDOWS_FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
UI_FONT_CANDIDATES = (
    "Noto Sans SC",
    "Microsoft YaHei UI",
    "DengXian",
    "Segoe UI",
)
MONOSPACE_FONT_CANDIDATES = (
    "Cascadia Mono",
    "Consolas",
)
AUTO_ACCOUNT_SQL_PARAMETERS = {"uid", "userid"}


class _WheelValueChangeBlocker(QObject):
    """全局拦截下拉框和数值控件的滚轮改值。"""

    @staticmethod
    def _value_control(widget: object) -> bool:
        current = widget if isinstance(widget, QWidget) else None
        while current is not None:
            if isinstance(current, QAbstractSpinBox):
                return True
            if isinstance(current, QComboBox):
                # 下拉列表展开后仍允许滚动列表；关闭状态禁止改当前值。
                return not current.view().isVisible()
            current = current.parentWidget()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Wheel
            and self._value_control(watched)
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)


def _install_wheel_value_change_blocker(app: QApplication) -> None:
    if getattr(app, "_wheel_value_change_blocker", None) is not None:
        return
    blocker = _WheelValueChangeBlocker(app)
    app.installEventFilter(blocker)
    app._wheel_value_change_blocker = blocker


def _best_font_family(candidates: tuple[str, ...]) -> str:
    available = set(QFontDatabase.families())
    return next((family for family in candidates if family in available), candidates[-1])


def _quality_font(family: str, point_size: float) -> QFont:
    font = QFont(family)
    font.setPointSizeF(point_size)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    return font


def configure_application_fonts(app: QApplication) -> tuple[str, str]:
    """加载高清中文字体，并为所有 Qt 控件设置高质量矢量字体。"""
    _install_wheel_value_change_blocker(app)
    for filename in (
        "Noto Sans SC (TrueType).otf",
        "Noto Sans SC Medium (TrueType).otf",
        "Noto Sans SC Bold (TrueType).otf",
    ):
        font_path = WINDOWS_FONT_DIR / filename
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    ui_family = _best_font_family(UI_FONT_CANDIDATES)
    monospace_family = _best_font_family(MONOSPACE_FONT_CANDIDATES)
    app.setFont(_quality_font(ui_family, 10.0))
    app.setProperty("uiFontFamily", ui_family)
    app.setProperty("monospaceFontFamily", monospace_family)
    return ui_family, monospace_family


def application_monospace_font(point_size: float) -> QFont:
    app = QApplication.instance()
    configured = app.property("monospaceFontFamily") if app is not None else ""
    family = str(configured or _best_font_family(MONOSPACE_FONT_CANDIDATES))
    return _quality_font(family, point_size)


SECTION_INFO = (
    ("数据准备", "账号生成", "批量生成测试账号，或使用指定邮箱创建单个账号。"),
    ("数据准备", "锦标赛造数", "创建参赛账号并完成充值、下注等锦标赛数据准备。"),
    ("数据准备", "玩家分层", "按净利润优先、利润率兜底识别玩家层级，并可按 UID 构造目标分层数据。"),
    ("数据准备", "用户查询", "按 UID 直接查询并编辑数据库用户信息。"),
    ("接口与流程", "SQL 数据模板", "维护并执行可复用 SQL，用于快速准备业务测试数据。"),
    ("接口与流程", "API 请求模板", "保存、调试并复用环境化的 HTTP 请求。"),
    ("接口与流程", "自动化场景", "把 SQL、API、变量提取和断言编排为完整流程。"),
    ("设备工具", "Android 安装", "管理 APK 缓存，并对 Android 设备执行归因与安装。"),
    ("设备工具", "iOS 安装", "管理 IPA 缓存，并对 iPhone 执行归因与安装。"),
    ("设备工具", "Android 日志", "按应用、级别和关键词抓取并导出设备日志。"),
    ("通用工具", "时间戳工具", "解析秒/毫秒时间戳与日期时间，并进行时区展示和偏移计算。"),
    ("通用工具", "SSH 主机", "管理远程主机，测试 SSH 连接、执行命令并读取或修改主机时间。"),
    ("通用工具", "快捷访问", "集中管理常用链接、分类和登录字段，支持检索、复制与快速打开。"),
    ("系统", "环境与参数", "维护环境渠道参数、数据库连接和 SSH 私钥。"),
)


SECTION_INDEX = {title: index for index, (_, title, _) in enumerate(SECTION_INFO)}

# SECTION_INFO 负责左侧导航顺序；这里单独声明每个导航项对应的页面。
# 账号生成和锦标赛造数共用同一个页面，仅切换内部设置面板。
SECTION_CONTENT_INDEX = {
    "账号生成": 0,
    "锦标赛造数": 0,
    "玩家分层": 8,
    "用户查询": 9,
    "SQL 数据模板": 2,
    "API 请求模板": 3,
    "自动化场景": 4,
    "Android 安装": 5,
    "iOS 安装": 6,
    "Android 日志": 7,
    "时间戳工具": 10,
    "SSH 主机": 11,
    "快捷访问": 12,
    "环境与参数": 1,
}


APP_STYLESHEET = """
QWidget {
    color: #20242a;
    font-family: "Noto Sans SC", "Microsoft YaHei UI", "DengXian", "Segoe UI";
    font-size: 10pt;
}
QWidget#root { background: #f3f5f8; }
QDialog, QMessageBox { background: #ffffff; }
QFrame#topBar {
    background: #ffffff;
    border: 1px solid #dfe3e8;
    border-radius: 12px;
}

QLabel#title { color: #17191d; font-size: 18pt; font-weight: 700; }
QLabel#sectionTitle { color: #20242a; font-size: 11pt; font-weight: 600; }
QLabel#fieldLabel { color: #5d6470; font-size: 9pt; }
QLabel#pageDescription, QLabel#terminalMeta, QLabel#fieldHint,
QLabel#navigationMeta {
    color: #808792;
    font-size: 9pt;
}
QLabel#pageDescription { font-size: 9pt; }
QLabel#navigationMeta, QLabel#terminalMeta {
    font-family: "Cascadia Mono", "Consolas", monospace;
}
QLabel#navigationBrand, QLabel#sessionTitle {
    color: #17191d;
    font-weight: 700;
}
QLabel#navigationBrand { font-size: 13pt; }
QLabel#sessionTitle { font-family: "Cascadia Mono", "Consolas", monospace; font-size: 10pt; }
QLabel#navigationGroup {
    color: #8a919c;
    font-size: 8pt;
    font-weight: 700;
    padding: 10px 10px 3px 10px;
}
QLabel#metricSummary {
    color: #343a42;
    background: #f7f8fa;
    border: 1px solid #e0e4ea;
    border-radius: 8px;
    padding: 14px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    line-height: 1.5;
}
QLabel#tierBadge {
    color: #2846a6;
    background: #edf1ff;
    border: 1px solid #d6defa;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 11pt;
    font-weight: 700;
}
QLabel#statusTag {
    color: #58616d;
    background: #f2f4f7;
    border: 1px solid #dfe3e8;
    border-radius: 11px;
    padding: 4px 9px;
    font-size: 8.5pt;
    font-weight: 600;
}
QLabel#requestBadge {
    color: #2846a6;
    background: #edf1ff;
    border: 1px solid #d6defa;
    border-radius: 7px;
    padding: 7px 10px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-weight: 700;
}
QLabel#requestBadge:disabled {
    color: #808792;
    background: #f3f5f7;
    border-color: #dfe3e8;
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
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
    font-weight: 600;
}

QFrame#settingsPanel, QFrame#terminalPanel, QFrame#navigation,
QFrame#configCard {
    background: #ffffff;
    border: 1px solid #dfe3e8;
    border-radius: 10px;
}
QFrame#userLookupQueryPanel {
    background: #ffffff;
    border: 1px solid #e4e7eb;
    border-radius: 8px;
}
QFrame#userLookupResultPanel {
    background: #ffffff;
    border: 0;
}
QScrollArea#userLookupScroll,
QScrollArea#userLookupScroll > QWidget > QWidget,
QWidget#userLookupContent {
    background: #ffffff;
    border: 0;
}
QFrame#quickAccessDetail {
    background: #f8f9fc;
    border: 1px solid #e0e4ee;
    border-radius: 9px;
}
QFrame#terminalPanel, QFrame#configCard, QFrame#navigation { background: #ffffff; }
QFrame#userProfileCard {
    background: #f8f9fc;
    border: 1px solid #e0e4ee;
    border-radius: 10px;
}
QLabel#userFieldValue {
    color: #252a31;
    background: transparent;
    border: 0;
    padding: 6px 0;
}
QFrame#apkDropZone {
    background: #f8f9fb;
    border: 1px dashed #b9c0ca;
    border-radius: 7px;
}
QFrame#apkDropZone:hover, QFrame#apkDropZone[dragActive="true"] {
    background: #edf1ff;
    border-color: #4b67d1;
}
QFrame#apkDropZone:disabled {
    background: #f1f3f5;
    border-color: #dfe3e8;
}
QLabel#apkDropHint {
    color: #69717c;
    font-size: 9pt;
}
QFrame#apkDropZone[dragActive="true"] QLabel#apkDropHint {
    color: #2846a6;
    font-weight: 600;
}

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
QTabWidget::pane {
    background: #fbfcfd;
    border: 1px solid #d6dbe1;
    border-radius: 7px;
    top: -1px;
}
QTabBar::tab {
    color: #737b86;
    background: #f3f5f7;
    border: 1px solid #d6dbe1;
    padding: 7px 14px;
}
QTabBar::tab:first { border-top-left-radius: 7px; }
QTabBar::tab:last { border-top-right-radius: 7px; }
QTabBar::tab:selected {
    color: #20242a;
    background: #ffffff;
    font-weight: 700;
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
    font-size: 9pt;
    font-weight: 600;
}
QPlainTextEdit#terminal {
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
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
