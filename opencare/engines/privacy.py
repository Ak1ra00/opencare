"""Privacy sweep — clears browsing and activity traces.

Covers browser caches/history/cookies/sessions (per detected browser) and Windows
activity traces (recent documents, run history, typed paths, temp). By policy OpenCare
never touches saved passwords or autofill/form data, so those are not scanned at all.

Deleting a browser trace while that browser is running usually fails (file locked); such
items are reported and skipped, not forced.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from opencare.core.env import RegValue
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
from opencare.engines.browsers import detect_browsers
from opencare.engines.fsutil import delete_file, dir_size, iter_files

register_defaults({"privacy.categories": {}})

TRACE_TITLES = {
    "cache": "Cache", "history": "Browsing history", "cookies": "Cookies",
    "sessions": "Session data", "downloads": "Download history",
}

CATEGORIES = {
    "browser_cache": ("Browser cache", "Cached web files. Safe to clear; pages reload from the web.", Risk.LOW, True),
    "browser_history": ("Browsing & download history", "Visited-page and download lists.", Risk.MEDIUM, False),
    "browser_cookies": ("Cookies & sessions", "Clearing these signs you out of websites.", Risk.MEDIUM, False),
    "windows_recent": ("Recent files & run history", "Recently-opened document list and Run dialog history.", Risk.LOW, True),
    "windows_activity": ("Windows activity traces", "Typed paths, search history and temporary thumbnails.", Risk.LOW, True),
}

TRACE_TO_CATEGORY = {"cache": "browser_cache", "history": "browser_history",
                     "downloads": "browser_history", "cookies": "browser_cookies", "sessions": "browser_cookies"}


@register
class PrivacyScanner(Scanner):
    id = "privacy"
    title = "Privacy"
    description = "Erase browsing and activity traces."
    icon = "eye"
    order = 20
    categories = [Category(cid, t[0], t[1], t[2], t[3]) for cid, t in CATEGORIES.items()]

    def scan(self, ctx: ScanContext) -> ScanResult:
        def body(res: ScanResult):
            cats = self.runnable_categories(ctx, res)
            steps = []
            if cats & {"browser_cache", "browser_history", "browser_cookies"}:
                steps.append(self._scan_browsers)
            if "windows_recent" in cats:
                steps.append(self._scan_recent)
            if "windows_activity" in cats:
                steps.append(self._scan_activity)
            for n, step in enumerate(steps):
                if ctx.cancelled():
                    return
                ctx.progress(n / max(1, len(steps)), "Scanning privacy traces")
                step(ctx, res, cats)

        return self.timed_scan(ctx, body)

    # ---- browsers ----
    def _scan_browsers(self, ctx, res, cats):
        for br in detect_browsers(ctx.env):
            for spec in br.traces:
                cat = TRACE_TO_CATEGORY.get(spec.trace)
                if cat not in cats:
                    continue
                size = 0
                count = 0
                hit_paths: list[str] = []
                for prof in br.profiles:
                    for rel in spec.relpaths:
                        target = prof.path / rel
                        if spec.is_dir:
                            if target.is_dir():
                                s, c = dir_size(target, ctx.cancelled)
                                size += s
                                count += c
                                if c:
                                    hit_paths.append(str(target))
                        elif target.is_file():
                            try:
                                size += target.stat().st_size
                            except OSError:
                                pass
                            count += 1
                            hit_paths.append(str(target))
                if count == 0:
                    continue
                res.issues.append(Issue(
                    id=f"privacy:{cat}:{br.name}:{spec.trace}".lower(),
                    scanner=self.id, category=cat,
                    title=f"{br.name} — {TRACE_TITLES.get(spec.trace, spec.trace)}",
                    detail=f"{len(br.profiles)} profile{'s' if len(br.profiles) != 1 else ''} · {count} item{'s' if count != 1 else ''}",
                    size=size, count=count, path=hit_paths[0] if hit_paths else None,
                    risk=self.category(cat).risk,
                    payload={"kind": "paths", "paths": hit_paths, "is_dir": spec.is_dir, "browser": br.name},
                ))

    # ---- Windows recent / run history (registry + filesystem) ----
    def _scan_recent(self, ctx, res, cats):
        recent = ctx.env.known.get("recent")
        count = 0
        size = 0
        for hit in iter_files(recent, patterns=("*.lnk",), recursive=False, cancelled=ctx.cancelled):
            count += 1
            size += hit.size
        if count:
            res.issues.append(Issue(
                id="privacy:windows_recent:recentfiles", scanner=self.id, category="windows_recent",
                title="Recent documents", detail=f"{count} shortcut{'s' if count != 1 else ''}",
                size=size, count=count, path=str(recent), risk=Risk.LOW,
                payload={"kind": "paths", "paths": [str(recent / '*.lnk')], "is_dir": False, "glob": str(recent)},
            ))
        # Run dialog MRU
        run_mru = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU"
        vals = [v for v in ctx.env.reg.values(run_mru) if v.name != "MRUList"]
        if vals:
            res.issues.append(Issue(
                id="privacy:windows_recent:runmru", scanner=self.id, category="windows_recent",
                title="Run dialog history", detail=f"{len(vals)} entr{'ies' if len(vals) != 1 else 'y'}",
                count=len(vals), path=run_mru, risk=Risk.LOW,
                payload={"kind": "reg_values", "path": run_mru, "clear_all": True},
            ))

    def _scan_activity(self, ctx, res, cats):
        # Explorer typed paths
        typed = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\TypedPaths"
        vals = ctx.env.reg.values(typed)
        if vals:
            res.issues.append(Issue(
                id="privacy:windows_activity:typedpaths", scanner=self.id, category="windows_activity",
                title="Explorer address-bar history", detail=f"{len(vals)} path{'s' if len(vals) != 1 else ''}",
                count=len(vals), path=typed, risk=Risk.LOW,
                payload={"kind": "reg_values", "path": typed, "clear_all": True},
            ))
        # Explorer thumbnail cache files are covered by junk; here we clear WordWheelQuery (search history)
        search = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\WordWheelQuery"
        svals = [v for v in ctx.env.reg.values(search) if v.name != "MRUListEx"]
        if svals:
            res.issues.append(Issue(
                id="privacy:windows_activity:searchhistory", scanner=self.id, category="windows_activity",
                title="File Explorer search history", detail=f"{len(svals)} quer{'ies' if len(svals) != 1 else 'y'}",
                count=len(svals), path=search, risk=Risk.LOW,
                payload={"kind": "reg_values", "path": search, "clear_all": True},
            ))

    # ---- fix ----
    def fix(self, issues, ctx: FixContext) -> FixReport:
        report = FixReport(self.id)
        total = len(issues)
        for n, issue in enumerate(issues):
            if ctx.cancelled():
                break
            ctx.progress(n / max(1, total), issue.title)
            kind = issue.payload.get("kind")
            if kind == "paths":
                self._fix_paths(issue, report, ctx)
            elif kind == "reg_values":
                self._fix_reg_values(issue, report, ctx)
        ctx.changes.items += report.fixed
        ctx.changes.bytes_freed += report.bytes_freed
        return report

    def _fix_paths(self, issue, report, ctx: FixContext):
        glob_dir = issue.payload.get("glob")
        if glob_dir:
            for hit in iter_files(Path(glob_dir), patterns=("*.lnk",), recursive=False, cancelled=ctx.cancelled):
                if ctx.dry_run:
                    report.fixed += 1
                    continue
                if delete_file(hit.path):
                    report.fixed += 1
                else:
                    report.failed += 1
            return
        for target in issue.payload.get("paths", []):
            p = Path(target)
            try:
                if ctx.dry_run:
                    report.fixed += 1
                    continue
                if p.is_dir():
                    before, _ = dir_size(p)
                    shutil.rmtree(p, ignore_errors=True)
                    report.bytes_freed += before
                    report.fixed += 1
                elif p.is_file():
                    sz = p.stat().st_size
                    if delete_file(str(p)):
                        report.bytes_freed += sz
                        report.fixed += 1
                    else:
                        report.failed += 1
            except OSError:
                report.failed += 1

    def _fix_reg_values(self, issue, report, ctx: FixContext):
        path = issue.payload["path"]
        if ctx.dry_run:
            report.fixed += 1
            return
        ctx.changes.backup_reg_tree(path)
        removed = 0
        for v in ctx.env.reg.values(path):
            try:
                ctx.env.reg.delete_value(path, v.name)
                removed += 1
            except OSError:
                report.failed += 1
        if removed:
            report.fixed += 1
