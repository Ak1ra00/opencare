"""Cleanup page: tabbed scan/review/fix across the file- and registry-based scanners."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from opencare.core.fmt import human_bytes
from opencare.core.tasks import run_task
from opencare.engines.base import ScanContext, ScanResult, Scanner
from opencare.engines.base import all_scanners
from opencare.ui import theme
from opencare.ui.widgets import (
    EmptyState,
    IssueTree,
    Page,
    PageHeader,
    ProgressPanel,
    danger_button,
    ghost_button,
    primary_button,
    secondary_button,
)
from opencare.ui.widgets.feedback import ConfirmDialog, toast

CLEANUP_SCANNERS = ["junk", "privacy", "registry", "shortcuts"]


class ScannerPanel(QWidget):
    """One scanner's scan/review/fix panel."""

    def __init__(self, page, scanner: Scanner):
        super().__init__()
        self.page = page
        self.scanner = scanner
        self.services = page.services
        self._task = None
        self._result: ScanResult | None = None
        self._build()
        self._show_prescan()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(12)

        desc = QLabel(self.scanner.description)
        desc.setProperty("role", "subtitle")
        lay.addWidget(desc)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)

        # prescan
        self._prescan = QWidget()
        pv = QVBoxLayout(self._prescan)
        pv.setAlignment(Qt.AlignCenter)
        self._empty = EmptyState(self.scanner.icon, f"Scan for {self.scanner.title.lower()}",
                                 "Nothing is changed until you choose to fix.", "accent")
        pv.addWidget(self._empty)
        scan_btn = primary_button(f"Scan {self.scanner.title.lower()}", "search")
        scan_btn.clicked.connect(self.start_scan)
        pv.addWidget(scan_btn, alignment=Qt.AlignCenter)
        self._stack.addWidget(self._prescan)

        # scanning
        self._scanning = QWidget()
        sv = QVBoxLayout(self._scanning)
        sv.setAlignment(Qt.AlignCenter)
        self._progress = ProgressPanel()
        self._progress.setMaximumWidth(480)
        self._progress.cancelled.connect(self._cancel_scan)
        sv.addWidget(self._progress)
        self._stack.addWidget(self._scanning)

        # results
        self._results = QWidget()
        rv = QVBoxLayout(self._results)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(10)
        self._tree = IssueTree()
        self._tree.selection_changed.connect(self._on_selection)
        self._tree.ignore_requested.connect(self._ignore)
        self._tree.exclude_requested.connect(self._exclude)
        rv.addWidget(self._tree, 1)

        bar = QHBoxLayout()
        self._select_all = ghost_button("Select all")
        self._select_all.clicked.connect(lambda: self._tree.set_all_checked(True))
        self._select_none = ghost_button("Select none")
        self._select_none.clicked.connect(lambda: self._tree.set_all_checked(False))
        bar.addWidget(self._select_all)
        bar.addWidget(self._select_none)
        bar.addStretch(1)
        self._summary = QLabel("")
        self._summary.setProperty("role", "muted")
        bar.addWidget(self._summary)
        self._rescan_btn = secondary_button("Rescan", "refresh")
        self._rescan_btn.clicked.connect(self.start_scan)
        bar.addWidget(self._rescan_btn)
        self._fix_btn = primary_button("Clean selected", "check")
        self._fix_btn.clicked.connect(self._do_fix)
        bar.addWidget(self._fix_btn)
        rv.addLayout(bar)
        self._stack.addWidget(self._results)

        # clean (empty) state
        self._clean = QWidget()
        cv = QVBoxLayout(self._clean)
        cv.setAlignment(Qt.AlignCenter)
        self._clean_state = EmptyState("check_circle", f"No {self.scanner.title.lower()} issues found", "This area is clean.", "success")
        cv.addWidget(self._clean_state)
        again = secondary_button("Scan again", "refresh")
        again.clicked.connect(self.start_scan)
        cv.addWidget(again, alignment=Qt.AlignCenter)
        self._stack.addWidget(self._clean)

    def _show_prescan(self):
        self._stack.setCurrentWidget(self._prescan)

    def load_result(self, result: ScanResult):
        self._result = result
        if result.issues:
            self._tree.load(self.scanner, result)
            self._stack.setCurrentWidget(self._results)
        else:
            self._stack.setCurrentWidget(self._clean)

    def start_scan(self):
        self._stack.setCurrentWidget(self._scanning)
        self._progress.set_label(f"Scanning {self.scanner.title.lower()}…")
        self._progress.set_progress(0, "")

        def work(handle):
            ctx = ScanContext(
                env=self.services.env, settings=self.services.settings,
                categories=self.scanner.enabled_categories(self.services.settings),
                progress=lambda f, t: handle.progress(f, t),
                cancelled=lambda: handle.cancelled,
            )
            return self.scanner.scan(ctx)

        self._task = run_task(
            work,
            on_progress=lambda f, t: self._progress.set_progress(f, t),
            on_result=self.load_result,
            on_error=lambda e: (toast(self, f"Scan failed: {e}", "danger"), self._show_prescan()),
        )

    def _cancel_scan(self):
        if self._task:
            self._task.cancel()
        self._show_prescan()

    def _on_selection(self, size: int, count: int):
        parts = []
        if count:
            parts.append(f"{count} selected")
        if size:
            parts.append(human_bytes(size))
        self._summary.setText("  ·  ".join(parts))
        self._fix_btn.setEnabled(count > 0)
        self._fix_btn.setText("Clean selected" + (f" ({human_bytes(size)})" if size else ""))

    def _ignore(self, issue):
        ignored = list(self.services.settings["ignored_issues"] or [])
        ignored.append(issue.id)
        self.services.settings["ignored_issues"] = ignored
        toast(self, "Item will be ignored in future scans", "info")
        self.start_scan()

    def _exclude(self, path):
        ex = list(self.services.settings["exclusions"] or [])
        ex.append(path)
        self.services.settings["exclusions"] = ex
        toast(self, "Location excluded", "info")
        self.start_scan()

    def _do_fix(self):
        issues = self._tree.selected_issues()
        if not issues:
            return
        risky = [i for i in issues if i.risk.value != "low"]
        size = sum(i.size for i in issues)
        msg = f"Clean {len(issues)} selected item{'s' if len(issues) != 1 else ''}"
        if size:
            msg += f", reclaiming about {human_bytes(size)}"
        msg += "?"
        details = ""
        if risky:
            details = f"{len(risky)} item(s) are marked Caution or Risky. A backup is saved first so you can undo from History."
        if not ConfirmDialog.ask(self, "Confirm cleanup", msg,
                                 confirm_text="Clean now", danger=bool(risky), details=details):
            return

        self._stack.setCurrentWidget(self._scanning)
        self._progress.set_label("Cleaning…")
        self._progress.allow_cancel(False)

        def work(handle):
            return self.services.checkup.fix(
                issues, title=f"{self.scanner.title} cleanup",
                progress=lambda f, t: handle.progress(f, t),
                cancelled=lambda: handle.cancelled,
            )

        self._task = run_task(work, on_progress=lambda f, t: self._progress.set_progress(f, t),
                              on_result=self._after_fix, on_error=lambda e: toast(self, f"Cleanup failed: {e}", "danger"))

    def _after_fix(self, outcome):
        self._progress.allow_cancel(True)
        cs, reports = outcome
        report = reports.get(self.scanner.id)
        if report:
            freed = human_bytes(report.bytes_freed) if report.bytes_freed else ""
            msg = f"Cleaned {report.fixed} item{'s' if report.fixed != 1 else ''}"
            if freed:
                msg += f" · {freed} freed"
            toast(self, msg, "success")
        self.page.refresh_history_badge()
        self.start_scan()


class CleanupPage(Page):
    page_id = "cleanup"
    title = "Cleanup"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._panels: dict[str, ScannerPanel] = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        header = PageHeader("Cleanup", "Scan each area, review exactly what will be removed, then clean.")
        self._scan_all = primary_button("Scan all areas", "search")
        self._scan_all.clicked.connect(self._scan_all_areas)
        header.add_action(self._scan_all)
        lay.addWidget(header)

        self._tabbar = QTabBar()
        self._tabbar.setExpanding(False)
        self._tabbar.setDrawBase(False)
        self._stack = QStackedWidget()
        scanners = {s.id: s for s in all_scanners()}
        for sid in CLEANUP_SCANNERS:
            scanner = scanners.get(sid)
            if not scanner:
                continue
            panel = ScannerPanel(self, scanner)
            self._panels[sid] = panel
            self._tabbar.addTab(scanner.title)
            self._stack.addWidget(panel)
        self._tabbar.currentChanged.connect(self._stack.setCurrentIndex)
        lay.addWidget(self._tabbar)
        lay.addWidget(self._stack, 1)

    def _scan_all_areas(self):
        for panel in self._panels.values():
            panel.start_scan()

    def on_show(self):
        # if Home just produced a checkup, pre-load matching results
        from opencare.ui.pages.home import last_checkup

        result = last_checkup()
        if result:
            for sid, panel in self._panels.items():
                r = result.results.get(sid)
                if r is not None and panel._result is None:
                    panel.load_result(r)

    def refresh_history_badge(self):
        pass
