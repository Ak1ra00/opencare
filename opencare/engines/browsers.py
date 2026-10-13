"""Detect installed browsers and enumerate their per-profile trace files.

Chromium family (Chrome, Edge, Brave, Opera, Vivaldi, …) and Firefox family share a
small set of well-known relative file/dir names per profile. We only ever target cache,
history, cookies and download-history artifacts — never "Login Data" (passwords) or
"Web Data" autofill, which OpenCare leaves alone by policy.
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

from opencare.core.env import Environment


@dataclass
class BrowserProfile:
    browser: str
    profile: str
    path: Path


@dataclass
class TraceSpec:
    trace: str                       # logical trace id: cache|history|cookies|downloads|sessions
    relpaths: tuple[str, ...]        # files or dirs relative to the profile
    is_dir: bool = False


# Chromium: trace -> relative artifacts. "History" holds both browsing and download history;
# we treat it as history (deleting it clears both). Cache dirs are safe to wipe wholesale.
CHROMIUM_TRACES = [
    TraceSpec("cache", ("Cache", "Code Cache", "GPUCache", "Service Worker/CacheStorage"), is_dir=True),
    TraceSpec("history", ("History", "History-journal", "Visited Links", "Top Sites", "Network Action Predictor"),),
    TraceSpec("cookies", ("Network/Cookies", "Network/Cookies-journal", "Cookies", "Cookies-journal"),),
    TraceSpec("sessions", ("Sessions", "Session Storage"), is_dir=True),
]

FIREFOX_TRACES = [
    TraceSpec("cache", ("cache2",), is_dir=True),
    TraceSpec("history", ("places.sqlite", "places.sqlite-wal"),),
    TraceSpec("cookies", ("cookies.sqlite", "cookies.sqlite-wal"),),
    TraceSpec("sessions", ("sessionstore-backups",), is_dir=True),
]

# Chromium browsers: name -> localappdata relative "User Data" root
CHROMIUM_BROWSERS = {
    "Google Chrome": "Google/Chrome/User Data",
    "Microsoft Edge": "Microsoft/Edge/User Data",
    "Brave": "BraveSoftware/Brave-Browser/User Data",
    "Vivaldi": "Vivaldi/User Data",
    "Opera": "Opera Software/Opera Stable",
    "Opera GX": "Opera Software/Opera GX Stable",
    "Chromium": "Chromium/User Data",
}


@dataclass
class DetectedBrowser:
    name: str
    family: str  # chromium | firefox
    profiles: list[BrowserProfile] = field(default_factory=list)
    traces: list[TraceSpec] = field(default_factory=list)


def _chromium_profiles(root: Path) -> list[str]:
    if not root.exists():
        return []
    names = []
    for p in root.iterdir():
        if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile ")):
            if (p / "Preferences").exists() or (p / "History").exists():
                names.append(p.name)
    # Opera Stable stores the profile at the root itself
    if not names and (root / "History").exists():
        names.append(".")
    return names


def _firefox_profiles(env: Environment) -> list[BrowserProfile]:
    base = env.known.get("appdata") / "Mozilla/Firefox"
    ini = base / "profiles.ini"
    out: list[BrowserProfile] = []
    if not ini.exists():
        return out
    cp = configparser.ConfigParser()
    try:
        cp.read(ini, encoding="utf-8")
    except (OSError, configparser.Error):
        return out
    for section in cp.sections():
        if not section.lower().startswith("profile"):
            continue
        path = cp.get(section, "Path", fallback=None)
        if not path:
            continue
        is_rel = cp.get(section, "IsRelative", fallback="1") == "1"
        full = (base / path) if is_rel else Path(path)
        if full.exists():
            out.append(BrowserProfile("Mozilla Firefox", full.name, full))
    return out


def detect_browsers(env: Environment) -> list[DetectedBrowser]:
    found: list[DetectedBrowser] = []
    local = env.known.get("localappdata")
    roaming_cache = env.known.get("appdata")  # Opera uses roaming for some installs
    for name, rel in CHROMIUM_BROWSERS.items():
        for base in (local, roaming_cache):
            root = base / rel
            profiles = _chromium_profiles(root)
            if profiles:
                found.append(DetectedBrowser(
                    name=name, family="chromium",
                    profiles=[BrowserProfile(name, pr, (root if pr == "." else root / pr)) for pr in profiles],
                    traces=CHROMIUM_TRACES,
                ))
                break
    ff = _firefox_profiles(env)
    if ff:
        found.append(DetectedBrowser(name="Mozilla Firefox", family="firefox", profiles=ff, traces=FIREFOX_TRACES))
    return found
