"""IssueTree — grouped, checkable results view used by every cleanup page.

Rows: category headers (tri-state checkbox, count + size) with issue children.
Emits ``selection_changed`` with the selected byte total. Context menu offers open
location / open registry / ignore. Call ``load(scanner, result)`` then
``selected_issues()`` to drive a fix.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QBrush
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeWidget, QTreeWidgetItem

from opencare.core.fmt import human_bytes
from opencare.engines.base import Issue, Risk, ScanResult, Scanner
from opencare.ui import icons, theme

ROLE_ISSUE = Qt.UserRole + 1
ROLE_KIND = Qt.UserRole + 2

RISK_BADGE = {Risk.LOW: ("success", "Safe"), Risk.MEDIUM: ("warning", "Caution"), Risk.HIGH: ("danger", "Risky")}


class IssueTree(QTreeWidget):
    # selected_bytes can exceed 2 GB, so it must be 64-bit, not a C++ int
    selection_changed = Signal("qlonglong", int)  # selected_bytes, selected_count
    ignore_requested = Signal(object)     # Issue
    exclude_requested = Signal(str)       # path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHeaderLabels(["Item", "Risk", "Size"])
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setExpandsOnDoubleClick(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemChanged.connect(self._on_item_changed)
        self._scanner: Scanner | None = None
        self._updating = False
        h = self.header()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.setColumnWidth(1, 90)

    def load(self, scanner: Scanner, result: ScanResult):
        self._updating = True
        self.clear()
        self._scanner = scanner
        groups = result.by_category()
        for cat in scanner.categories:
            issues = groups.get(cat.id)
            if not issues:
                continue
            total = sum(i.size for i in issues)
            parent = QTreeWidgetItem(self)
            parent.setData(0, ROLE_KIND, "category")
            parent.setData(0, ROLE_ISSUE, cat.id)
            parent.setFlags(parent.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            parent.setText(0, f"{cat.title}  ·  {len(issues)} item{'s' if len(issues) != 1 else ''}")
            parent.setIcon(0, icons.icon(scanner.icon, theme.hex_color("text_muted"), 16))
            parent.setText(2, human_bytes(total) if total else "")
            parent.setToolTip(0, cat.description)
            token, label = RISK_BADGE[cat.risk]
            parent.setText(1, label)
            parent.setForeground(1, QBrush(theme.color(token)))
            for issue in issues:
                child = QTreeWidgetItem(parent)
                child.setData(0, ROLE_KIND, "issue")
                child.setData(0, ROLE_ISSUE, issue)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked if issue.selected else Qt.Unchecked)
                child.setText(0, issue.title)
                child.setToolTip(0, f"{issue.detail}\n{issue.path or ''}".strip())
                child.setText(2, human_bytes(issue.size) if issue.size else "")
                if issue.risk != cat.risk:
                    tok, lab = RISK_BADGE[issue.risk]
                    child.setText(1, lab)
                    child.setForeground(1, QBrush(theme.color(tok)))
            parent.setExpanded(len(groups) <= 2 or len(issues) <= 8)
        self._updating = False
        self._emit()

    def _on_item_changed(self, item, col):
        if self._updating or col != 0:
            return
        if item.data(0, ROLE_KIND) == "issue":
            issue: Issue = item.data(0, ROLE_ISSUE)
            issue.selected = item.checkState(0) == Qt.Checked
        self._emit()

    def _emit(self):
        total = 0
        count = 0
        for issue in self.selected_issues():
            total += issue.size
            count += 1
        self.selection_changed.emit(total, count)

    def selected_issues(self) -> list[Issue]:
        out = []
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    out.append(child.data(0, ROLE_ISSUE))
        return out

    def all_issues(self) -> list[Issue]:
        out = []
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                out.append(parent.child(j).data(0, ROLE_ISSUE))
        return out

    def set_all_checked(self, checked: bool):
        self._updating = True
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setCheckState(0, state)
            for j in range(self.topLevelItem(i).childCount()):
                child = self.topLevelItem(i).child(j)
                child.setCheckState(0, state)
                child.data(0, ROLE_ISSUE).selected = checked
        self._updating = False
        self._emit()

    def _menu(self, pos):
        item = self.itemAt(pos)
        if not item or item.data(0, ROLE_KIND) != "issue":
            return
        issue: Issue = item.data(0, ROLE_ISSUE)
        menu = QMenu(self)
        if issue.path:
            if issue.path.upper().startswith(("HKLM", "HKCU", "HKEY", "HKCR", "HKU")):
                act = QAction(icons.icon("database", theme.hex_color("text_muted"), 16), "Open in Registry Editor", self)
                act.triggered.connect(lambda: self._open_registry(issue.path))
            else:
                act = QAction(icons.icon("folder", theme.hex_color("text_muted"), 16), "Open file location", self)
                act.triggered.connect(lambda: self._open_location(issue.path))
            menu.addAction(act)
            exclude = QAction("Always exclude this location", self)
            exclude.triggered.connect(lambda: self.exclude_requested.emit(issue.path))
            menu.addAction(exclude)
        ignore = QAction(icons.icon("close", theme.hex_color("text_muted"), 16), "Ignore this item in future scans", self)
        ignore.triggered.connect(lambda: self.ignore_requested.emit(issue))
        menu.addAction(ignore)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _open_location(self, path):
        from opencare.core import shell

        shell.open_in_explorer(path)

    def _open_registry(self, path):
        from opencare.core import shell

        shell.open_registry_at(path)
