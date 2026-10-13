"""Persistent settings stored as a flat JSON object of dotted keys.

    s = get_settings()
    s["junk.min_age_hours"]          # default if unset
    s["junk.min_age_hours"] = 48     # persisted immediately
    s.subscribe(lambda key, value: ...)

Modules declare their keys with register_defaults({...}) at import time.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from opencare.core import paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    # appearance / shell
    "ui.theme": "system",  # system | light | dark
    "ui.window_geometry": None,
    "ui.last_page": "home",
    "app.run_at_login": False,
    "app.minimize_to_tray": True,
    "app.close_to_tray": False,
    "app.notifications": True,
    # checkup
    "checkup.scanners": {"junk": True, "privacy": True, "registry": True, "shortcuts": True, "startup": True, "security": True},
    "checkup.last_run": None,
    "checkup.last_summary": None,
    "checkup.schedule": "off",  # off | daily | weekly | monthly
    "checkup.schedule_time": "12:00",
    "checkup.auto_fix_scheduled": False,
    # global safety
    "safety.create_restore_point": False,
    "safety.delete_to_recycle_bin": False,
    "history.keep_days": 60,
    "exclusions": [],  # list of path prefixes / registry key prefixes never touched
    "ignored_issues": [],  # issue ids the user chose to ignore
    # lifetime statistics shown on Home
    "stats.bytes_freed": 0,
    "stats.items_fixed": 0,
    "stats.checkups": 0,
}

_lock = threading.RLock()


def register_defaults(values: dict[str, Any]) -> None:
    with _lock:
        for k, v in values.items():
            DEFAULTS.setdefault(k, v)


class Settings:
    def __init__(self, file: Path | None = None):
        self._file = file or paths.settings_file()
        self._data: dict[str, Any] = {}
        self._subs: list[Callable[[str, Any], None]] = []
        self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self._file.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                self._data = {}
        except FileNotFoundError:
            self._data = {}
        except (OSError, ValueError) as e:
            log.warning("settings unreadable (%s); starting fresh", e)
            backup = self._file.with_suffix(".corrupt.json")
            try:
                self._file.replace(backup)
            except OSError:
                pass
            self._data = {}

    def _save(self) -> None:
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._file)

    def get(self, key: str, default: Any = None) -> Any:
        with _lock:
            if key in self._data:
                return self._data[key]
            if key in DEFAULTS:
                v = DEFAULTS[key]
                return json.loads(json.dumps(v))  # defensive copy of mutable defaults
            return default

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def set(self, key: str, value: Any) -> None:
        with _lock:
            if self._data.get(key, object()) == value:
                return
            self._data[key] = value
            self._save()
            subs = list(self._subs)
        for fn in subs:
            try:
                fn(key, value)
            except Exception:  # a broken subscriber must not break settings
                log.exception("settings subscriber failed for %s", key)

    def update(self, values: dict[str, Any]) -> None:
        for k, v in values.items():
            self.set(k, v)

    def reset(self, key: str) -> None:
        with _lock:
            if key in self._data:
                del self._data[key]
                self._save()
        for fn in list(self._subs):
            fn(key, self.get(key))

    def subscribe(self, fn: Callable[[str, Any], None]) -> Callable[[], None]:
        self._subs.append(fn)
        return lambda: self._subs.remove(fn) if fn in self._subs else None

    # convenience for exclusions / ignore list
    def is_excluded(self, path_or_key: str) -> bool:
        target = path_or_key.lower().rstrip("\\")
        for ex in self.get("exclusions") or []:
            ex = str(ex).lower().rstrip("\\")
            if ex and (target == ex or target.startswith(ex + "\\")):
                return True
        return False

    def is_ignored(self, issue_id: str) -> bool:
        return issue_id in set(self.get("ignored_issues") or [])


_instance: Settings | None = None


def get_settings() -> Settings:
    global _instance
    with _lock:
        if _instance is None:
            _instance = Settings()
        return _instance


def set_settings_instance(s: Settings | None) -> None:
    """Testing hook."""
    global _instance
    _instance = s
