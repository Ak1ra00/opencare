"""Filesystem helpers shared by file-based scanners (junk, privacy, large files)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


@dataclass
class FileHit:
    path: str
    size: int
    mtime: float


def iter_files(
    root: Path,
    *,
    patterns: tuple[str, ...] | None = None,
    min_age_hours: float = 0.0,
    recursive: bool = True,
    cancelled: Callable[[], bool] = lambda: False,
    follow_symlinks: bool = False,
    skip_dirs: tuple[str, ...] = (),
    max_entries: int = 2_000_000,
) -> Iterator[FileHit]:
    """Yield files under ``root`` matching ``patterns`` and older than ``min_age_hours``.

    Robust against permission errors and reparse points; never raises for a bad entry.
    """
    if not root.exists():
        return
    now = time.time()
    cutoff = now - min_age_hours * 3600
    skip_lower = tuple(s.lower() for s in skip_dirs)
    seen = 0
    stack = [root]
    while stack:
        if cancelled():
            return
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    seen += 1
                    if seen > max_entries:
                        return
                    try:
                        if entry.is_dir(follow_symlinks=follow_symlinks):
                            if recursive and entry.name.lower() not in skip_lower:
                                stack.append(Path(entry.path))
                            continue
                        if not entry.is_file(follow_symlinks=follow_symlinks):
                            continue
                        if patterns and not _match_any(entry.name, patterns):
                            continue
                        st = entry.stat(follow_symlinks=follow_symlinks)
                        if min_age_hours and st.st_mtime > cutoff:
                            continue
                        yield FileHit(entry.path, st.st_size, st.st_mtime)
                    except (OSError, ValueError):
                        continue
        except (OSError, ValueError):
            continue


def _match_any(name: str, patterns: tuple[str, ...]) -> bool:
    import fnmatch

    low = name.lower()
    return any(fnmatch.fnmatch(low, p) for p in patterns)


def dir_size(path: Path, cancelled: Callable[[], bool] = lambda: False) -> tuple[int, int]:
    """Return (total_bytes, file_count) for a directory tree."""
    total = count = 0
    for hit in iter_files(path, cancelled=cancelled):
        total += hit.size
        count += 1
    return total, count


def delete_file(path: str, to_recycle: bool = False) -> bool:
    """Delete a file (optionally to the Recycle Bin). Returns True on success."""
    try:
        if to_recycle:
            from opencare.core.shell import send_to_recycle_bin

            if send_to_recycle_bin(path):
                return True
        p = Path(path)
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
        p.unlink()
        return True
    except (OSError, PermissionError):
        return False


def is_in_use(path: str) -> bool:
    """Best-effort check whether a file is locked by another process."""
    try:
        with open(path, "a"):
            return False
    except (PermissionError, OSError):
        return True
