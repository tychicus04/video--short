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
        self.brief = "# Tiêu đề\n"  # what the researcher writes to brief.vi.md
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
            f("brief.vi.md").write_text(self.brief)
            f("brief.en.md").write_text("# Title\n")
            if not self.no_notebook:
                f("notebook.txt").write_text("nb-123\n")
        elif agent == "vs-transcriber":
            f("fragments_text.json").write_text('{"0": "Hello there."}')
        elif agent == "vs-translator" and "script.proposed.json" in prompt:
            run.write("script.proposed.json", [{"id": 1, "phrases": "Chào | bạn", "note": "sửa theo review"},
                                               {"id": 2, "phrases": "Tạm biệt", "note": ""}])
        elif agent in ("vs-reviewer", "vs-reviewer-neon"):
            r = self.reviews.pop(0) if self.reviews else {"verdict": "Đạt", "findings": []}
            if r is not None:
                run.write("review.json", r)
            run.file("review.md").write_text("Kết luận: " + (r or {}).get("verdict", "?"))
        elif agent == "vs-translator":
            run.write("script.vi.json", [{"id": 1, "phrases": "Xin | chào", "note": ""},
                                         {"id": 2, "phrases": "Tạm biệt", "note": "ngắn hơn"}])
        elif agent == "vs-writer" and "script.proposed.json" in prompt:
            run.write("script.proposed.json", [{"id": 1, "phrases": "Tiêu đề", "note": ""},
                                               {"id": 2, "phrases": "Bình thường | máy chủ chạy", "note": "sửa theo review"}])
        elif agent == "vs-scene":
            run.write("scene.json", {"sections": []})
        elif agent == "vs-writer":
            run.write("script.vi.json", [{"id": 1, "phrases": "Tiêu đề", "note": ""},
                                         {"id": 2, "phrases": "Bình thường | máy chủ chạy đúng", "note": "theo brief"}])
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
    run.write("cost.json", [{"step": "x", "agent": "vs-reviewer", "seconds": 1, "cost_usd": auto.BUDGET + 0.4, "models": [], "ok": True}])
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


# --- the neon style: the brief, then vs-writer, then the voice ------------------------------------------------------

MECHANISM = "Cơ chế từng bước\n0. Bình thường: máy chủ chạy đúng.\n1. Gói tin đến.\n2. Máy chủ bị chiếm.\n"


@pytest.fixture
def neon_flow(flow):
    run, fk = flow
    run.write("run.json", run.read("run.json") | {"style": "neon"})
    fk.brief = "# Tiêu đề\n\n" + MECHANISM  # the fake researcher's brief has the mechanism the gate wants
    return run, fk


def test_neon_stops_for_brief_then_script_and_never_touches_notebooklm_video(neon_flow):
    run, fk = neon_flow
    assert auto.run_auto(run) == WAIT_BRIEF
    run.mark("approve_brief")
    assert auto.run_auto(run) == WAIT_SCRIPT and run.file("loi.md").exists()
    assert fk.agents["vs-writer"] == 1 and "check" in fk.cmds
    assert not {"fetch", "detect", "text"} & set(fk.cmds) and ["source", "add"] not in fk.nb
    run.mark("approve_script")
    auto.run_auto(run)  # on to the voice and its timeline, then the picture
    assert fk.order.index("tts") < fk.order.index("timeline")


def test_neon_resume_stays_neon(neon_flow):  # Review Focus 5
    run, fk = neon_flow
    auto.run_auto(run)
    run.mark("approve_brief")
    auto.run_auto(run)
    assert auto.get_state(run)["state"] == "wait_script"
    assert fk.agents["vs-translator"] == 0 and "fetch" not in fk.cmds
    before = (dict(fk.agents), list(fk.cmds))
    assert auto.run_auto(run) == WAIT_SCRIPT  # a rerun of the stop repeats nothing
    assert (dict(fk.agents), list(fk.cmds)) == before


def test_neon_auto_mode_stops_without_mechanism(neon_flow):
    run, fk = neon_flow
    run.write("run.json", run.read("run.json") | {"auto": True})
    fk.brief = "# Tiêu đề\n"  # no "Cơ chế từng bước"
    assert auto.run_auto(run) == WAIT_BRIEF and "cơ chế" in auto.get_state(run)["message"]
    assert auto.get_state(run)["state"] == "wait_brief" and fk.agents["vs-researcher"] == 2 and not fk.agents["vs-writer"]


@pytest.mark.parametrize("steps", [
    "1. Một.\n2. Hai.\n3. Ba.\n",                       # three steps, but no step 0
    "0. Bình thường: ổn.\n1. Một.\n",                   # step 0 and only one more
    "Không có\n",
])
def test_neon_mechanism_gate_needs_step_0_and_two_more(neon_flow, steps):
    run, fk = neon_flow
    run.write("run.json", run.read("run.json") | {"auto": True})
    fk.brief = "# Tiêu đề\n\nCơ chế từng bước\n" + steps
    assert auto.run_auto(run) == WAIT_BRIEF and not fk.agents["vs-writer"]
    assert "cơ chế" in auto.get_state(run)["message"] and f"{run.path}/brief.vi.md" in auto.get_state(run)["message"]


def test_neon_gate_also_stops_an_approved_brief_and_passes_once_fixed(neon_flow):
    run, fk = neon_flow
    fk.brief = "# Tiêu đề\n"
    auto.run_auto(run)
    run.mark("approve_brief")
    assert auto.run_auto(run) == WAIT_BRIEF and "cơ chế" in auto.get_state(run)["message"] and not fk.agents["vs-writer"]
    run.file("brief.vi.md").write_text("# Tiêu đề\n\n" + MECHANISM)  # Tai fixes the brief and runs `vshort auto` again
    assert auto.run_auto(run) == WAIT_SCRIPT and fk.agents["vs-writer"] == 1


def test_neon_auto_mode_checks_the_brief_for_the_mechanism_not_the_english(neon_flow):
    run, fk = neon_flow
    run.write("run.json", run.read("run.json") | {"auto": True})
    assert auto.run_auto(run) == WAIT_SCRIPT
    research, check = fk.prompts["vs-researcher"]
    assert "KHÔNG viết" in research and "brief.en.md" in research
    assert "Cơ chế từng bước" in research and "Soát brief" in check
    assert "cả hai bản" not in check and "brief.en.md" not in check and "Không có" not in check


def test_neon_stop_messages_never_send_tai_to_an_english_brief_or_a_translation(neon_flow):
    run, fk = neon_flow
    auto.run_auto(run)
    brief_stop = auto.get_state(run)["message"]
    run.mark("approve_brief")
    auto.run_auto(run)
    script_stop = auto.get_state(run)["message"]
    for m in (brief_stop, script_stop):
        assert "brief.en.md" not in m and "bản dịch" not in m and "translation.md" not in m
    assert f"{run.path}/brief.vi.md" in brief_stop and f"vshort approve {run.path} brief" in brief_stop
    assert f"{run.path}/loi.md" in script_stop and f"vshort approve {run.path} script" in script_stop
    assert not run.file("translation.md").exists()


def test_neon_writer_gets_the_run_and_its_check_must_pass(neon_flow):
    run, fk = neon_flow
    run.mark("approve_brief")
    fk.codes["check"] = [2]
    assert auto.run_auto(run) == FAILED
    st = auto.get_state(run)
    assert st["state"] == "error" and "vshort check" in st["message"] and "mã 2" in st["message"]
    assert not run.done("write") and not run.file("loi.md").exists()
    assert str(run.path) in fk.prompts["vs-writer"][0]
    assert auto.run_auto(run) == WAIT_SCRIPT and run.done("write")  # the rerun writes again, the check passes


def test_neon_loi_md_has_a_row_per_sentence_and_the_estimated_length(neon_flow):
    from vshort import script
    run, fk = neon_flow
    run.mark("approve_brief")
    auto.run_auto(run)
    rows = run.file("loi.md").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("| id |") and "âm tiết" in rows[0] and "giây" in rows[0] and "note" in rows[0]
    assert [c.strip() for c in rows[2].split("|")[1:-1]] == ["1", "Tiêu đề", "2", f"{2 / script.PACE:.1f}".replace(".", ","), ""]
    cells = [c.strip() for c in rows[3].split("|")[1:-1]]
    assert cells == ["2", "Bình thường máy chủ chạy đúng", "6", f"{6 / script.PACE:.1f}".replace(".", ","), "theo brief"]
    assert "|" not in cells[1] and rows[-1] == f"Tổng: 8 âm tiết, ~{8 / script.PACE:.0f} giây"


def test_neon_goes_on_from_the_approved_script_to_the_voice_its_timeline_and_the_picture(neon_flow):
    run, fk = neon_flow
    for s in ("approve_brief", "research", "write", "approve_script"):
        run.mark(s)
    run.write("script.vi.json", [{"id": 1, "phrases": "Tiêu đề", "note": ""}])
    run.file("brief.vi.md").write_text(fk.brief)
    assert auto.run_auto(run) == OK
    assert fk.cmds[:2] == ["tts", "timeline"] and not fk.agents["vs-writer"]  # nothing is written again
    assert not {"fetch", "detect", "text", "clean", "stills", "visuals"} & set(fk.cmds) and not fk.agents["vs-visuals"]


def test_neon_stale_voice_reads_again_once_and_quota_stops(neon_flow):
    from vshort.cli import QUOTA
    run, fk = neon_flow
    for s in ("approve_brief", "research", "write", "approve_script"):
        run.mark(s)
    run.file("brief.vi.md").write_text(fk.brief)
    fk.codes["timeline"] = [2]
    auto.run_auto(run)
    assert fk.cmds.count("tts") == 2 and fk.cmds.count("timeline") == 2 and run.done("timeline")
    run.unmark("tts", "timeline")
    fk.codes["tts"] = [QUOTA]
    assert auto.run_auto(run) == QUOTA and "ZeroTTS" in auto.get_state(run)["message"]


# --- the neon style: scene, render, review, the fix rounds -------------------------------------------------------------

def approve_all(run, fk):
    """Brief approved, script approved: the run is at the voice and the picture."""
    assert auto.run_auto(run) == WAIT_BRIEF
    run.mark("approve_brief")
    assert auto.run_auto(run) == WAIT_SCRIPT
    run.mark("approve_script")


def _scene_finding(what="nhãn đè", fix="dời chip"):
    return {"verdict": "Cần sửa", "findings": [{"agent": "scene", "ids": [5], "at": "00:21", "what": what, "fix": fix}]}


def test_neon_runs_through_to_done(neon_flow):
    run, fk = neon_flow
    approve_all(run, fk)                                         # brief, script
    assert auto.run_auto(run) == OK and auto.get_state(run)["state"] == "done"
    assert fk.order.index("scene") < fk.order.index("render") and fk.agents["vs-reviewer-neon"] == 1
    assert fk.order.index("timeline") < fk.order.index("vs-scene") < fk.order.index("scene")  # the agent, then the check
    assert not fk.agents["vs-reviewer"] and not fk.agents["vs-visuals"] and not fk.agents["vs-translator"]
    msg = auto.get_state(run)["message"]
    assert "final.mp4" in msg and "Đạt" in msg and "Chi phí Claude" in msg
    assert "Co giãn" not in msg and "visuals" not in msg


def test_neon_scene_agent_gets_the_run_and_does_not_start_in_fix_mode(neon_flow):
    run, fk = neon_flow
    approve_all(run, fk)
    auto.run_auto(run)
    [prompt] = fk.prompts["vs-scene"]
    assert str(run.path) in prompt and "review.json" not in prompt and "Sửa theo" not in prompt


def test_neon_finish_leaves_out_the_old_flows_lines(neon_flow):
    run, fk = neon_flow
    run.write("visuals.json", [{"kind": "patch", "id": 2, "old": "a", "new": "b"}])  # left over from nothing: still not listed
    approve_all(run, fk)
    auto.run_auto(run)
    assert "patch" not in auto.get_state(run)["message"] and "Co giãn" not in auto.get_state(run)["message"]


def test_neon_scene_that_fails_vshort_scene_stops_and_the_rerun_asks_again(neon_flow):
    run, fk = neon_flow
    approve_all(run, fk)
    fk.codes["scene"] = [2]
    assert auto.run_auto(run) == FAILED
    st = auto.get_state(run)
    assert st["state"] == "error" and "vshort scene" in st["message"] and "mã 2" in st["message"]
    assert not run.done("scene") and "render" not in fk.cmds and fk.agents["vs-scene"] == 1
    assert auto.run_auto(run) == OK and fk.agents["vs-scene"] == 2


def test_neon_scene_finding_replans_and_rerenders(neon_flow):
    run, fk = neon_flow
    fk.reviews = [_scene_finding()]
    approve_all(run, fk)
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-scene"] == 2 and fk.cmds.count("render") == 2 and fk.agents["vs-reviewer-neon"] == 2
    fix_prompt = fk.prompts["vs-scene"][1]
    assert "review.json" in fix_prompt and "nhãn đè" in fix_prompt and "dời chip" in fix_prompt and "00:21" in fix_prompt
    assert fk.cmds.count("scene") == 2 and run.done("fixed1") and run.done("fix1_scene")
    assert fk.prompts["vs-reviewer-neon"][1].startswith("Soát lại") and "dời chip" in fk.prompts["vs-reviewer-neon"][1]
    # the order of the fix: the agent, `vshort scene` again, and only then the render
    tail = fk.order[fk.order.index("vs-scene", fk.order.index("render")):]
    assert tail[:3] == ["vs-scene", "scene", "render"]


def test_neon_fix_that_does_not_pass_vshort_scene_is_asked_again_on_resume(neon_flow):
    run, fk = neon_flow
    fk.reviews = [_scene_finding()]
    approve_all(run, fk)
    fk.codes["scene"] = [0, 1]                       # the first plan passes, the fix does not
    assert auto.run_auto(run) == FAILED and "vshort scene" in auto.get_state(run)["message"]
    assert not run.done("fix1_scene") and fk.cmds.count("render") == 1
    assert auto.run_auto(run) == OK and fk.agents["vs-scene"] == 3 and fk.cmds.count("render") == 2


def test_neon_crash_inside_a_scene_fix_redoes_the_fix_on_resume(neon_flow):
    run, fk = neon_flow
    fk.reviews = [_scene_finding()]
    approve_all(run, fk)
    fk.die_in = "fix1_scene"
    with pytest.raises(KeyboardInterrupt):
        auto.run_auto(run)
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-scene"] == 2 and fk.cmds.count("render") == 2 and fk.agents["vs-reviewer-neon"] == 2


def test_neon_fix_rounds_stop_after_two(neon_flow):
    run, fk = neon_flow
    fk.reviews = [_scene_finding()] * 3
    approve_all(run, fk)
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-reviewer-neon"] == 3 and fk.agents["vs-scene"] == 3 and fk.cmds.count("render") == 3
    assert auto.get_state(run)["state"] == "done" and "còn lỗi" in auto.get_state(run)["message"]


def test_neon_writer_finding_waits_for_tai_and_unmarks_voice_and_scene(neon_flow):   # Review Focus 1
    run, fk = neon_flow
    fk.reviews = [{"verdict": "Cần sửa", "findings": [{"agent": "writer", "ids": [3], "what": "nói quá brief", "fix": "bỏ 'hoàn toàn'"}]}]
    approve_all(run, fk)
    assert auto.run_auto(run) == WAIT_SCRIPT and run.file("script.proposed.json").exists()
    assert not any(run.done(s) for s in ("approve_script", "tts", "timeline", "scene", "render"))
    assert run.done("write") and run.done("fixed1")
    prompt = fk.prompts["vs-writer"][1]
    assert "script.proposed.json" in prompt and "nói quá brief" in prompt and "bỏ 'hoàn toàn'" in prompt
    msg = auto.get_state(run)["message"]
    assert auto.get_state(run)["state"] == "wait_script" and "lời" in msg and "bản dịch" not in msg
    assert "máy chủ chạy" in msg and f"vshort approve {run.path} script" in msg and not fk.agents["vs-translator"]


def test_neon_after_tai_approves_the_new_words_the_voice_the_scene_and_the_render_are_redone(neon_flow):
    run, fk = neon_flow
    fk.reviews = [{"verdict": "Cần sửa", "findings": [{"agent": "writer", "ids": [3], "what": "nói quá brief"}]}]
    approve_all(run, fk)
    assert auto.run_auto(run) == WAIT_SCRIPT
    run.file("script.proposed.json").replace(run.file("script.vi.json"))
    run.mark("approve_script")
    assert auto.run_auto(run) == OK
    assert fk.cmds.count("tts") == 2 and fk.agents["vs-scene"] == 2 and fk.cmds.count("render") == 2
    assert fk.agents["vs-reviewer-neon"] == 2 and fk.prompts["vs-reviewer-neon"][1].startswith("Soát lại")
    assert fk.agents["vs-writer"] == 2  # the first draft and the fix: not asked a third time


def test_neon_scene_and_writer_findings_in_one_round_fix_the_scene_first_then_wait(neon_flow):
    run, fk = neon_flow
    fk.reviews = [{"verdict": "Cần sửa", "findings": [
        {"agent": "scene", "ids": [2], "what": "chip đè", "fix": "dời"}, {"agent": "writer", "ids": [3], "what": "nói quá"}]}]
    approve_all(run, fk)
    assert auto.run_auto(run) == WAIT_SCRIPT
    assert fk.agents["vs-scene"] == 2 and "chip đè" in fk.prompts["vs-scene"][1] and "nói quá" not in fk.prompts["vs-scene"][1]
    assert "nói quá" in fk.prompts["vs-writer"][1] and "chip đè" not in fk.prompts["vs-writer"][1]
    assert not run.done("scene") and not run.done("render")


def test_neon_reviewer_may_only_name_scene_writer_or_none(neon_flow):
    run, fk = neon_flow
    fk.reviews = [{"verdict": "Cần sửa", "findings": [{"agent": "visuals", "ids": [1], "what": "x"}]}]
    approve_all(run, fk)
    assert auto.run_auto(run) == FAILED and "review.json" in auto.get_state(run)["message"]
    assert fk.agents["vs-reviewer-neon"] == 1 and fk.agents["vs-scene"] == 1


def test_read_review_kinds_and_the_optional_fix(tmp_path):
    run = _run(tmp_path)
    ok = {"verdict": "Cần sửa", "findings": [{"agent": "scene", "ids": [1], "what": "x", "fix": "y"}, {"agent": "none", "what": "z"}]}
    run.write("review.json", ok)
    assert auto.read_review(run, ("scene", "writer", "none")) == ok
    with pytest.raises(auto.AgentError):                                    # the old default does not know "scene"
        auto.read_review(run)
    run.write("review.json", {"verdict": "Cần sửa", "findings": [{"agent": "translator", "ids": [1], "what": "x", "fix": "y"}]})
    assert auto.read_review(run)["findings"][0]["fix"] == "y"               # the old kinds take a fix too
    with pytest.raises(auto.AgentError):                                    # and the neon ones refuse "translator"
        auto.read_review(run, ("scene", "writer", "none"))
    run.write("review.json", {"verdict": "Cần sửa", "findings": [{"agent": "scene", "ids": [1], "what": "x", "fix": 3}]})
    with pytest.raises(auto.AgentError):                                    # fix is a string
        auto.read_review(run, ("scene", "writer", "none"))
    run.write("review.json", {"verdict": "Cần sửa", "findings": [{"agent": "none", "ids": [1], "what": "x", "fix": None}]})
    auto.read_review(run, ("scene", "writer", "none"))                      # null is "no fix", not a bad file


def test_the_old_findings_list_shows_a_fix_only_when_there_is_one():
    old = {"agent": "visuals", "ids": [2], "at": "00:03", "what": "chữ sai"}
    assert auto._items([old]) == "- visuals, câu 2, 00:03: chữ sai"
    assert auto._items([old | {"fix": "sửa thành 8.1"}]) == "- visuals, câu 2, 00:03: chữ sai — sửa: sửa thành 8.1"


def test_neon_reading_the_voice_again_throws_away_the_scene_and_the_render(neon_flow):   # Ruling 3
    run, fk = neon_flow
    for s in ("approve_brief", "research", "write", "approve_script", "tts", "scene", "render"):
        run.mark(s)
    run.file("brief.vi.md").write_text(fk.brief)
    fk.codes["timeline"] = [2]                       # the voice was made from another script
    auto.run_auto(run)
    assert fk.cmds.count("tts") == 1 and fk.cmds.count("timeline") == 2                  # `tts` was unmarked by the stale voice
    assert fk.agents["vs-scene"] == 1 and fk.cmds.count("scene") == 1 and fk.cmds.count("render") == 1
    assert fk.order.index("timeline") < fk.order.index("vs-scene") < fk.order.index("render")


def test_old_flow_reading_the_voice_again_leaves_scene_and_render_alone(flow):
    run, fk = flow
    run.mark("scene")
    run.mark("render")
    fk.codes["timeline"] = [2]
    auto._timeline(run)
    assert run.done("scene") and run.done("render") and fk.cmds.count("tts") == 1


def test_neon_agents_have_their_timeouts():
    assert auto.TIMEOUT["vs-scene"] == 2400 and auto.TIMEOUT["vs-reviewer-neon"] == 3600 and auto.BUDGET == 30.0


def test_neon_a_scene_that_is_made_again_is_rendered_again(neon_flow):
    """`vshort scene` refused by hand unmarks `scene` only: the next run remakes the scene and must not keep the old video."""
    run, fk = neon_flow
    for s in ("approve_brief", "research", "write", "approve_script", "tts", "timeline", "render"):
        run.mark(s)
    run.file("brief.vi.md").write_text(fk.brief)
    assert not run.done("scene")
    assert auto.run_auto(run) == OK
    assert fk.agents["vs-scene"] == 1 and fk.cmds.count("render") == 1
    assert fk.order.index("scene") < fk.order.index("render")


def test_neon_recheck_after_a_writer_round_asks_for_the_whole_video(neon_flow):   # Ruling 32a
    run, fk = neon_flow
    fk.reviews = [{"verdict": "Cần sửa", "findings": [{"agent": "scene", "ids": [2], "what": "chip đè", "fix": "dời"},
                                                      {"agent": "writer", "ids": [3], "what": "nói quá", "fix": "bỏ"}]}]
    approve_all(run, fk)
    assert auto.run_auto(run) == WAIT_SCRIPT
    run.file("script.proposed.json").replace(run.file("script.vi.json"))
    run.mark("approve_script")
    assert auto.run_auto(run) == OK
    again = fk.prompts["vs-reviewer-neon"][1]
    assert again.startswith("Soát lại") and "cả video" in again and "chỉ các phần đã sửa" not in again
    assert "nói quá" in again and "chip đè" in again and str(run.path) in again  # what was fixed is listed all the same


def test_neon_recheck_after_a_scene_round_stays_on_the_fixed_parts(neon_flow):
    run, fk = neon_flow
    fk.reviews = [_scene_finding()]
    approve_all(run, fk)
    assert auto.run_auto(run) == OK
    again = fk.prompts["vs-reviewer-neon"][1]
    assert again.startswith("Soát lại: chỉ các phần đã sửa") and "cả video" not in again


def test_old_recheck_prompt_is_unchanged(flow):
    run, fk = flow
    _approved(run)
    fk.reviews = [_needs("translator", "câu 1 nói quá")]
    auto.run_auto(run)
    run.file("script.proposed.json").replace(run.file("script.vi.json"))
    run.mark("approve_script")
    auto.run_auto(run)
    assert fk.prompts["vs-reviewer"][1].startswith("Soát lại: chỉ các phần đã sửa.\n\nRUN=")
