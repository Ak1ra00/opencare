"""Design tokens and Qt stylesheet for OpenCare's light and dark themes.

Use ``color("accent")`` etc. for custom painting; widgets get styled through the global
QSS below via objectName / dynamic properties:
  QPushButton[kind="primary" | "secondary" | "danger" | "ghost"]
  QFrame#Card, QLabel[role="title" | "subtitle" | "muted" | "h2" | "stat" | "caption"]
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#F4F6F8",
    "sidebar": "#ECEFF3",
    "surface": "#FFFFFF",
    "surface_alt": "#F1F4F7",
    "hover": "#E6EAEF",
    "border": "#DDE2E8",
    "text": "#18202A",
    "text_muted": "#5A6573",
    "text_faint": "#8C96A3",
    "accent": "#0E9384",
    "accent_hover": "#0B7D70",
    "accent_soft": "#D8F3EE",
    "accent_text": "#FFFFFF",
    "danger": "#D14343",
    "danger_soft": "#FBE4E4",
    "warning": "#D9831F",
    "warning_soft": "#FCEFD9",
    "success": "#1E9A55",
    "success_soft": "#DDF3E6",
    "info": "#2F6FDB",
    "info_soft": "#E1EBFB",
    "track": "#E2E7ED",
    "shadow": "#1A000000",
}

DARK = {
    "bg": "#111418",
    "sidebar": "#0C0F12",
    "surface": "#1A1E23",
    "surface_alt": "#21262C",
    "hover": "#272D34",
    "border": "#2C333B",
    "text": "#E7EBEF",
    "text_muted": "#9AA5B1",
    "text_faint": "#6B7682",
    "accent": "#2CC5B2",
    "accent_hover": "#4FD8C6",
    "accent_soft": "#123A35",
    "accent_text": "#06201C",
    "danger": "#F06A6A",
    "danger_soft": "#3A1E20",
    "warning": "#F0A44B",
    "warning_soft": "#3A2C17",
    "success": "#43C97F",
    "success_soft": "#163222",
    "info": "#6EA2F5",
    "info_soft": "#18263D",
    "track": "#2A3138",
    "shadow": "#66000000",
}

FONT_FAMILY = "Segoe UI Variable Text"
FONT_FALLBACK = "Segoe UI"
RADIUS = 10


class _ThemeManager(QObject):
    changed = Signal(bool)  # is_dark

    def __init__(self):
        super().__init__()
        self.mode = "system"
        self.dark = False

    def tokens(self) -> dict[str, str]:
        return DARK if self.dark else LIGHT


manager = _ThemeManager()


def color(name: str) -> QColor:
    return QColor(manager.tokens()[name])


def hex_color(name: str) -> str:
    return manager.tokens()[name]


def is_dark() -> bool:
    return manager.dark


def _system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # pragma: no cover
        return False


def base_font(point_size: float = 10.0, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT_FAMILY)
    if not f.exactMatch():
        f = QFont(FONT_FALLBACK)
    f.setPointSizeF(point_size)
    f.setWeight(weight)
    return f


def apply_theme(app: QApplication, mode: str = "system") -> None:
    manager.mode = mode
    manager.dark = _system_is_dark() if mode == "system" else mode == "dark"
    t = manager.tokens()
    app.setStyle("Fusion")
    app.setFont(base_font())
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(t["bg"]))
    pal.setColor(QPalette.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.Base, QColor(t["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["surface_alt"]))
    pal.setColor(QPalette.Text, QColor(t["text"]))
    pal.setColor(QPalette.Button, QColor(t["surface"]))
    pal.setColor(QPalette.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(t["accent_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(t["surface"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(t["text_faint"]))
    pal.setColor(QPalette.Link, QColor(t["accent"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["text_faint"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(t))
    manager.changed.emit(manager.dark)


def stylesheet(t: dict[str, str]) -> str:
    return f"""
* {{ outline: none; }}
QWidget {{ color: {t['text']}; }}
QMainWindow, QDialog {{ background: {t['bg']}; }}
QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 6px 8px; border-radius: 6px; }}

/* sidebar */
#Sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
#Sidebar QPushButton[nav="true"] {{
    text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    color: {t['text_muted']}; background: transparent; font-size: 10.5pt;
}}
#Sidebar QPushButton[nav="true"]:hover {{ background: {t['hover']}; color: {t['text']}; }}
#Sidebar QPushButton[nav="true"]:checked {{ background: {t['accent_soft']}; color: {t['accent']}; font-weight: 600; }}
#Brand {{ font-size: 13pt; font-weight: 700; }}

/* typography */
QLabel[role="title"] {{ font-size: 18pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 12.5pt; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: 10.5pt; font-weight: 600; }}
QLabel[role="subtitle"] {{ color: {t['text_muted']}; font-size: 10.5pt; }}
QLabel[role="muted"] {{ color: {t['text_muted']}; }}
QLabel[role="faint"] {{ color: {t['text_faint']}; }}
QLabel[role="caption"] {{ color: {t['text_muted']}; font-size: 9pt; }}
QLabel[role="stat"] {{ font-size: 20pt; font-weight: 600; }}
QLabel[role="link"] {{ color: {t['accent']}; }}

/* cards */
QFrame#Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: {RADIUS}px; }}
QFrame#Card[hover="true"]:hover {{ border-color: {t['accent']}; }}
QFrame#Divider {{ background: {t['border']}; max-height: 1px; min-height: 1px; }}

/* buttons */
QPushButton {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
    padding: 7px 16px; font-weight: 500;
}}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:disabled {{ color: {t['text_faint']}; background: {t['surface_alt']}; }}
QPushButton[kind="primary"] {{ background: {t['accent']}; color: {t['accent_text']}; border: 1px solid {t['accent']}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {t['accent_hover']}; border-color: {t['accent_hover']}; }}
QPushButton[kind="primary"]:disabled {{ background: {t['track']}; border-color: {t['track']}; color: {t['text_faint']}; }}
QPushButton[kind="danger"] {{ background: {t['danger']}; color: #FFFFFF; border: 1px solid {t['danger']}; font-weight: 600; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {t['accent']}; padding: 6px 10px; }}
QPushButton[kind="ghost"]:hover {{ background: {t['accent_soft']}; }}
QPushButton[size="large"] {{ padding: 12px 28px; font-size: 12pt; border-radius: 10px; }}

/* inputs */
QLineEdit, QComboBox, QSpinBox, QTimeEdit {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 6px 8px;
    selection-background-color: {t['accent']}; selection-color: {t['accent_text']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']}; selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1.5px solid {t['text_faint']}; background: {t['surface']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url(:/oc/check_white.svg); }}
QCheckBox::indicator:indeterminate {{ background: {t['accent']}; border-color: {t['accent']}; image: url(:/oc/dash_white.svg); }}
QRadioButton::indicator {{ width: 16px; height: 16px; }}

/* lists, trees, tables */
QTreeView, QListView, QTableView {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
    alternate-background-color: {t['surface_alt']}; gridline-color: {t['border']};
}}
QTreeView::item, QListView::item, QTableView::item {{ padding: 4px 2px; min-height: 26px; }}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background: {t['hover']}; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
QHeaderView::section {{
    background: {t['surface']}; color: {t['text_muted']}; border: none; border-bottom: 1px solid {t['border']};
    padding: 6px 8px; font-weight: 600;
}}

/* scrollbars */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['track']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['text_faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['track']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; width: 0; height: 0; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* progress */
QProgressBar {{ background: {t['track']}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}

/* tabs */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; margin-right: 4px; color: {t['text_muted']}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['accent']}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {t['text']}; }}

QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['accent_soft']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

/* badges */
QLabel[badge="neutral"] {{ background: {t['surface_alt']}; color: {t['text_muted']}; border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}
QLabel[badge="accent"] {{ background: {t['accent_soft']}; color: {t['accent']}; border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}
QLabel[badge="danger"] {{ background: {t['danger_soft']}; color: {t['danger']}; border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}
QLabel[badge="warning"] {{ background: {t['warning_soft']}; color: {t['warning']}; border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}
QLabel[badge="success"] {{ background: {t['success_soft']}; color: {t['success']}; border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}
QLabel[badge="info"] {{ background: {t['info_soft']}; color: {t['info']}; border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}

#Toast {{ background: {t['text']}; color: {t['bg']}; border-radius: 8px; padding: 10px 16px; }}
"""
