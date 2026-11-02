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


# --- the flow, with fake agents / vshort / NotebookLM -------------------------------------------------------------

from collections import Counter  # noqa: E402

from vshort.cli import AUTH, FAILED, OK, WAIT_BRIEF, WAIT_SCRIPT  # noqa: E402

SENTS = [{"id": 1, "start": 0.0, "end": 2.0, "en": "Hello there."}, {"id": 2, "start": 2.0, "end": 4.0, "en": "Bye."}]


class Fakes:
    """What the real agents and commands would leave behind, plus a record of every call."""

    def __init__(self, run: Run):
        self.run, self.agents, self.cmds, self.nb = run, Counter(), [], []
        self.prompts: dict[str, list[str]] = {}
        self.codes: dict[str, list[int]] = {}  # vshort step -> exit codes to return, in order (then 0)
        self.no_notebook = False

    def claude(self, run, step, agent, prompt, timeout):
        self.agents[agent] += 1
        self.prompts.setdefault(agent, []).append(prompt)
        f = run.file
        if agent == "vs-researcher" and step == "research":
            f("brief.vi.md").write_text("# Tiêu đề\n")
            f("brief.en.md").write_text("# Title\n")
            if not self.no_notebook:
                f("notebook.txt").write_text("nb-123\n")
        elif agent == "vs-transcriber":
            f("fragments_text.json").write_text('{"0": "Hello there."}')
        elif agent == "vs-translator":
            run.write("script.vi.json", [{"id": 1, "phrases": "Xin | chào", "note": ""},
                                         {"id": 2, "phrases": "Tạm biệt", "note": "ngắn hơn"}])
        return "xong"

    def vshort(self, args):
        cmd = args[0]
        self.cmds.append(cmd)
        code = (self.codes.get(cmd) or [0]).pop(0) if self.codes.get(cmd) else 0
        if code:
            return code
        if cmd == "detect":
            self.run.write("fragments.json", [{"i": 0}])
            (self.run.path / "sheets").mkdir(exist_ok=True)
            (self.run.path / "sheets" / "sheet00.png").write_bytes(b"")
        if cmd == "text":
            self.run.write("sentences.en.json", SENTS)
        if cmd not in ("check", "approve"):
            self.run.mark(cmd)
        return 0

    def notebooklm(self, args):
        self.nb.append(args[:2])
        return 0


@pytest.fixture
def flow(tmp_path, monkeypatch):
    run = _run(tmp_path)
    run.write("run.json", {"slug": "s", "topic": "Chủ đề", "notebook_id": "", "auto": False})
    fk = Fakes(run)
    monkeypatch.setattr(auto, "run_claude", fk.claude)
    monkeypatch.setattr(auto, "run_vshort", fk.vshort)
    monkeypatch.setattr(auto, "notebooklm", fk.notebooklm)
    return run, fk


def test_stops_for_brief_then_for_translation(flow):
    run, fk = flow
    assert auto.run_auto(run) == WAIT_BRIEF
    assert auto.get_state(run)["state"] == "wait_brief" and dict(fk.agents) == {"vs-researcher": 1}
    assert run.read("run.json")["notebook_id"] == "nb-123"
    run.mark("approve_brief")
    assert auto.run_auto(run) == WAIT_SCRIPT
    assert auto.get_state(run)["state"] == "wait_script"
    table = run.file("translation.md").read_text()
    assert "Hello there." in table and "Xin chào" in table and "ngắn hơn" in table and "|" in table
    assert fk.nb == [["source", "add"]]
    assert fk.cmds[:4] == ["fetch", "detect", "text", "check"]


def test_rerun_does_not_repeat_finished_steps(flow):
    run, fk = flow
    run.mark("approve_brief")
    assert auto.run_auto(run) == WAIT_SCRIPT
    before = (dict(fk.agents), len(fk.nb), fk.cmds.count("fetch"))
    assert auto.run_auto(run) == WAIT_SCRIPT
    assert (dict(fk.agents), len(fk.nb), fk.cmds.count("fetch")) == before


def test_auto_mode_checks_brief_instead_of_stopping(flow):
    run, fk = flow
    run.write("run.json", run.read("run.json") | {"auto": True})
    assert auto.run_auto(run) == WAIT_SCRIPT
    assert fk.agents["vs-researcher"] == 2 and "Soát brief" in fk.prompts["vs-researcher"][1]


def test_notebooklm_login_stops_with_auth(flow):
    run, fk = flow
    run.mark("approve_brief")
    fk.codes["fetch"] = [AUTH]
    assert auto.run_auto(run) == AUTH
    st = auto.get_state(run)
    assert st["state"] == "error" and "đăng nhập" in st["message"]


def test_missing_notebook_id_is_an_error(flow):
    run, fk = flow
    fk.no_notebook = True
    assert auto.run_auto(run) == FAILED
    assert "notebook.txt" in auto.get_state(run)["message"]


def test_translation_that_fails_check_stops(flow):
    run, fk = flow
    run.mark("approve_brief")
    fk.codes["check"] = [2]
    assert auto.run_auto(run) == FAILED
    assert "vshort check" in auto.get_state(run)["message"] and not run.done("translate")
