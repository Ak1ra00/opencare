"""Junk file scanner — reclaimable caches and temporary files.

Targets are standard Windows and common-application cache/temp locations. Each location
belongs to a category so the user can choose what to clear. Nothing under System32 or a
protected path is ever listed. Files younger than the age threshold are kept (they may
still be in use). Removal optionally routes through the Recycle Bin.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
from opencare.engines.fsutil import FileHit, delete_file, iter_files
from opencare.engines.safety import is_protected_path

register_defaults({
    "junk.min_age_hours": 24,
    "junk.categories": {},
})


@dataclass
class JunkLocation:
    category: str
    label: str
    base: str                    # KnownFolders key or absolute path
    sub: str = ""                # subpath under base
    patterns: tuple[str, ...] = ()  # fnmatch patterns; empty = all files
    recursive: bool = True
    min_age_hours: float | None = None  # overrides category default


TEMP_PATTERNS = ("*.tmp", "*.temp", "*.~*", "~*", "*.old", "*.chk", "*.gid", "*.dmp", "*._mp", "*.log.old")

LOCATIONS: list[JunkLocation] = [
    # Windows temporary files
    JunkLocation("windows_temp", "User temp folder", "temp"),
    JunkLocation("windows_temp", "Windows temp folder", "windows", "Temp"),
    # System cache
    JunkLocation("system_cache", "Windows Prefetch", "windows", "Prefetch", patterns=("*.pf",), min_age_hours=168),
    JunkLocation("system_cache", "Windows Update cache", "windows", "SoftwareDistribution\\Download"),
    JunkLocation("system_cache", "Font cache", "localappdata", "FontCache"),
    JunkLocation("system_cache", "Thumbnail cache", "localappdata", "Microsoft\\Windows\\Explorer", patterns=("thumbcache_*.db", "iconcache_*.db")),
    JunkLocation("system_cache", "Delivery Optimization files", "windows", "SoftwareDistribution\\DeliveryOptimization"),
    # Crash dumps & error reports
    JunkLocation("crash_dumps", "Application crash dumps", "localappdata", "CrashDumps", patterns=("*.dmp", "*.mdmp")),
    JunkLocation("crash_dumps", "Windows Error Reporting", "localappdata", "Microsoft\\Windows\\WER"),
    JunkLocation("crash_dumps", "Minidumps", "windows", "Minidump", patterns=("*.dmp",)),
    # Leftover temp files across the profile
    JunkLocation("leftover_temp", "Temporary files in Downloads", "downloads", patterns=TEMP_PATTERNS, recursive=False),
    JunkLocation("leftover_temp", "Leftover installer files", "temp", patterns=("*.msi", "*.cab", "~*.tmp")),
    # Recycle Bin is handled specially (reported as one item)
]

# category -> (title, description, risk, default_on)
CATEGORIES = {
    "windows_temp": ("Temporary files", "Temp folders used by Windows and apps for scratch data.", Risk.LOW, True),
    "system_cache": ("System caches", "Regenerable caches: Prefetch, Windows Update, fonts, thumbnails.", Risk.LOW, True),
    "crash_dumps": ("Crash dumps & error reports", "Memory dumps and error reports from crashed programs.", Risk.LOW, True),
    "leftover_temp": ("Leftover temporary files", "Stray .tmp/.old files left behind by installers and apps.", Risk.LOW, True),
    "recycle_bin": ("Recycle Bin", "Items you already sent to the Recycle Bin.", Risk.MEDIUM, False),
}


@register
class JunkScanner(Scanner):
    id = "junk"
    title = "Junk Files"
    description = "Reclaim disk space from caches and temporary files."
    icon = "broom"
    order = 10
    categories = [
        Category(cid, t[0], t[1], t[2], t[3]) for cid, t in CATEGORIES.items()
    ]

    def scan(self, ctx: ScanContext) -> ScanResult:
        def body(res: ScanResult):
            cats = self.runnable_categories(ctx, res)
            default_age = float(ctx.settings["junk.min_age_hours"])
            locs = [loc for loc in LOCATIONS if loc.category in cats]
            total = len(locs) + (1 if "recycle_bin" in cats else 0)
            done = 0
            for loc in locs:
                if ctx.cancelled():
                    return
                ctx.progress(done / max(1, total), f"Scanning {loc.label}")
                self._scan_location(ctx, res, loc, default_age)
                done += 1
            if "recycle_bin" in cats and not ctx.cancelled():
                ctx.progress(done / max(1, total), "Scanning Recycle Bin")
                self._scan_recycle_bin(res)

        return self.timed_scan(ctx, body)

    def _scan_location(self, ctx, res, loc: JunkLocation, default_age: float):
        base = ctx.env.known.get(loc.base)
        root = base / loc.sub if loc.sub else base
        if is_protected_path(str(root)):
            return
        age = loc.min_age_hours if loc.min_age_hours is not None else default_age
        size = 0
        count = 0
        sample: list[str] = []
        for hit in iter_files(root, patterns=loc.patterns or None, min_age_hours=age,
                              recursive=loc.recursive, cancelled=ctx.cancelled):
            if ctx.settings.is_excluded(hit.path) or is_protected_path(hit.path):
                continue
            size += hit.size
            count += 1
            if len(sample) < 6:
                sample.append(Path(hit.path).name)
        if count == 0:
            return
        issue = Issue(
            id=f"junk:{loc.category}:{str(root).lower()}",
            scanner=self.id,
            category=loc.category,
            title=loc.label,
            detail=f"{count} file{'s' if count != 1 else ''} · e.g. " + ", ".join(sample) if sample else loc.label,
            size=size,
            count=count,
            path=str(root),
            risk=self.category(loc.category).risk,
            payload={"root": str(root), "patterns": loc.patterns, "age": age,
                     "recursive": loc.recursive, "kind": "files"},
        )
        res.issues.append(issue)

    def _scan_recycle_bin(self, res):
        try:
            from opencare.engines.recyclebin import recycle_bin_stats

            size, count = recycle_bin_stats()
        except Exception:  # noqa: BLE001
            return
        if count <= 0:
            return
        res.issues.append(Issue(
            id="junk:recycle_bin:all",
            scanner=self.id,
            category="recycle_bin",
            title="Recycle Bin contents",
            detail=f"{count} item{'s' if count != 1 else ''}",
            size=size,
            count=count,
            risk=Risk.MEDIUM,
            payload={"kind": "recycle_bin"},
        ))

    def fix(self, issues: list[Issue], ctx: FixContext) -> FixReport:
        report = FixReport(self.id)
        to_recycle = bool(ctx.settings["safety.delete_to_recycle_bin"])
        total = len(issues)
        for n, issue in enumerate(issues):
            if ctx.cancelled():
                break
            ctx.progress(n / max(1, total), issue.title)
            kind = issue.payload.get("kind")
            if kind == "recycle_bin":
                self._empty_recycle_bin(report, ctx)
                continue
            self._clean_files(issue, report, ctx, to_recycle)
        ctx.changes.bytes_freed += report.bytes_freed
        ctx.changes.items += report.fixed
        return report

    def _clean_files(self, issue, report, ctx: FixContext, to_recycle: bool):
        root = Path(issue.payload["root"])
        patterns = tuple(issue.payload.get("patterns") or ())
        for hit in iter_files(root, patterns=patterns or None,
                              min_age_hours=issue.payload.get("age", 0),
                              recursive=issue.payload.get("recursive", True),
                              cancelled=ctx.cancelled):
            if ctx.settings.is_excluded(hit.path) or is_protected_path(hit.path):
                continue
            if ctx.dry_run:
                report.fixed += 1
                report.bytes_freed += hit.size
                continue
            if delete_file(hit.path, to_recycle):
                report.fixed += 1
                report.bytes_freed += hit.size
            else:
                report.failed += 1

    def _empty_recycle_bin(self, report, ctx: FixContext):
        if ctx.dry_run:
            report.fixed += 1
            return
        try:
            from opencare.engines.recyclebin import empty_recycle_bin, recycle_bin_stats

            size, _ = recycle_bin_stats()
            if empty_recycle_bin():
                report.fixed += 1
                report.bytes_freed += size
            else:
                report.failed += 1
        except Exception as e:  # noqa: BLE001
            report.errors.append(str(e))
            report.failed += 1
