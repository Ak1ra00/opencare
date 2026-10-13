"""Application data locations (%LOCALAPPDATA%\\OpenCare by default).

Set OPENCARE_DATA_DIR to relocate everything (used by tests).
"""
from __future__ import annotations

import os
from pathlib import Path

from opencare import APP_NAME


def data_dir() -> Path:
    override = os.environ.get("OPENCARE_DATA_DIR")
    base = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def history_dir() -> Path:
    return _sub("history")


def logs_dir() -> Path:
    return _sub("logs")


def cache_dir() -> Path:
    return _sub("cache")


def settings_file() -> Path:
    return data_dir() / "settings.json"
