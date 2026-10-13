"""Large-file finder: list the biggest files under a chosen folder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from opencare.engines.fsutil import iter_files


@dataclass
class LargeFile:
    path: str
    size: int
    mtime: float


def find_large_files(root: str, min_mb: float = 100, limit: int = 200,
                     cancelled=lambda: False, progress=lambda f, t="": None) -> list[LargeFile]:
    min_bytes = int(min_mb * 1024 * 1024)
    hits: list[LargeFile] = []
    scanned = 0
    for hit in iter_files(Path(root), cancelled=cancelled):
        scanned += 1
        if scanned % 2000 == 0:
            progress(0.0, f"Scanned {scanned:,} files")
        if hit.size >= min_bytes:
            hits.append(LargeFile(hit.path, hit.size, hit.mtime))
    hits.sort(key=lambda h: h.size, reverse=True)
    return hits[:limit]
