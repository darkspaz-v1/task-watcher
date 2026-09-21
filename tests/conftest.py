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
