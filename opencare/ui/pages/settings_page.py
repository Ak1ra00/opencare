"""Settings page: appearance, safety, scheduling and scanner selection."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from opencare import __version__
from opencare.engines.base import all_scanners
from opencare.ui import theme
from opencare.ui.widgets import (
    Card,
    Divider,
    Page,
    PageHeader,
    ToggleSwitch,
)
from opencare.ui.widgets.feedback import toast


class SettingRow(QWidget):
    def __init__(self, title, subtitle, control):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(title)
        t.setProperty("role", "h3")
        col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setProperty("role", "subtitle")
            s.setWordWrap(True)
            col.addWidget(s)
        lay.addLayout(col, 1)
        lay.addWidget(control, alignment=Qt.AlignVCenter)


class SettingsPage(Page):
    page_id = "settings"
    title = "Settings"

    def __init__(self, services, parent=None):
        super().__init__(services, parent)
        self._build()

    def _toggle(self, key):
        sw = ToggleSwitch()
        sw.setChecked(bool(self.services.settings[key]))
        sw.toggled.connect(lambda on: self.services.settings.set(key, on))
        return sw

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lay.addWidget(PageHeader("Settings", "Appearance, safety and what the checkup scans."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 6, 0)
        iv.setSpacing(14)

        # appearance
        appearance = Card()
        appearance.body().addWidget(self._h2("Appearance"))
        theme_combo = QComboBox()
        theme_combo.addItems(["Match Windows", "Light", "Dark"])
        theme_combo.setCurrentIndex({"system": 0, "light": 1, "dark": 2}.get(self.services.settings["ui.theme"], 0))
        theme_combo.currentIndexChanged.connect(self._change_theme)
        appearance.body().addWidget(SettingRow("Theme", "Light, dark, or follow the Windows setting.", theme_combo))
        iv.addWidget(appearance)

        # safety
        safety = Card()
        safety.body().addWidget(self._h2("Safety"))
        safety.body().addWidget(SettingRow("Send deleted files to the Recycle Bin",
                                           "Slower, but junk files can be recovered from the Recycle Bin.",
                                           self._toggle("safety.delete_to_recycle_bin")))
        safety.body().addWidget(Divider())
        safety.body().addWidget(SettingRow("Confirm before fixing",
                                           "Always preview and confirm. (Recommended — kept on.)",
                                           self._locked_on()))
        iv.addWidget(safety)

        # checkup scanners
        scanners_card = Card()
        scanners_card.body().addWidget(self._h2("Include in checkup"))
        enabled = dict(self.services.settings["checkup.scanners"] or {})
        for i, scanner in enumerate(all_scanners()):
            if i:
                scanners_card.body().addWidget(Divider())
            sw = ToggleSwitch()
            sw.setChecked(enabled.get(scanner.id, True))
            sw.toggled.connect(lambda on, sid=scanner.id: self._toggle_scanner(sid, on))
            scanners_card.body().addWidget(SettingRow(scanner.title, scanner.description, sw))
        iv.addWidget(scanners_card)

        # about
        about = Card()
        about.body().addWidget(self._h2("About"))
        info = QLabel(f"OpenCare {__version__}\nAn original Windows maintenance toolkit. Your changes are backed up and reversible from the History page.")
        info.setProperty("role", "subtitle")
        info.setWordWrap(True)
        about.body().addWidget(info)
        iv.addWidget(about)

        iv.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

    def _h2(self, text):
        l = QLabel(text)
        l.setProperty("role", "h2")
        return l

    def _locked_on(self):
        sw = ToggleSwitch()
        sw.setChecked(True)
        sw.setEnabled(False)
        return sw

    def _change_theme(self, index):
        value = {0: "system", 1: "light", 2: "dark"}[index]
        self.services.settings["ui.theme"] = value
        from PySide6.QtWidgets import QApplication

        theme.apply_theme(QApplication.instance(), value)
        toast(self, "Theme updated", "info")

    def _toggle_scanner(self, sid, on):
        d = dict(self.services.settings["checkup.scanners"] or {})
        d[sid] = on
        self.services.settings["checkup.scanners"] = d
