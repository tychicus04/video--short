import json
import os

from vshort import stages
from vshort.stages import DEFAULT_SECONDS as D

TYP = dict(D)
TOTAL = sum(D.values())
AFTER_APPROVE = D["build"] + D["render"] + D["review"] + D["cover"]
# every step that is always marked, research … review0, for an automatic run
THROUGH_REVIEW0 = {"research", "brief_check", "source", "fetch", "motion_design", "detect", "transcribe", "text",
                   "translate", "approve_script", "plates", "motion", "motion_bind", "stills", "tts", "visuals",
                   "visuals_agent", "timeline", "render", "review0"}


def by_key(v):
    return {s["key"]: s for s in v["stages"]}


def test_stage_of():
    assert stages.stage_of("motion_design") == "notebooklm"
    assert stages.stage_of("fix1_motion") == "review"
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
    assert [s["step"] for s in st["notebooklm"]["steps"]] == ["source", "fetch", "motion_design"]
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
    done = {"research", "brief_check", "source", "fetch", "motion_design", "detect", "transcribe", "text", "translate"}
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
    v = stages.view("running", True, THROUGH_REVIEW0 - {"render"}, {"fix1_motion": {"start": now - 30}}, TYP, now)
    st = by_key(v)
    assert st["review"]["status"] == "running"
    assert st["render"]["status"] == "done"


def test_fix_round_rerun_stays_on_review():
    # fix1_motion is marked, then `vshort motion` and render run again: still "Soát và sửa", never back to stage 7 or 8
    times = {"review0": {"start": 0, "end": 100}, "fix1_motion": {"start": 110, "end": 200}, "motion": {"start": 210}}
    v = stages.view("running", True, (THROUGH_REVIEW0 - {"render"}) | {"fix1_motion"}, times, TYP, now=300)
    st = by_key(v)
    assert st["review"]["status"] == "running"
    assert st["render"]["status"] == "done" and st["build"]["status"] == "done"
    assert v["percent"] >= round(100 * (TOTAL - D["review"] - D["cover"]) / TOTAL)


def test_translator_resume_shows_build():
    # Tai took the translator's proposal: the voice and pictures are made again before a fresh review
    again = {"tts", "timeline", "render", "motion", "motion_bind", "stills", "visuals"}
    done = (THROUGH_REVIEW0 - again) | {"fix1_translator", "fixed1"}
    times = {"fix1_translator": {"start": 100, "end": 200}, "tts": {"start": 500}}
    st = by_key(stages.view("running", True, done, times, TYP, now=600))
    assert st["build"]["status"] == "running"
    assert st["review"]["status"] == "next"


def test_canvas_agent_alone_keeps_translate():
    # NotebookLM, subtitles and the translation are done; only the canvas agent (started with NotebookLM) is left
    done = {"research", "brief_check", "source", "fetch", "detect", "transcribe", "text", "translate"}
    times = {"motion_design": {"start": 5}, "source": {"start": 0, "end": 5}, "fetch": {"start": 10, "end": 900},
             "translate": {"start": 1200, "end": 1400}}
    before = stages.view("running", True, done - {"translate"}, times | {"translate": {"start": 1200}}, TYP, now=1399)
    v = stages.view("running", True, done, times, TYP, now=2000)
    assert by_key(v)["translate"]["status"] == "running"
    assert by_key(v)["notebooklm"]["seconds"] == 5 + 890  # motion_design is not NotebookLM's time
    assert v["percent"] >= before["percent"]
    # no number frozen at "còn 1 phút" while only the canvas agent works: unknown, and the step shows why
    assert v["eta"]["until_stop"] is None and v["eta"]["stop"] == "Duyệt bản dịch"
    assert {"step": "motion_design", "label": "Vẽ hình động từ brief", "status": "running"} in by_key(v)["translate"]["steps"]


def test_rerun_of_an_earlier_step_does_not_walk_back():
    # render answered 2: the motion check runs again while render is still open; the page stays at "Dựng video"
    done = THROUGH_REVIEW0 - {"render", "review0", "motion"}
    times = {"timeline": {"start": 0, "end": 10}, "render": {"start": 20}, "motion": {"start": 200}}
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
