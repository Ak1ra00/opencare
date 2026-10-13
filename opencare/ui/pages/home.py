"""Home page: health score ring, one-click checkup, and a summary of findings."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from opencare.core.fmt import human_bytes, relative_time
from opencare.core.tasks import run_task
from opencare.engines.checkup import CheckupResult, score_band
from opencare.ui import icons, theme
from opencare.ui.widgets import (
    Card,
    EmptyState,
    Page,
    PageHeader,
    ProgressPanel,
    ScoreRing,
    StatTile,
    primary_button,
    secondary_button,
)
from opencare.ui.widgets.feedback import toast

SCANNER_META = [
    ("junk", "Junk files", "broom"),
    ("privacy", "Privacy traces", "eye"),
    ("registry", "Registry issues", "database"),
    ("shortcuts", "Broken shortcuts", "link"),
    ("startup", "Startup items", "startup"),
    ("security", "Security", "shield_check"),
]


class HomePage(Page):
    page_id = "home"
    title = "Home"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._task = None
        self._result: CheckupResult | None = None
        self._build()
        self._show_idle()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        header = PageHeader("System health", "Run a checkup to see what can be cleaned and improved.")
        outer.addWidget(header)

        top = QHBoxLayout()
        top.setSpacing(18)

        # left: score + action card
        self._hero = Card(padding=24)
        hero_lay = self._hero.body()
        hero_lay.setAlignment(Qt.AlignCenter)
        self._ring = ScoreRing(diameter=210)
        hero_lay.addWidget(self._ring, alignment=Qt.AlignCenter)
        self._band = QLabel("")
        self._band.setProperty("role", "h2")
        self._band.setAlignment(Qt.AlignCenter)
        hero_lay.addWidget(self._band)
        self._subline = QLabel("")
        self._subline.setProperty("role", "subtitle")
        self._subline.setAlignment(Qt.AlignCenter)
        self._subline.setWordWrap(True)
        hero_lay.addWidget(self._subline)

        self._progress = ProgressPanel()
        self._progress.cancelled.connect(self._cancel)
        self._progress.setVisible(False)
        hero_lay.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        self._scan_btn = primary_button("Run checkup", "search", large=True)
        self._scan_btn.clicked.connect(self._start_checkup)
        btn_row.addWidget(self._scan_btn)
        self._fix_btn = secondary_button("Review & fix", "check", large=True)
        self._fix_btn.clicked.connect(lambda: self.services_window().go_to("cleanup") if self.services_window() else None)
        self._fix_btn.setVisible(False)
        btn_row.addWidget(self._fix_btn)
        hero_lay.addLayout(btn_row)
        top.addWidget(self._hero, 1)

        # right: findings grid
        right = QVBoxLayout()
        right.setSpacing(12)
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        self._tile_issues = StatTile("Issues found", "—", "alert", "warning")
        self._tile_space = StatTile("Reclaimable", "—", "broom", "accent")
        stat_row.addWidget(self._tile_issues)
        stat_row.addWidget(self._tile_space)
        right.addLayout(stat_row)

        self._findings = Card()
        self._findings.body().setSpacing(2)
        self._findings_grid = QGridLayout()
        self._findings_grid.setVerticalSpacing(6)
        self._findings_grid.setHorizontalSpacing(10)
        self._findings.body().addLayout(self._findings_grid)
        self._findings_rows: dict[str, tuple[QLabel, QLabel]] = {}
        for i, (sid, label, icon_name) in enumerate(SCANNER_META):
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon_name, theme.hex_color("text_muted"), 16))
            name = QLabel(label)
            value = QLabel("—")
            value.setProperty("role", "muted")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._findings_grid.addWidget(ic, i, 0)
            self._findings_grid.addWidget(name, i, 1)
            self._findings_grid.addWidget(value, i, 2)
            self._findings_grid.setColumnStretch(1, 1)
            self._findings_rows[sid] = (name, value)
        right.addWidget(self._findings, 1)
        top.addLayout(right, 1)

        outer.addLayout(top, 1)

    def services_window(self):
        w = self.window()
        return w if hasattr(w, "go_to") else None

    def on_show(self):
        if self._result is None:
            self._show_idle()

    # ---- idle / last summary ----
    def _show_idle(self):
        last = self.services.settings["checkup.last_summary"]
        last_run = self.services.settings["checkup.last_run"]
        if last:
            score = last.get("score", 100)
            band, token = score_band(score)
            self._ring.set_score(score, str(score), band, token)
            self._band.setText(band)
            self._subline.setText(f"Last checkup {relative_time(last_run)} · {last.get('issues', 0)} issues · {human_bytes(last.get('reclaimable', 0))} reclaimable")
            self._tile_issues.set_value(str(last.get("issues", 0)))
            self._tile_space.set_value(human_bytes(last.get("reclaimable", 0)))
            for sid, n in (last.get("per_scanner") or {}).items():
                if sid in self._findings_rows:
                    self._findings_rows[sid][1].setText("Clear" if n == 0 else f"{n} found")
        else:
            self._ring.set_score(0, "?", "Not scanned yet")
            self._band.setText("Ready for a checkup")
            self._subline.setText("Run a checkup to measure your PC's health.")

    # ---- run ----
    def _start_checkup(self):
        self._scan_btn.setVisible(False)
        self._fix_btn.setVisible(False)
        self._band.setText("Scanning…")
        self._subline.setText("")
        self._progress.setVisible(True)
        self._progress.set_progress(0, "Starting")
        self._ring.set_score(0, "…", "Scanning")

        def work(handle):
            return self.services.checkup.run(
                progress=lambda f, t: handle.progress(f, t),
                cancelled=lambda: handle.cancelled,
            )

        self._task = run_task(
            work,
            on_progress=lambda f, t: self._progress.set_progress(f, t),
            on_result=self._on_done,
            on_error=self._on_error,
        )

    def _cancel(self):
        if self._task:
            self._task.cancel()
        self._progress.setVisible(False)
        self._scan_btn.setVisible(True)
        self._show_idle()

    def _on_error(self, exc):
        self._progress.setVisible(False)
        self._scan_btn.setVisible(True)
        toast(self, f"Checkup failed: {exc}", "danger")

    def _on_done(self, result: CheckupResult):
        self._result = result
        self._progress.setVisible(False)
        self._scan_btn.setVisible(True)
        self._scan_btn.setText("Scan again")
        self.services.checkup.record_checkup(result)
        band, token = score_band(result.score)
        self._ring.set_score(result.score, str(result.score), band, token)
        self._band.setText(band)
        self._tile_issues.set_value(str(result.total_issues))
        self._tile_space.set_value(human_bytes(result.total_reclaimable))
        for sid, (name, value) in self._findings_rows.items():
            r = result.results.get(sid)
            if r is None:
                value.setText("—")
                continue
            n = len(r.issues)
            if n == 0:
                value.setText("✓ Clear")
                value.setStyleSheet(f"color: {theme.hex_color('success')};")
            else:
                size = r.total_size
                value.setText(f"{n} found" + (f" · {human_bytes(size)}" if size else ""))
                value.setStyleSheet(f"color: {theme.hex_color('warning')};")
        if result.total_issues:
            self._subline.setText("Review the findings and choose what to fix.")
            self._fix_btn.setVisible(True)
            # stash for the cleanup page
            self.services.settings  # noqa
            _LAST["result"] = result
        else:
            self._subline.setText("Everything looks clean. Nice work.")


# simple in-process handoff of the latest checkup to the cleanup page
_LAST: dict = {}


def last_checkup() -> CheckupResult | None:
    return _LAST.get("result")
