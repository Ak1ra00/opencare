"""Broken shortcut scanner — .lnk files whose target no longer exists.

Scans Desktop, Start Menu (user + common) and Recent. A shortcut is "broken" only when
it has a resolvable local target path that is missing; shortcuts to URLs, UNC paths,
AppX apps or with empty targets are left alone. Removed shortcuts are quarantined (moved
into the change set), so an undo puts them back exactly.
"""
from __future__ import annotations

from pathlib import Path

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
from opencare.engines.fsutil import iter_files

register_defaults({"shortcuts.categories": {}})

LOCATIONS = [
    ("desktop", "desktop", "Desktop"),
    ("public_desktop", "public_desktop", "Public Desktop"),
    ("startmenu_user", "startmenu_user", "Start Menu"),
    ("startmenu_common", "startmenu_common", "Start Menu (all users)"),
    ("recent", "recent", "Recent items"),
]


@register
class ShortcutScanner(Scanner):
    id = "shortcuts"
    title = "Shortcuts"
    description = "Remove shortcuts whose target no longer exists."
    icon = "link"
    order = 40
    categories = [
        Category("broken", "Broken shortcuts", "Shortcuts pointing to files or programs that are gone.", Risk.LOW, True),
    ]

    def scan(self, ctx: ScanContext) -> ScanResult:
        def body(res: ScanResult):
            if "broken" not in self.runnable_categories(ctx, res):
                return
            from opencare.core.shell import resolve_shortcut

            broken_by_loc: dict[str, list[tuple[str, str]]] = {}
            locs = LOCATIONS
            for n, (key, folder, label) in enumerate(locs):
                if ctx.cancelled():
                    return
                ctx.progress(n / len(locs), f"Checking {label}")
                root = ctx.env.known.get(folder)
                for hit in iter_files(root, patterns=("*.lnk",), cancelled=ctx.cancelled):
                    if ctx.settings.is_excluded(hit.path):
                        continue
                    info = resolve_shortcut(hit.path)
                    if info is None:
                        continue
                    target = info.get("target", "")
                    if self._is_broken(target):
                        broken_by_loc.setdefault(label, []).append((hit.path, target))
            for label, items in broken_by_loc.items():
                for path, target in items:
                    name = Path(path).stem
                    res.issues.append(Issue(
                        id=f"shortcuts:broken:{path.lower()}", scanner=self.id, category="broken",
                        title=name, detail=f"{label} · target missing: {target}", path=path, risk=Risk.LOW,
                        payload={"kind": "lnk", "path": path, "target": target},
                    ))

        return self.timed_scan(ctx, body)

    @staticmethod
    def _is_broken(target: str) -> bool:
        if not target:
            return False
        low = target.lower()
        if low.startswith(("http://", "https://", "ftp://", "\\\\", "shell:", "steam:")):
            return False
        if "://" in low:
            return False
        try:
            return not Path(target).exists()
        except OSError:
            return False

    def fix(self, issues, ctx: FixContext) -> FixReport:
        report = FixReport(self.id)
        total = len(issues)
        for n, issue in enumerate(issues):
            if ctx.cancelled():
                break
            ctx.progress(n / max(1, total), issue.title)
            path = issue.payload["path"]
            if ctx.dry_run:
                report.fixed += 1
                continue
            try:
                if Path(path).exists():
                    ctx.changes.quarantine_file(path)
                report.fixed += 1
            except OSError as e:
                report.failed += 1
                report.errors.append(str(e))
        ctx.changes.items += report.fixed
        return report
