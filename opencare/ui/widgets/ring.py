"""ScoreRing — animated circular health/score indicator."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from opencare.ui import theme


class ScoreRing(QWidget):
    def __init__(self, parent=None, diameter: int = 200):
        super().__init__(parent)
        self._d = diameter
        self.setMinimumSize(diameter, diameter)
        self._value = 0.0
        self._target = 0.0
        self._caption = ""
        self._big = ""
        self._token = "accent"
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_score(self, pct: float, big: str, caption: str, token: str = "accent"):
        self._big, self._caption, self._token = big, caption, token
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(max(0.0, min(100.0, pct)))
        self._anim.start()

    def get_value(self) -> float:
        return self._value

    def set_value(self, v: float):
        self._value = v
        self.update()

    value = Property(float, get_value, set_value)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        thickness = max(10, side // 14)
        m = thickness / 2 + 2
        rect = QRectF(m + (self.width() - side) / 2, m + (self.height() - side) / 2, side - 2 * m, side - 2 * m)

        p.setPen(QPen(QColor(theme.hex_color("track")), thickness, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 0, 360 * 16)

        accent = QColor(theme.hex_color(self._token))
        p.setPen(QPen(accent, thickness, Qt.SolidLine, Qt.RoundCap))
        span = int(-self._value / 100 * 360 * 16)
        p.drawArc(rect, 90 * 16, span)

        p.setPen(QColor(theme.hex_color("text")))
        f = QFont(theme.FONT_FALLBACK)
        f.setPointSizeF(side * 0.19)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        big_rect = QRectF(rect.left(), rect.center().y() - side * 0.17, rect.width(), side * 0.24)
        p.drawText(big_rect, Qt.AlignCenter, self._big)

        p.setPen(QColor(theme.hex_color("text_muted")))
        f2 = QFont(theme.FONT_FALLBACK)
        f2.setPointSizeF(side * 0.058)
        p.setFont(f2)
        cap_rect = QRectF(rect.left(), rect.center().y() + side * 0.08, rect.width(), side * 0.1)
        p.drawText(cap_rect, Qt.AlignCenter, self._caption)
