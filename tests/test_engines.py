"""Tests for registry, shortcuts, startup and security engines (all sandboxed)."""
from pathlib import Path

from opencare.engines.base import FixContext, ScanContext


def _scan(scanner, env, settings, cats):
    return scanner.scan(ScanContext(env=env, settings=settings, categories=cats))


# ---------- registry ----------
def test_registry_app_path_missing(sandbox_env, settings, change_store):
    from opencare.engines.registry_clean import RegistryScanner

    reg = sandbox_env.reg
    good = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\good.exe"
    bad = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\gone.exe"
    exe = sandbox_env.known.get("localappdata") / "good.exe"
    exe.write_bytes(b"MZ")
    reg.set_value(good, "", str(exe))
    reg.set_value(bad, "", r"C:\nowhere\gone.exe")

    scanner = RegistryScanner()
    res = _scan(scanner, sandbox_env, settings, {"file_refs"})
    ids = [i.payload["path"] for i in res.issues]
    assert bad in ids and good not in ids

    cs = change_store.new_change_set("registry")
    scanner.fix(res.issues, FixContext(env=sandbox_env, settings=settings, changes=cs))
    cs.save()
    assert not reg.exists(bad)
    # undo recreates it
    change_store.restore(cs.id)
    assert reg.get_value(bad, "").value == r"C:\nowhere\gone.exe"


def test_registry_never_touches_protected(sandbox_env, settings, change_store):
    from opencare.engines.base import Issue
    from opencare.engines.registry_clean import RegistryScanner

    scanner = RegistryScanner()
    cs = change_store.new_change_set("registry")
    issue = Issue("registry:file_refs:x", "registry", "file_refs", "x",
                  payload={"kind": "reg_key", "path": r"HKLM\SYSTEM\CurrentControlSet\Services\Foo"})
    report = scanner.fix([issue], FixContext(env=sandbox_env, settings=settings, changes=cs))
    assert report.failed == 1 and report.fixed == 0


# ---------- shortcuts ----------
def test_shortcuts_broken_detection():
    from opencare.engines.shortcuts import ShortcutScanner

    assert ShortcutScanner._is_broken(r"C:\does\not\exist.exe")
    assert not ShortcutScanner._is_broken("https://example.com")
    assert not ShortcutScanner._is_broken("")
    assert not ShortcutScanner._is_broken(r"\\server\share\x")


# ---------- startup ----------
def test_startup_list_and_toggle(sandbox_env, settings, change_store):
    from opencare.engines import startup

    key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
    sandbox_env.reg.set_value(key, "MyApp", r"C:\app\my.exe")
    items = startup.list_items(sandbox_env)
    mine = [i for i in items if i.name == "MyApp"]
    assert mine and mine[0].enabled

    cs = change_store.new_change_set("startup")
    assert startup.set_enabled(sandbox_env, mine[0], False, cs)
    # moved to disabled backup key
    assert sandbox_env.reg.get_value(key, "MyApp") is None
    after = [i for i in startup.list_items(sandbox_env) if i.name == "MyApp"]
    assert after and not after[0].enabled

    cs.save()
    change_store.restore(cs.id)
    assert sandbox_env.reg.get_value(key, "MyApp").value == r"C:\app\my.exe"


def test_startup_scan_flags_missing_target(sandbox_env, settings):
    from opencare.engines.startup import StartupScanner

    key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    present = sandbox_env.known.get("localappdata") / "present.exe"
    present.write_bytes(b"MZ")
    sandbox_env.reg.set_value(key, "Good", f'"{present}"')
    sandbox_env.reg.set_value(key, "Bad", r'"C:\gone\bad.exe" --run')

    res = _scan(StartupScanner(), sandbox_env, settings, {"invalid"})
    names = {i.title for i in res.issues}
    assert "Bad" in names and "Good" not in names


# ---------- security ----------
def test_security_firewall_off(sandbox_env, settings):
    from opencare.engines.security import SecurityScanner

    base = r"HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"
    sandbox_env.reg.set_value(base + r"\StandardProfile", "EnableFirewall", 0)
    sandbox_env.reg.set_value(base + r"\PublicProfile", "EnableFirewall", 1)
    res = _scan(SecurityScanner(), sandbox_env, settings, {"firewall"})
    fw = [i for i in res.issues if i.category == "firewall"]
    assert fw and "Private" in fw[0].detail
    assert fw[0].payload["kind"] == "advisory"


def test_all_scanners_register():
    from opencare.engines.base import all_scanners

    ids = {s.id for s in all_scanners()}
    assert {"junk", "privacy", "registry", "shortcuts", "startup", "security"} <= ids
