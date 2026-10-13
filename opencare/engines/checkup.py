"""Checkup orchestrator — runs scanners, aggregates results, scores system health, and
applies fixes inside a single undoable change set.

A health score (0-100) is derived from how many issues and how much reclaimable space
each scanner found, weighted by severity. It is a heuristic summary, not a precise metric.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from opencare.core.changes import ChangeSet, ChangeStore
from opencare.core.env import Environment
from opencare.core.fmt import now_iso
from opencare.core.settings import Settings, get_settings
from opencare.engines.base import (
    FixContext,
    FixReport,
    Issue,
    Risk,
    ScanContext,
    ScanResult,
    Scanner,
    all_scanners,
)

# How many "score points" each scanner's problems can subtract, at most.
SCANNER_WEIGHT = {
    "security": 34, "registry": 16, "startup": 14, "junk": 14, "privacy": 12, "shortcuts": 10,
}
RISK_PENALTY = {Risk.LOW: 1.0, Risk.MEDIUM: 2.0, Risk.HIGH: 3.5}


@dataclass
class CheckupResult:
    results: dict[str, ScanResult] = field(default_factory=dict)
    score: int = 100
    started: str = ""
    finished: str = ""
    cancelled: bool = False

    @property
    def all_issues(self) -> list[Issue]:
        out: list[Issue] = []
        for r in self.results.values():
            out.extend(r.issues)
        return out

    @property
    def total_issues(self) -> int:
        return sum(len(r.issues) for r in self.results.values())

    @property
    def total_reclaimable(self) -> int:
        return sum(r.total_size for r in self.results.values())

    def issues_for(self, scanner_id: str) -> list[Issue]:
        r = self.results.get(scanner_id)
        return r.issues if r else []


def compute_score(results: dict[str, ScanResult]) -> int:
    score = 100.0
    for sid, result in results.items():
        weight = SCANNER_WEIGHT.get(sid, 8)
        if not result.issues:
            continue
        # saturating penalty: more/worse issues cost more but can't exceed the weight
        severity = sum(RISK_PENALTY.get(i.risk, 1.0) for i in result.issues)
        # junk is scored partly by size (1 point per 2 GB, capped)
        if sid == "junk":
            severity += min(6.0, result.total_size / (2 * 1024**3))
        penalty = weight * (1 - 1 / (1 + severity / 6))
        score -= penalty
    return max(1, min(100, round(score)))


def score_band(score: int) -> tuple[str, str]:
    """(label, theme token)."""
    if score >= 85:
        return "Excellent", "success"
    if score >= 65:
        return "Good", "accent"
    if score >= 40:
        return "Needs attention", "warning"
    return "At risk", "danger"


class Checkup:
    def __init__(self, env: Environment | None = None, settings: Settings | None = None,
                 store: ChangeStore | None = None):
        self.env = env or Environment.real()
        self.settings = settings or get_settings()
        self.store = store or ChangeStore(self.env)

    def selected_scanners(self) -> list[Scanner]:
        enabled = self.settings["checkup.scanners"] or {}
        return [s for s in all_scanners() if enabled.get(s.id, True)]

    def run(self, progress=None, cancelled=lambda: False, scanners=None) -> CheckupResult:
        scanners = scanners if scanners is not None else self.selected_scanners()
        out = CheckupResult(started=now_iso())
        n = len(scanners)
        for i, scanner in enumerate(scanners):
            if cancelled():
                out.cancelled = True
                break

            def sub_progress(frac, text, _i=i, _s=scanner):
                if progress:
                    progress((_i + frac) / max(1, n), f"{_s.title}: {text}" if text else _s.title)

            ctx = ScanContext(
                env=self.env, settings=self.settings,
                categories=scanner.enabled_categories(self.settings),
                progress=sub_progress, cancelled=cancelled,
            )
            out.results[scanner.id] = scanner.scan(ctx)
        out.finished = now_iso()
        out.score = compute_score(out.results)
        return out

    def fix(self, issues: list[Issue], title: str = "Checkup fixes",
            progress=None, cancelled=lambda: False, dry_run=False) -> tuple[ChangeSet, dict[str, FixReport]]:
        """Apply the given issues, grouped by scanner, inside one change set."""
        by_scanner: dict[str, list[Issue]] = {}
        for issue in issues:
            by_scanner.setdefault(issue.scanner, []).append(issue)
        cs = self.store.new_change_set(title)
        reports: dict[str, FixReport] = {}
        scanners = {s.id: s for s in all_scanners()}
        total = sum(len(v) for v in by_scanner.values()) or 1
        done = 0
        for sid, items in by_scanner.items():
            if cancelled():
                break
            scanner = scanners.get(sid)
            if not scanner:
                continue

            def sub_progress(frac, text, _done=done, _n=len(items)):
                if progress:
                    progress((_done + frac * _n) / total, text)

            fctx = FixContext(env=self.env, settings=self.settings, changes=cs,
                              progress=sub_progress, cancelled=cancelled, dry_run=dry_run)
            reports[sid] = scanner.fix(items, fctx)
            done += len(items)
        if not dry_run and not cs.is_empty:
            cs.save()
            self._update_stats(reports)
        return cs, reports

    def _update_stats(self, reports: dict[str, FixReport]):
        bytes_freed = sum(r.bytes_freed for r in reports.values())
        fixed = sum(r.fixed for r in reports.values())
        self.settings["stats.bytes_freed"] = (self.settings["stats.bytes_freed"] or 0) + bytes_freed
        self.settings["stats.items_fixed"] = (self.settings["stats.items_fixed"] or 0) + fixed

    def record_checkup(self, result: CheckupResult):
        self.settings["checkup.last_run"] = result.finished or now_iso()
        self.settings["checkup.last_summary"] = {
            "score": result.score,
            "issues": result.total_issues,
            "reclaimable": result.total_reclaimable,
            "per_scanner": {sid: len(r.issues) for sid, r in result.results.items()},
        }
        self.settings["stats.checkups"] = (self.settings["stats.checkups"] or 0) + 1
