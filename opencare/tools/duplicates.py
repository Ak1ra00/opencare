"""Duplicate-file finder: group identical files by size then content hash."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from opencare.engines.fsutil import iter_files


@dataclass
class DuplicateGroup:
    hash: str
    size: int
    paths: list[str] = field(default_factory=list)

    @property
    def wasted(self) -> int:
        return self.size * max(0, len(self.paths) - 1)


def _hash_file(path: str, chunk: int = 1 << 20, partial: bool = False) -> str | None:
    h = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb") as f:
            if partial:
                h.update(f.read(chunk))
            else:
                while True:
                    block = f.read(chunk)
                    if not block:
                        break
                    h.update(block)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def find_duplicates(root: str, min_bytes: int = 1024, cancelled=lambda: False,
                    progress=lambda f, t="": None) -> list[DuplicateGroup]:
    by_size: dict[int, list[str]] = defaultdict(list)
    for hit in iter_files(Path(root), cancelled=cancelled):
        if hit.size >= min_bytes:
            by_size[hit.size].append(hit.path)

    candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}
    groups: list[DuplicateGroup] = []
    total = len(candidates) or 1
    for n, (size, paths) in enumerate(candidates.items()):
        if cancelled():
            break
        progress(n / total, f"Comparing {len(paths)} files of {size:,} bytes")
        # stage 1: partial hash to prune
        by_partial: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            ph = _hash_file(p, partial=True)
            if ph:
                by_partial[ph].append(p)
        for part_paths in by_partial.values():
            if len(part_paths) < 2:
                continue
            by_full: dict[str, list[str]] = defaultdict(list)
            for p in part_paths:
                fh = _hash_file(p)
                if fh:
                    by_full[fh].append(p)
            for fh, dup_paths in by_full.items():
                if len(dup_paths) > 1:
                    groups.append(DuplicateGroup(fh, size, dup_paths))
    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups
