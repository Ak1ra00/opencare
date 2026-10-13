"""Elevation helpers. OpenCare runs as invoker and elevates only on request."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    """Start an elevated copy of OpenCare (UAC prompt). Returns True if launched."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, list(sys.argv[1:])
    else:
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        params = ["-m", "opencare", *sys.argv[1:]]
    params += extra_args or []
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, subprocess.list2cmdline(params), os.getcwd(), 1)
    return rc > 32


NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def run_hidden(args: list[str], timeout: float = 20, **kw) -> subprocess.CompletedProcess:
    """Run a console tool without flashing a window; text output, never raises on exit code."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW, encoding="utf-8", errors="replace", **kw)


def powershell(script: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return run_hidden(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=timeout)
