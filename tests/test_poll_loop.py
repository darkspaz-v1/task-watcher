import threading
from types import SimpleNamespace

import pytest

app = pytest.importorskip("app")  # skipped where Tk/pystray/winotify can't be imported


def test_poll_loop_survives_an_exception_and_keeps_polling(monkeypatch):
    stop = threading.Event()
    calls = []

    def poll_once():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("task file locked")  # first tick blows up
        stop.set()  # second tick proves the loop kept going

    fake = SimpleNamespace(_stop=stop, config={"poll_interval_seconds": 0}, _poll_once=poll_once)
    monkeypatch.setattr(app.time, "sleep", lambda s: None)
    app.TaskWatcherApp.poll_loop(fake)
    assert len(calls) == 2


def test_parse_updated_at_falls_back_to_now_for_bad_values():
    parse = app.TaskWatcherApp._parse_updated_at
    assert parse(None, 123.0) == 123.0
    assert parse("garbage", 123.0) == 123.0
    assert parse("2026-01-01T00:00:00", 0.0) != 0.0
