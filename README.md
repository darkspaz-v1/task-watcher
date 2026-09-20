# Task Watcher

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

**Stack:** Python, Tkinter, `pystray`, `win10toast`, Pillow.

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
run.bat
```

That creates the virtualenv on first run, installs `requirements.txt`, and starts the app. Windows
only — these use Win32 APIs and a system tray.

## License

MIT — see [LICENSE](LICENSE).
