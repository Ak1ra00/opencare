"""Recycle Bin size query and emptying via the Windows shell API."""
from __future__ import annotations

import ctypes
import logging

log = logging.getLogger(__name__)


class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]


def recycle_bin_stats() -> tuple[int, int]:
    """(total_bytes, item_count) across all drives. (0, 0) if unavailable."""
    try:
        info = _SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
        res = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if res != 0:
            return 0, 0
        return int(info.i64Size), int(info.i64NumItems)
    except (OSError, AttributeError) as e:
        log.debug("recycle bin query failed: %s", e)
        return 0, 0


def empty_recycle_bin(confirm: bool = False, progress_ui: bool = False, sound: bool = False) -> bool:
    SHERB_NOCONFIRMATION = 0x1
    SHERB_NOPROGRESSUI = 0x2
    SHERB_NOSOUND = 0x4
    flags = 0
    if not confirm:
        flags |= SHERB_NOCONFIRMATION
    if not progress_ui:
        flags |= SHERB_NOPROGRESSUI
    if not sound:
        flags |= SHERB_NOSOUND
    try:
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        return res == 0 or res == -2147418113  # S_OK or "already empty"
    except (OSError, AttributeError) as e:
        log.warning("empty recycle bin failed: %s", e)
        return False
