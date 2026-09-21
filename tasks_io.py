import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)
_warned = set()  # files already reported; the poll loop re-reads every second

APP_DIR = Path(__file__).parent
TASKS_DIR = APP_DIR / "tasks"
TASKS_DIR.mkdir(exist_ok=True)

VALID_STATUSES = {"running", "waiting", "done", "failed"}


def task_path(task_id):
    safe = "".join(c for c in task_id if c.isalnum() or c in "-_") or "task"
    return TASKS_DIR / f"{safe}.json"


def write_task(task_id, data):
    """data: dict with at least 'label' and 'status' (running/waiting/done/failed).
    'progress' is an int 0-100 or None for indeterminate.

    Writes via a per-process temp file + atomic os.replace so a reader (or a second
    writer - e.g. two Claude Code hook invocations for the same session firing close
    together) never sees a half-written file or hits a Windows sharing violation."""
    data = dict(data)
    if data.get("status") not in VALID_STATUSES:
        data["status"] = "running"
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    final_path = task_path(task_id)
    tmp_path = final_path.with_name(f"{final_path.stem}.{os.getpid()}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp_path, final_path)
    return data


def read_all_tasks():
    tasks = {}
    for f in TASKS_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                if f.name not in _warned:
                    _warned.add(f.name)
                    log.warning("skipping %s: top-level JSON is not an object", f.name)
                continue
            if data.get("status") not in VALID_STATUSES:
                data["status"] = "running"
            tasks[f.stem] = data
        except OSError:
            # File being replaced by a writer right now: skip it this poll, the next one re-reads.
            log.debug("skipping unreadable task file %s", f.name, exc_info=True)
            continue
        except ValueError:
            # Invalid JSON / bad encoding: skip it so one bad file can't take the panel down.
            if f.name not in _warned:
                _warned.add(f.name)
                log.warning("skipping %s: not valid JSON", f.name, exc_info=True)
            continue
    return tasks


def delete_task(task_id):
    p = task_path(task_id)
    if p.exists():
        p.unlink()
