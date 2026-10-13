"""Headless UI construction tests: every page builds and the window navigates."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def services(sandbox_env, settings, tmp_path):
    from opencare.core.changes import ChangeStore
    from opencare.engines.checkup import Checkup
    from opencare.services import Services

    store = ChangeStore(sandbox_env, tmp_path / "history")
    return Services(env=sandbox_env, settings=settings, store=store,
                    checkup=Checkup(sandbox_env, settings, store))


def test_theme_applies(qapp):
    from opencare.ui import theme

    theme.apply_theme(qapp, "dark")
    assert theme.is_dark()
    theme.apply_theme(qapp, "light")
    assert not theme.is_dark()


def test_every_page_builds(qapp, services):
    from opencare.ui import theme
    from opencare.ui.main_window import PAGES

    theme.apply_theme(qapp, "light")
    import importlib

    for page_id, _, _, module_name, class_name in PAGES:
        module = importlib.import_module(module_name)
        page = getattr(module, class_name)(services)
        assert page is not None


def test_main_window_navigates(qapp, services):
    from opencare.ui import theme
    from opencare.ui.main_window import MainWindow, PAGES

    theme.apply_theme(qapp, "light")
    win = MainWindow(services)
    for page_id, *_ in PAGES:
        win.navigate(page_id)
        assert win._current == page_id
    win.close()
