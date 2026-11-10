import json
import os

from vshort import stages
from vshort.stages import DEFAULT_SECONDS as D

TYP = dict(D)
TOTAL = sum(D.values())
AFTER_APPROVE = D["build"] + D["render"] + D["review"] + D["cover"]
# every step that is always marked, research … review0, for an automatic run
THROUGH_REVIEW0 = {"research", "brief_check", "source", "fetch", "detect", "transcribe", "text", "translate",
                   "approve_script", "clean", "stills", "tts", "visuals", "visuals_agent", "timeline", "render", "review0"}


def by_key(v):
    return {s["key"]: s for s in v["stages"]}


def test_stage_of():
    assert stages.stage_of("fetch") == "notebooklm" and stages.stage_of("clean") == "build"
    assert stages.stage_of("fix1_visuals") == "review"
    assert stages.stage_of("motion_design") is None and stages.stage_of("shots") is None  # gone with the drawn pictures
    assert stages.stage_of("fixed2") == "review"
    assert stages.stage_of("check") is None


def test_typical_is_the_median_of_recent_runs_else_default():
    h = [{"source": {"start": 0, "end": s}} for s in (600, 1500, 900)]
    assert stages.typical(h)["notebooklm"] == 900
    assert stages.typical([])["review"] == 720


def test_span_leaves_out_the_gap_before_a_rerun():
    # render failed, Tai pressed "Chạy lại" an hour later: the hour is not render's time
    times = {"timeline": {"start": 0, "end": 10}, "render": {"start": 3600, "end": 3700}}
    assert stages.span(times, "render") == 110
    assert stages.span({}, "render") is None


def test_running_notebooklm_two_numbers():
    v = stages.view("running", True, {"research", "brief_check"},
                    {"source": {"start": 0}, "fetch": {"start": 10}}, TYP, now=10 + 660)
    st = by_key(v)
    assert st["brief"]["status"] == "done"
    assert st["notebooklm"]["status"] == "running" and st["notebooklm"]["seconds"] == 670
    assert st["notebooklm"]["overdue"] is False
    assert [s["step"] for s in st["notebooklm"]["steps"]] == ["source", "fetch"]
    assert st["subtitles"]["status"] == "next"
    assert v["current"] == 2
    assert v["eta"] == {"stop": "Duyệt bản dịch", "until_stop": (900 - 670) + 180 + 240, "after_stop": AFTER_APPROVE}
    assert v["percent"] == round(100 * (480 + 300 + 670) / TOTAL)


def test_overdue_stage_floors_and_flags():
    v = stages.view("running", True, {"research", "brief_check"},
                    {"source": {"start": 0}, "fetch": {"start": 10}}, TYP, now=10 + 2000)
    assert by_key(v)["notebooklm"]["overdue"] is True
    assert v["eta"]["until_stop"] == 60 + 180 + 240
    assert v["percent"] == round(100 * (480 + 300 + 900) / TOTAL)


def test_waiting_for_translation_is_you():
    done = {"research", "brief_check", "source", "fetch", "detect", "transcribe", "text", "translate"}
    v = stages.view("wait_script", True, done, {}, TYP, now=0)
    assert by_key(v)["approve"]["status"] == "you"
    assert v["current"] == 5
    assert v["eta"] == {"stop": "Duyệt bản dịch", "until_stop": 0, "after_stop": AFTER_APPROVE}


def test_brief_stop_when_not_auto():
    v = stages.view("running", False, set(), {"research": {"start": 0}}, TYP, now=100)
    assert by_key(v)["research"]["status"] == "running"
    assert v["eta"]["stop"] == "Duyệt brief"
    assert v["eta"]["until_stop"] == 480 - 100
    assert v["eta"]["after_stop"] == TOTAL - 480 - 300


def test_fix_round_shows_review_not_render():
    now = 1000
    v = stages.view("running", True, THROUGH_REVIEW0 - {"render"}, {"fix1_visuals": {"start": now - 30}}, TYP, now)
    st = by_key(v)
    assert st["review"]["status"] == "running"
    assert st["render"]["status"] == "done"


def test_fix_round_rerun_stays_on_review():
    # fix1_visuals is marked, then `vshort visuals` and render run again: still "Soát và sửa", never back to stage 7 or 8
    times = {"review0": {"start": 0, "end": 100}, "fix1_visuals": {"start": 110, "end": 200}, "visuals": {"start": 210}}
    v = stages.view("running", True, (THROUGH_REVIEW0 - {"render"}) | {"fix1_visuals"}, times, TYP, now=300)
    st = by_key(v)
    assert st["review"]["status"] == "running"
    assert st["render"]["status"] == "done" and st["build"]["status"] == "done"
    assert v["percent"] >= round(100 * (TOTAL - D["review"] - D["cover"]) / TOTAL)


def test_translator_resume_shows_build():
    # Tai took the translator's proposal: the voice and pictures are made again before a fresh review
    again = {"tts", "timeline", "render", "stills", "visuals"}
    done = (THROUGH_REVIEW0 - again) | {"fix1_translator", "fixed1"}
    times = {"fix1_translator": {"start": 100, "end": 200}, "tts": {"start": 500}}
    st = by_key(stages.view("running", True, done, times, TYP, now=600))
    assert st["build"]["status"] == "running"
    assert st["review"]["status"] == "next"


def test_rerun_of_an_earlier_step_does_not_walk_back():
    # timeline answered 2: the voice is read again while render is still open; the page stays at "Dựng video"
    done = THROUGH_REVIEW0 - {"render", "review0", "tts"}
    times = {"timeline": {"start": 0, "end": 10}, "render": {"start": 20}, "tts": {"start": 200}}
    v = stages.view("running", True, done, times, TYP, now=210)
    assert by_key(v)["render"]["status"] == "running" and by_key(v)["build"]["status"] == "done"


def test_finished_is_all_done():
    v = stages.view("done", True, THROUGH_REVIEW0 | {"cover"}, {}, TYP, now=0)
    assert {s["status"] for s in v["stages"]} == {"done"}
    assert v["percent"] == 100 and v["current"] is None
    assert v["eta"] == {"stop": None, "until_stop": None, "after_stop": None}


def test_error_marks_first_unfinished_stage():
    v = stages.view("error", False, {"research", "approve_brief"}, {}, TYP, now=0)
    assert [s["status"] for s in v["stages"]] == ["done", "done", "error"] + ["next"] * 7
    assert v["current"] == 2


def test_view_without_times_uses_state_only():
    v = stages.view("running", False, {"research", "approve_brief", "source"}, {}, TYP, now=0)
    st = by_key(v)
    assert st["notebooklm"]["status"] == "running" and st["notebooklm"]["seconds"] is None
    assert st["research"]["seconds"] is None


def test_history_reads_recent_done_runs(tmp_path):
    def run(name, state, mtime, times=True):
        d = tmp_path / name
        d.mkdir()
        (d / "auto.json").write_text(json.dumps({"state": state}))
        os.utime(d / "auto.json", (mtime, mtime))
        if times:
            (d / "times.json").write_text(json.dumps({"research": {"start": 0, "end": mtime}}))

    for i in range(1, 7):
        run(f"d{i}", "done", i)
    run("e", "error", 99)
    run("n", "done", 98, times=False)
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "auto.json").write_text("[")
    assert [h["research"]["end"] for h in stages.history(tmp_path)] == [6, 5, 4, 3, 2]


def test_fix_round_without_a_fix_step_is_review():
    # a round whose fix has not started has no fix1_* step yet: auto.json's round says the video is in round 1
    done = THROUGH_REVIEW0 - {"render"}
    times = {"render": {"start": 50}}
    assert by_key(stages.view("running", True, done, times, TYP, now=60, fix_round=1))["review"]["status"] == "running"
    # round 1 whose fixes are done (Tai took the translator's proposal): the rerun is what it looks like
    st = by_key(stages.view("running", True, done | {"fixed1"}, times, TYP, now=60, fix_round=1))
    assert st["render"]["status"] == "running" and st["review"]["status"] == "next"


def test_the_render_stage_says_what_it_does_now():
    assert [stages.stage_of(s) for s in ("timeline", "render")] == ["render"] * 2
    assert "Co giãn" in next(what for k, _, what in stages.STAGES if k == "render")
    assert "xóa phụ đề Anh" in next(what for k, _, what in stages.STAGES if k == "build")


# --- the neon style: nine stages, the voice and the scene in place of NotebookLM -----------------------------------

NEON = stages.FLOWS["neon"]
NT = dict(NEON.default_seconds)
NEON_KEYS = ["research", "brief", "write", "approve", "voice", "scene", "render", "review", "cover"]
NEON_DONE = {"research", "brief_check", "write", "approve_script", "tts", "timeline", "scene", "render", "review0"}


def nview(*args, **kw):
    return stages.view(*args, **kw, style="neon")


def test_neon_stage_list_and_steps():
    assert [k for k, _, _ in NEON.stages] == NEON_KEYS
    assert [label for _, label, _ in NEON.stages] == ["Tìm hiểu", "Duyệt brief", "Viết lời", "Duyệt lời", "Giọng đọc",
                                                     "Kịch bản hình", "Dựng video", "Soát và sửa", "Ảnh bìa và xuất"]
    assert set(NEON.default_seconds) == set(NEON_KEYS) and NEON.default_seconds["scene"] == 900 and NEON.default_seconds["render"] == 600
    for step, key in [("write", "write"), ("approve_script", "approve"), ("tts", "voice"), ("timeline", "voice"), ("scene", "scene"),
                      ("render", "render"), ("review0", "review"), ("fix1_scene", "review"), ("fix2_writer", "review"),
                      ("fixed1", "review"), ("cover", "cover"), ("brief_check", "brief")]:
        assert stages.stage_of(step, "neon") == key, step
    # the old flow's names mean what they meant
    assert stages.stage_of("tts") == "build" and stages.stage_of("timeline") == "render"
    assert stages.stage_of("write") is None and stages.stage_of("scene") is None and stages.stage_of("fix1_scene") == "review"
    assert stages.stage_of("fetch", "neon") is None  # NotebookLM's steps are not part of a neon run


def test_old_runs_unchanged():
    assert stages.FLOWS["old"] == (stages.STAGES, stages.STEPS_OF, stages.DEFAULT_SECONDS) and len(stages.STAGES) == 10
    args = ("running", True, {"research", "brief_check"}, {"source": {"start": 0}, "fetch": {"start": 10}}, TYP, 700)
    assert stages.view(*args) == stages.view(*args, style="old")
    assert stages.typical([]) == stages.typical([], "old") == TYP


def test_neon_waiting_script_shows_duyet_loi():
    v = nview("wait_script", True, {"research", "brief_check", "write"}, {}, NT, now=0)
    st = by_key(v)
    assert st["approve"]["label"] == "Duyệt lời" and st["approve"]["status"] == "you"
    assert [s["status"] for s in v["stages"]] == ["done"] * 3 + ["you"] + ["next"] * 5 and v["current"] == 3
    assert v["eta"] == {"stop": "Duyệt lời", "until_stop": 0,
                        "after_stop": sum(NT[k] for k in ("voice", "scene", "render", "review", "cover"))}


def test_neon_brief_stop_and_running_voice():
    v = nview("wait_brief", False, {"research"}, {}, NT, now=0)
    assert v["current"] == 1 and by_key(v)["brief"]["status"] == "you" and v["eta"]["stop"] == "Duyệt brief"
    # tts and timeline are one stage, the voice; the steps shown are the two
    done = {"research", "brief_check", "write", "approve_script", "tts"}
    times = {"tts": {"start": 0, "end": 100}, "timeline": {"start": 105}}
    v = nview("running", True, done, times, NT, now=110)
    st = by_key(v)
    assert v["current"] == 4 and st["voice"]["status"] == "running" and st["voice"]["seconds"] == 105
    assert [(s["step"], s["status"]) for s in st["voice"]["steps"]] == [("tts", "done"), ("timeline", "running")]
    assert st["scene"]["status"] == "next"


def test_neon_scene_and_render_each_have_their_own_stage():
    done = {"research", "brief_check", "write", "approve_script", "tts", "timeline"}
    v = nview("running", True, done, {"scene": {"start": 0}}, NT, now=300)
    st = by_key(v)
    assert st["scene"]["status"] == "running" and st["scene"]["seconds"] == 300 and st["voice"]["status"] == "done"
    assert st["render"]["status"] == "next"
    v = nview("running", True, done | {"scene"}, {"scene": {"start": 0, "end": 800}, "render": {"start": 810}}, NT, now=900)
    assert by_key(v)["render"]["status"] == "running" and by_key(v)["scene"]["seconds"] == 800


def test_neon_fix_round_reads_as_review_with_what_is_fixed():
    done = NEON_DONE - {"render"}
    times = {"review0": {"start": 0, "end": 100}, "fix1_scene": {"start": 110, "end": 200}, "scene": {"start": 210}}
    v = nview("running", True, done | {"fix1_scene"}, times, NT, now=300)
    st = by_key(v)
    assert st["review"]["status"] == "running" and st["render"]["status"] == "done" and st["scene"]["status"] == "done"
    assert [(s["step"], s["label"]) for s in st["review"]["steps"]] == [("review0", "Soát"), ("fix1_scene", "Sửa vòng 1: kịch bản hình")]
    # the writer's fix: the voice and the picture are made again, still shown as the review until fixed1
    v = nview("running", True, NEON_DONE - {"tts"}, {"fix1_writer": {"start": 0, "end": 5}, "tts": {"start": 9}}, NT, now=20, fix_round=1)
    assert by_key(v)["review"]["status"] == "running"
    assert stages._label("fix2_writer", "neon") == "Sửa vòng 2: lời"


def test_neon_without_times_is_read_from_state_and_a_finished_run_is_all_done():
    v = nview("running", True, {"research", "brief_check", "write", "approve_script"}, {}, NT, now=0)
    assert v["current"] == 4  # the voice: the first step not done is tts
    v = nview("done", True, NEON_DONE | {"cover"}, {}, NT, now=0)
    assert {s["status"] for s in v["stages"]} == {"done"} and v["percent"] == 100 and len(v["stages"]) == 9
    # queued again: what state.json says is done
    v = nview("idle", True, {"research", "brief_check", "write"}, {}, NT, now=0)
    assert [s["status"] for s in v["stages"]] == ["done"] * 3 + ["next"] * 6


def test_typical_and_history_are_per_style(tmp_path):
    assert stages.typical([], "neon")["scene"] == 900 and stages.typical([], "neon")["render"] == 600
    assert stages.typical([{"scene": {"start": 0, "end": 300}}] * 3, "neon")["scene"] == 300
    assert "notebooklm" not in stages.typical([], "neon") and "scene" not in stages.typical([])

    def run(name, style, mtime):
        d = tmp_path / name
        d.mkdir()
        (d / "auto.json").write_text(json.dumps({"state": "done"}))
        os.utime(d / "auto.json", (mtime, mtime))
        (d / "times.json").write_text(json.dumps({"research": {"start": 0, "end": mtime}}))
        if style:
            (d / "run.json").write_text(json.dumps({"style": style}))
    run("o1", None, 1); run("n1", "neon", 2); run("o2", None, 3); run("n2", "neon", 4)
    run("odd", "old", 5); (tmp_path / "odd" / "run.json").write_text("[1]")
    assert [h["research"]["end"] for h in stages.history(tmp_path, "neon")] == [4, 2]
    assert [h["research"]["end"] for h in stages.history(tmp_path)] == [5, 3, 1]  # run.json not an object: the old flow


def test_the_fact_check_is_a_step_of_the_neon_research_stage_with_a_label_of_its_own():
    assert stages.stage_of("fact_check", "neon") == "research" and stages.stage_of("fact_check") is None  # the NotebookLM flow has none
    times = {"research": {"start": 0, "end": 300}, "fact_check": {"start": 300}}
    v = stages.view("running", False, {"new", "research"}, times, stages.typical([], "neon"), 400, style="neon")
    assert v["stages"][0]["status"] == "running" and v["stages"][0]["seconds"] == 400
    assert [(s["step"], s["label"], s["status"]) for s in v["stages"][0]["steps"]] == [
        ("research", "Tìm hiểu", "done"), ("fact_check", "Soát dữ kiện với nguồn", "running")]
