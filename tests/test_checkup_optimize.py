from opencare.core.changes import ChangeStore
from opencare.engines import optimize
from opencare.engines.checkup import Checkup, compute_score, score_band


def test_checkup_runs_all_and_scores(sandbox_env, settings, tmp_path):
    # seed a junk temp file and a broken registry app path
    temp = sandbox_env.known.get("temp")
    (temp / "x.tmp").write_bytes(b"x" * 1000)
    settings["junk.min_age_hours"] = 0
    sandbox_env.reg.set_value(
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\gone.exe", "", r"C:\no\gone.exe")

    store = ChangeStore(sandbox_env, tmp_path / "history")
    checkup = Checkup(sandbox_env, settings, store)
    result = checkup.run()
    assert set(result.results) >= {"junk", "registry", "privacy", "shortcuts", "startup", "security"}
    assert result.total_issues >= 2
    assert 1 <= result.score <= 100


def test_checkup_fix_groups_into_one_changeset(sandbox_env, settings, tmp_path):
    temp = sandbox_env.known.get("temp")
    (temp / "a.tmp").write_bytes(b"x" * 500)
    settings["junk.min_age_hours"] = 0
    store = ChangeStore(sandbox_env, tmp_path / "history")
    checkup = Checkup(sandbox_env, settings, store)
    result = checkup.run()
    issues = result.issues_for("junk")
    cs, reports = checkup.fix(issues, "test fixes")
    assert reports["junk"].fixed >= 1
    assert store.get(cs.id) is not None
    assert settings["stats.items_fixed"] >= 1


def test_score_monotonic_and_bands():
    from opencare.engines.base import Issue, Risk, ScanResult

    empty = {"junk": ScanResult("junk")}
    assert compute_score(empty) == 100
    heavy = {"security": ScanResult("security", issues=[
        Issue(f"security:x:{i}", "security", "firewall", "f", risk=Risk.MEDIUM) for i in range(5)])}
    assert compute_score(heavy) < 100
    assert score_band(90)[0] == "Excellent"
    assert score_band(10)[0] == "At risk"


def test_optimize_tweak_apply_and_undo(sandbox_env, change_store):
    tweak = next(t for t in optimize.TWEAKS if t.id == "menu_show_delay")
    assert optimize.current_state(sandbox_env, tweak) is False
    cs = change_store.new_change_set("tweak")
    assert optimize.apply_tweak(sandbox_env, tweak, cs)
    cs.save()
    assert optimize.current_state(sandbox_env, tweak) is True
    change_store.restore(cs.id)
    # value did not exist before -> undo removes it
    assert sandbox_env.reg.get_value(tweak.path, tweak.name) is None
