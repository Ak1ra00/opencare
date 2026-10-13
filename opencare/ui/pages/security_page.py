"""Security page: read-only posture overview with advisories and settings shortcuts."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from opencare.core.tasks import run_task
from opencare.engines.base import ScanContext
from opencare.engines.base import get_scanner
from opencare.ui import icons, theme
from opencare.ui.widgets import (
    Badge,
    Card,
    Divider,
    EmptyState,
    Page,
    PageHeader,
    secondary_button,
)
from opencare.ui.widgets.feedback import toast


class SecurityPage(Page):
    page_id = "security"
    title = "Security"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        header = PageHeader("Security overview", "A read-only check of Windows' built-in protections. OpenCare never changes these for you.")
        refresh = secondary_button("Re-check", "refresh")
        refresh.clicked.connect(self.reload)
        header.add_action(refresh)
        lay.addWidget(header)

        self._host = QVBoxLayout()
        self._host.setSpacing(12)
        lay.addLayout(self._host)
        lay.addStretch(1)
        self._card = None

    def on_show(self):
        self.reload()

    def reload(self):
        while self._host.count():
            item = self._host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        scanner = get_scanner("security")

        def work(handle):
            ctx = ScanContext(env=self.services.env, settings=self.services.settings,
                              categories=scanner.enabled_categories(self.services.settings),
                              cancelled=lambda: handle.cancelled)
            return scanner.scan(ctx)

        run_task(work, on_result=self._show, on_error=lambda e: toast(self, f"Security check failed: {e}", "danger"))

    def _show(self, result):
        advisories = result.issues
        checks = [
            ("antivirus", "Antivirus protection", "shield_check"),
            ("firewall", "Firewall", "shield"),
            ("updates", "Windows Update", "refresh"),
            ("system_guard", "System safeguards", "lock"),
        ]
        by_cat = {}
        for a in advisories:
            by_cat.setdefault(a.category, []).append(a)

        card = Card()
        for i, (cat, label, icon_name) in enumerate(checks):
            if i:
                card.body().addWidget(Divider())
            card.body().addWidget(self._row(cat, label, icon_name, by_cat.get(cat, [])))
        self._host.addWidget(card)

    def _row(self, cat, label, icon_name, issues):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(12)
        ic = QLabel()
        ok = not issues
        token = "success" if ok else "warning"
        ic.setPixmap(icons.pixmap(icon_name, theme.hex_color(token), 22))
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(label)
        t.setProperty("role", "h3")
        col.addWidget(t)
        detail = QLabel("Protected" if ok else issues[0].detail)
        detail.setProperty("role", "subtitle")
        detail.setWordWrap(True)
        col.addWidget(detail)
        lay.addLayout(col, 1)
        if ok:
            lay.addWidget(Badge("OK", "success"), alignment=Qt.AlignVCenter)
        else:
            uri = issues[0].payload.get("settings_uri")
            if uri:
                btn = secondary_button("Open settings")
                btn.clicked.connect(lambda _=False, u=uri: self._open(u))
                lay.addWidget(btn, alignment=Qt.AlignVCenter)
            else:
                lay.addWidget(Badge("Review", "warning"), alignment=Qt.AlignVCenter)
        return w

    def _open(self, uri):
        import os

        try:
            os.startfile(uri)  # noqa: S606 - user-initiated settings launch
        except OSError:
            toast(self, "Could not open the settings page.", "danger")
