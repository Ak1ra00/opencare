"""Performance optimization: a catalog of reversible Windows tweaks, plus performance
modes and a memory-trim action. This is not a Scanner (it has no scan/fix issue flow);
the Optimize page drives it directly.

Every tweak is a registry value with a known "optimized" and "default" state. Applying a
tweak records the previous value into a ChangeSet, so it is individually reversible. We
never apply anything automatically — the user picks tweaks and clicks Apply.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from opencare.core.changes import ChangeSet
from opencare.core.env import Environment
from opencare.engines.base import Risk


@dataclass
class Tweak:
    id: str
    title: str
    description: str
    category: str                       # "performance" | "responsiveness" | "privacy" | "visual"
    path: str
    name: str
    optimized_value: int
    value_type: Literal["dword"] = "dword"
    requires_admin: bool = False
    requires_restart: bool = False
    risk: Risk = Risk.LOW
    note: str = ""


TWEAKS: list[Tweak] = [
    Tweak("menu_show_delay", "Faster menu display",
          "Reduce the delay before menus open (0 ms instead of 400 ms).",
          "responsiveness", r"HKCU\Control Panel\Desktop", "MenuShowDelay", 0, note="Sets the delay to 0."),
    Tweak("low_level_hooks_timeout", "Close unresponsive apps faster",
          "Lower the time Windows waits before considering a hung app closeable.",
          "responsiveness", r"HKCU\Control Panel\Desktop", "LowLevelHooksTimeout", 1000),
    Tweak("hung_app_timeout", "Shorter hung-app wait",
          "Reduce how long Windows waits on a non-responding application.",
          "responsiveness", r"HKCU\Control Panel\Desktop", "HungAppTimeout", 4000),
    Tweak("taskbar_animations", "Disable taskbar animations",
          "Turn off taskbar animation effects for snappier response.",
          "visual", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarAnimations", 0),
    Tweak("startup_delay", "Remove startup app delay",
          "Skip the artificial delay Windows adds before launching startup apps.",
          "performance", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize", "StartupDelayInMSec", 0),
    Tweak("show_file_ext", "Show file extensions",
          "Always show file name extensions in Explorer.",
          "privacy", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "HideFileExt", 0),
    Tweak("verbose_shutdown", "Verbose startup/shutdown status",
          "Show detailed status messages during startup and shutdown.",
          "performance", r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "VerboseStatus", 1, requires_admin=True),
    Tweak("disable_tips", "Disable Windows tips & suggestions",
          "Stop Windows showing tips, tricks and suggestions notifications.",
          "privacy", r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338389Enabled", 0),
    Tweak("disable_telemetry_min", "Minimise diagnostic data",
          "Set diagnostic data collection to the lowest level your edition allows.",
          "privacy", r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0, requires_admin=True),
]


def current_state(env: Environment, tweak: Tweak) -> bool | None:
    """True if already at optimized value, False if not, None if unreadable."""
    v = env.reg.get_value(tweak.path, tweak.name)
    if v is None:
        return False
    try:
        return int(v.value) == tweak.optimized_value
    except (TypeError, ValueError):
        return None


def apply_tweak(env: Environment, tweak: Tweak, changes: ChangeSet) -> bool:
    import winreg

    old = env.reg.get_value(tweak.path, tweak.name)
    try:
        changes.record_tweak(tweak.id, tweak.path, tweak.name, old)
        env.reg.set_value(tweak.path, tweak.name, tweak.optimized_value, winreg.REG_DWORD)
        return True
    except OSError:
        return False


def trim_working_sets(limit: int = 200) -> tuple[int, int]:
    """Ask Windows to trim the working set of accessible processes (a gentle RAM cleanup).

    Returns (trimmed, freed_estimate_bytes). Best-effort; skips processes we can't open.
    """
    import ctypes

    try:
        import psutil
    except ImportError:
        return 0, 0
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_QUERY_LIMITED = 0x1000
    trimmed = 0
    freed = 0
    own = __import__("os").getpid()
    for proc in psutil.process_iter(["pid", "name"]):
        pid = proc.info["pid"]
        if pid in (0, 4) or pid == own:
            continue
        if trimmed >= limit:
            break
        h = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            continue
        try:
            before = _working_set(psapi, h)
            if psapi.EmptyWorkingSet(h):
                after = _working_set(psapi, h)
                if before and after and before > after:
                    freed += before - after
                trimmed += 1
        finally:
            kernel32.CloseHandle(h)
    return trimmed, freed


def _working_set(psapi, handle) -> int:
    import ctypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint), ("PageFaultCount", ctypes.c_uint),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return int(pmc.WorkingSetSize)
    return 0
