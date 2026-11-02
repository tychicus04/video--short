import json
import sys

import pytest

from vshort import auto
from vshort.run import Run

FAKE = """import json, os, sys, time
spec = json.loads(os.environ["FAKE_CLAUDE"])
time.sleep(spec.get("sleep", 0))
print(spec["out"] if isinstance(spec["out"], str) else json.dumps(spec["out"]))
sys.exit(spec.get("code", 0))
"""


@pytest.fixture
def claude(tmp_path, monkeypatch):
    """Point auto.CLAUDE at a fake `claude`; returns a setter for what it prints, its exit code and delay."""
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE)
    monkeypatch.setattr(auto, "CLAUDE", [sys.executable, str(fake)])

    def set_(out, code=0, sleep=0):
        monkeypatch.setenv("FAKE_CLAUDE", json.dumps({"out": out, "code": code, "sleep": sleep}))
    return set_


def _run(tmp_path):
    (tmp_path / "run").mkdir()
    return Run(tmp_path / "run")


def test_run_claude_returns_result_and_logs_cost(tmp_path, claude):
    run = _run(tmp_path)
    claude({"result": "xong", "total_cost_usd": 0.12, "is_error": False, "modelUsage": {"claude-haiku-5-5": {}}})
    assert auto.run_claude(run, "translate", "vs-translator", "dịch đi", timeout=30) == "xong"
    [row] = run.read("cost.json")
    assert (row["step"], row["agent"], row["cost_usd"], row["models"], row["ok"]) == \
        ("translate", "vs-translator", 0.12, ["claude-haiku-5-5"], True)
    assert auto.total_cost(run) == 0.12


def test_run_claude_error_cases_raise_with_reason(tmp_path, claude):
    run = _run(tmp_path)
    claude({"result": "hỏng", "total_cost_usd": 0.05, "is_error": True, "modelUsage": {}})
    with pytest.raises(auto.AgentError):
        auto.run_claude(run, "translate", "vs-translator", "p", timeout=30)
    assert run.read("cost.json")[-1]["ok"] is False and run.read("cost.json")[-1]["cost_usd"] == 0.05

    claude({"result": ""}, code=1)
    with pytest.raises(auto.AgentError, match="vs-translator"):
        auto.run_claude(run, "translate", "vs-translator", "p", timeout=30)

    claude("không phải json")
    with pytest.raises(auto.AgentError):
        auto.run_claude(run, "translate", "vs-translator", "p", timeout=30)

    claude({"result": "x"}, sleep=2)
    with pytest.raises(auto.AgentError, match="quá"):
        auto.run_claude(run, "translate", "vs-translator", "p", timeout=1)
    assert run.read("cost.json")[-1] | {"seconds": 0} == {"step": "translate", "agent": "vs-translator", "seconds": 0,
                                                         "cost_usd": 0, "models": [], "ok": False}


def test_unmark_removes_steps(tmp_path):
    run = _run(tmp_path)
    run.mark("tts")
    run.mark("timeline")
    run.unmark("tts")
    assert not Run(run.path).done("tts") and Run(run.path).done("timeline")


def test_lock_refuses_second_and_takes_dead_lock(tmp_path):
    run = _run(tmp_path)
    assert auto.acquire_lock(run) and not auto.acquire_lock(run)
    run.file("auto.lock").write_text("999999")  # no such process: a run that died
    assert auto.acquire_lock(run)
    auto.release_lock(run)
    assert not run.file("auto.lock").exists()


def test_state_round_trips(tmp_path):
    run = _run(tmp_path)
    assert auto.get_state(run)["state"] == "none"
    auto.set_state(run, "wait_brief", "duyệt brief")
    s = auto.get_state(run)
    assert (s["state"], s["message"], s["round"]) == ("wait_brief", "duyệt brief", 0)
