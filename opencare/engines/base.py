"""Engine contract shared by every scanner (see ARCHITECTURE.md)."""
from __future__ import annotations

import enum
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from opencare.core.changes import ChangeSet
from opencare.core.env import Environment
from opencare.core.settings import Settings

log = logging.getLogger(__name__)


class Risk(str, enum.Enum):
    LOW = "low"        # safe to remove, nothing user-visible changes
    MEDIUM = "medium"  # usually safe; may reset a preference, sign-in or cache
    HIGH = "high"      # can affect apps; off by default, backed up


@dataclass
class Category:
    id: str
    title: str
    description: str
    risk: Risk = Risk.LOW
    default_on: bool = True
    requires_admin: bool = False


@dataclass
class Issue:
    id: str                     # unique & stable: "<scanner>:<category>:<identity>"
    scanner: str
    category: str
    title: str
    detail: str = ""
    size: int = 0               # bytes reclaimed by fixing (0 if n/a)
    count: int = 1              # underlying items represented
    path: str | None = None     # file path or registry path (for "open location")
    risk: Risk = Risk.LOW
    selected: bool = True
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    scanner: str
    issues: list[Issue] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_categories: list[str] = field(default_factory=list)  # e.g. need admin
    duration: float = 0.0
    cancelled: bool = False

    @property
    def total_size(self) -> int:
        return sum(i.size for i in self.issues)

    @property
    def total_count(self) -> int:
        return sum(i.count for i in self.issues)

    def by_category(self) -> dict[str, list[Issue]]:
        out: dict[str, list[Issue]] = {}
        for i in self.issues:
            out.setdefault(i.category, []).append(i)
        return out


@dataclass
class FixReport:
    scanner: str
    fixed: int = 0
    failed: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)


Progress = Callable[[float, str], None]


@dataclass
class ScanContext:
    env: Environment
    settings: Settings
    categories: set[str]
    progress: Progress = lambda f, t="": None
    cancelled: Callable[[], bool] = lambda: False


@dataclass
class FixContext:
    env: Environment
    settings: Settings
    changes: ChangeSet
    progress: Progress = lambda f, t="": None
    cancelled: Callable[[], bool] = lambda: False
    dry_run: bool = False


class Scanner(ABC):
    id: str = ""
    title: str = ""
    description: str = ""
    icon: str = "sparkle"
    order: int = 100
    categories: list[Category] = []

    def category(self, cid: str) -> Category:
        for c in self.categories:
            if c.id == cid:
                return c
        raise KeyError(cid)

    def default_categories(self) -> set[str]:
        return {c.id for c in self.categories if c.default_on}

    def enabled_categories(self, settings: Settings) -> set[str]:
        """Categories enabled in settings (key '<id>.categories'), else defaults."""
        chosen = settings.get(f"{self.id}.categories")
        if isinstance(chosen, dict):
            return {c.id for c in self.categories if chosen.get(c.id, c.default_on)}
        return self.default_categories()

    def runnable_categories(self, ctx: ScanContext, result: ScanResult) -> set[str]:
        """Filter ctx.categories by admin requirement; records skipped ones."""
        out = set()
        for c in self.categories:
            if c.id not in ctx.categories:
                continue
            if c.requires_admin and not ctx.env.is_admin:
                result.skipped_categories.append(c.id)
                continue
            out.add(c.id)
        return out

    @abstractmethod
    def scan(self, ctx: ScanContext) -> ScanResult: ...

    @abstractmethod
    def fix(self, issues: list[Issue], ctx: FixContext) -> FixReport: ...

    # helper for subclasses
    def timed_scan(self, ctx: ScanContext, body: Callable[[ScanResult], None]) -> ScanResult:
        res = ScanResult(scanner=self.id)
        t0 = time.perf_counter()
        try:
            body(res)
        except Exception as e:  # noqa: BLE001 - scanners must not crash the checkup
            log.exception("%s scan failed", self.id)
            res.errors.append(f"{type(e).__name__}: {e}")
        res.cancelled = ctx.cancelled()
        res.issues = [i for i in res.issues if not ctx.settings.is_ignored(i.id)]
        res.duration = time.perf_counter() - t0
        return res


_REGISTRY: dict[str, Scanner] = {}


def register(cls: type[Scanner]) -> type[Scanner]:
    inst = cls()
    _REGISTRY[inst.id] = inst
    return cls


def all_scanners() -> list[Scanner]:
    # import engine modules so they self-register
    import importlib

    for mod in ("junk", "privacy", "registry_clean", "shortcuts", "startup", "security"):
        try:
            importlib.import_module(f"opencare.engines.{mod}")
        except ImportError as e:
            log.debug("engine %s unavailable: %s", mod, e)
    return sorted(_REGISTRY.values(), key=lambda s: s.order)


def get_scanner(scanner_id: str) -> Scanner:
    all_scanners()
    return _REGISTRY[scanner_id]
