"""Core reusable widgets and button factories."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from opencare.ui import icons, theme


def _btn(text: str, kind: str, icon_name: str | None, large: bool) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("kind", kind)
    if large:
        b.setProperty("size", "large")
    b.setCursor(Qt.PointingHandCursor)
    if icon_name:
        col = {"primary": "accent_text", "danger": "#FFFFFF"}.get(kind)
        tint = theme.hex_color("accent_text") if kind == "primary" else ("#FFFFFF" if kind == "danger" else theme.hex_color("accent" if kind == "ghost" else "text"))
        b.setIcon(icons.icon(icon_name, tint, 18))
        b.setIconSize(QSize(18, 18))
    return b


def primary_button(text: str, icon_name: str | None = None, large: bool = False) -> QPushButton:
    return _btn(text, "primary", icon_name, large)


def secondary_button(text: str, icon_name: str | None = None, large: bool = False) -> QPushButton:
    return _btn(text, "secondary", icon_name, large)


def danger_button(text: str, icon_name: str | None = None, large: bool = False) -> QPushButton:
    return _btn(text, "danger", icon_name, large)


def ghost_button(text: str, icon_name: str | None = None) -> QPushButton:
    return _btn(text, "ghost", icon_name, False)


def icon_button(icon_name: str, tooltip: str = "", size: int = 32, token: str = "text_muted") -> QPushButton:
    b = QPushButton()
    b.setProperty("kind", "ghost")
    b.setFixedSize(size, size)
    b.setCursor(Qt.PointingHandCursor)
    b.setIcon(icons.icon(icon_name, theme.hex_color(token), int(size * 0.6)))
    b.setIconSize(QSize(int(size * 0.6), int(size * 0.6)))
    if tooltip:
        b.setToolTip(tooltip)
    return b


class Card(QFrame):
    def __init__(self, parent=None, hover=False, padding=16, shadow=False):
        super().__init__(parent)
        self.setObjectName("Card")
        if hover:
            self.setProperty("hover", "true")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(padding, padding, padding, padding)
        lay.setSpacing(10)
        self._lay = lay
        if shadow:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(24)
            eff.setOffset(0, 4)
            eff.setColor(QColor(0, 0, 0, 40))
            self.setGraphicsEffect(eff)

    def body(self) -> QVBoxLayout:
        return self._lay

    def add(self, w: QWidget):
        self._lay.addWidget(w)
        return w


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class Badge(QLabel):
    def __init__(self, text: str, kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setProperty("badge", kind)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

    def set_kind(self, kind: str):
        self.setProperty("badge", kind)
        self.style().unpolish(self)
        self.style().polish(self)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(10)
        self._title = QLabel(title)
        self._title.setProperty("role", "title")
        row.addWidget(self._title)
        self._row = row
        row.addStretch(1)
        lay.addLayout(row)
        self._subtitle = QLabel(subtitle)
        self._subtitle.setProperty("role", "subtitle")
        self._subtitle.setVisible(bool(subtitle))
        self._subtitle.setWordWrap(True)
        lay.addWidget(self._subtitle)

    def set_subtitle(self, text: str):
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def add_action(self, w: QWidget):
        self._row.addWidget(w)


class StatTile(Card):
    def __init__(self, label: str, value: str = "—", icon_name: str | None = None, token: str = "accent", parent=None):
        super().__init__(parent, padding=14)
        self.body().setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        self._icon = QLabel()
        if icon_name:
            self._icon.setPixmap(icons.pixmap(icon_name, theme.hex_color(token), 18))
        top.addWidget(self._icon)
        lab = QLabel(label)
        lab.setProperty("role", "caption")
        top.addWidget(lab)
        top.addStretch(1)
        self.body().addLayout(top)
        self._value = QLabel(value)
        self._value.setProperty("role", "stat")
        self.body().addWidget(self._value)

    def set_value(self, value: str):
        self._value.setText(value)


class ToggleSwitch(QAbstractButton):
    """Animated iOS-style on/off switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, v: float):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off = QColor(theme.hex_color("track"))
        on = QColor(theme.hex_color("accent"))
        r = self.rect().adjusted(1, 1, -1, -1)
        track = QColor(on if self.isChecked() else off)
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + self._pos * (r.width() - d - 6)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(int(x), r.top() + 3, d, d)


class SegmentedControl(QWidget):
    changed = Signal(int)

    def __init__(self, options: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.setStyleSheet(
            f"#Segmented {{ background: {theme.hex_color('surface_alt')}; border-radius: 8px; }}"
            f"#Segmented QPushButton {{ border: none; background: transparent; padding: 6px 16px; border-radius: 6px; color: {theme.hex_color('text_muted')}; font-weight: 500; }}"
            f"#Segmented QPushButton:checked {{ background: {theme.hex_color('surface')}; color: {theme.hex_color('text')}; font-weight: 600; }}"
        )
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, opt in enumerate(options):
            b = QPushButton(opt)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            if i == 0:
                b.setChecked(True)
            self._group.addButton(b, i)
            lay.addWidget(b)
        self._group.idClicked.connect(self.changed.emit)

    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current_index(self, i: int):
        btn = self._group.button(i)
        if btn:
            btn.setChecked(True)


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, subtitle: str = "", token: str = "success", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, theme.hex_color(token), 56))
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        t = QLabel(title)
        t.setProperty("role", "h2")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setProperty("role", "subtitle")
            s.setAlignment(Qt.AlignCenter)
            s.setWordWrap(True)
            lay.addWidget(s)


class Page(QWidget):
    """Base class for sidebar pages."""

    page_id: str = ""
    title: str = ""
    subtitle: str = ""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services

    def on_show(self):
        """Called each time the page becomes visible."""

    def on_hide(self):
        pass
