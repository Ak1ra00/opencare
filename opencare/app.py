"""Application entry point: QApplication setup, theming, single instance, main window."""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from opencare import APP_ID, APP_NAME, __version__
from opencare.core.logging_setup import setup_logging
from opencare.core.settings import get_settings
from opencare.services import Services
from opencare.ui import icons, theme

log = logging.getLogger(__name__)


def _set_app_user_model_id():
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    setup_logging()
    log.info("Starting %s %s", APP_NAME, __version__)
    _set_app_user_model_id()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(True)

    settings = get_settings()
    theme.apply_theme(app, settings["ui.theme"] or "system")
    app.setWindowIcon(icons.icon("shield_check", theme.hex_color("accent"), 64))

    # react to live system light/dark changes when in "system" mode
    def on_scheme_changed(*_):
        if (settings["ui.theme"] or "system") == "system":
            theme.apply_theme(app, "system")

    try:
        app.styleHints().colorSchemeChanged.connect(on_scheme_changed)
    except (AttributeError, TypeError):
        pass

    services = Services.create()
    from opencare.ui.main_window import MainWindow

    window = MainWindow(services)
    window.show()
    return app.exec()
