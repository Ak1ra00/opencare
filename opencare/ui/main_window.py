"""Main application window: sidebar navigation + lazily-built page stack."""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from opencare import APP_NAME, __version__
from opencare.services import Services
from opencare.ui import icons, theme

log = logging.getLogger(__name__)

# (page_id, label, icon, module, class)
PAGES = [
    ("home", "Home", "home", "opencare.ui.pages.home", "HomePage"),
    ("cleanup", "Cleanup", "broom", "opencare.ui.pages.cleanup", "CleanupPage"),
    ("optimize", "Optimize", "rocket", "opencare.ui.pages.optimize_page", "OptimizePage"),
    ("startup", "Startup", "startup", "opencare.ui.pages.startup_page", "StartupPage"),
    ("security", "Security", "shield_check", "opencare.ui.pages.security_page", "SecurityPage"),
    ("tools", "Tools", "wrench", "opencare.ui.pages.tools_page", "ToolsPage"),
    ("history", "History", "history", "opencare.ui.pages.history_page", "HistoryPage"),
    ("settings", "Settings", "settings", "opencare.ui.pages.settings_page", "SettingsPage"),
]


class Sidebar(QWidget):
    def __init__(self, on_navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(icons.pixmap("shield_check", theme.hex_color("accent"), 26))
        brand_row.addWidget(logo)
        brand = QLabel(APP_NAME)
        brand.setObjectName("Brand")
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        lay.addLayout(brand_row)
        lay.addSpacing(16)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for page_id, label, icon_name, _, _ in PAGES:
            if page_id == "history":
                lay.addStretch(1)
            btn = QPushButton(f"  {label}")
            btn.setProperty("nav", "true")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(icons.icon(icon_name, theme.hex_color("text_muted"), 18))
            btn.setIconSize(QSize(18, 18))
            btn.clicked.connect(lambda _=False, pid=page_id: on_navigate(pid))
            self._group.addButton(btn)
            self._buttons[page_id] = btn
            lay.addWidget(btn)

        lay.addSpacing(8)
        self.footer = QLabel()
        self.footer.setProperty("role", "caption")
        self.footer.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.footer)

    def set_active(self, page_id: str):
        btn = self._buttons.get(page_id)
        if btn:
            btn.setChecked(True)
            # refresh icon tint to accent for the active one
        for pid, b in self._buttons.items():
            icon_name = next(p[2] for p in PAGES if p[0] == pid)
            tint = theme.hex_color("accent") if pid == page_id else theme.hex_color("text_muted")
            b.setIcon(icons.icon(icon_name, tint, 18))

    def set_footer(self, text: str):
        self.footer.setText(text)


class MainWindow(QWidget):
    def __init__(self, services: Services):
        super().__init__()
        self.services = services
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(980, 640)
        self.resize(1180, 760)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar(self.navigate)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack, 1)

        self._pages: dict[str, QWidget] = {}
        self._page_index: dict[str, int] = {}
        self._current: str | None = None

        self._restore_geometry()
        self._start_footer_timer()

        last = services.settings["ui.last_page"] or "home"
        self.navigate(last if any(p[0] == last for p in PAGES) else "home")

    def _lazy_page(self, page_id: str) -> QWidget | None:
        if page_id in self._pages:
            return self._pages[page_id]
        meta = next((p for p in PAGES if p[0] == page_id), None)
        if not meta:
            return None
        _, _, _, module_name, class_name = meta
        try:
            import importlib

            module = importlib.import_module(module_name)
            page = getattr(module, class_name)(self.services)
        except Exception:  # noqa: BLE001
            log.exception("failed to build page %s", page_id)
            from opencare.ui.widgets import EmptyState

            page = EmptyState("alert", "This page failed to load", f"See the log for details ({page_id}).", "danger")
        self._pages[page_id] = page
        self._page_index[page_id] = self.stack.addWidget(page)
        return page

    def navigate(self, page_id: str):
        page = self._lazy_page(page_id)
        if page is None:
            return
        if self._current and self._current in self._pages:
            cur = self._pages[self._current]
            if hasattr(cur, "on_hide"):
                cur.on_hide()
        self.stack.setCurrentIndex(self._page_index[page_id])
        self.sidebar.set_active(page_id)
        self._current = page_id
        self.services.settings["ui.last_page"] = page_id
        if hasattr(page, "on_show"):
            page.on_show()

    def go_to(self, page_id: str):
        """Public navigation hook for pages (e.g. Home → Cleanup)."""
        self.navigate(page_id)

    # ---- footer live stats ----
    def _start_footer_timer(self):
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._update_footer)
        self._timer.start()
        self._update_footer()

    def _update_footer(self):
        try:
            import psutil

            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.sidebar.set_footer(f"CPU {cpu:.0f}%   ·   RAM {ram:.0f}%")
        except Exception:  # noqa: BLE001
            self.sidebar.set_footer(f"v{__version__}")

    # ---- geometry persistence ----
    def _restore_geometry(self):
        geo = self.services.settings["ui.window_geometry"]
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except (ValueError, TypeError):
                pass

    def closeEvent(self, event):
        try:
            self.services.settings["ui.window_geometry"] = bytes(self.saveGeometry()).hex()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
