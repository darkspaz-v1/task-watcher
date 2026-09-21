# Task Watcher

[![CI](https://github.com/darkspaz-v1/task-watcher/actions/workflows/ci.yml/badge.svg)](https://github.com/darkspaz-v1/task-watcher/actions/workflows/ci.yml)

One panel answering "is it done yet?" for anything long-running — including Claude Code itself.

## How it works

- Always-on-top panel plus a tray icon, one progress row per task.
- Two ways to register a task:
  1. **Watch a process** by PID or name. Progress is shown as indeterminate, because liveness alone
     cannot tell you how far along something is.
  2. **Drop a JSON file** into the `tasks` folder with `progress` (0-100) and `status`. Anything that
     can write a file can report into this.
- Fires a Windows toast the moment a task flips to done or failed.
- **Auto-fails a task after 30 minutes with no update**, so an abandoned job does not sit at 40 percent
  forever pretending to be alive.

## Claude Code integration

`hook_bridge.py` is wired into Claude Code hooks (`~/.claude/settings.json`), so every session reports
its own progress into this panel with no per-session setup.

**Stack:** Python, Tkinter, `pystray`, `winotify`, `psutil`, Pillow.

## Part of a suite

One of seven small Windows tray utilities built as separate, self-contained apps: each has its own
folder, its own virtualenv and its own `run.bat`, with no shared runtime. They are deliberately not a
framework — the only thing they share is a set of conventions.

| Convention | Why |
|---|---|
| Single-instance guard via a `.singleton.lock` file | An earlier `.instance.lock` design could get stuck after a force-kill and leave the app permanently unlaunchable |
| Relaunch brings the existing window forward | Previously a second launch silently did nothing, which was indistinguishable from the app being broken |
| Config lives in `config.json`, read at startup | Edit it, then fully exit the tray icon and relaunch — a running process never re-reads it |
| Tray icon generated in code (`icon.py`) | No binary asset to keep in sync |

## Running it

```
py -m venv venv
venv\Scripts\pip install -r requirements.txt
run.bat
```

Create the virtualenv and install once; after that `run.bat` starts the tray app using `venv\Scripts\pythonw.exe`.
Windows only — these use Win32 APIs and a system tray.

## Development

```
venv\Scripts\pip install -r requirements-dev.txt
venv\Scripts\python -m pytest
venv\Scripts\ruff check .
```

The tests cover the pure logic: the `tasks/` file read/write round trip, the hook-event parsing in
`hook_bridge.py` (including a subprocess test that the hook stays silent and exits 0 on bad input), and
process liveness checks. They use a temp folder and never touch your real `tasks/` folder or open a window.
CI runs the same two commands on Windows with Python 3.12 and 3.13.

## Troubleshooting

Log file location: `logs/task-watcher.log` next to `app.py` (rotating, 1 MB x 3); the Claude Code hook writes
its own `logs/hook_bridge.log` and only when something goes wrong. Set `APP_LOG_LEVEL=DEBUG` before launching
to also record errors the app deliberately ignores (for example a failed toast notification). A crash traceback
goes to `app_error.log`.

## License

MIT — see [LICENSE](LICENSE).
