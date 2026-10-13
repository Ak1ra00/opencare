"""Startup manager — enumerate and toggle programs that run at login.

Sources: Run / RunOnce registry keys (HKCU + HKLM, native and WOW64) and the user/common
Startup folders. This engine is used two ways:
  - as a Scanner in the checkup it only *reports* startup items whose target file is
    missing (category "invalid"); it does not disable working startup items automatically.
  - the Startup page calls list_items()/set_enabled() directly to let the user manage them.

Disabling preserves the entry: registry entries are moved to a backup key / startup-folder
files are moved to a disabled folder, both recorded for undo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from opencare.core.changes import Operation, register_restore_handler
from opencare.core.env import Environment
from opencare.core.settings import register_defaults
from opencare.engines.base import (
    Category,
    FixContext,
    FixReport,
    Issue,
    Risk,
    ScanContext,
    ScanResult,
    Scanner,
    register,
)

register_defaults({"startup.categories": {}})

DISABLED_KEY_SUFFIX = r"\OpenCareDisabled"


@dataclass
class StartupItem:
    name: str
    command: str
    location: str          # human label
    source: str            # "registry" | "folder"
    scope: str             # "user" | "machine"
    enabled: bool
    exe: str = ""
    identity: str = ""     # stable id
    reg_key: str = ""      # for registry items
    file_path: str = ""    # for folder items
    wow: bool = False


def _exe_of(command: str) -> str:
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        return command[1:end] if end > 0 else command[1:]
    low = command.lower()
    idx = low.find(".exe")
    return command[: idx + 4] if idx > 0 else command.split(" ")[0]


RUN_KEYS = [
    ("HKCU", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "user", False),
    ("HKLM", r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "machine", False),
    ("HKLM", r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "machine", True),
]


def list_items(env: Environment) -> list[StartupItem]:
    items: list[StartupItem] = []
    for hive, key, scope, wow in RUN_KEYS:
        reg = env.reg32 if wow else env.reg
        for v in reg.values(key):
            if not v.name:
                continue
            items.append(StartupItem(
                name=v.name, command=str(v.value), location=f"{hive}\\…\\Run", source="registry",
                scope=scope, enabled=True, exe=_exe_of(str(v.value)),
                identity=f"reg:{key}:{v.name}".lower(), reg_key=key, wow=wow,
            ))
        # disabled backups
        dkey = key + DISABLED_KEY_SUFFIX
        for v in reg.values(dkey):
            if not v.name:
                continue
            items.append(StartupItem(
                name=v.name, command=str(v.value), location=f"{hive}\\…\\Run", source="registry",
                scope=scope, enabled=False, exe=_exe_of(str(v.value)),
                identity=f"reg:{key}:{v.name}".lower(), reg_key=key, wow=wow,
            ))
    for folder, scope in (("startmenu_user", "user"), ("startmenu_common", "machine")):
        base = env.known.get(folder) / "Programs" / "Startup"
        if base.exists():
            for f in base.glob("*"):
                if f.suffix.lower() in (".lnk", ".url", ".bat", ".cmd", ".exe") and f.is_file():
                    items.append(StartupItem(
                        name=f.stem, command=str(f), location="Startup folder", source="folder",
                        scope=scope, enabled=True, exe=str(f),
                        identity=f"folder:{str(f)}".lower(), file_path=str(f),
                    ))
        disabled = base.parent / "Startup (disabled by OpenCare)"
        if disabled.exists():
            for f in disabled.glob("*"):
                if f.is_file():
                    items.append(StartupItem(
                        name=f.stem, command=str(f), location="Startup folder", source="folder",
                        scope=scope, enabled=False, exe=str(f),
                        identity=f"folder:{str(base / f.name)}".lower(), file_path=str(base / f.name),
                    ))
    return items


def set_enabled(env: Environment, item: StartupItem, enabled: bool, changes=None) -> bool:
    """Enable/disable one startup item, recording the change for undo."""
    if item.enabled == enabled:
        return True
    if item.source == "registry":
        return _toggle_registry(env, item, enabled, changes)
    return _toggle_folder(env, item, enabled, changes)


def _toggle_registry(env: Environment, item: StartupItem, enabled: bool, changes) -> bool:
    reg = env.reg32 if item.wow else env.reg
    active = item.reg_key
    backup = item.reg_key + DISABLED_KEY_SUFFIX
    src, dst = (backup, active) if enabled else (active, backup)
    v = reg.get_value(src, item.name)
    if v is None:
        return False
    try:
        reg.set_value(dst, item.name, v.value, v.type)
        reg.delete_value(src, item.name)
        if changes is not None:
            changes.record_startup_entry({"mode": "registry", "key": item.reg_key, "name": item.name,
                                          "wow": item.wow, "now_enabled": enabled})
        return True
    except OSError:
        return False


def _toggle_folder(env: Environment, item: StartupItem, enabled: bool, changes) -> bool:
    active = Path(item.file_path)
    disabled_dir = active.parent / "Startup (disabled by OpenCare)"
    disabled = disabled_dir / active.name
    try:
        if enabled:
            active.parent.mkdir(parents=True, exist_ok=True)
            if disabled.exists():
                disabled.replace(active)
        else:
            disabled_dir.mkdir(parents=True, exist_ok=True)
            if active.exists():
                active.replace(disabled)
        if changes is not None:
            changes.record_startup_entry({"mode": "folder", "active": str(active), "disabled": str(disabled),
                                          "now_enabled": enabled})
        return True
    except OSError:
        return False


def _restore_startup(env: Environment, op: Operation, payload_dir) -> None:
    d = op.data
    # reverse of the recorded toggle: put it back to its previous state
    was_enabled = d["now_enabled"]
    if d["mode"] == "registry":
        reg = env.reg32 if d.get("wow") else env.reg
        active = d["key"]
        backup = d["key"] + DISABLED_KEY_SUFFIX
        src, dst = (active, backup) if was_enabled else (backup, active)
        v = reg.get_value(src, d["name"])
        if v is not None:
            reg.set_value(dst, d["name"], v.value, v.type)
            try:
                reg.delete_value(src, d["name"])
            except OSError:
                pass
    else:
        active, disabled = Path(d["active"]), Path(d["disabled"])
        if was_enabled and active.exists():
            disabled.parent.mkdir(parents=True, exist_ok=True)
            active.replace(disabled)
        elif not was_enabled and disabled.exists():
            active.parent.mkdir(parents=True, exist_ok=True)
            disabled.replace(active)


register_restore_handler("startup_entry", _restore_startup)


@register
class StartupScanner(Scanner):
    id = "startup"
    title = "Startup"
    description = "Review programs that launch when Windows starts."
    icon = "startup"
    order = 50
    categories = [
        Category("invalid", "Invalid startup entries", "Startup items whose program file no longer exists.", Risk.LOW, True),
    ]

    def scan(self, ctx: ScanContext) -> ScanResult:
        def body(res: ScanResult):
            if "invalid" not in self.runnable_categories(ctx, res):
                return
            for item in list_items(ctx.env):
                if ctx.cancelled():
                    return
                if not item.enabled:
                    continue
                exe = item.exe
                if not exe:
                    continue
                if item.source == "folder":
                    continue  # a .lnk in Startup is handled by the shortcuts engine
                if os.sep in exe and not Path(os.path.expandvars(exe)).exists():
                    res.issues.append(Issue(
                        id=f"startup:invalid:{item.identity}", scanner=self.id, category="invalid",
                        title=item.name, detail=f"{item.location} · missing: {exe}", path=item.reg_key, risk=Risk.LOW,
                        payload={"identity": item.identity, "name": item.name, "reg_key": item.reg_key,
                                 "wow": item.wow, "command": item.command},
                    ))

        return self.timed_scan(ctx, body)

    def fix(self, issues, ctx: FixContext) -> FixReport:
        report = FixReport(self.id)
        all_items = {i.identity: i for i in list_items(ctx.env)}
        for issue in issues:
            if ctx.cancelled():
                break
            item = all_items.get(issue.payload["identity"])
            if not item:
                continue
            if ctx.dry_run:
                report.fixed += 1
                continue
            if set_enabled(ctx.env, item, False, ctx.changes):
                report.fixed += 1
            else:
                report.failed += 1
        ctx.changes.items += report.fixed
        return report
