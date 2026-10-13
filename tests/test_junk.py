import os
import time

from opencare.engines.base import FixContext, ScanContext
from opencare.engines.junk import JunkScanner
from opencare.engines.safety import is_protected_path


def _ctx(sandbox_env, settings, cats=None):
    scanner = JunkScanner()
    return scanner, ScanContext(
        env=sandbox_env, settings=settings,
        categories=cats or {"windows_temp", "system_cache", "crash_dumps", "leftover_temp"},
    )


def _age(path, hours):
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


def test_junk_scan_and_clean(sandbox_env, settings, change_store):
    settings["junk.min_age_hours"] = 24
    temp = sandbox_env.known.get("temp")
    (temp / "a.tmp").write_bytes(b"x" * 1000)
    (temp / "b.tmp").write_bytes(b"y" * 2000)
    _age(temp / "a.tmp", 48)
    _age(temp / "b.tmp", 48)
    # too new -> ignored
    (temp / "fresh.tmp").write_bytes(b"z" * 5000)

    scanner, ctx = _ctx(sandbox_env, settings)
    result = scanner.scan(ctx)
    temp_issues = [i for i in result.issues if i.payload.get("root", "").lower() == str(temp).lower()]
    assert temp_issues, "expected a temp-folder issue"
    issue = temp_issues[0]
    assert issue.count == 2
    assert issue.size == 3000

    cs = change_store.new_change_set("junk")
    fctx = FixContext(env=sandbox_env, settings=settings, changes=cs)
    report = scanner.fix([issue], fctx)
    assert report.fixed == 2
    assert report.bytes_freed == 3000
    assert not (temp / "a.tmp").exists()
    assert (temp / "fresh.tmp").exists()


def test_dry_run_deletes_nothing(sandbox_env, settings, change_store):
    settings["junk.min_age_hours"] = 0
    temp = sandbox_env.known.get("temp")
    (temp / "c.tmp").write_bytes(b"x" * 100)
    scanner, ctx = _ctx(sandbox_env, settings)
    result = scanner.scan(ctx)
    cs = change_store.new_change_set("junk")
    fctx = FixContext(env=sandbox_env, settings=settings, changes=cs, dry_run=True)
    report = scanner.fix(result.issues, fctx)
    assert report.fixed >= 1
    assert (temp / "c.tmp").exists()


def test_exclusions_are_respected(sandbox_env, settings, change_store):
    settings["junk.min_age_hours"] = 0
    temp = sandbox_env.known.get("temp")
    keep = temp / "keep"
    keep.mkdir()
    (keep / "important.tmp").write_bytes(b"x" * 100)
    settings["exclusions"] = [str(keep)]
    scanner, ctx = _ctx(sandbox_env, settings)
    result = scanner.scan(ctx)
    cs = change_store.new_change_set("junk")
    scanner.fix(result.issues, FixContext(env=sandbox_env, settings=settings, changes=cs))
    assert (keep / "important.tmp").exists()


def test_protected_paths():
    assert is_protected_path(r"C:\Windows\System32\kernel32.dll")
    assert is_protected_path(r"C:\Windows\notepad.exe")
    assert is_protected_path(r"C:\Windows\SysWOW64\x.dll")
    assert not is_protected_path(r"C:\Users\Me\AppData\Local\Temp\x.tmp")
    assert is_protected_path(r"C:\Users\Me\ntuser.dat")
