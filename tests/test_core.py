import winreg

from opencare.core.env import SandboxRegistryAdapter
from opencare.core.fmt import human_bytes, human_duration


def test_sandbox_registry_is_isolated(sandbox_env):
    reg = sandbox_env.reg
    reg.set_value(r"HKLM\SOFTWARE\Demo", "Name", "value")
    assert reg.get_value(r"HKLM\SOFTWARE\Demo", "Name").value == "value"
    # physically stored under HKCU\Software\OpenCareTest\<id>\HKLM
    assert isinstance(reg, SandboxRegistryAdapter)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\OpenCareTest\{reg.sandbox_id}\HKLM\SOFTWARE\Demo") as k:
        assert winreg.QueryValueEx(k, "Name")[0] == "value"


def test_sandbox_destroy_removes_everything(sandbox_env):
    reg = sandbox_env.reg
    reg.set_value(r"HKCU\Software\A\B\C", "x", 1)
    reg.destroy()
    assert not reg.exists(r"HKCU\Software\A")


def test_reg_tree_backup_and_restore(sandbox_env, change_store):
    reg = sandbox_env.reg
    key = r"HKLM\SOFTWARE\Vendor\App"
    reg.set_value(key, "Path", r"C:\missing\app.exe")
    reg.set_value(key + r"\Sub", "Count", 7)
    reg.set_value(key + r"\Sub", "Blob", b"\x01\x02", winreg.REG_BINARY)

    cs = change_store.new_change_set("test")
    cs.backup_reg_tree(key)
    reg.delete_tree(key)
    cs.save()
    assert not reg.exists(key)

    restored, failed = change_store.restore(cs.id)
    assert (restored, failed) == (1, 0)
    assert reg.get_value(key, "Path").value == r"C:\missing\app.exe"
    assert reg.get_value(key + r"\Sub", "Count").value == 7
    assert reg.get_value(key + r"\Sub", "Blob").value == b"\x01\x02"


def test_quarantine_and_restore(sandbox_env, change_store):
    f = sandbox_env.known.get("desktop") / "Old.lnk"
    f.write_bytes(b"lnk")
    cs = change_store.new_change_set("shortcuts")
    cs.quarantine_file(str(f))
    cs.save()
    assert not f.exists()
    change_store.restore(cs.id)
    assert f.read_bytes() == b"lnk"


def test_tweak_restore_removes_new_value(sandbox_env, change_store):
    reg = sandbox_env.reg
    cs = change_store.new_change_set("tweak")
    cs.record_tweak("demo", r"HKCU\Software\T", "Flag", None)
    reg.set_value(r"HKCU\Software\T", "Flag", 1)
    cs.save()
    change_store.restore(cs.id)
    assert reg.get_value(r"HKCU\Software\T", "Flag") is None


def test_settings_defaults_and_persist(settings):
    assert settings["ui.theme"] == "system"
    settings["ui.theme"] = "dark"
    from opencare.core.settings import Settings

    again = Settings(settings._file)
    assert again["ui.theme"] == "dark"


def test_exclusions(settings):
    settings["exclusions"] = [r"C:\Keep"]
    assert settings.is_excluded(r"C:\Keep\file.tmp")
    assert settings.is_excluded(r"c:\keep")
    assert not settings.is_excluded(r"C:\Keeper\x")


def test_formatting():
    assert human_bytes(0) == "0 B"
    assert human_bytes(1536) == "1.5 KB"
    assert human_bytes(5 * 1024**3) == "5.0 GB"
    assert human_duration(0.25) == "250 ms"
    assert human_duration(75) == "1 min 15 s"
