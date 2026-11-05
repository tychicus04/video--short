import pytest

from vshort import auto, timing
from vshort.run import Run


def test_start_end_round_trip(tmp_path):
    timing.start(tmp_path, "fetch", now=100)
    timing.end(tmp_path, "fetch", now=160)
    assert timing.read(tmp_path) == {"fetch": {"start": 100, "end": 160}}
    timing.start(tmp_path, "fetch", now=200)  # run again: the old end goes
    assert timing.read(tmp_path) == {"fetch": {"start": 200}}


def test_start_keeps_an_open_step(tmp_path):
    timing.start(tmp_path, "cover", now=10)
    timing.start(tmp_path, "cover", now=50)  # `vshort cover` inside the cover agent's step
    assert timing.read(tmp_path)["cover"] == {"start": 10}


def test_end_without_start(tmp_path):
    timing.end(tmp_path, "approve_brief", now=7)
    assert timing.read(tmp_path) == {"approve_brief": {"end": 7}}


def test_close_open_drops_unfinished_steps(tmp_path):
    timing.start(tmp_path, "fetch", now=1)
    timing.end(tmp_path, "fetch", now=2)
    timing.start(tmp_path, "detect", now=3)
    timing.close_open(tmp_path)
    assert timing.read(tmp_path) == {"fetch": {"start": 1, "end": 2}}


def test_read_broken_times_is_empty(tmp_path):
    f = tmp_path / timing.FILE
    f.write_text("{oops")
    assert timing.read(tmp_path) == {}
    f.write_text("[1]")
    assert timing.read(tmp_path) == {}
    f.write_text('{"fetch": 5, "detect": {"start": "x"}, "text": {"start": 1, "end": 2}}')  # edited by hand
    assert timing.read(tmp_path) == {"text": {"start": 1, "end": 2}}
    timing.end(tmp_path, "fetch", now=9)  # a broken entry never fails a step's mark
    assert timing.read(tmp_path)["fetch"] == {"end": 9}
    f.write_text('{"fetch": {"start": 1, "end": 1e999}, "text": {"start": 1, "end": 2}}')  # infinity: round() would raise
    assert timing.read(tmp_path) == {"text": {"start": 1, "end": 2}}


def test_mark_ends_the_step(tmp_path):
    Run(tmp_path).mark("tts")
    assert "end" in timing.read(tmp_path)["tts"]


def test_run_vshort_starts_its_step(tmp_path, monkeypatch):
    from vshort import cli
    monkeypatch.setattr(cli, "main", lambda args: 0)
    auto.run_vshort(["render", str(tmp_path)])
    assert "start" in timing.read(tmp_path)["render"]
    auto.run_vshort(["render", str(tmp_path / "missing")])  # not a run folder: nothing written there
    assert not (tmp_path / "missing").exists()


def test_run_claude_starts_its_step(tmp_path):
    run = Run(tmp_path)
    with pytest.raises(auto.AgentError):  # conftest: `claude` is `false`
        auto.run_claude(run, "research", "vs-researcher", "p", timeout=30)
    assert "start" in timing.read(run.path)["research"]


def test_run_auto_closes_open_steps_first(tmp_path, monkeypatch):
    run = Run(tmp_path)
    (tmp_path / timing.FILE).write_text('{"fetch": {"start": 1}}')  # a run that died during fetch
    seen = {}
    monkeypatch.setattr(auto, "_flow", lambda r: seen.update(timing.read(r.path)) or 0)
    assert auto.run_auto(run) == 0
    assert "fetch" not in seen


def test_a_failed_write_never_fails_a_step(tmp_path):
    gone = tmp_path / "gone"  # the folder cannot be written: the marks are lost, the step goes on
    timing.start(gone, "fetch", now=1)
    timing.end(gone, "fetch", now=2)
    timing.close_open(gone)
    assert timing.read(gone) == {}
