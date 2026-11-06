import json
import sys

import pytest

from vshort import auto
from vshort.run import Run

FAKE = """import json, os, sys, time
spec = json.loads(os.environ["FAKE_CLAUDE"])
time.sleep(spec.get("sleep", 0))
if spec.get("echo_env"):
    spec["out"]["result"] = os.environ.get(spec["echo_env"], "")
print(spec["out"] if isinstance(spec["out"], str) else json.dumps(spec["out"]))
sys.exit(spec.get("code", 0))
"""


@pytest.fixture
def claude(tmp_path, monkeypatch):
    """Point auto.CLAUDE at a fake `claude`; returns a setter for what it prints, its exit code and delay."""
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE)
    monkeypatch.setattr(auto, "CLAUDE", [sys.executable, str(fake)])

    def set_(out, code=0, sleep=0, echo_env=None):
        monkeypatch.setenv("FAKE_CLAUDE", json.dumps({"out": out, "code": code, "sleep": sleep, "echo_env": echo_env}))
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


def test_a_pid_that_started_after_its_file_is_not_our_run(tmp_path):
    import os, time
    run = _run(tmp_path)
    run.file("auto.lock").write_text(str(os.getpid()))
    assert auto.locked_by(run) == os.getpid()            # this process was running when the lock was written
    old = time.time() - 10 * 365 * 86400
    os.utime(run.file("auto.lock"), (old, old))          # lock written long before this process started: pid reused
    assert auto.locked_by(run) is None
    auto.set_state(run, "running", pid=os.getpid())
    os.utime(run.file("auto.json"), (old, old))
    run.file("auto.lock").unlink()
    assert not auto.alive_run(run)


def test_started_is_none_for_no_such_process():
    assert auto._started(999999) is None and auto._started(0) is None


def test_state_round_trips(tmp_path):
    run = _run(tmp_path)
    assert auto.get_state(run)["state"] == "none"
    auto.set_state(run, "wait_brief", "duyệt brief")
    s = auto.get_state(run)
    assert (s["state"], s["message"], s["round"]) == ("wait_brief", "duyệt brief", 0)


# --- the flow, with fake agents / vshort / NotebookLM -------------------------------------------------------------

import threading  # noqa: E402
from collections import Counter  # noqa: E402


from vshort.cli import AUTH, FAILED, OK, WAIT_BRIEF, WAIT_SCRIPT  # noqa: E402

SENTS = [{"id": 1, "start": 0.0, "end": 2.0, "en": "Hello there."}, {"id": 2, "start": 2.0, "end": 4.0, "en": "Bye."}]


class Fakes:
    """What the real agents and commands would leave behind, plus a record of every call."""

    def __init__(self, run: Run):
        self.run, self.agents, self.cmds, self.nb = run, Counter(), [], []
        self.prompts: dict[str, list[str]] = {}
        self.order: list[str] = []  # every agent and vshort command, in the order they were called
        self.args: dict[str, list[list[str]]] = {}  # vshort step -> the argument list of each call
        self.codes: dict[str, list[int]] = {}  # vshort step -> exit codes to return, in order (then 0)
        self.no_notebook = False
        self.boom: set[str] = set()  # vshort steps that raise
        self.die_in: str | None = None  # agent step that "kills" the run (raises SystemExit) once
        self.reviews: list[dict | None] = []  # what each reviewer call writes to review.json (None: nothing); then Đạt
        self.fail_steps: set[str] = set()  # agent steps that fail (AgentError)
        self.fetched = threading.Event()  # set when `vshort fetch` runs
        self.wait_fetch = False  # the design agent waits (≤ 5 s) for fetch: proves it runs alongside
        self.saw_fetch = None

    def claude(self, run, step, agent, prompt, timeout):
        if step == self.die_in:
            self.die_in = None
            raise KeyboardInterrupt  # the process dies mid-call: nothing after it runs
        self.agents[agent] += 1
        self.order.append(agent)
        self.prompts.setdefault(agent, []).append(prompt)
        if step in self.fail_steps:
            raise auto.AgentError(f"{agent} lỗi ở bước {step}")
        f = run.file
        if agent == "vs-researcher" and step == "research":
            f("brief.vi.md").write_text("# Tiêu đề\n")
            f("brief.en.md").write_text("# Title\n")
            if not self.no_notebook:
                f("notebook.txt").write_text("nb-123\n")
        elif agent == "vs-transcriber":
            f("fragments_text.json").write_text('{"0": "Hello there."}')
        elif agent == "vs-translator" and "script.proposed.json" in prompt:
            run.write("script.proposed.json", [{"id": 1, "phrases": "Chào | bạn", "note": "sửa theo review"},
                                               {"id": 2, "phrases": "Tạm biệt", "note": ""}])
        elif agent == "vs-reviewer":
            r = self.reviews.pop(0) if self.reviews else {"verdict": "Đạt", "findings": []}
            if r is not None:
                run.write("review.json", r)
            run.file("review.md").write_text("Kết luận: " + (r or {}).get("verdict", "?"))
        elif agent == "vs-translator":
            run.write("script.vi.json", [{"id": 1, "phrases": "Xin | chào", "note": ""},
                                         {"id": 2, "phrases": "Tạm biệt", "note": "ngắn hơn"}])
        elif agent == "vs-visuals":
            run.write("visuals.json", [{"kind": "patch", "ids": [2]}])
        return "xong"

    def vshort(self, args):
        cmd = args[0]
        self.cmds.append(cmd)
        self.order.append(cmd)
        self.args.setdefault(cmd, []).append(args)
        code = (self.codes.get(cmd) or [0]).pop(0) if self.codes.get(cmd) else 0
        if code:
            return code
        if cmd in self.boom:
            raise RuntimeError(f"{cmd} hỏng")
        if cmd == "fetch":
            self.fetched.set()
        if cmd == "detect":
            self.run.write("fragments.json", [{"i": 0}])
            (self.run.path / "sheets").mkdir(exist_ok=True)
            (self.run.path / "sheets" / "sheet00.png").write_bytes(b"")
        if cmd == "text":
            self.run.write("sentences.en.json", SENTS)
        if cmd not in ("check", "approve") and "--design" not in args:
            Run(self.run.path).mark(cmd)  # like the real commands: their own Run, not ours
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
    monkeypatch.setattr(auto, "ROOT", tmp_path)
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
    assert fk.nb == [["auth", "check"], ["source", "add"]]
    assert fk.cmds[:4] == ["fetch", "detect", "text", "check"]


def test_expired_notebooklm_stops_before_research(flow, monkeypatch):
    from vshort.cli import RELOGIN
    run, fk = flow
    monkeypatch.setattr(auto, "notebooklm", lambda args: fk.nb.append(args[:2]) or (4 if args[:2] == ["auth", "check"] else 0))
    assert auto.run_auto(run) == 4
    st = auto.get_state(run)
    assert st["state"] == "error" and st["message"] == RELOGIN and not fk.agents


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
    assert "Bình thường" in fk.prompts["vs-researcher"][1] and "vs-an-du" not in fk.agents


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


def _approved(run):
    for s in ("approve_brief", "research", "source", "fetch", "detect", "transcribe", "text", "translate", "approve_script"):
        run.mark(s)
    run.write("run.json", run.read("run.json") | {"notebook_id": "nb"})
    run.write("sentences.en.json", SENTS)


def test_build_runs_steps_in_order_with_tts_alongside(flow):
    run, fk = flow
    _approved(run)
    auto.run_auto(run)
    c = fk.cmds
    assert {"tts", "clean", "stills", "visuals", "timeline", "render"} <= set(c)
    assert c.index("clean") < c.index("stills") < c.index("visuals") < c.index("timeline") < c.index("render")
    assert c.index("tts") < c.index("timeline")
    assert dict(fk.agents) == {"vs-visuals": 1, "vs-reviewer": 1, "vs-researcher": 1}  # the cover is the researcher's


def test_visuals_failure_follows_the_skill_fallbacks(flow):
    run, fk = flow
    _approved(run)
    fk.codes["visuals"] = [2, 2, 0]
    auto.run_auto(run)
    after = fk.cmds[fk.cmds.index("visuals"):]
    assert after[:4] == ["visuals", "visuals", "stills", "visuals"]
    assert run.read("visuals.json") == [{"kind": "patch", "ids": [2]}]  # the agent's version, put back after stills


def test_visuals_failing_every_way_ends_with_no_visuals(flow):
    run, fk = flow
    _approved(run)
    fk.codes["visuals"] = [2, 2, 2, 0]
    auto.run_auto(run)
    assert run.read("visuals.json") == [] and run.file("visuals.loi.json").exists()


def test_tts_quota_stops_with_reason(flow):
    from vshort.cli import QUOTA
    run, fk = flow
    _approved(run)
    fk.codes["tts"] = [QUOTA]
    assert auto.run_auto(run) == QUOTA
    st = auto.get_state(run)
    assert st["state"] == "error" and "ZeroTTS" in st["message"] and "render" not in fk.cmds


def test_timeline_stale_voice_reruns_tts_once(flow):
    run, fk = flow
    _approved(run)
    fk.codes["timeline"] = [2]
    auto.run_auto(run)
    assert fk.cmds.count("tts") == 2 and fk.cmds.count("timeline") == 2 and "render" in fk.cmds


def test_marks_from_two_threads_are_all_kept(tmp_path):
    import threading
    run = _run(tmp_path)

    def mark_many(prefix):
        for i in range(200):
            Run(run.path).mark(f"{prefix}{i}")

    ts = [threading.Thread(target=mark_many, args=(x,)) for x in "ab"]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(Run(run.path).state) == 400


def _needs(agent, what="lỗi"):
    return {"verdict": "Cần sửa", "findings": [{"agent": agent, "ids": [1], "at": "00:03", "what": what}]}


def test_pass_review_finishes_with_cost_summary(flow):
    run, fk = flow
    _approved(run)
    run.write("cost.json", [{"step": "x", "agent": "vs-visuals", "seconds": 1, "cost_usd": 1.25, "models": [], "ok": True}])
    assert auto.run_auto(run) == OK
    st = auto.get_state(run)
    assert st["state"] == "done"
    for want in ("final.mp4", "Ảnh", "Co giãn", "$1.25", "Đạt"):
        assert want in st["message"], want
    assert "Vượt ngân sách" not in st["message"]


def test_fix_rounds_stop_after_two(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [_needs("visuals")] * 3
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-reviewer"] == 3 and fk.agents["vs-visuals"] == 3
    st = auto.get_state(run)
    assert st["state"] == "done" and "còn lỗi" in st["message"]


def test_translator_finding_waits_for_tai(flow):
    run, fk = flow
    _approved(run)
    run.write("script.vi.json", [{"id": 1, "phrases": "Xin | chào", "note": ""}, {"id": 2, "phrases": "Tạm biệt", "note": ""}])
    before = run.file("script.vi.json").read_text()
    fk.reviews = [_needs("translator", "câu 1 nói quá")]
    assert auto.run_auto(run) == WAIT_SCRIPT
    assert run.file("script.vi.json").read_text() == before and run.file("script.proposed.json").exists()
    assert not run.done("tts") and not run.done("approve_script")
    assert "Chào bạn" in auto.get_state(run)["message"]
    # Tai takes the proposal and approves: the voice is read again, then a fresh reviewer checks the fix
    run.file("script.proposed.json").replace(run.file("script.vi.json"))
    run.mark("approve_script")
    assert auto.run_auto(run) == OK
    assert fk.cmds.count("tts") == 2 and fk.agents["vs-reviewer"] == 2
    assert fk.prompts["vs-reviewer"][1].startswith("Soát lại") and "câu 1 nói quá" in fk.prompts["vs-reviewer"][1]


def test_bad_review_json_stops_without_looping(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [None]
    assert auto.run_auto(run) == FAILED
    assert "review.json" in auto.get_state(run)["message"] and fk.agents["vs-reviewer"] == 1


def test_over_budget_warns(flow):
    run, fk = flow
    _approved(run)
    run.write("cost.json", [{"step": "x", "agent": "vs-reviewer", "seconds": 1, "cost_usd": 5.4, "models": [], "ok": True}])
    assert auto.run_auto(run) == OK
    assert "Vượt ngân sách" in auto.get_state(run)["message"]


# --- final review fixes --------------------------------------------------------------------------------------------

def test_unexpected_exception_ends_in_error_not_running(flow):
    run, fk = flow
    _approved(run)
    fk.boom = {"render"}
    assert auto.run_auto(run) == FAILED
    st = auto.get_state(run)
    assert st["state"] == "error" and "auto.log" in st["message"] and "render hỏng" in st["message"]


def test_crash_inside_a_fix_round_redoes_the_fix_on_resume(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [_needs("visuals", "chữ 8.0.5 sai")]
    fk.die_in = "fix1_visuals"
    with pytest.raises(KeyboardInterrupt):
        auto.run_auto(run)
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-visuals"] == 2  # the first pass, then the fix — redone after the crash
    assert fk.cmds.count("render") == 2 and fk.agents["vs-reviewer"] == 2
    assert fk.prompts["vs-reviewer"][1].startswith("Soát lại")


def test_bad_review_json_is_retried_on_rerun(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [None]
    assert auto.run_auto(run) == FAILED
    assert auto.run_auto(run) == OK and fk.agents["vs-reviewer"] == 2


def test_review_findings_need_what_and_ids(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [{"verdict": "Cần sửa", "findings": [{"agent": "motion", "ids": 3}]}]
    assert auto.run_auto(run) == FAILED
    assert "review.json" in auto.get_state(run)["message"]


def test_translator_fix_redoes_stills_and_visuals_checks(flow):
    run, fk = flow
    _approved(run)
    run.write("script.vi.json", [{"id": 1, "phrases": "Xin | chào", "note": ""}, {"id": 2, "phrases": "Tạm biệt", "note": ""}])
    fk.reviews = [_needs("translator", "câu 1 nói quá")]
    assert auto.run_auto(run) == WAIT_SCRIPT
    assert not run.done("stills") and not run.done("visuals") and run.done("visuals_agent") and not run.done("render")


def test_agents_do_not_inherit_the_claude_session(tmp_path, claude, monkeypatch):
    run = _run(tmp_path)
    monkeypatch.setenv("CLAUDECODE", "1")
    claude({"result": "", "total_cost_usd": 0, "is_error": False}, echo_env="CLAUDECODE")
    assert auto.run_claude(run, "s", "vs-translator", "p", timeout=30) == ""


def test_cost_rows_from_two_threads_are_all_kept(tmp_path):
    run = _run(tmp_path)

    def log_many():
        for _ in range(100):
            auto._log_cost(run, "s", "a", 0, {}, True)

    ts = [threading.Thread(target=log_many) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(run.read("cost.json")) == 200


def test_old_run_gets_clean_and_ignores_motion_marks(flow):
    run, fk = flow
    _approved(run)
    for s in ("plates", "motion_design", "motion", "motion_bind", "stills", "visuals_agent", "visuals", "shots_agent", "shots"):
        run.mark(s)  # a run past the old pictures when the server updated: no `clean` yet
    run.write("motion.json", {"beats": []})
    assert auto.run_auto(run) == OK
    c = fk.cmds
    assert c.index("clean") < c.index("stills") < c.index("visuals") < c.index("render")  # stills of the new clean video
    assert "motion" not in c and "shots" not in c and "plates" not in c
    assert set(fk.agents) <= {"vs-reviewer", "vs-researcher"}  # the old visuals plan is checked again, not redrawn


def test_fix_round_routes_only_visuals_and_translator(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [_needs("visuals", "chữ 8.0.5 sai")]
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-visuals"] == 2 and "chữ 8.0.5 sai" in fk.prompts["vs-visuals"][1]
    assert fk.cmds.count("render") == 2 and fk.prompts["vs-reviewer"][1].startswith("Soát lại")
    run.write("review.json", {"verdict": "Cần sửa", "findings": [{"agent": "motion", "ids": [1], "what": "x"}]})
    with pytest.raises(auto.AgentError):  # the canvas is gone: a reviewer naming it wrote a bad file
        auto.read_review(run)


def test_finish_reports_long_holds_from_pieces_json(flow):
    run, fk = flow
    _approved(run)
    piece = {"src": 0, "src_end": 1, "dst": 0, "dst_end": 1, "speed": 1}
    run.write("pieces.json", [piece | {"id": 1, "hold": 0.4, "dropped": 0.0}, piece | {"id": 2, "hold": 2.3, "dropped": 0.0},
                              piece | {"id": 3, "hold": 0.0, "dropped": 1.2}])
    assert auto._retime_note(run) == "Co giãn: câu 2 giữ 2,3 s; câu 3 bỏ đuôi 1,2 s"
    run.write("pieces.json", [piece | {"id": 1, "hold": 0.4, "dropped": 0.0}])
    assert auto._retime_note(run) == "Co giãn: không câu nào phải giữ hay bỏ đuôi"
