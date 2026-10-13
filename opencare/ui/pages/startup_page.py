"""Startup page: list every login-launched program and enable/disable it."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from opencare.core.tasks import run_task
from opencare.engines import startup
from opencare.ui import icons, theme
from opencare.ui.widgets import (
    Badge,
    Card,
    Divider,
    EmptyState,
    Page,
    PageHeader,
    ToggleSwitch,
    secondary_button,
)
from opencare.ui.widgets.feedback import toast


class StartupRow(QWidget):
    def __init__(self, page, item: startup.StartupItem):
        super().__init__()
        self.page = page
        self.item = item
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("startup", theme.hex_color("text_muted"), 18))
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        t = QLabel(item.name)
        t.setProperty("role", "h3")
        name_row.addWidget(t)
        scope = Badge("All users" if item.scope == "machine" else "You", "neutral")
        name_row.addWidget(scope)
        missing = item.exe and ("\\" in item.exe or "/" in item.exe) and not _exists(item.exe)
        if missing:
            name_row.addWidget(Badge("File missing", "danger"))
        name_row.addStretch(1)
        col.addLayout(name_row)
        path = QLabel(item.command)
        path.setProperty("role", "faint")
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(path)
        lay.addLayout(col, 1)
        self.toggle = ToggleSwitch()
        self.toggle.setChecked(item.enabled)
        self.toggle.toggled.connect(self._toggled)
        lay.addWidget(self.toggle, alignment=Qt.AlignVCenter)

    def _toggled(self, on: bool):
        self.page.on_toggle(self.item, on, self.toggle)


def _exists(path):
    import os
    from pathlib import Path

    try:
        return Path(os.path.expandvars(path)).exists()
    except OSError:
        return False


class StartupPage(Page):
    page_id = "startup"
    title = "Startup"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        header = PageHeader("Startup programs", "Programs that launch when you sign in. Disabling keeps the entry so you can re-enable it.")
        refresh = secondary_button("Refresh", "refresh")
        refresh.clicked.connect(self.reload)
        header.add_action(refresh)
        lay.addWidget(header)

        self._count = QLabel("")
        self._count.setProperty("role", "muted")
        lay.addWidget(self._count)

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

        def work(handle):
            return startup.list_items(self.services.env)

        run_task(work, on_result=self._populate, on_error=lambda e: toast(self, f"Could not read startup items: {e}", "danger"))

    def _populate(self, items):
        if not items:
            self._list.addWidget(EmptyState("startup", "No startup programs", "Nothing runs automatically at sign-in.", "success"))
            self._count.setText("")
            return
        enabled = sum(1 for i in items if i.enabled)
        self._count.setText(f"{len(items)} programs · {enabled} enabled")
        card = Card()
        for i, item in enumerate(sorted(items, key=lambda x: (not x.enabled, x.name.lower()))):
            if i:
                card.body().addWidget(Divider())
            card.body().addWidget(StartupRow(self, item))
        self._list.addWidget(card)
        self._list.addStretch(1)

    def on_toggle(self, item, on, toggle):
        cs = self.services.store.new_change_set(f"Startup: {'enable' if on else 'disable'} {item.name}")
        if startup.set_enabled(self.services.env, item, on, cs):
            cs.save()
            item.enabled = on
            toast(self, f"{item.name} {'enabled' if on else 'disabled'}", "success")
        else:
            toggle.setChecked(item.enabled)
            toast(self, f"Could not change {item.name}. It may need administrator rights.", "warning")
