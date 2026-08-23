"""Invoked by Claude Code hooks (see ~/.claude/settings.json). Reads the hook's
event JSON from stdin and writes/updates a task file in tasks/ so task-watcher
picks it up. One task file per Claude Code session (tasks/claude-<session_id>.json).

Deliberately minimal and defensive: any failure here must never break the calling
Claude Code session, so all errors are swallowed.
"""
import json
import os
import sys
import time
from pathlib import Path

TASKS_DIR = Path(__file__).parent / "tasks"


def main():
    try:
        TASKS_DIR.mkdir(exist_ok=True)
        event = json.load(sys.stdin)
    except Exception:
        return

    event_name = event.get("hook_event_name", "")
    session_id = str(event.get("session_id", "unknown"))[:12]
    task_id = f"claude-{session_id}"
    task_file = TASKS_DIR / f"{task_id}.json"

    existing = {}
    if task_file.exists():
        try:
            existing = json.loads(task_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    progress = existing.get("progress") or 0
    status = "running"
    label = existing.get("label", "Claude Code session")

    if event_name == "PreToolUse":
        tool_name = event.get("tool_name", "a tool")
        label = f"Claude Code: running {tool_name}"
        progress = min(progress + 5, 90)
    elif event_name == "PostToolUse":
        tool_name = event.get("tool_name", "a tool")
        label = f"Claude Code: finished {tool_name}"
        progress = min(progress + 5, 90)
    elif event_name == "Notification":
        label = "Claude Code: needs your attention"
        status = "waiting"
    elif event_name in ("Stop", "SubagentStop"):
        label = "Claude Code: session finished"
        status = "done"
        progress = 100
    else:
        return

    data = {
        "label": label,
        "progress": progress,
        "status": status,
        "source": "claude-code",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        # Atomic write: separate parallel Claude Code tool calls each invoke this
        # script as their own process, so two writes for the same session can land
        # close together. A per-PID temp file + os.replace avoids a torn/half-written
        # file and Windows sharing-violation errors from overlapping direct writes.
        tmp_path = task_file.with_name(f"{task_file.stem}.{os.getpid()}.tmp")
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp_path, task_file)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
