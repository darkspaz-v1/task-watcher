import json

import tasks_io
from tasks_io import delete_task, read_all_tasks, task_path, write_task


def test_write_then_read_round_trip(isolated_tasks_dir):
    written = write_task("build-1", {"label": "Build", "status": "running", "progress": 40})
    tasks = read_all_tasks()
    assert set(tasks) == {"build-1"}
    assert tasks["build-1"] == written
    assert tasks["build-1"]["label"] == "Build"
    assert tasks["build-1"]["progress"] == 40


def test_write_stamps_updated_at(isolated_tasks_dir):
    data = write_task("t", {"label": "x", "status": "done"})
    assert len(data["updated_at"]) == len("2026-01-01T00:00:00")
    assert data["updated_at"][4] == "-" and data["updated_at"][10] == "T"


def test_write_does_not_mutate_callers_dict(isolated_tasks_dir):
    original = {"label": "x", "status": "done"}
    write_task("t", original)
    assert "updated_at" not in original


def test_invalid_status_is_normalised_to_running_on_write(isolated_tasks_dir):
    assert write_task("t", {"label": "x", "status": "banana"})["status"] == "running"
    assert write_task("t2", {"label": "x"})["status"] == "running"


def test_invalid_status_is_normalised_on_read(isolated_tasks_dir):
    (isolated_tasks_dir / "hand.json").write_text(json.dumps({"label": "hand", "status": "??"}), encoding="utf-8")
    assert read_all_tasks()["hand"]["status"] == "running"


def test_all_valid_statuses_survive(isolated_tasks_dir):
    for s in ("running", "waiting", "done", "failed"):
        assert write_task(f"t-{s}", {"label": s, "status": s})["status"] == s


def test_indeterminate_progress_none_round_trips(isolated_tasks_dir):
    write_task("p", {"label": "watch", "status": "running", "progress": None})
    assert read_all_tasks()["p"]["progress"] is None


def test_overwrite_replaces_previous_state(isolated_tasks_dir):
    write_task("t", {"label": "a", "status": "running", "progress": 10})
    write_task("t", {"label": "a", "status": "done", "progress": 100})
    assert read_all_tasks()["t"]["status"] == "done"
    assert len(list(isolated_tasks_dir.glob("*.json"))) == 1


def test_atomic_write_leaves_no_temp_files(isolated_tasks_dir):
    write_task("t", {"label": "a", "status": "running"})
    assert [p.name for p in isolated_tasks_dir.iterdir()] == ["t.json"]


def test_task_id_is_sanitised_against_path_traversal(isolated_tasks_dir):
    p = task_path("../../evil name!")
    assert p.parent == isolated_tasks_dir
    assert p.name == "evilname.json"
    assert task_path("!!!").name == "task.json"


def test_corrupt_and_non_object_files_are_skipped(isolated_tasks_dir):
    write_task("good", {"label": "ok", "status": "done"})
    (isolated_tasks_dir / "torn.json").write_text('{"label": "x", "sta', encoding="utf-8")
    (isolated_tasks_dir / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
    (isolated_tasks_dir / "leftover.1234.tmp").write_text("{}", encoding="utf-8")
    assert set(read_all_tasks()) == {"good"}


def test_delete_task_removes_file_and_tolerates_missing(isolated_tasks_dir):
    write_task("t", {"label": "a", "status": "done"})
    delete_task("t")
    assert read_all_tasks() == {}
    delete_task("t")  # already gone: no error


def test_module_writes_only_inside_patched_dir(isolated_tasks_dir):
    write_task("t", {"label": "a", "status": "done"})
    assert tasks_io.TASKS_DIR == isolated_tasks_dir
    assert (isolated_tasks_dir / "t.json").exists()
