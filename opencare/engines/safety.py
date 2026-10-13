"""Guardrails: paths and registry locations OpenCare must never clean or modify.

These are deliberately broad. A cleaner should rather keep junk than risk a system file.
"""
from __future__ import annotations

import os
from pathlib import Path

# Absolute path prefixes that are never deletion targets.
_PROTECTED_PREFIXES = (
    r"c:\windows\system32",
    r"c:\windows\syswow64",
    r"c:\windows\winsxs",
    r"c:\windows\servicing",
    r"c:\windows\fonts",
    r"c:\windows\boot",
    r"c:\windows\system",
    r"c:\program files\windowsapps",
    r"c:\$recycle.bin",  # handled via the shell API, never by file walk
    r"c:\system volume information",
)

# Filenames that must never be deleted even if they match a junk pattern.
_PROTECTED_NAMES = {
    "ntuser.dat", "desktop.ini", "bootmgr", "pagefile.sys", "hiberfil.sys", "swapfile.sys",
}

# Registry key prefixes that must never be deleted (only specific values are ever touched).
_PROTECTED_REG_PREFIXES = (
    r"hklm\system\currentcontrolset\services",
    r"hklm\system\currentcontrolset\control",
    r"hklm\security",
    r"hklm\sam",
)


def _norm(path: str) -> str:
    try:
        return os.path.normpath(path).lower().replace("/", "\\")
    except (OSError, ValueError):
        return path.lower()


def is_protected_path(path: str) -> bool:
    n = _norm(path)
    name = Path(n).name
    if name in _PROTECTED_NAMES:
        return True
    windir = _norm(os.environ.get("SystemRoot", r"C:\Windows"))
    # anything directly inside %WINDIR% root but not a known-safe subfolder is protected
    for prefix in _PROTECTED_PREFIXES:
        if n == prefix or n.startswith(prefix + "\\"):
            return True
    # the WINDIR root itself (files sitting directly in C:\Windows)
    if os.path.dirname(n) == windir:
        return True
    return False


def is_protected_registry(key_path: str) -> bool:
    n = key_path.lower().replace("/", "\\").replace("hkey_local_machine", "hklm").replace("hkey_current_user", "hkcu")
    return any(n == p or n.startswith(p + "\\") for p in _PROTECTED_REG_PREFIXES)


def is_signed_microsoft_service(_name: str) -> bool:  # placeholder hook; startup engine fills this in
    return False
