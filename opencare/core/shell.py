"""Windows shell helpers: shortcut resolution, recycle bin, open-in-explorer."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from opencare.core.admin import run_hidden

log = logging.getLogger(__name__)


def resolve_shortcut(lnk_path: str) -> dict | None:
    """Return {target, args, working_dir, icon} for a .lnk, or None if unreadable."""
    try:
        import pythoncom  # type: ignore
        from win32com.shell import shell  # type: ignore

        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLinkW)
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(lnk_path)
        target, _ = link.GetPath(shell.SLGP_RAWPATH)
        icon, _ = link.GetIconLocation()
        return {
            "target": os.path.expandvars(target or ""),
            "args": link.GetArguments(),
            "working_dir": os.path.expandvars(link.GetWorkingDirectory() or ""),
            "icon": os.path.expandvars(icon or ""),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("resolve_shortcut failed for %s: %s", lnk_path, e)
        return None


def send_to_recycle_bin(path: str) -> bool:
    try:
        from win32com.shell import shell, shellcon  # type: ignore

        flags = shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI
        res = shell.SHFileOperation((0, shellcon.FO_DELETE, path + "\0", None, flags, None, None))
        return res[0] == 0
    except Exception as e:  # noqa: BLE001
        log.warning("recycle-bin delete failed for %s: %s", path, e)
        return False


def open_in_explorer(path: str) -> None:
    p = Path(path)
    if p.exists() and p.is_file():
        run_hidden(["explorer.exe", "/select,", str(p)], timeout=10)
    elif p.exists():
        os.startfile(str(p))  # noqa: S606 - user-initiated open
    elif p.parent.exists():
        os.startfile(str(p.parent))  # noqa: S606


def open_registry_at(key_path: str) -> None:
    """Open regedit focused on a key (writes LastKey under the current user)."""
    try:
        import winreg

        last = key_path.replace("HKLM", "HKEY_LOCAL_MACHINE").replace("HKCU", "HKEY_CURRENT_USER")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Applets\Regedit") as k:
            winreg.SetValueEx(k, "LastKey", 0, winreg.REG_SZ, "Computer\\" + last)
        run_hidden(["regedit.exe"], timeout=5)
    except Exception as e:  # noqa: BLE001
        log.warning("open regedit failed: %s", e)
