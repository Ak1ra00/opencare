"""Human-friendly formatting."""
from __future__ import annotations

import datetime as _dt


def human_bytes(n: int | float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}" if abs(n) < 100 else f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} TB"


def human_count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n:,} {singular if n == 1 else (plural or singular + 's')}"


def human_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m} min {s} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"


def relative_time(when: _dt.datetime | str | None, now: _dt.datetime | None = None) -> str:
    if not when:
        return "never"
    if isinstance(when, str):
        try:
            when = _dt.datetime.fromisoformat(when)
        except ValueError:
            return when
    now = now or _dt.datetime.now()
    delta = now - when
    secs = delta.total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    days = delta.days
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    return when.strftime("%d %b %Y")


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()
