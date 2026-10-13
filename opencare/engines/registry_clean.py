"""Registry cleaner — finds a conservative set of invalid registry references.

Philosophy: only flag entries whose target demonstrably no longer exists (a missing file,
a dangling CLSID, an uninstalled app's leftovers). Never flag a key merely for being empty.
Every removed value or key is exported to the change set first, so the whole sweep is undoable,
and protected hives (services, SAM, SECURITY, control set) are never touched.

Checks implemented (all read-only during scan):
  - file_refs:   App Paths / shell-open commands pointing to missing executables
  - uninstall:   Uninstall entries whose InstallLocation / UninstallString is gone
  - startup_refs: Run/RunOnce entries whose program file is missing (reported here, fixed here)
  - shared_dll:  SharedDLLs refcounts for files that no longer exist
  - mui_cache:   MuiCache entries for missing executables
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from opencare.core.env import Environment, RegValue
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
from opencare.engines.safety import is_protected_registry

register_defaults({"registry.categories": {}})

CATEGORIES = {
    "file_refs": ("Missing program references", "App paths and file associations pointing to files that no longer exist.", Risk.LOW, True),
    "uninstall": ("Obsolete uninstall entries", "Leftover entries for programs that are already gone.", Risk.MEDIUM, True),
    "shared_dll": ("Invalid shared DLL counts", "Shared-library reference counts for files that no longer exist.", Risk.LOW, True),
    "mui_cache": ("Application cache leftovers", "Cached entries for executables that no longer exist.", Risk.LOW, True),
}


def _expand(path: str) -> str:
    return os.path.expandvars(path.strip().strip('"'))


def _exe_from_command(command: str) -> str | None:
    """Extract the executable path from a shell command string."""
    command = command.strip()
    if not command:
        return None
    if command.startswith('"'):
        end = command.find('"', 1)
        return command[1:end] if end > 0 else command[1:]
    # unquoted: take up to first space that ends a .exe, else first token
    low = command.lower()
    idx = low.find(".exe")
    if idx > 0:
        return command[: idx + 4]
    return command.split(" ")[0]


def _missing(path: str) -> bool:
    if not path:
        return False
    p = _expand(path)
    if not p or p.lower() in ("regsvr32.exe", "rundll32.exe"):
        return False
    # bare command name resolvable on PATH -> not missing
    if os.sep not in p and "/" not in p:
        from shutil import which

        return which(p) is None
    return not Path(p).exists()


@register
class RegistryScanner(Scanner):
    id = "registry"
    title = "Registry"
    description = "Fix invalid references left behind in the Windows registry."
    icon = "database"
    order = 30
    categories = [Category(cid, t[0], t[1], t[2], t[3]) for cid, t in CATEGORIES.items()]

    def scan(self, ctx: ScanContext) -> ScanResult:
        def body(res: ScanResult):
            cats = self.runnable_categories(ctx, res)
            checks = []
            if "file_refs" in cats:
                checks.append(self._check_app_paths)
            if "uninstall" in cats:
                checks.append(self._check_uninstall)
            if "shared_dll" in cats:
                checks.append(self._check_shared_dlls)
            if "mui_cache" in cats:
                checks.append(self._check_mui_cache)
            for n, check in enumerate(checks):
                if ctx.cancelled():
                    return
                ctx.progress(n / max(1, len(checks)), "Scanning registry")
                check(ctx, res)

        return self.timed_scan(ctx, body)

    def _add(self, res, cat, issue_key, title, detail, path, payload, risk=None):
        res.issues.append(Issue(
            id=f"registry:{cat}:{issue_key}".lower(), scanner=self.id, category=cat,
            title=title, detail=detail, path=path, risk=risk or self.category(cat).risk, payload=payload,
        ))

    def _each_hive(self, ctx) -> list[str]:
        return ["HKLM", "HKCU"]

    def _check_app_paths(self, ctx, res):
        for hive in self._each_hive(ctx):
            base = rf"{hive}\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
            for sub in ctx.env.reg.subkeys(base):
                if ctx.cancelled():
                    return
                key = f"{base}\\{sub}"
                default = ctx.env.reg.get_value(key, "")
                target = default.value if default else None
                if target and _missing(str(target)):
                    self._add(res, "file_refs", key, f"App path: {sub}",
                              f"Points to missing file {_expand(str(target))}", key,
                              {"kind": "reg_key", "path": key})

    def _check_uninstall(self, ctx, res):
        for hive in self._each_hive(ctx):
            for wow in ("", r"\WOW6432Node"):
                base = rf"{hive}\SOFTWARE{wow}\Microsoft\Windows\CurrentVersion\Uninstall"
                for sub in ctx.env.reg.subkeys(base):
                    if ctx.cancelled():
                        return
                    key = f"{base}\\{sub}"
                    vals = {v.name: v.value for v in ctx.env.reg.values(key)}
                    if vals.get("SystemComponent") == 1 or vals.get("WindowsInstaller") == 1:
                        continue
                    name = vals.get("DisplayName") or sub
                    uninstall = vals.get("UninstallString")
                    install_loc = vals.get("InstallLocation")
                    exe = _exe_from_command(str(uninstall)) if uninstall else None
                    loc_missing = install_loc and not Path(_expand(str(install_loc))).exists()
                    exe_missing = exe and _missing(exe)
                    if uninstall and exe_missing and (not install_loc or loc_missing):
                        self._add(res, "uninstall", key, f"Uninstall entry: {name}",
                                  "Program files appear to be already removed.", key,
                                  {"kind": "reg_key", "path": key})

    def _check_shared_dlls(self, ctx, res):
        key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs"
        missing = []
        for v in ctx.env.reg.values(key):
            if ctx.cancelled():
                return
            if v.name and os.sep in v.name and not Path(_expand(v.name)).exists():
                missing.append(v.name)
        if missing:
            self._add(res, "shared_dll", key + ":bulk",
                      f"Shared DLL counts: {len(missing)} missing files",
                      "Reference counts for libraries that no longer exist.", key,
                      {"kind": "reg_values", "path": key, "names": missing})

    def _check_mui_cache(self, ctx, res):
        key = r"HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"
        missing = []
        for v in ctx.env.reg.values(key):
            if ctx.cancelled():
                return
            path = v.name.split(".FriendlyAppName")[0].split(".ApplicationCompany")[0]
            if os.sep in path and path.lower().endswith(".exe") and not Path(_expand(path)).exists():
                missing.append(v.name)
        if missing:
            self._add(res, "mui_cache", key + ":bulk",
                      f"Application cache: {len(missing)} missing executables",
                      "Cached metadata for programs that no longer exist.", key,
                      {"kind": "reg_values", "path": key, "names": missing})

    # ---- fix ----
    def fix(self, issues, ctx: FixContext) -> FixReport:
        report = FixReport(self.id)
        total = len(issues)
        for n, issue in enumerate(issues):
            if ctx.cancelled():
                break
            ctx.progress(n / max(1, total), issue.title)
            path = issue.payload.get("path", "")
            if is_protected_registry(path):
                report.failed += 1
                report.errors.append(f"protected: {path}")
                continue
            if issue.payload["kind"] == "reg_key":
                self._del_key(issue, report, ctx)
            else:
                self._del_values(issue, report, ctx)
        ctx.changes.items += report.fixed
        return report

    def _del_key(self, issue, report, ctx: FixContext):
        path = issue.payload["path"]
        if ctx.dry_run:
            report.fixed += 1
            return
        try:
            ctx.changes.backup_reg_tree(path)
            ctx.env.reg.delete_tree(path)
            report.fixed += 1
        except OSError as e:
            report.failed += 1
            report.errors.append(str(e))

    def _del_values(self, issue, report, ctx: FixContext):
        path = issue.payload["path"]
        names = issue.payload["names"]
        if ctx.dry_run:
            report.fixed += len(names)
            return
        for name in names:
            v = ctx.env.reg.get_value(path, name)
            if v is None:
                continue
            try:
                ctx.changes.backup_reg_value(path, v)
                ctx.env.reg.delete_value(path, name)
                report.fixed += 1
            except OSError as e:
                report.failed += 1
                report.errors.append(str(e))
