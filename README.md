# OpenCare

A Windows 10/11 PC maintenance toolkit — one-click checkup, cleanup, startup
management, performance tuning, a security overview, a utilities toolbox, a live
resource monitor, and a full undo history.

Built with Python 3.12 and PySide6 (Qt 6). Original work; not affiliated with any
other maintenance product.

## Principles
- **Nothing changes without your consent.** Scans are read-only; every fix is previewed.
- **Reversible by default.** Registry edits, startup/service changes and quarantined
  files are backed up into a change set you can undo from the History page.
- **Conservative.** Risky categories are off by default and clearly labelled. System
  files, signed services and in-use files are never touched.

## Develop
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m opencare       # run
.venv\Scripts\python -m pytest -q      # tests (sandboxed; never touches the real system)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map and engine contract.
