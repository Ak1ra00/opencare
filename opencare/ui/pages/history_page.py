"""History page: every change set, with details and one-click undo."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from opencare.core.fmt import human_bytes, relative_time
from opencare.core.tasks import run_task
from opencare.ui import icons, theme
from opencare.ui.widgets import (
    Badge,
    Card,
    Divider,
    EmptyState,
    Page,
    PageHeader,
    danger_button,
    ghost_button,
    secondary_button,
)
from opencare.ui.widgets.feedback import ConfirmDialog, toast


class ChangeCard(Card):
    def __init__(self, page, cs):
        super().__init__(hover=True)
        self.page = page
        self.cs = cs
        self._build()

    def _build(self):
        row = QHBoxLayout()
        row.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("history", theme.hex_color("accent"), 22))
        row.addWidget(ic, alignment=Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        title_row = QHBoxLayout()
        t = QLabel(self.cs.title)
        t.setProperty("role", "h3")
        title_row.addWidget(t)
        title_row.addStretch(1)
        when = QLabel(relative_time(self.cs.created))
        when.setProperty("role", "faint")
        title_row.addWidget(when)
        col.addLayout(title_row)

        bits = []
        if self.cs.items:
            bits.append(f"{self.cs.items} item{'s' if self.cs.items != 1 else ''}")
        if self.cs.bytes_freed:
            bits.append(f"{human_bytes(self.cs.bytes_freed)} freed")
        reversible = any(not op.restored for op in self.cs.operations)
        restored = self.cs.operations and all(op.restored for op in self.cs.operations)
        sub = QLabel("  ·  ".join(bits) if bits else "No measurable change")
        sub.setProperty("role", "subtitle")
        col.addWidget(sub)
        row.addLayout(col, 1)

        if restored:
            row.addWidget(Badge("Undone", "neutral"), alignment=Qt.AlignVCenter)
        elif reversible:
            undo = secondary_button("Undo", "undo")
            undo.clicked.connect(self._undo)
            row.addWidget(undo, alignment=Qt.AlignVCenter)
        else:
            row.addWidget(Badge("Not reversible", "neutral"), alignment=Qt.AlignVCenter)
        self.body().addLayout(row)

        if self.cs.operations:
            ops = QLabel("\n".join(f"• {op.description}" + (" (undone)" if op.restored else "")
                                    for op in self.cs.operations[:6]))
            ops.setProperty("role", "faint")
            ops.setWordWrap(True)
            if len(self.cs.operations) > 6:
                ops.setText(ops.text() + f"\n… and {len(self.cs.operations) - 6} more")
            self.body().addWidget(ops)

    def _undo(self):
        if not ConfirmDialog.ask(self, "Undo this change?",
                                 f"Restore everything from “{self.cs.title}”?",
                                 confirm_text="Undo", danger=False):
            return

        def work(handle):
            return self.page.services.store.restore(self.cs.id, progress=lambda f, t: handle.progress(f, t))

        run_task(work, on_result=self._done, on_error=lambda e: toast(self, f"Undo failed: {e}", "danger"))

    def _done(self, outcome):
        restored, failed = outcome
        if failed:
            toast(self, f"Restored {restored} item(s), {failed} could not be restored", "warning")
        else:
            toast(self, f"Restored {restored} item(s)", "success")
        self.page.reload()


class HistoryPage(Page):
    page_id = "history"
    title = "History"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        header = PageHeader("History", "Every change OpenCare made, newest first. Undo restores backed-up items.")
        clear = ghost_button("Clear old entries")
        clear.clicked.connect(self._prune)
        header.add_action(clear)
        lay.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 6, 0)
        self._list.setSpacing(10)
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, 1)

    def on_show(self):
        self.reload()

    def reload(self):
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        change_sets = self.services.store.list()
        if not change_sets:
            self._list.addWidget(EmptyState("history", "No changes yet", "When OpenCare cleans or fixes something, it appears here.", "accent"))
            return
        for cs in change_sets:
            self._list.addWidget(ChangeCard(self, cs))
        self._list.addStretch(1)

    def _prune(self):
        days = self.services.settings["history.keep_days"] or 60
        if not ConfirmDialog.ask(self, "Clear old history",
                                 f"Remove change records older than {days} days? Their backups are deleted too, so those changes can no longer be undone.",
                                 confirm_text="Clear old", danger=True):
            return
        removed = self.services.store.prune(days)
        toast(self, f"Removed {removed} old record(s)", "info")
        self.reload()
