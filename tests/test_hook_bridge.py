import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import hook_bridge
from hook_bridge import build_task_data

ROOT = Path(hook_bridge.__file__).parent


# --- pure event -> task mapping ---------------------------------------------

def test_pre_tool_use_marks_running_and_bumps_progress():
    d = build_task_data({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, {})
    assert d["label"] == "Claude Code: running Bash"
    assert d["status"] == "running"
    assert d["progress"] == 5
    assert d["source"] == "claude-code"


def test_post_tool_use_label():
    d = build_task_data({"hook_event_name": "PostToolUse", "tool_name": "Edit"}, {"progress": 10})
    assert d["label"] == "Claude Code: finished Edit"
    assert d["progress"] == 15


def test_missing_tool_name_defaults():
    d = build_task_data({"hook_event_name": "PreToolUse"}, {})
    assert d["label"] == "Claude Code: running a tool"


def test_progress_is_capped_at_90_until_stop():
    d = build_task_data({"hook_event_name": "PreToolUse", "tool_name": "X"}, {"progress": 89})
    assert d["progress"] == 90
    d = build_task_data({"hook_event_name": "PostToolUse", "tool_name": "X"}, {"progress": 90})
    assert d["progress"] == 90


def test_notification_sets_waiting_and_keeps_progress():
    d = build_task_data({"hook_event_name": "Notification"}, {"progress": 35})
    assert d["status"] == "waiting"
    assert d["progress"] == 35
    assert d["label"] == "Claude Code: needs your attention"


@pytest.mark.parametrize("name", ["Stop", "SubagentStop"])
def test_stop_events_complete_the_task(name):
    d = build_task_data({"hook_event_name": name}, {"progress": 40})
    assert d["status"] == "done" and d["progress"] == 100
    assert d["label"] == "Claude Code: session finished"


@pytest.mark.parametrize("event", [{}, {"hook_event_name": "UserPromptSubmit"}, {"hook_event_name": ""}])
def test_unknown_events_are_ignored(event):
    assert build_task_data(event, {}) is None


def test_null_progress_in_existing_file_is_treated_as_zero():
    d = build_task_data({"hook_event_name": "PreToolUse", "tool_name": "X"}, {"progress": None})
    assert d["progress"] == 5


def test_updated_at_is_iso_seconds():
    d = build_task_data({"hook_event_name": "Stop"}, {})
    assert d["updated_at"][10] == "T" and len(d["updated_at"]) == 19


# --- main(): stdin in, task file out, stdout untouched ----------------------

def run_main(monkeypatch, event):
    monkeypatch.setattr(sys, "stdin", io.StringIO(event if isinstance(event, str) else json.dumps(event)))
    hook_bridge.main()


def read_task(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def test_main_writes_one_file_per_session_using_first_12_chars(monkeypatch, isolated_tasks_dir, capsys):
    run_main(monkeypatch, {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "abcdef123456789"})
    assert read_task(isolated_tasks_dir, "claude-abcdef123456.json")["label"] == "Claude Code: running Bash"
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""  # hook contract: nothing on stdout/stderr


def test_main_accumulates_progress_across_events(monkeypatch, isolated_tasks_dir):
    for _ in range(3):
        run_main(monkeypatch, {"hook_event_name": "PostToolUse", "tool_name": "X", "session_id": "s1"})
    assert read_task(isolated_tasks_dir, "claude-s1.json")["progress"] == 15
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s1"})
    final = read_task(isolated_tasks_dir, "claude-s1.json")
    assert (final["status"], final["progress"]) == ("done", 100)


def test_main_ignores_garbage_and_unknown_events(monkeypatch, isolated_tasks_dir):
    run_main(monkeypatch, "not json at all")
    run_main(monkeypatch, "")
    run_main(monkeypatch, {"hook_event_name": "Whatever", "session_id": "zzz"})
    assert list(isolated_tasks_dir.iterdir()) == []


def test_main_recovers_from_corrupt_existing_file(monkeypatch, isolated_tasks_dir):
    (isolated_tasks_dir / "claude-s2.json").write_text("{torn", encoding="utf-8")
    run_main(monkeypatch, {"hook_event_name": "PreToolUse", "tool_name": "X", "session_id": "s2"})
    assert read_task(isolated_tasks_dir, "claude-s2.json")["progress"] == 5


def test_script_contract_exit_zero_and_silent_on_bad_input():
    """Run the real script the way Claude Code does: bad stdin must not fail or print."""
    for stdin in ["", "garbage", "[1,2]", '{"hook_event_name": "Unknown"}']:
        r = subprocess.run(
            [sys.executable, str(ROOT / "hook_bridge.py")], input=stdin, capture_output=True, text=True, timeout=30
        )
        assert r.returncode == 0, stdin
        assert r.stdout == "" and r.stderr == "", stdin


def test_main_recovers_from_wrong_shaped_existing_file(monkeypatch, isolated_tasks_dir):
    # Valid JSON but not an object (e.g. a stray list): used to make every later
    # hook event for this session raise and be silently dropped.
    (isolated_tasks_dir / "claude-s3.json").write_text("[1, 2]", encoding="utf-8")
    run_main(monkeypatch, {"hook_event_name": "PreToolUse", "tool_name": "X", "session_id": "s3"})
    assert read_task(isolated_tasks_dir, "claude-s3.json")["progress"] == 5
