from opencare.engines.base import FixContext, ScanContext
from opencare.engines.browsers import detect_browsers
from opencare.engines.privacy import PrivacyScanner


def _make_chrome(env):
    root = env.known.get("localappdata") / "Google/Chrome/User Data/Default"
    root.mkdir(parents=True)
    (root / "Preferences").write_text("{}")
    cache = root / "Cache"
    cache.mkdir()
    (cache / "data_0").write_bytes(b"x" * 4096)
    (cache / "f_00001").write_bytes(b"y" * 2048)
    (root / "History").write_bytes(b"h" * 500)
    net = root / "Network"
    net.mkdir()
    (net / "Cookies").write_bytes(b"c" * 300)
    return root


def test_detect_chromium(sandbox_env):
    _make_chrome(sandbox_env)
    browsers = detect_browsers(sandbox_env)
    assert any(b.name == "Google Chrome" and b.family == "chromium" for b in browsers)


def test_privacy_scan_browser_cache(sandbox_env, settings, change_store):
    _make_chrome(sandbox_env)
    scanner = PrivacyScanner()
    ctx = ScanContext(env=sandbox_env, settings=settings, categories={"browser_cache"})
    res = scanner.scan(ctx)
    cache_issues = [i for i in res.issues if i.category == "browser_cache"]
    assert cache_issues
    assert cache_issues[0].size == 4096 + 2048

    cs = change_store.new_change_set("privacy")
    scanner.fix(cache_issues, FixContext(env=sandbox_env, settings=settings, changes=cs))
    root = sandbox_env.known.get("localappdata") / "Google/Chrome/User Data/Default"
    assert not (root / "Cache").exists()
    assert (root / "History").exists()  # history category not selected


def test_privacy_never_scans_passwords(sandbox_env, settings):
    root = _make_chrome(sandbox_env)
    (root / "Login Data").write_bytes(b"secret")
    (root / "Web Data").write_bytes(b"autofill")
    scanner = PrivacyScanner()
    ctx = ScanContext(env=sandbox_env, settings=settings,
                      categories={"browser_cache", "browser_history", "browser_cookies"})
    res = scanner.scan(ctx)
    for issue in res.issues:
        for p in issue.payload.get("paths", []):
            assert "login data" not in p.lower()
            assert "web data" not in p.lower()


def test_run_mru_cleared_and_restorable(sandbox_env, settings, change_store):
    reg = sandbox_env.reg
    key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU"
    reg.set_value(key, "a", "cmd\\1")
    reg.set_value(key, "b", "notepad\\1")
    reg.set_value(key, "MRUList", "ab")
    scanner = PrivacyScanner()
    res = scanner.scan(ScanContext(env=sandbox_env, settings=settings, categories={"windows_recent"}))
    mru = [i for i in res.issues if i.id.endswith("runmru")]
    assert mru
    cs = change_store.new_change_set("privacy")
    scanner.fix(mru, FixContext(env=sandbox_env, settings=settings, changes=cs))
    cs.save()
    assert reg.get_value(key, "a") is None
    # undo restores it
    change_store.restore(cs.id)
    assert reg.get_value(key, "a").value == "cmd\\1"
