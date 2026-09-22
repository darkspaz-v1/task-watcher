"""Invoked by Claude Code hooks (see ~/.claude/settings.json). Reads the hook's
event JSON from stdin and writes/updates a task file in tasks/ so task-watcher
picks it up. One task file per Claude Code session (tasks/claude-<session_id>.json).

Deliberately minimal and defensive: any failure here must never break the calling
Claude Code session, so all errors are swallowed.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

from applog import setup_logging
from tasks_io import task_path

TASKS_DIR = Path(__file__).parent / "tasks"


def build_task_data(event, existing):
    """Pure mapping from a Claude Code hook event (plus the session's previous task
    data) to the new task data, or None when the event should be ignored."""
    event_name = event.get("hook_event_name", "")
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
        return None

    return {
        "label": label,
        "progress": progress,
        "status": status,
        "source": "claude-code",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _log_failure(message):
    """Record a swallowed failure in logs/hook_bridge.log. Set up lazily so the
    normal path stays as cheap as before; never writes to stdout/stderr, which
    belong to the Claude Code hook contract."""
    logging.raiseExceptions = False  # a logging error must not print to the caller's stderr
    setup_logging("hook_bridge")
    logging.getLogger("hook_bridge").warning(message, exc_info=True)


def main():
    try:
        TASKS_DIR.mkdir(exist_ok=True)
        event = json.load(sys.stdin)
    except (OSError, ValueError):
        # Unreadable/empty/non-JSON stdin: nothing to report, and the hook must not fail.
        _log_failure("could not read hook event from stdin")
        return

    session_id = str(event.get("session_id", "unknown"))[:12]
    task_id = f"claude-{session_id}"
    # Sanitize through the same helper tasks_io uses for its own file names, so a
    # session id containing characters unsafe on the filesystem (\ / : * ? " < > |)
    # can never produce a path tasks_io itself wouldn't produce for the same id.
    task_file = task_path(task_id)

    existing = {}
    if task_file.exists():
        try:
            existing = json.loads(task_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _log_failure(f"could not read existing task file {task_file.name}; starting fresh")
            existing = {}
    if not isinstance(existing, dict):
        # Valid JSON but not an object: treat like a missing file instead of raising
        # on every later event for this session.
        existing = {}

    data = build_task_data(event, existing)
    if data is None:
        return

    try:
        # Atomic write: separate parallel Claude Code tool calls each invoke this
        # script as their own process, so two writes for the same session can land
        # close together. A per-PID temp file + os.replace avoids a torn/half-written
        # file and Windows sharing-violation errors from overlapping direct writes.
        tmp_path = task_file.with_name(f"{task_file.stem}.{os.getpid()}.tmp")
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp_path, task_file)
    except OSError:
        _log_failure(f"could not write task file {task_file.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Last resort by design: this runs inside every Claude Code hook call, and
        # nothing here may ever break or slow the calling session.
        _log_failure("unexpected error in hook_bridge")
