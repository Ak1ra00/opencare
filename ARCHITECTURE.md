# OpenCare — architecture

OpenCare is a Windows 10/11 PC maintenance app: one-click checkup, cleanup, startup
management, performance tuning, security status, a toolbox of utilities, a live resource
monitor and a full undo history. Python 3.12 + PySide6 (Qt 6), no other GUI deps.

It is an original product. Do not use other vendors' names, artwork, text or rule
databases. Implement from public Windows documentation and general knowledge.

## Principles
1. **Nothing changes without consent.** Scans are read-only. Every fix is previewed and
   confirmed in the UI; destructive operations show exactly what will happen.
2. **Everything reversible is backed up first** into a *change set* (History page can undo):
   registry keys/values (JSON export), quarantined files (moved, not deleted), service
   start types, startup entries, tweaks. Junk/privacy files are the exception: they are
   deleted (optionally to the Recycle Bin) because restoring caches is pointless.
3. **Conservative defaults.** Risky categories exist but are off by default and labelled.
   Never touch: passwords, saved form data, anything under `C:\Windows\System32`,
   Microsoft-signed services, files in use, files newer than the age threshold.
4. **Testable without touching the machine.** Engines only reach the OS through
   `core.env.Environment` (known folders + `RegistryAdapter`). Tests build a sandbox
   environment (temp folders + `HKCU\Software\OpenCareTest\<uuid>` registry root).
5. **Responsive UI.** Long work runs in `core.tasks` workers with progress + cancel.
6. **Least privilege.** Runs as invoker. Admin-only categories are marked and offer
   "Restart as administrator".

## Layout
```
opencare/
  __init__.py            APP_NAME, __version__
  __main__.py            python -m opencare
  app.py                 QApplication, theme, single instance, CLI args, main window, tray
  core/
    paths.py             data/backups/logs dirs (%LOCALAPPDATA%\OpenCare)
    settings.py          Settings (JSON, defaults, dotted keys, changed signal)
    logging_setup.py     rotating file log
    admin.py             is_admin(), relaunch_as_admin()
    env.py               Environment, KnownFolders, RegistryAdapter (real + sandbox)
    changes.py           ChangeSet / ChangeStore / restore handlers (undo)
    tasks.py             run_task(): QThreadPool worker with progress/cancel
    fmt.py               bytes/durations/relative time formatting
    shell.py             .lnk resolve, recycle bin, open location, delete-to-recycle
  engines/
    base.py              Issue, Category, ScanResult, FixReport, Scanner, register()
    junk.py              junk files
    privacy.py           privacy traces
    registry_clean.py    registry issues
    shortcuts.py         broken shortcuts
    startup.py           startup items (+ boot time)
    optimize.py          performance mode, memory trim, tweaks catalog, network tools
    security.py          security status checks
  tools/                 toolbox utilities (pure logic, UI in ui/pages/tools*)
  ui/
    theme.py             design tokens + QSS for light/dark
    icons.py             original SVG line icons -> QIcon/QPixmap
    widgets/             shared widgets (see below)
    main_window.py       sidebar + lazy page stack
    pages/               one module per page
    monitor_widget.py    floating resource monitor
    tray.py              system tray icon + menu
tests/                   pytest; sandboxed; never modifies the real system
```

## Engine contract (`opencare/engines/base.py`)
```python
class Scanner(ABC):
    id: str; title: str; description: str; icon: str
    categories: list[Category]          # id, title, description, risk, default_on, requires_admin
    def scan(self, ctx: ScanContext) -> ScanResult: ...
    def fix(self, issues: list[Issue], ctx: FixContext) -> FixReport: ...
```
- `ScanContext`: `env`, `settings`, `categories` (enabled ids), `progress(frac, text)`,
  `cancelled()`.
- `FixContext`: same plus `changes: ChangeSet`, `dry_run: bool`.
- `Issue`: `id, scanner, category, title, detail, size, count, path, risk, selected, payload`.
- Scanners register with `@register` and are listed by `engines.base.all_scanners()`.
  The Home checkup runs every registered scanner whose id is enabled in settings.
- Scanners must: honour `cancelled()`, report progress, skip what they cannot access
  (record in `errors`, do not raise), skip categories with `requires_admin` when
  `env.is_admin` is false (report as skipped), and respect `settings["exclusions"]`.

## Undo (`opencare/core/changes.py`)
A `ChangeSet` is a folder `history/<id>/` with `changeset.json` + backup payloads.
Helpers record reversible operations; `ChangeStore.restore(id)` replays them in reverse:
- `backup_reg_key(path)` before deleting a key tree (JSON export of the subtree)
- `backup_reg_value(path, name)` before deleting/changing a value
- `quarantine(path)` moves a file into the change set (restorable)
- `record(kind, description, undo_data)` for custom kinds; register a restore handler with
  `register_restore_handler(kind, fn)` (e.g. `service_start_type`, `startup_entry`, `tweak`).

## UI system
- Window 1180x760 (min 980x640), native frame. Sidebar 220 px: Home, Cleanup, Optimize,
  Startup, Security, Tools, History, Settings; footer shows live CPU/RAM.
- Pages subclass `ui.widgets.Page` (`page_id`, `title`, `on_show()`), registered in
  `ui/main_window.py` `PAGES` and constructed lazily.
- Shared widgets (`opencare.ui.widgets`): `Page`, `PageHeader`, `Card`, `StatTile`,
  `ToggleSwitch`, `ScoreRing`, `SegmentedControl`, `ProgressPanel`, `EmptyState`,
  `IssueTree` (checkable grouped results with sizes, context menu: open location / exclude),
  `ConfirmDialog`, `Toast`, `Badge`, buttons via `primary_button()/secondary_button()/
  danger_button()`.
- Colours only via `ui.theme` tokens (`theme.color("accent")`); QSS uses object names /
  dynamic properties (`class="primary"`). Light and dark themes must both look right.
- Icons only via `ui.icons.icon(name, color=None, size=20)`; add new original icons there.

## Settings (`%LOCALAPPDATA%\OpenCare\settings.json`)
Dotted keys with defaults in `core/settings.py` `DEFAULTS`. Modules add their own keys to
`DEFAULTS` (namespaced: `junk.*`, `privacy.*`, `monitor.*` ...).

## Conventions
- Python 3.12, type hints, dataclasses, `pathlib`. No print(); use `logging`.
- Windows APIs via `winreg`, `ctypes`, `pywin32`, `psutil`, `subprocess` (`CREATE_NO_WINDOW`).
- PowerShell/WMI calls are slow: cache, run in workers, time out (<= 20 s).
- Tests: `.venv\Scripts\python -m pytest -q`. Use `tests/conftest.py` fixtures
  `sandbox_env` and `qapp`. GUI tests run with `QT_QPA_PLATFORM=offscreen`.
