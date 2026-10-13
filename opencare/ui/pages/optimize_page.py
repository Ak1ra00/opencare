"""Optimize page: toggleable Windows tweaks grouped by category, plus a memory trim."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from opencare.core.fmt import human_bytes
from opencare.core.tasks import run_task
from opencare.engines import optimize
from opencare.engines.base import Risk
from opencare.ui import icons, theme
from opencare.ui.widgets import (
    Badge,
    Card,
    Divider,
    Page,
    PageHeader,
    StatTile,
    ToggleSwitch,
    primary_button,
    secondary_button,
)
from opencare.ui.widgets.feedback import ConfirmDialog, toast

CATEGORY_TITLES = {
    "performance": "Performance",
    "responsiveness": "Responsiveness",
    "visual": "Visual effects",
    "privacy": "Privacy & noise",
}


class TweakRow(QWidget):
    def __init__(self, page, tweak: optimize.Tweak):
        super().__init__()
        self.page = page
        self.tweak = tweak
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        t = QLabel(tweak.title)
        t.setProperty("role", "h3")
        title_row.addWidget(t)
        if tweak.requires_admin:
            title_row.addWidget(Badge("Admin", "warning"))
        if tweak.risk == Risk.MEDIUM:
            title_row.addWidget(Badge("Caution", "warning"))
        title_row.addStretch(1)
        text.addLayout(title_row)
        d = QLabel(tweak.description)
        d.setProperty("role", "subtitle")
        d.setWordWrap(True)
        text.addWidget(d)
        lay.addLayout(text, 1)
        self.toggle = ToggleSwitch()
        state = optimize.current_state(page.services.env, tweak)
        self.toggle.setChecked(bool(state))
        self.toggle.setEnabled(tweak.requires_admin is False or page.services.env.is_admin)
        self.toggle.toggled.connect(self._changed)
        lay.addWidget(self.toggle, alignment=Qt.AlignVCenter)

    def _changed(self, on: bool):
        self.page.on_toggle(self.tweak, on, self.toggle)


class OptimizePage(Page):
    page_id = "optimize"
    title = "Optimize"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        header = PageHeader("Optimize", "Reversible tweaks and a quick memory cleanup. Each change can be undone from History.")
        lay.addWidget(header)

        # memory trim card
        mem = Card()
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("memory", theme.hex_color("accent"), 28))
        row.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        tt = QLabel("Free up memory")
        tt.setProperty("role", "h3")
        col.addWidget(tt)
        self._mem_desc = QLabel("Trim idle memory held by running programs.")
        self._mem_desc.setProperty("role", "subtitle")
        col.addWidget(self._mem_desc)
        row.addLayout(col, 1)
        self._trim_btn = primary_button("Free memory", "rocket")
        self._trim_btn.clicked.connect(self._trim_memory)
        row.addWidget(self._trim_btn, alignment=Qt.AlignVCenter)
        mem.body().addLayout(row)
        lay.addWidget(mem)

        # tweaks grouped by category in a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 6, 0)
        iv.setSpacing(14)
        by_cat: dict[str, list[optimize.Tweak]] = {}
        for tw in optimize.TWEAKS:
            by_cat.setdefault(tw.category, []).append(tw)
        for cat, title in CATEGORY_TITLES.items():
            tweaks = by_cat.get(cat)
            if not tweaks:
                continue
            card = Card()
            head = QLabel(title)
            head.setProperty("role", "h2")
            card.body().addWidget(head)
            for i, tw in enumerate(tweaks):
                if i:
                    card.body().addWidget(Divider())
                card.body().addWidget(TweakRow(self, tw))
            iv.addWidget(card)
        iv.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

    def on_toggle(self, tweak, on, toggle):
        if not on:
            # turning a tweak off = reverting it; we apply by writing back default via undo-less path
            # simplest correct behaviour: re-read and inform the user to use History for full revert
            toast(self, "To fully revert a tweak, use Undo on the History page.", "info")
            return
        if tweak.requires_admin and not self.services.env.is_admin:
            toast(self, "This tweak needs administrator rights.", "warning")
            toggle.setChecked(False)
            return
        cs = self.services.store.new_change_set(f"Tweak: {tweak.title}")
        if optimize.apply_tweak(self.services.env, tweak, cs):
            cs.save()
            self.services.settings["stats.items_fixed"] = (self.services.settings["stats.items_fixed"] or 0) + 1
            toast(self, f"Applied: {tweak.title}" + ("  (restart to take effect)" if tweak.requires_restart else ""), "success")
        else:
            toggle.setChecked(False)
            toast(self, "Could not apply this tweak.", "danger")

    def _trim_memory(self):
        self._trim_btn.setEnabled(False)
        self._trim_btn.setText("Freeing…")

        def work(handle):
            return optimize.trim_working_sets()

        run_task(work, on_result=self._trimmed, on_error=self._trim_error)

    def _trimmed(self, outcome):
        trimmed, freed = outcome
        self._trim_btn.setEnabled(True)
        self._trim_btn.setText("Free memory")
        if trimmed:
            toast(self, f"Trimmed {trimmed} processes · about {human_bytes(freed)} released", "success")
        else:
            toast(self, "No memory could be trimmed right now.", "info")

    def _trim_error(self, exc):
        self._trim_btn.setEnabled(True)
        self._trim_btn.setText("Free memory")
        toast(self, f"Memory cleanup failed: {exc}", "danger")
