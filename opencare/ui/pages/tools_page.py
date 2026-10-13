"""Tools page: a grid of utilities (large files, duplicates, system info)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from opencare.core.fmt import human_bytes, relative_time
from opencare.core.shell import open_in_explorer
from opencare.core.tasks import run_task
from opencare.ui import icons, theme
from opencare.ui.widgets import (
    Card,
    EmptyState,
    IssueTree,
    Page,
    PageHeader,
    ProgressPanel,
    ghost_button,
    primary_button,
    secondary_button,
)
from opencare.ui.widgets.feedback import toast

TOOLS = [
    ("large_files", "Large files", "disk", "Find the biggest files eating your disk space."),
    ("duplicates", "Duplicate files", "duplicate", "Find identical copies you can remove."),
    ("sysinfo", "System information", "cpu", "A quick overview of your PC's hardware."),
]


class ToolsPage(Page):
    page_id = "tools"
    title = "Tools"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self._header = PageHeader("Toolbox", "Extra utilities for a deeper clean-up.")
        back = ghost_button("< All tools")
        back.clicked.connect(lambda: self._go(0))
        self._back = back
        self._header.add_action(back)
        lay.addWidget(self._header)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)

        # grid of tool cards
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setSpacing(14)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (tid, name, icon_name, desc) in enumerate(TOOLS):
            card = self._tool_card(tid, name, icon_name, desc)
            grid.addWidget(card, i // 2, i % 2)
        grid.setRowStretch((len(TOOLS) + 1) // 2, 1)
        self._stack.addWidget(grid_host)

        self._large = LargeFilesTool(self)
        self._dupes = DuplicatesTool(self)
        self._sysinfo = SysInfoTool(self)
        self._stack.addWidget(self._large)
        self._stack.addWidget(self._dupes)
        self._stack.addWidget(self._sysinfo)
        self._index = {"large_files": 1, "duplicates": 2, "sysinfo": 3}
        self._go(0)

    def _tool_card(self, tid, name, icon_name, desc):
        card = Card(hover=True)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, theme.hex_color("accent"), 26))
        row.addWidget(ic, alignment=Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(name)
        t.setProperty("role", "h3")
        col.addWidget(t)
        d = QLabel(desc)
        d.setProperty("role", "subtitle")
        d.setWordWrap(True)
        col.addWidget(d)
        row.addLayout(col, 1)
        card.body().addLayout(row)
        open_btn = secondary_button("Open")
        open_btn.clicked.connect(lambda: self._go(self._index[tid]))
        card.body().addWidget(open_btn, alignment=Qt.AlignLeft)
        return card

    def _go(self, index):
        self._stack.setCurrentIndex(index)
        self._back.setVisible(index != 0)
        self._header.set_subtitle("Extra utilities for a deeper clean-up." if index == 0 else TOOLS[index - 1][3])


class _FolderToolBase(QWidget):
    def __init__(self, page, title=""):
        super().__init__()
        self.page = page
        self.services = page.services
        self._task = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)
        bar = QHBoxLayout()
        self._path_label = QLabel("Choose a folder to scan")
        self._path_label.setProperty("role", "muted")
        bar.addWidget(self._path_label, 1)
        choose = secondary_button("Choose folder…", "folder")
        choose.clicked.connect(self._choose)
        bar.addWidget(choose)
        self._scan_btn = primary_button("Scan", "search")
        self._scan_btn.clicked.connect(self._start)
        self._scan_btn.setEnabled(False)
        bar.addWidget(self._scan_btn)
        lay.addLayout(bar)
        self._progress = ProgressPanel()
        self._progress.setVisible(False)
        self._progress.cancelled.connect(self._cancel)
        lay.addWidget(self._progress)
        self._body = QVBoxLayout()
        lay.addLayout(self._body, 1)
        self._root = None

    def _choose(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder to scan")
        if folder:
            self._root = folder
            self._path_label.setText(folder)
            self._scan_btn.setEnabled(True)

    def _cancel(self):
        if self._task:
            self._task.cancel()
        self._progress.setVisible(False)

    def _start(self):
        raise NotImplementedError


class LargeFilesTool(_FolderToolBase):
    def __init__(self, page):
        super().__init__(page, "Large files")
        self._tree = None

    def _start(self):
        from opencare.tools.large_files import find_large_files

        self._progress.setVisible(True)
        self._progress.set_indeterminate(True)
        self._progress.set_label("Scanning for large files…")
        self._scan_btn.setEnabled(False)

        def work(handle):
            return find_large_files(self._root, min_mb=50,
                                    cancelled=lambda: handle.cancelled,
                                    progress=lambda f, t: handle.progress(f, t))

        self._task = run_task(work, on_progress=lambda f, t: self._progress.set_progress(f, t),
                              on_result=self._show, on_error=lambda e: toast(self, f"Scan failed: {e}", "danger"))

    def _show(self, files):
        self._progress.setVisible(False)
        self._progress.set_indeterminate(False)
        self._scan_btn.setEnabled(True)
        self._clear_body()
        if not files:
            self._body.addWidget(EmptyState("disk", "No large files found", "Nothing over 50 MB in that folder.", "success"))
            return
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

        tree = QTreeWidget()
        tree.setHeaderLabels(["File", "Size", "Modified"])
        tree.setRootIsDecorated(False)
        tree.header().setStretchLastSection(False)
        tree.setColumnWidth(0, 520)
        for f in files:
            it = QTreeWidgetItem([f.path, human_bytes(f.size), relative_time(__import__("datetime").datetime.fromtimestamp(f.mtime))])
            tree.addTopLevelItem(it)
        tree.itemDoubleClicked.connect(lambda item, _col: open_in_explorer(item.text(0)))
        total = sum(f.size for f in files)
        head = QLabel(f"{len(files)} files · {human_bytes(total)} total · double-click to open location")
        head.setProperty("role", "muted")
        self._body.addWidget(head)
        self._body.addWidget(tree, 1)

    def _clear_body(self):
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class DuplicatesTool(_FolderToolBase):
    def _start(self):
        from opencare.tools.duplicates import find_duplicates

        self._progress.setVisible(True)
        self._progress.set_label("Looking for duplicate files…")
        self._scan_btn.setEnabled(False)

        def work(handle):
            return find_duplicates(self._root, cancelled=lambda: handle.cancelled,
                                   progress=lambda f, t: handle.progress(f, t))

        self._task = run_task(work, on_progress=lambda f, t: self._progress.set_progress(f, t),
                              on_result=self._show, on_error=lambda e: toast(self, f"Scan failed: {e}", "danger"))

    def _show(self, groups):
        self._progress.setVisible(False)
        self._scan_btn.setEnabled(True)
        self._clear_body()
        if not groups:
            self._body.addWidget(EmptyState("duplicate", "No duplicates found", "Every file in that folder is unique.", "success"))
            return
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

        tree = QTreeWidget()
        tree.setHeaderLabels(["Duplicate sets", "Size", "Wasted"])
        tree.setColumnWidth(0, 520)
        for g in groups:
            parent = QTreeWidgetItem([f"{len(g.paths)} copies", human_bytes(g.size), human_bytes(g.wasted)])
            for p in g.paths:
                parent.addChild(QTreeWidgetItem([p, "", ""]))
            tree.addTopLevelItem(parent)
        tree.itemDoubleClicked.connect(lambda item, _col: open_in_explorer(item.text(0)) if "\\" in item.text(0) else None)
        wasted = sum(g.wasted for g in groups)
        head = QLabel(f"{len(groups)} duplicate sets · {human_bytes(wasted)} reclaimable · review before deleting")
        head.setProperty("role", "muted")
        self._body.addWidget(head)
        self._body.addWidget(tree, 1)

    def _clear_body(self):
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class SysInfoTool(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)
        self._host = QVBoxLayout()
        lay.addLayout(self._host)
        lay.addStretch(1)
        self._loaded = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load()

    def _load(self):
        from opencare.tools.sysinfo import collect

        info = collect()
        from PySide6.QtWidgets import QGridLayout

        for section, rows in info.sections.items():
            card = Card()
            head = QLabel(section)
            head.setProperty("role", "h2")
            card.body().addWidget(head)
            grid = QGridLayout()
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(4)
            for i, (k, v) in enumerate(rows):
                kl = QLabel(k)
                kl.setProperty("role", "muted")
                vl = QLabel(v)
                vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                grid.addWidget(kl, i, 0)
                grid.addWidget(vl, i, 1)
            grid.setColumnStretch(1, 1)
            card.body().addLayout(grid)
            self._host.addWidget(card)
