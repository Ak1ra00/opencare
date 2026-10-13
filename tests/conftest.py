"""Shared fixtures. Nothing here (or in any test) may touch the real system:
use ``sandbox_env`` for folders + registry and ``settings`` for an isolated settings file."""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "opencare-data"
    data.mkdir()
    monkeypatch.setenv("OPENCARE_DATA_DIR", str(data))
    from opencare.core import settings as settings_mod

    settings_mod.set_settings_instance(None)
    yield
    settings_mod.set_settings_instance(None)


@pytest.fixture
def settings(tmp_path):
    from opencare.core.settings import Settings, set_settings_instance

    s = Settings(tmp_path / "opencare-data" / "settings.json")
    set_settings_instance(s)
    return s


@pytest.fixture
def sandbox_env(tmp_path):
    from opencare.core.env import Environment

    env = Environment.sandboxed(tmp_path / "sandbox", f"t{uuid.uuid4().hex[:10]}", is_admin=True)
    yield env
    env.reg.destroy()


@pytest.fixture
def change_store(sandbox_env, tmp_path):
    from opencare.core.changes import ChangeStore

    root = tmp_path / "history"
    root.mkdir()
    return ChangeStore(sandbox_env, root)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
