"""Progress panel, confirm dialog, and transient toast."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from opencare.ui import icons, theme
from opencare.ui.widgets.base import danger_button, primary_button, secondary_button


class ProgressPanel(QWidget):
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._label = QLabel("Working…")
        self._label.setProperty("role", "subtitle")
        lay.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)
        row = QHBoxLayout()
        self._detail = QLabel("")
        self._detail.setProperty("role", "faint")
        self._detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self._detail, 1)
        self._cancel = secondary_button("Cancel")
        self._cancel.clicked.connect(self.cancelled.emit)
        row.addWidget(self._cancel)
        lay.addLayout(row)

    def set_label(self, text: str):
        self._label.setText(text)

    def set_progress(self, frac: float, detail: str = ""):
        self._bar.setValue(int(frac * 1000))
        if detail:
            self._detail.setText(self._elide(detail))

    def set_indeterminate(self, on: bool):
        self._bar.setRange(0, 0) if on else self._bar.setRange(0, 1000)

    def allow_cancel(self, on: bool):
        self._cancel.setVisible(on)

    def _elide(self, text: str) -> str:
        return text if len(text) <= 90 else "…" + text[-88:]


class ConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, confirm_text: str = "Continue",
                 danger: bool = False, details: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 18)
        lay.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)
        ic = QLabel()
        token = "danger" if danger else "accent"
        ic.setPixmap(icons.pixmap("warning_tri" if danger else "info", theme.hex_color(token), 28))
        ic.setAlignment(Qt.AlignTop)
        top.addWidget(ic)
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        t = QLabel(title)
        t.setProperty("role", "h2")
        text_col.addWidget(t)
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setProperty("role", "subtitle")
        text_col.addWidget(msg)
        top.addLayout(text_col, 1)
        lay.addLayout(top)

        if details:
            d = QLabel(details)
            d.setWordWrap(True)
            d.setProperty("role", "faint")
            d.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(d)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = secondary_button("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = danger_button(confirm_text) if danger else primary_button(confirm_text)
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        row.addWidget(ok)
        lay.addLayout(row)

    @staticmethod
    def ask(parent, title, message, confirm_text="Continue", danger=False, details="") -> bool:
        return ConfirmDialog(title, message, confirm_text, danger, details, parent).exec() == QDialog.Accepted


class Toast(QWidget):
    """Transient message that floats near the bottom of its parent."""

    def __init__(self, parent, text: str, kind: str = "neutral", msec: int = 2800):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)
        ic = {"success": ("check_circle", "success"), "danger": ("alert", "danger"),
              "warning": ("warning_tri", "warning"), "info": ("info", "info")}.get(kind)
        if ic:
            lbl = QLabel()
            lbl.setPixmap(icons.pixmap(ic[0], theme.hex_color(ic[1]), 18))
            lay.addWidget(lbl)
        t = QLabel(text)
        t.setStyleSheet(f"color: {theme.hex_color('bg')};")
        lay.addWidget(t)
        self._eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._eff)
        self._msec = msec
        self.adjustSize()

    def show_toast(self):
        parent = self.parentWidget()
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 40
        self.move(max(10, x), max(10, y))
        self.show()
        self.raise_()
        self._fade(0.0, 1.0, 180)
        QTimer.singleShot(self._msec, self._dismiss)

    def _dismiss(self):
        anim = self._fade(1.0, 0.0, 240)
        anim.finished.connect(self.deleteLater)

    def _fade(self, a, b, dur):
        anim = QPropertyAnimation(self._eff, b"opacity", self)
        anim.setStartValue(a)
        anim.setEndValue(b)
        anim.setDuration(dur)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()
        self._anim = anim
        return anim


def toast(parent, text: str, kind: str = "neutral", msec: int = 2800):
    # walk up to the top-level window so it isn't clipped by a page
    top = parent.window() if parent else None
    t = Toast(top or parent, text, kind, msec)
    t.show_toast()
    return t
