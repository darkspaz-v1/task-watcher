import pytest

import hook_bridge
import tasks_io


@pytest.fixture(autouse=True)
def isolated_tasks_dir(tmp_path, monkeypatch):
    """Point both modules at a temp folder so tests never touch the real tasks/ dir."""
    d = tmp_path / "tasks"
    d.mkdir()
    monkeypatch.setattr(tasks_io, "TASKS_DIR", d)
    monkeypatch.setattr(hook_bridge, "TASKS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def isolated_logging(tmp_path, monkeypatch):
    """Send app log files to tmp and detach any handler a test's code path added to the root logger."""
    import logging

    import applog

    monkeypatch.setattr(applog, "LOG_DIR", tmp_path / "logs")
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for h in [h for h in root.handlers if h not in before]:
        root.removeHandler(h)
        h.close()
    root.setLevel(level)
