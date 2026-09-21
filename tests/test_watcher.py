import psutil

import watcher


def test_non_process_task_returns_none():
    assert watcher.check_process_alive({"label": "file-based"}) is None


def test_pid_task_uses_pid_exists(monkeypatch):
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: pid == 4242)
    assert watcher.check_process_alive({"pid": 4242}) is True
    assert watcher.check_process_alive({"pid": 1}) is False


class _FakeProc:
    def __init__(self, name):
        self.info = {"name": name}


def test_process_name_match_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [_FakeProc("System"), _FakeProc("FFmpeg.exe")])
    assert watcher.check_process_alive({"process_name": "ffmpeg.EXE"}) is True
    assert watcher.check_process_alive({"process_name": "nothing.exe"}) is False


def test_process_with_no_name_is_skipped(monkeypatch):
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [_FakeProc(None)])
    assert watcher.check_process_alive({"process_name": "x.exe"}) is False
