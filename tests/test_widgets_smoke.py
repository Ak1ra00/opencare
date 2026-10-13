"""Smoke tests: widgets and icons construct and render off-screen without error."""
import pytest

from opencare.ui import icons, theme


@pytest.fixture(autouse=True)
def _theme(qapp):
    theme.apply_theme(qapp, "light")
    yield


def test_all_icons_render():
    for name in icons.ICONS:
        pm = icons.pixmap(name, size=20)
        assert not pm.isNull(), name


def test_widgets_construct(qapp):
    from opencare.ui import widgets

    widgets.primary_button("Go", "rocket")
    widgets.secondary_button("Cancel")
    widgets.danger_button("Delete", "trash")
    widgets.ToggleSwitch()
    widgets.SegmentedControl(["A", "B", "C"])
    widgets.StatTile("Freed", "1.2 GB", "broom")
    widgets.Badge("PRO", "accent")
    widgets.EmptyState("check_circle", "All clear")
    ring = widgets.ScoreRing()
    ring.set_score(82, "82", "Good")
    widgets.ProgressPanel()


def test_issue_tree_selection(qapp):
    from opencare.engines.base import Category, Issue, Risk, ScanResult, Scanner
    from opencare.ui.widgets import IssueTree

    class Dummy(Scanner):
        id = "junk"
        title = "Junk"
        icon = "broom"
        categories = [Category("cache", "Cache", "caches", Risk.LOW), Category("logs", "Logs", "logs", Risk.LOW)]

        def scan(self, ctx):
            return ScanResult(self.id)

        def fix(self, issues, ctx):
            from opencare.engines.base import FixReport

            return FixReport(self.id)

    res = ScanResult("junk", issues=[
        Issue("junk:cache:a", "junk", "cache", "a.tmp", size=1000),
        Issue("junk:cache:b", "junk", "cache", "b.tmp", size=2000),
        Issue("junk:logs:c", "junk", "logs", "c.log", size=500),
    ])
    tree = IssueTree()
    captured = []
    tree.selection_changed.connect(lambda b, c: captured.append((b, c)))
    tree.load(Dummy(), res)
    assert len(tree.all_issues()) == 3
    assert captured[-1] == (3500, 3)
    tree.set_all_checked(False)
    assert captured[-1] == (0, 0)
    assert tree.selected_issues() == []
