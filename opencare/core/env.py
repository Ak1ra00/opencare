"""The single seam between engines and the operating system.

Engines never import winreg / os environment directly; they take an ``Environment`` and
go through ``env.reg`` (registry) and ``env.known`` (folders). Tests pass a sandboxed
Environment whose registry lives under HKCU\\Software\\OpenCareTest\\<uuid> and whose
folders are temp dirs, so a test run can never modify the real machine.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - non-Windows dev
    winreg = None  # type: ignore

HKEY_NAMES = {}
if winreg:
    HKEY_NAMES = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKU": winreg.HKEY_USERS,
        "HKEY_USERS": winreg.HKEY_USERS,
    }


@dataclass
class RegValue:
    name: str
    value: object
    type: int


def split_root(path: str) -> tuple[str, str]:
    path = path.replace("/", "\\").lstrip("\\")
    root, _, rest = path.partition("\\")
    return root.upper(), rest


class RegistryAdapter:
    """Thin wrapper over winreg with a WOW64 view and read/enumerate/delete helpers."""

    def __init__(self, wow64_32: bool = False):
        self._wow = (winreg.KEY_WOW64_32KEY if winreg else 0) if wow64_32 else (winreg.KEY_WOW64_64KEY if winreg else 0)

    def _root(self, root: str) -> int:
        if root not in HKEY_NAMES:
            raise KeyError(f"unknown registry root {root!r}")
        return HKEY_NAMES[root]

    def open(self, path: str, write: bool = False):
        root, sub = split_root(path)
        access = (winreg.KEY_READ | (winreg.KEY_WRITE if write else 0)) | self._wow
        return winreg.OpenKey(self._root(root), sub, 0, access)

    def exists(self, path: str) -> bool:
        try:
            with self.open(path):
                return True
        except OSError:
            return False

    def subkeys(self, path: str) -> list[str]:
        out: list[str] = []
        try:
            with self.open(path) as k:
                i = 0
                while True:
                    try:
                        out.append(winreg.EnumKey(k, i))
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
        return out

    def values(self, path: str) -> list[RegValue]:
        out: list[RegValue] = []
        try:
            with self.open(path) as k:
                i = 0
                while True:
                    try:
                        name, value, vtype = winreg.EnumValue(k, i)
                        out.append(RegValue(name, value, vtype))
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
        return out

    def get_value(self, path: str, name: str) -> RegValue | None:
        try:
            with self.open(path) as k:
                value, vtype = winreg.QueryValueEx(k, name)
                return RegValue(name, value, vtype)
        except OSError:
            return None

    def set_value(self, path: str, name: str, value, vtype: int | None = None) -> None:
        root, sub = split_root(path)
        if vtype is None:
            vtype = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
        key = winreg.CreateKeyEx(self._root(root), sub, 0, winreg.KEY_WRITE | self._wow)
        with key:
            winreg.SetValueEx(key, name, 0, vtype, value)

    def delete_value(self, path: str, name: str) -> None:
        with self.open(path, write=True) as k:
            winreg.DeleteValue(k, name)

    def create_key(self, path: str) -> None:
        root, sub = split_root(path)
        winreg.CreateKeyEx(self._root(root), sub, 0, winreg.KEY_WRITE | self._wow).Close()

    def delete_tree(self, path: str) -> None:
        """Recursively delete a key and all children."""
        for child in self.subkeys(path):
            self.delete_tree(path + "\\" + child)
        root, sub = split_root(path)
        try:
            winreg.DeleteKeyEx(self._root(root), sub, self._wow, 0)
        except (OSError, NotImplementedError):
            with winreg.OpenKey(self._root(root), "", 0, winreg.KEY_WRITE | self._wow) as parent:
                winreg.DeleteKey(parent, sub)

    def walk(self, path: str) -> Iterator[str]:
        yield path
        for child in self.subkeys(path):
            yield from self.walk(path + "\\" + child)


class SandboxRegistryAdapter(RegistryAdapter):
    """Maps every hive (HKLM/HKCU/HKU/HKCR) under HKCU\\Software\\OpenCareTest\\<id>\\<HIVE>.

    Engines keep using logical paths like ``HKLM\\SOFTWARE\\...``; nothing outside the
    sandbox key can be read or written. ``destroy()`` removes the whole sandbox.
    """

    BASE = r"Software\OpenCareTest"

    def __init__(self, sandbox_id: str):
        super().__init__()
        self.sandbox_id = sandbox_id
        self._base = f"{self.BASE}\\{sandbox_id}"

    def _map(self, path: str) -> tuple[int, str]:
        root, sub = split_root(path)
        canon = {"HKEY_LOCAL_MACHINE": "HKLM", "HKEY_CURRENT_USER": "HKCU", "HKEY_USERS": "HKU", "HKEY_CLASSES_ROOT": "HKCR"}.get(root, root)
        if canon not in ("HKLM", "HKCU", "HKU", "HKCR"):
            raise KeyError(f"unknown registry root {root!r}")
        mapped = f"{self._base}\\{canon}" + (f"\\{sub}" if sub else "")
        return winreg.HKEY_CURRENT_USER, mapped

    def open(self, path: str, write: bool = False):
        hive, sub = self._map(path)
        return winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | (winreg.KEY_WRITE if write else 0))

    def set_value(self, path: str, name: str, value, vtype: int | None = None) -> None:
        hive, sub = self._map(path)
        if vtype is None:
            vtype = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
        with winreg.CreateKeyEx(hive, sub, 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, name, 0, vtype, value)

    def create_key(self, path: str) -> None:
        hive, sub = self._map(path)
        winreg.CreateKeyEx(hive, sub, 0, winreg.KEY_WRITE).Close()

    def delete_tree(self, path: str) -> None:
        for child in self.subkeys(path):
            self.delete_tree(path + "\\" + child)
        hive, sub = self._map(path)
        winreg.DeleteKey(hive, sub)

    def destroy(self) -> None:
        def rm(sub: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_READ) as k:
                    children = []
                    i = 0
                    while True:
                        try:
                            children.append(winreg.EnumKey(k, i))
                            i += 1
                        except OSError:
                            break
            except OSError:
                return
            for c in children:
                rm(sub + "\\" + c)
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass

        rm(self._base)


class KnownFolders:
    """Resolve common Windows locations; overridable per-folder for the sandbox."""

    def __init__(self, overrides: dict[str, Path] | None = None):
        self._ov = {k: Path(v) for k, v in (overrides or {}).items()}

    def _env(self, name: str, fallback: str) -> Path:
        return Path(os.environ.get(name, fallback))

    def get(self, key: str) -> Path:
        if key in self._ov:
            return self._ov[key]
        home = Path.home()
        table = {
            "home": home,
            "temp": Path(os.environ.get("TEMP", home / "AppData/Local/Temp")),
            "localappdata": self._env("LOCALAPPDATA", str(home / "AppData/Local")),
            "appdata": self._env("APPDATA", str(home / "AppData/Roaming")),
            "windows": self._env("SystemRoot", "C:/Windows"),
            "systemdrive": Path(os.environ.get("SystemDrive", "C:") + "\\"),
            "prefetch": Path(os.environ.get("SystemRoot", "C:/Windows")) / "Prefetch",
            "recent": self._env("APPDATA", str(home / "AppData/Roaming")) / "Microsoft/Windows/Recent",
            "startmenu_user": self._env("APPDATA", str(home / "AppData/Roaming")) / "Microsoft/Windows/Start Menu",
            "startmenu_common": Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows/Start Menu",
            "desktop": home / "Desktop",
            "downloads": home / "Downloads",
            "programdata": Path(os.environ.get("ProgramData", "C:/ProgramData")),
            "programfiles": Path(os.environ.get("ProgramFiles", "C:/Program Files")),
            "programfiles_x86": Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
            "public_desktop": Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop",
        }
        return table.get(key, home / key)

    def windows_temp(self) -> Path:
        return self.get("windows") / "Temp"


@dataclass
class Environment:
    reg: RegistryAdapter = field(default_factory=RegistryAdapter)
    reg32: RegistryAdapter = field(default_factory=lambda: RegistryAdapter(wow64_32=True))
    known: KnownFolders = field(default_factory=KnownFolders)
    is_admin: bool = False
    sandbox: bool = False
    hkcu_root: str = "HKCU"  # sandbox remaps user-hive writes under here

    @classmethod
    def real(cls) -> "Environment":
        from opencare.core.admin import is_admin

        return cls(is_admin=is_admin())

    @classmethod
    def sandboxed(cls, root: Path, sandbox_id: str, is_admin: bool = True) -> "Environment":
        """Temp-folder + sandbox-registry environment for tests and dry runs.

        Every known folder resolves inside ``root`` (created on demand).
        """
        names = ["home", "temp", "localappdata", "appdata", "windows", "systemdrive", "prefetch", "recent",
                 "startmenu_user", "startmenu_common", "desktop", "downloads", "programdata", "programfiles"]
        overrides = {n: root / n for n in names}
        overrides["recent"] = root / "appdata/Microsoft/Windows/Recent"
        overrides["prefetch"] = root / "windows/Prefetch"
        for p in overrides.values():
            p.mkdir(parents=True, exist_ok=True)
        reg = SandboxRegistryAdapter(sandbox_id)
        return cls(reg=reg, reg32=reg, known=KnownFolders(overrides), is_admin=is_admin, sandbox=True)
