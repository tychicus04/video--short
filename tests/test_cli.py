import io
import json
import shutil
import wave
from pathlib import Path
from subprocess import CompletedProcess

import numpy as np
import pytest
from conftest import write_silence
from PIL import Image, ImageDraw

from vshort import cli
from vshort.cli import main
from vshort.media import frame_at
from vshort.run import Run
from vshort.tts import QuotaExceeded, clip_paths


def test_fetch_auth_error_exit_4(tmp_path, monkeypatch, capsys):
    main(["new", "demo", "--runs-dir", str(tmp_path)])
    monkeypatch.setattr(cli, "run_notebooklm", lambda a: CompletedProcess(a, 1, "", "Not logged in."))
    assert main(["fetch", str(tmp_path / "demo"), "--notebook", "abc"]) == 4
    assert "scp storage_state.json" in capsys.readouterr().err


def test_fetch_generates_waits_and_downloads_that_video(tmp_path, monkeypatch):
    main(["new", "demo", "--runs-dir", str(tmp_path)])
    calls = []

    def fake(args):
        calls.append(args)
        if args[0] == "generate":
            return CompletedProcess(args, 0, json.dumps({"task_id": "art1", "status": "pending"}), "")
        if args[:2] == ["artifact", "wait"]:
            return CompletedProcess(args, 0, json.dumps({"artifact_id": "art1", "status": "completed"}), "")
        return CompletedProcess(args, 0, "saved", "")

    monkeypatch.setattr(cli, "run_notebooklm", fake)
    assert main(["fetch", str(tmp_path / "demo"), "--notebook", "abc", "--prompt", "Follow the brief"]) == 0
    assert calls[0][-1] == "Follow the brief"
    assert calls[0][:2] == ["generate", "video"] and " --format short --language en " in f" {' '.join(calls[0])} "
    assert calls[2][:2] == ["download", "video"] and "art1" in calls[2]
    assert json.loads((tmp_path / "demo" / "run.json").read_text())["notebook_id"] == "abc"
    assert Run(tmp_path / "demo").done("fetch")


def test_state_resume(tmp_path):
    r = Run(tmp_path)
    r.mark("detect")
    assert Run(tmp_path).done("detect") and not Run(tmp_path).done("tts")


def test_parallel_marks_both_survive(tmp_path):
    a, b = Run(tmp_path), Run(tmp_path)  # both opened before either marks: tts | plates -> stills
    a.mark("tts")
    b.mark("stills")
    assert Run(tmp_path).done("tts") and Run(tmp_path).done("stills")


def test_check_exit_2(tmp_path):
    (tmp_path / "sentences.en.json").write_text('[{"id": 1, "start": 0, "end": 1, "en": "Hi."}]')
    (tmp_path / "script.vi.json").write_text('[{"id": 1, "phrases": "", "note": ""}]')
    assert main(["check", str(tmp_path)]) == 2


def _timeline_run(tmp_path, script, made_from=None):
    """script.vi.json and the tts.json of clips made from `made_from` (default: the same script)."""
    (tmp_path / "script.vi.json").write_text(json.dumps(script))
    lines = [(r["id"], cli._speech(r["phrases"])) for r in (made_from or script) if r["phrases"].strip()]
    paths = clip_paths(lines, tmp_path / "tts", cli._tts_tag(cli.config()))
    (tmp_path / "tts").mkdir()
    for p in paths:
        write_silence(p, 1.0)
    (tmp_path / "tts.json").write_text(json.dumps(
        [{"id": i, "path": str(p), "duration": 1.0} for (i, _), p in zip(lines, paths)]))


SCRIPT = [{"id": 1, "phrases": "a"}, {"id": 2, "phrases": ""}, {"id": 3, "phrases": "b"}]


def test_timeline_writes_back_to_back_narration(tmp_path):
    _timeline_run(tmp_path, SCRIPT)
    assert main(["timeline", str(tmp_path)]) == 0
    t = json.loads((tmp_path / "timeline.json").read_text())
    assert [p["id"] for p in t["placements"]] == [1, 3] and abs(t["total"] - 3.2) < 1e-6  # 0.2+1+0.5+1+0.5
    assert (tmp_path / "narration.wav").exists() and Run(tmp_path).done("timeline")


def test_timeline_refuses_clips_of_another_script(tmp_path, capsys):
    changed = [  # (script now, script the clips were made from)
        (SCRIPT + [{"id": 4, "phrases": "c"}], SCRIPT),  # a line was added
        (SCRIPT[:2], SCRIPT),  # a line was dropped
        ([SCRIPT[0], SCRIPT[1], {"id": 3, "phrases": "b khác"}], SCRIPT),  # same ids, other words
    ]
    for n, (script, made_from) in enumerate(changed):
        run = tmp_path / str(n)
        run.mkdir()
        _timeline_run(run, script, made_from)
        assert main(["timeline", str(run)]) == 2
        assert capsys.readouterr().err == "giọng đọc cũ không khớp kịch bản — chạy lại `vshort tts`\n"
        assert not (run / "timeline.json").exists() and not (run / "narration.wav").exists()
        assert not Run(run).done("timeline")


def test_timeline_ignores_the_markup_of_the_script(tmp_path):
    script = [{"id": 1, "phrases": "a | *b*"}, {"id": 3, "phrases": "c"}]
    _timeline_run(tmp_path, script, [{"id": 1, "phrases": "a b"}, {"id": 3, "phrases": "c"}])  # the voice says the same
    assert main(["timeline", str(tmp_path)]) == 0


def _out_of_quota(tmp_path, monkeypatch, local):
    """Gemini is out for the day; `local(text)` stands in for one ZeroTTS call. Returns the texts each was asked."""
    (tmp_path / "script.vi.json").write_text(
        '[{"id": 1, "phrases": "Xin | *chào*", "note": ""}, {"id": 2, "phrases": "Tạm biệt", "note": ""}]')
    monkeypatch.setattr(cli, "load_api_key", lambda p: "k")
    seen = {"gemini": [], "zerotts": []}

    def gemini(key, model, voice, style=""):
        def speak(text):
            seen["gemini"].append(text)
            raise QuotaExceeded()
        return speak

    def zerotts(model_dir, voice):
        return lambda text: seen["zerotts"].append(text) or local(text)

    monkeypatch.setattr(cli, "gemini_speaker", gemini)
    monkeypatch.setattr(cli, "zerotts_speaker", zerotts)
    return seen


def _wav(seconds):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(bytes(2 * round(seconds * 48000)))
    return buf.getvalue()


def test_tts_out_of_gemini_quota_reads_each_line_with_zerotts(tmp_path, monkeypatch):
    seen = _out_of_quota(tmp_path, monkeypatch, lambda text: _wav(1.5))
    assert main(["tts", str(tmp_path)]) == 0
    assert seen["gemini"] == ["Xin chào.\n\nTạm biệt."]  # the words the subtitles show, without | and *
    assert seen["zerotts"] == ["Xin chào", "Tạm biệt"]  # one call per line: nothing to cut at silences
    assert [c["duration"] for c in json.loads((tmp_path / "tts.json").read_text())] == [1.5, 1.5]
    assert main(["timeline", str(tmp_path)]) == 0  # the ZeroTTS clips count as made from this script
    seen["gemini"].clear()
    assert main(["tts", str(tmp_path)]) == 0 and seen["gemini"] == []  # a rerun keeps the ZeroTTS voice


def test_tts_quota_exit_75_when_zerotts_cannot_run(tmp_path, monkeypatch, capsys):
    def missing(text):
        raise FileNotFoundError(2, "No such file or directory", "zerotts")

    _out_of_quota(tmp_path, monkeypatch, missing)
    assert main(["tts", str(tmp_path)]) == 75
    assert "ZeroTTS không chạy được" in (err := capsys.readouterr().err) and "chạy lại" in err
    assert not list((tmp_path / "tts").glob("*.wav")) and not Run(tmp_path).done("tts")


def test_fetch_rerun_continues_the_same_video(tmp_path, monkeypatch):
    main(["new", "demo", "--runs-dir", str(tmp_path)])
    calls, waits = [], iter([CompletedProcess([], 1, "", "Not logged in."),
                             CompletedProcess([], 0, json.dumps({"status": "completed"}), "")])

    def fake(args):
        calls.append(args)
        if args[0] == "generate":
            return CompletedProcess(args, 0, json.dumps({"task_id": "art1"}), "")
        if args[:2] == ["artifact", "wait"]:
            return next(waits)
        return CompletedProcess(args, 0, "saved", "")

    monkeypatch.setattr(cli, "run_notebooklm", fake)
    assert main(["fetch", str(tmp_path / "demo"), "--notebook", "abc"]) == 4
    assert main(["fetch", str(tmp_path / "demo"), "--notebook", "abc"]) == 0
    assert [c[0] for c in calls].count("generate") == 1


def test_text_refuses_missing_transcriptions(tmp_path, capsys):
    frag = {"start": 0, "end": 1, "y0": 900, "y1": 960, "text": None}
    (tmp_path / "fragments.json").write_text(json.dumps([{"i": 0, **frag}, {"i": 1, **frag, "start": 1, "end": 2}]))
    (tmp_path / "fragments_text.json").write_text('{"0": "Hi."}')
    assert main(["text", str(tmp_path)]) == 2
    assert "1" in capsys.readouterr().err


def _visuals_run(tmp_path, ids=(1, 3, 4), scenes=(0, 0, 1)):
    """A run with stills: cream page with a dark bar inside the box (96, 96, 404, 144)."""
    (tmp_path / "stills").mkdir()
    for i in ids:
        img = Image.new("RGB", (720, 1280), (243, 239, 230))
        ImageDraw.Draw(img).rectangle((104, 104, 396, 136), fill=(50, 50, 50))
        ImageDraw.Draw(img).ellipse((200 + i * 20, 600, 400 + i * 20, 800), fill=(90, 120, 160))
        img.save(tmp_path / "stills" / f"{i}.png")
    (tmp_path / "stills.json").write_text(json.dumps(
        [{"id": i, "t": float(i), "scene": s} for i, s in zip(ids, scenes)]))
    (tmp_path / "sentences.en.json").write_text(json.dumps(
        [{"id": i, "start": float(i) - 1, "end": float(i), "en": "x."} for i in ids]))
    (tmp_path / "script.vi.json").write_text(json.dumps([{"id": i, "phrases": "câu", "note": ""} for i in ids]))
    (tmp_path / "clean.mp4").write_bytes(b"")  # appear_time is stubbed in these tests
    return tmp_path


@pytest.fixture(autouse=True)
def _appear(monkeypatch):
    """The moment a patched line's wrong text shows: a quarter second into its English stretch (appear_time is
    tested on real video in test_visuals)."""
    seen = []
    monkeypatch.setattr(cli, "appear_time", lambda video, a, b, box, still: seen.append((a, b, box)) or a + 0.25)
    return seen


def _png(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


def test_visuals_cmd_rejects_bad_items(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "visuals.json").write_text(json.dumps([
        {"kind": "patch", "ids": [9], "box": [0, 0, 900, 50], "text": "x.example", "note": "n"},
        {"kind": "svg", "id": 1, "file": "visuals/1.svg", "source": "https://a.example", "accessed": "2026-10-31",
         "note": "n"},
        {"kind": "photo", "id": 3, "file": "visuals/3.jpg", "accessed": "2026-10-31", "credit": "Nguồn: A",
         "note": "n"},
    ]))
    assert main(["visuals", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert all(s in err for s in ["9", "900", "kind 'svg' không còn dùng", "kind 'photo' không còn dùng"])
    assert not (tmp_path / "frames").exists() and not (tmp_path / "frames.json").exists()
    assert not Run(tmp_path).done("visuals")


def test_visuals_cmd_rejects_unknown_patch_ids(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [1, 7], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 2
    assert "[7]" in capsys.readouterr().err and not (tmp_path / "frames").exists()


def test_visuals_cmd_rejects_bad_json(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1,), scenes=(0,))
    for text in ("{oops", '{"kind": "patch"}'):
        (tmp_path / "visuals.json").write_text(text)
        assert main(["visuals", str(tmp_path)]) == 2
        assert "visuals.json" in capsys.readouterr().err
    assert not (tmp_path / "frames").exists()


def test_visuals_cmd_writes_only_patched_lines_with_from(tmp_path, _appear):
    _visuals_run(tmp_path)
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "99.png").write_bytes(b"stale")
    box = [96, 96, 404, 144]
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [1, 3], "box": box, "text": "tin-tuc.example", "note": "địa chỉ sai"}]))
    assert main(["visuals", str(tmp_path)]) == 0
    # line 1 is the first line: its stretch starts at 0; line 3's at its English start, 2.0
    assert json.loads((tmp_path / "frames.json").read_text()) == [
        {"id": 1, "file": "frames/1.png", "from": 0.25}, {"id": 3, "file": "frames/3.png", "from": 2.25}]
    assert _appear == [(0.0, 1.0, tuple(box)), (2.0, 3.0, tuple(box))]  # up to the still's moment
    assert not (tmp_path / "frames" / "99.png").exists() and Run(tmp_path).done("visuals")
    for i in (1, 3):
        before, after = _png(tmp_path / "stills" / f"{i}.png"), _png(tmp_path / "frames" / f"{i}.png")
        assert np.abs(before[96:144, 96:404] - after[96:144, 96:404]).max() > 0
        before[96:144, 96:404] = after[96:144, 96:404] = 0
        assert np.array_equal(before, after)
    for text in ("[]", None):  # nothing to patch: no frames at all, the video plays everywhere
        (tmp_path / "visuals.json").unlink()
        if text:
            (tmp_path / "visuals.json").write_text(text)
        assert main(["visuals", str(tmp_path)]) == 0
        assert json.loads((tmp_path / "frames.json").read_text()) == [] and not list((tmp_path / "frames").iterdir())

def test_visuals_cmd_hairline_in_the_box_is_not_text(tmp_path):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    for i in (1, 3):
        img = Image.new("RGB", (720, 1280), (243, 239, 230))
        ImageDraw.Draw(img).line((110, 120, 390, 120), fill=(40, 40, 40), width=1)
        img.save(tmp_path / "stills" / f"{i}.png")
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [3], "box": [96, 96, 404, 144], "text": "Cập nhật", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 0
    ink = _png(tmp_path / "frames" / "3.png")[96:144, 96:404].sum(2) < 400
    assert ink.any(1).sum() >= 12  # readable text, not a crash and not a hairline


def test_visuals_cmd_render_failure_keeps_the_previous_frames(tmp_path, monkeypatch, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    assert main(["visuals", str(tmp_path)]) == 0
    kept = {p.name: p.read_bytes() for p in (tmp_path / "frames").iterdir()}
    rows = (tmp_path / "frames.json").read_text()
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [1, 3], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "n"}]))

    def boom(*args, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "patch_text", boom)
    assert main(["visuals", str(tmp_path)]) == 1
    assert "boom" in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in (tmp_path / "frames").iterdir()} == kept
    assert (tmp_path / "frames.json").read_text() == rows


def _render_run(tmp_path, make_video, frames=()):
    """Two lines over 10 s of NotebookLM video (grey level 10 + 20 per second): English 0–3 s and 3–6.5 s, Vietnamese
    0.2–1.7 s and 2.0–4.5 s of a 5 s voice."""
    v = make_video(tmp_path, scenes=[(k, k + 1, "#" + f"{10 + 20 * k:02x}" * 3) for k in range(10)], captions=[])
    shutil.copy(v, tmp_path / "source.mp4")
    shutil.copy(v, tmp_path / "clean.mp4")
    (tmp_path / "sentences.en.json").write_text(json.dumps(
        [{"id": 1, "start": 0.1, "end": 3.0, "en": "One."}, {"id": 2, "start": 3.0, "end": 6.5, "en": "Two."}]))
    (tmp_path / "script.vi.json").write_text(json.dumps(
        [{"id": 1, "phrases": "Một câu", "note": ""}, {"id": 2, "phrases": "Hai | câu", "note": ""}]))
    (tmp_path / "timeline.json").write_text(json.dumps(
        {"total": 5.0, "placements": [{"id": 1, "start": 0.2, "dur": 1.5}, {"id": 2, "start": 2.0, "dur": 2.5}]}))
    (tmp_path / "frames").mkdir()
    Image.new("RGB", (720, 1280), (220, 30, 30)).save(tmp_path / "frames" / "2.png")
    (tmp_path / "frames.json").write_text(json.dumps(list(frames)))
    write_silence(tmp_path / "narration.wav", 5.0)


def test_render_cmd_plays_the_video_retimed_with_the_patched_still(tmp_path, make_video, capsys):
    _render_run(tmp_path, make_video, [{"id": 2, "file": "frames/2.png", "from": 4.0}])
    assert main(["render", str(tmp_path)]) == 0
    out = tmp_path / "final.mp4"
    assert Run(tmp_path).done("render") and str(out) in capsys.readouterr().out
    ps = json.loads((tmp_path / "pieces.json").read_text())
    assert [(p["id"], p["src"], p["dst"], p["dst_end"]) for p in ps] == [(1, 0.0, 0.0, 2.0), (2, 3.0, 2.0, 5.0)]
    assert ps[1]["speed"] == pytest.approx(3.5 / 3.0)  # 3.0–6.5 s of English into 3 s
    assert abs(int(frame_at(out, 1.0)[300, 360].mean()) - 30) < 6  # line 1: source 1.0 s at 1.5x → second 1
    assert np.abs(frame_at(out, 2.3)[300, 360].astype(int) - (220, 30, 30)).max() > 60  # the video, before the wrong text
    # from source 4.0 s (output 2.0 + 1.0 / 1.1667 = 2.86 s) the patched still stands until the line ends
    assert np.abs(frame_at(out, 3.5)[300, 360].astype(int) - (220, 30, 30)).max() < 20
    assert json.loads((tmp_path / "sfx.json").read_text()) is not None and (tmp_path / "subs.ass").exists()


def test_render_cmd_needs_clean_mp4(tmp_path, make_video, capsys):
    _render_run(tmp_path, make_video)
    (tmp_path / "clean.mp4").unlink()
    assert main(["render", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "thiếu clean.mp4 (chạy `vshort clean`)\n"


def test_render_cmd_refuses_frames_json_of_the_still_pictures(tmp_path, make_video, capsys):
    _render_run(tmp_path, make_video, [{"id": 1, "file": "frames/2.png", "group": "s0"}])  # no "from": written before 06/11
    assert main(["render", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "frames.json kiểu cũ (chạy lại `vshort visuals`)\n"


def test_render_cmd_names_missing_frame_files_and_keeps_the_old_video(tmp_path, make_video, capsys):
    _render_run(tmp_path, make_video, [{"id": 2, "file": "frames/9.png", "from": 4.0}])
    (tmp_path / "final.mp4").write_bytes(b"good")
    assert main(["render", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "thiếu file khung hình: frames/9.png (chạy lại `vshort visuals`)\n"
    assert (tmp_path / "final.mp4").read_bytes() == b"good" and not Run(tmp_path).done("render")


def test_render_cmd_rejects_a_timeline_of_another_script(tmp_path, make_video, capsys):
    _render_run(tmp_path, make_video)
    (tmp_path / "script.vi.json").write_text(json.dumps(
        [{"id": 1, "phrases": "Một câu", "note": ""}, {"id": 2, "phrases": "", "note": ""}]))  # line 2 now silent
    assert main(["render", str(tmp_path)]) == 2
    assert "timeline.json" in capsys.readouterr().err

def test_status_lists_every_step_in_order(tmp_path, capsys):
    Run(tmp_path).mark("tts")
    assert main(["status", str(tmp_path)]) == 0
    marks = [ln.split() for ln in capsys.readouterr().out.splitlines()]
    assert marks == [[("✓" if s == "tts" else "·"), s]
                     for s in "new fetch detect text plates tts stills motion visuals timeline render".split()]


EX = Path(__file__).resolve().parent.parent / "examples" / "motion"


def _motion_run(tmp_path, bind=True):
    shutil.copy(EX / "coruna.json", tmp_path / "motion.json")
    if bind:
        shutil.copy(EX / "coruna.bind.json", tmp_path / "motion.bind.json")
    shutil.copy(EX / "coruna.script.json", tmp_path / "script.vi.json")
    script = json.loads((EX / "coruna.script.json").read_text())
    (tmp_path / "brief.vi.md").write_text("\n".join(r["phrases"] for r in script), encoding="utf-8")


def test_motion_cmd_without_a_file_means_no_animation(tmp_path, capsys):
    (tmp_path / "script.vi.json").write_text(json.dumps([{"id": 1, "phrases": "a"}]))
    (tmp_path / "motion").mkdir()
    assert main(["motion", str(tmp_path)]) == 0
    assert "Không có hình động." in capsys.readouterr().out
    assert Run(tmp_path).done("motion") and not (tmp_path / "motion").exists()


def test_motion_cmd_lists_every_problem(tmp_path, capsys):
    _motion_run(tmp_path)
    doc = json.loads((tmp_path / "motion.json").read_text())
    doc["things"][1]["label"] = "WebKit"
    doc["things"][0]["url"] = "apple.com"
    (tmp_path / "motion.json").write_text(json.dumps(doc))
    assert main(["motion", str(tmp_path)]) == 2
    err = capsys.readouterr().err.lower()
    assert "webkit" in err and "apple.com" in err and not Run(tmp_path).done("motion")


def test_motion_cmd_writes_the_sheet(tmp_path, capsys):
    _motion_run(tmp_path)
    assert main(["motion", str(tmp_path)]) == 0
    assert (tmp_path / "motion" / "sheet.png").exists()
    assert "1 khung, 3/3 nhịp, câu 7–13" in capsys.readouterr().out and Run(tmp_path).done("motion")


def test_motion_design_checks_the_canvas_against_the_brief(tmp_path, capsys):
    _motion_run(tmp_path, bind=False)
    assert main(["motion", str(tmp_path), "--design"]) == 0
    assert "3 nhịp" in capsys.readouterr().out and (tmp_path / "motion" / "design.png").exists()
    assert not Run(tmp_path).done("motion")
    (tmp_path / "brief.vi.md").write_text("không có chữ nào khớp", encoding="utf-8")
    assert main(["motion", str(tmp_path), "--design"]) == 2
    assert "sandbox" in capsys.readouterr().err


def test_motion_cmd_without_a_bind_says_so(tmp_path, capsys):
    _motion_run(tmp_path, bind=False)
    assert main(["motion", str(tmp_path)]) == 2
    assert "thiếu motion.bind.json" in capsys.readouterr().err and not Run(tmp_path).done("motion")


@pytest.mark.parametrize("bind", [True, False])
def test_old_motion_file_is_rejected_plainly(tmp_path, capsys, bind):
    _motion_run(tmp_path, bind=bind)
    (tmp_path / "motion.json").write_text(json.dumps({"lines": [7], "note": "n", "scenes": []}))
    assert main(["motion", str(tmp_path)]) == 2
    assert "dạng cũ" in capsys.readouterr().err


def test_motion_cmd_copies_library_shapes_into_the_run(tmp_path, monkeypatch, capsys):
    from vshort import shapes
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "bo-nho.json").write_text(json.dumps({"name": "bộ nhớ", "strokes": [[[0, 0], [100, 60]]]}))
    monkeypatch.setattr(shapes, "LIBRARY", lib)
    run = tmp_path / "run"
    run.mkdir()
    _goi_tin_run(run)
    doc = json.loads((run / "motion.json").read_text())
    doc["things"].append({"id": "m", "kind": "shape", "shape": "bo-nho", "box": [300, 150, 420, 250], "beat": 1})
    (run / "motion.json").write_text(json.dumps(doc))
    assert main(["motion", str(run)]) == 0
    assert json.loads((run / "shapes" / "bo-nho.json").read_text())["name"] == "bộ nhớ"


def test_motion_cmd_rejects_a_run_shape_that_changes_the_library(tmp_path, monkeypatch, capsys):
    from vshort import shapes
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "bo-nho.json").write_text(json.dumps({"name": "bộ nhớ", "strokes": [[[0, 0], [100, 60]]]}))
    monkeypatch.setattr(shapes, "LIBRARY", lib)
    run = tmp_path / "run"
    (run / "shapes").mkdir(parents=True)
    _goi_tin_run(run)
    (run / "shapes" / "bo-nho.json").write_text(json.dumps({"name": "bộ nhớ", "strokes": [[[0, 60], [100, 0]]]}))
    assert main(["motion", str(run), "--design"]) == 2
    assert "đặt tên mới" in capsys.readouterr().err


@pytest.mark.parametrize("edit", [
    lambda d: d["things"][1].update(kind=["dot"]),
    lambda d: d["things"][10].update(icon=["key"]),
    lambda d: d["things"][0].update(color={"x": 1}),
    lambda d: d["beats"][0]["acts"][0].update(thing=["bug"]),
    lambda d: d["beats"][1]["acts"][0].update(path=["wire"]),
    lambda d: d["beats"][1]["acts"][3].update(to=None),  # a red act with a stray `to`
    lambda d: d["beats"][1]["acts"][3].update(path=[]),
    lambda d: d["things"][1].update(beat="1"),
    lambda d: d.update(beats={"a": 1}),
    lambda d: d.update(things=[1, 2]),
])
def test_motion_cmd_reports_malformed_docs_without_a_traceback(tmp_path, capsys, edit):
    _motion_run(tmp_path)
    doc = json.loads((tmp_path / "motion.json").read_text())
    edit(doc)
    (tmp_path / "motion.json").write_text(json.dumps(doc))
    assert main(["motion", str(tmp_path)]) == 2
    assert "motion.json" in capsys.readouterr().err
    assert main(["motion", str(tmp_path), "--design"]) == 2


@pytest.mark.parametrize("bind", ["[]", '{"lines": [7], "beats": "x"}', '{"lines": [7, 8], "note": "n", "beats": [1, 2, 3]}',
                                  '{"lines": [7], "note": "n", "beats": [null, null, null], "labels": [1]}'])
def test_motion_cmd_reports_malformed_binds_without_a_traceback(tmp_path, capsys, bind):
    _motion_run(tmp_path)
    (tmp_path / "motion.bind.json").write_text(bind)
    assert main(["motion", str(tmp_path)]) == 2
    assert "motion.bind.json" in capsys.readouterr().err


def _goi_tin_run(tmp_path):
    """A run of the A→B example: every spoken line placed and given a white frame."""
    shutil.copy(EX / "goi-tin.json", tmp_path / "motion.json")
    shutil.copy(EX / "goi-tin.bind.json", tmp_path / "motion.bind.json")
    shutil.copy(EX / "goi-tin.script.json", tmp_path / "script.vi.json")
    (tmp_path / "brief.vi.md").write_text("gói tin kẻ nghe lén", encoding="utf-8")
    (tmp_path / "frames").mkdir()
    Image.new("RGB", (720, 1280), "white").save(tmp_path / "frames" / "w.png")
    ids = [1, 2, 3, 4, 5]
    (tmp_path / "frames.json").write_text(json.dumps([{"id": i, "file": "frames/w.png", "group": "s0"} for i in ids]))
    (tmp_path / "timeline.json").write_text(json.dumps(
        {"total": 10.5, "placements": [{"id": i, "start": 0.2 + 2 * k, "dur": 1.7} for k, i in enumerate(ids)]}))
    write_silence(tmp_path / "narration.wav", 10.5)


def test_approve_brief_refuses_stale_english(tmp_path, capsys):
    import os
    en, vi = tmp_path / "brief.en.md", tmp_path / "brief.vi.md"
    en.write_text("en")
    vi.write_text("vi")
    os.utime(en, (1000, 1000))
    os.utime(vi, (2000, 2000))
    assert main(["approve", str(tmp_path), "brief"]) == 2
    assert "brief.en.md" in capsys.readouterr().err and not Run(tmp_path).done("approve_brief")
    os.utime(en, (3000, 3000))
    assert main(["approve", str(tmp_path), "brief"]) == 0 and Run(tmp_path).done("approve_brief")


def test_approve_script_runs_check(tmp_path, capsys):
    (tmp_path / "sentences.en.json").write_text('[{"id": 1, "start": 0, "end": 1, "en": "Hi"}]')
    (tmp_path / "script.vi.json").write_text('[{"id": 1, "phrases": "", "note": ""}]')
    assert main(["approve", str(tmp_path), "script"]) == 2 and not Run(tmp_path).done("approve_script")
    (tmp_path / "script.proposed.json").write_text("[]")
    assert main(["approve", str(tmp_path), "script"]) == 2
    assert "script.proposed.json" in capsys.readouterr().err


def test_wait_returns_state_code(tmp_path, capsys):
    from vshort import auto
    auto.set_state(Run(tmp_path), "wait_script", "xem bản dịch")
    assert main(["wait", str(tmp_path), "--poll", "0"]) == 21
    assert "xem bản dịch" in capsys.readouterr().out
    assert main(["wait", str(tmp_path / "chưa"), "--poll", "0"]) == 2


def test_status_shows_auto_state(tmp_path, capsys):
    from vshort import auto
    auto.set_state(Run(tmp_path), "running", "")
    assert main(["status", str(tmp_path)]) == 0
    assert "auto: running" in capsys.readouterr().out


def test_auto_foreground_starts_a_run_and_holds_the_lock(tmp_path, monkeypatch):
    from vshort import auto
    seen = []

    def fake_run_auto(run):
        seen.append((run.read("run.json"), run.file("auto.lock").exists()))
        return 21

    monkeypatch.setattr(auto, "run_auto", fake_run_auto)
    assert main(["auto", "my-slug", "--topic", "Chủ đề", "--auto", "--runs-dir", str(tmp_path), "--foreground"]) == 21
    meta, locked = seen[0]
    assert (meta["slug"], meta["topic"], meta["auto"], locked) == ("my-slug", "Chủ đề", True, True)
    run = tmp_path / "my-slug"
    assert not (run / "auto.lock").exists()  # released when it stops
    assert main(["auto", str(run), "--foreground"]) == 21 and seen[1][0]["topic"] == "Chủ đề"
    (run / "auto.lock").write_text(str(__import__("os").getpid()))  # another live run holds it
    assert main(["auto", str(run), "--foreground"]) == 2


def test_auto_launch_detaches_and_refuses_while_running(tmp_path, monkeypatch, capsys):
    import os
    from vshort import auto
    launched = []

    class FakePopen:
        def __init__(self, args, **kw):
            launched.append((args, kw))
            self.pid = 4242

    monkeypatch.setattr(cli.subprocess, "Popen", FakePopen)
    assert main(["auto", "s", "--topic", "Chủ đề", "--runs-dir", str(tmp_path)]) == 0
    args, kw = launched[0]
    run = tmp_path / "s"
    assert "--foreground" in args and str(run) in args and "-u" in args and kw["start_new_session"] is True
    assert auto.get_state(Run(run))["pid"] == 4242  # wait checks the background run, not the launcher, is alive
    assert auto.get_state(Run(run))["state"] == "running" and (run / "auto.log").exists()
    assert "4242" in capsys.readouterr().out
    (run / "auto.lock").write_text(str(os.getpid()))  # the background run is still going
    monkeypatch.setattr(auto, "_started", lambda pid: 0.0)  # FakePopen also replaces the Popen that `ps` needs
    assert main(["auto", str(run)]) == 2 and "đang chạy" in capsys.readouterr().err
    assert len(launched) == 1


def test_wait_reports_a_run_that_died(tmp_path, capsys):
    from vshort import auto
    auto.set_state(Run(tmp_path), "running", pid=999999)  # no such process, no lock: it died mid-step
    assert main(["wait", str(tmp_path), "--poll", "0"]) == 1
    assert "dừng giữa chừng" in capsys.readouterr().out


def test_auto_with_topic_refuses_an_existing_video(tmp_path, capsys):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "run.json").write_text('{"slug": "s", "notebook_id": "nb", "topic": "cũ"}')
    assert main(["auto", "s", "--topic", "mới", "--runs-dir", str(tmp_path), "--foreground"]) == 2
    assert json.loads((tmp_path / "s" / "run.json").read_text())["notebook_id"] == "nb"
    assert "vshort auto" in capsys.readouterr().err


# ---- vshort shots ----

SHOT_SAY = {1: "Máy chủ của bạn | nằm ở Hà Nội | chạy suốt ngày đêm",
            2: "Dữ liệu đi qua | bốn trạm trung gian | rồi mới tới bạn",
            3: "Thẻ này ghi lại | điều nhà cung cấp | khuyến cáo người dùng",
            4: "Ảnh này chụp lại | bài báo gốc đó | đăng cuối tháng mười"}
SHOT_AT = {1: (0.2, 3.6), 2: (4.0, 3.6), 3: (7.8, 3.6), 4: (11.8, 3.6)}  # voice start, length; the cuts fall mid-gap
SHOT_SEG = {1: (0.0, 3.9), 2: (3.9, 7.7), 3: (7.7, 11.6), 4: (11.6, 15.6)}
_CARD_TEXT = '<text x="100" y="{y}" font-family="Be Vietnam Pro, sans-serif" font-size="{em}" fill="#222">{t}</text>'
SHOT_CARD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280" width="720" height="1280">'
             '<rect x="60" y="300" width="600" height="420" rx="18" fill="none" stroke="#4a4a4a" stroke-width="3"/>'
             + _CARD_TEXT.format(y=400, em=32, t="Máy chủ ở Hà Nội đang chạy") + _CARD_TEXT.format(y=520, em=32, t="Cập nhật ngay hôm nay")
             + _CARD_TEXT.format(y=660, em=22, t="Nguồn: Synology, 29/10/2026") + "</svg>")


def _shots_run(tmp_path):
    """Four lines of 3.6 s: two NotebookLM stills (a dark picture at 100,300–500,500 on cream), a reference card and a photo.
    The old caption band starts at y 1000."""
    from vshort.visuals import svg_frame
    for d in ("frames", "visuals", "plates"):
        (tmp_path / d).mkdir()
    for i in (1, 2, 4):
        img = Image.new("RGB", (720, 1280), (243, 239, 230))
        ImageDraw.Draw(img).rectangle((100, 300, 500, 500), fill=(50, 50, 50))
        img.save(tmp_path / "frames" / f"{i}.png")
    (tmp_path / "visuals" / "3.svg").write_text(SHOT_CARD, encoding="utf-8")
    svg_frame(tmp_path / "visuals" / "3.svg").save(tmp_path / "frames" / "3.png")
    (tmp_path / "script.vi.json").write_text(json.dumps([{"id": i, "phrases": p} for i, p in SHOT_SAY.items()]), encoding="utf-8")
    (tmp_path / "timeline.json").write_text(json.dumps({"total": 15.6, "placements": [
        {"id": i, "start": s, "dur": d} for i, (s, d) in SHOT_AT.items()]}))
    groups = {1: "s0", 2: "s0", 3: "v3", 4: "v4"}
    (tmp_path / "frames.json").write_text(json.dumps([{"id": i, "file": f"frames/{i}.png", "group": g} for i, g in groups.items()]))
    (tmp_path / "visuals.json").write_text(json.dumps([
        {"kind": "svg", "id": 3, "file": "visuals/3.svg", "source": "https://a.example", "accessed": "2026-11-05", "note": "n"},
        {"kind": "photo", "id": 4, "file": "visuals/4.jpg", "source": "https://a.example", "accessed": "2026-11-05",
         "credit": "Nguồn: A", "note": "n"}]))
    (tmp_path / "plates" / "plates.json").write_text(json.dumps(
        [{"name": "p00", "x": 54, "y": 1000, "start": 0, "end": 15.6, "method": "clean", "moving": False}]))
    return tmp_path


def _card_pieces(run):
    from vshort import cards, render
    return cards.Card(run / "visuals" / "3.svg", *SHOT_SEG[3], render.XF).pieces


def _good_plan(run):
    """A plan every line of which is fine: marks on the dark picture, pops and doodles on paper; on the card a doodle on
    paper first, then a mark on each line once it has been written."""
    _, text1, text2, _ = (list(map(round, p.box)) for p in _card_pieces(run))
    return {
        "1": [{"phrase": 1, "mark": {"shape": "circle", "box": [120, 320, 480, 480]}},
              {"phrase": 2, "pop": {"text": "Hà Nội", "box": [100, 700, 300, 780]}},
              {"phrase": 3, "mark": {"shape": "tick", "box": [150, 350, 450, 450]}}],
        "2": [{"phrase": 1, "focus": [100, 300, 500, 500], "mark": {"shape": "underline", "box": [150, 330, 420, 470]}},
              {"phrase": 2, "focus": None},
              {"phrase": 3, "doodle": {"shape": "internet", "box": [200, 700, 400, 800]}}],
        "3": [{"phrase": 1, "doodle": {"shape": "internet", "box": [150, 800, 350, 900]}},
              {"phrase": 2, "mark": {"shape": "underline", "box": text1}},
              {"phrase": 3, "mark": {"shape": "circle", "box": text2}}]}


def _shots(run, plan, capsys):
    (run / "shots").mkdir(exist_ok=True)
    (run / "shots.json").write_text(json.dumps(plan))
    capsys.readouterr()
    code = main(["shots", str(run)])
    return code, capsys.readouterr()


def _ok_lines(run):
    return json.loads((run / "shots" / "ok.json").read_text())["lines"]


def test_prep_writes_helpers(tmp_path, capsys):
    _shots_run(tmp_path)
    assert main(["shots", str(tmp_path), "--prep"]) == 0
    text = (tmp_path / "shots" / "phrases.txt").read_text(encoding="utf-8").splitlines()
    assert "câu 1 (0.00–3.90s, ảnh frames/1.png, ảnh NotebookLM)" in text
    assert "  cụm 1 @0.20s: Máy chủ của bạn" in text and "  cụm 2 @1.40s: nằm ở Hà Nội" in text  # the words, without | and *
    assert "câu 3 (7.70–11.60s, ảnh frames/3.png, thẻ tư liệu)" in text
    assert "câu 4 (11.60–15.60s, ảnh frames/4.png, ảnh tư liệu)" in text
    assert text[-1] == "Dải phụ đề cũ trên ảnh NotebookLM bắt đầu ở y 1000: đừng cận vào đó."
    reveal = json.loads((tmp_path / "shots" / "reveal.json").read_text())
    assert list(reveal) == ["3"] and reveal["3"][0]["border"] is True  # only the card line writes itself out
    assert all(set(r) == {"t0", "t1", "box", "border"} for r in reveal["3"]) and len(reveal["3"]) == 4
    assert reveal["3"][0]["t1"] == 7.7
    for i in (1, 2, 3, 4):
        assert Image.open(tmp_path / "frames" / "grid" / f"{i}.png").size == (720, 1280)
    assert Image.open(tmp_path / "shots" / "shapes.png").width > 6 * 240  # the library's shapes are there, not only the run's
    assert not (tmp_path / "shots" / "ok.json").exists()


def test_shots_ok_writes_ok_json_and_sheet(tmp_path, capsys):
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    code, out = _shots(tmp_path, plan, capsys)
    assert code == 0 and out.err == ""
    assert out.out.strip() == f"nhịp hình: 3 câu, 9 nhịp; ảnh để xem: {tmp_path}/shots/sheet.png"
    ok = json.loads((tmp_path / "shots" / "ok.json").read_text())
    assert ok["lines"] == plan  # the beats as written, line 4 (no plan) is not there
    assert ok["stamp"] == cli._shots_stamp(Run(tmp_path), [1, 2, 3]) == cli._shots_stamp(Run(tmp_path), ok["lines"])  # ids or its keys
    assert set(ok["stamp"]) == {"script", "timeline", "frames", "pictures", "cards", "animated"}
    assert set(ok["stamp"]["pictures"]) == {"1", "2", "3"} and list(ok["stamp"]["cards"]) == ["3"] and ok["stamp"]["animated"] == []
    assert ok["stamp"]["script"] == {str(i): SHOT_SAY[i] for i in (1, 2, 3)}
    assert [p["id"] for p in ok["stamp"]["timeline"]] == [1, 2, 3] and len(ok["stamp"]["frames"]) == 4
    sheet = Image.open(tmp_path / "shots" / "sheet.png")
    assert sheet.size == (3 * 180, 3 * 320)  # a row per line, a cell per beat
    assert np.asarray(sheet).std() > 10  # something was drawn in the cells


def test_the_stamp_follows_what_a_beat_stands_on(tmp_path):
    _shots_run(tmp_path)
    run, before = Run(tmp_path), cli._shots_stamp(Run(tmp_path), [1])
    assert before == cli._shots_stamp(run, [1])
    script = json.loads((tmp_path / "script.vi.json").read_text())
    script[1]["phrases"] = "đổi lời | câu hai"
    (tmp_path / "script.vi.json").write_text(json.dumps(script, ensure_ascii=False))
    assert cli._shots_stamp(run, [1]) == before and cli._shots_stamp(run, [1, 2]) != before
    script[0]["phrases"] = "đổi lời | câu một"
    (tmp_path / "script.vi.json").write_text(json.dumps(script, ensure_ascii=False))
    assert cli._shots_stamp(run, [1]) != before
    tl = json.loads((tmp_path / "timeline.json").read_text())
    tl["placements"][0]["dur"] += 0.1
    (tmp_path / "timeline.json").write_text(json.dumps(tl))
    assert cli._shots_stamp(run, [1]) != cli._shots_stamp(run, [2])


@pytest.mark.parametrize("what, word", [
    ({"phrase": 1, "mark": {"shape": "circle", "box": [200, 800, 400, 900]}}, "giấy trống"),  # a mark on blank paper
    ({"phrase": 7, "mark": {"shape": "circle", "box": [120, 320, 480, 480]}}, "phrase"),  # a plan that breaks its form
])
def test_one_bad_line_is_left_out_of_ok_json_and_exit_2(tmp_path, capsys, what, word):
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    plan["2"] = [what] + plan["2"][1:]
    code, out = _shots(tmp_path, plan, capsys)
    errors = out.err.strip().splitlines()
    assert code == 2 and any(word in e for e in errors) and all(e.startswith("shots.json câu 2") for e in errors)
    assert list(_ok_lines(tmp_path)) == ["1", "3"] and _ok_lines(tmp_path)["1"] == plan["1"]  # the good ones are kept
    assert "nhịp hình" not in out.out


def test_a_card_line_counts_its_elements_as_changes_and_a_gap_is_refused(tmp_path, capsys):
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    plan["3"] = [{"phrase": 2, "focus": None}]  # the card is written out by 9.3 s, nothing changes to the end at 11.6
    code, out = _shots(tmp_path, plan, capsys)
    (err,) = out.err.splitlines()
    assert code == 2 and err.startswith("shots.json câu 3: ") and "không có thay đổi nào" in err
    plan["3"] = [{"phrase": 2, "focus": None}, {"phrase": 3, "focus": None}]  # a beat at 10.0 s closes it
    assert _shots(tmp_path, plan, capsys)[0] == 0


@pytest.mark.parametrize("field", ["mark", "focus"])
def test_mark_before_the_card_line_is_written_is_refused(tmp_path, capsys, field):
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    border, text1, text2, source = _card_pieces(tmp_path)
    assert text2.t1 > 8.8 >= text1.t1  # beat 2 starts at 8.8: text 1 is written by then, text 2 is not
    box = [round(v) for v in text2.box]
    plan["3"][1] = {"phrase": 2, field: box} if field == "focus" else {"phrase": 2, "mark": {"shape": "underline", "box": box}}
    code, out = _shots(tmp_path, plan, capsys)
    assert code == 2
    (err,) = [e for e in out.err.splitlines() if "câu 3" in e and "dòng chưa viết tới" in e]
    assert "nhịp 2" in err and field in err
    assert f"({round(text2.t1, 3)} s như shots/reveal.json)" in err and f"({round(8.8, 3)} s như shots/reveal.json)" in err  # the clock of reveal.json
    assert list(_ok_lines(tmp_path)) == ["1", "2"]
    plan["3"][1] = {"phrase": 2, "mark": {"shape": "underline", "box": [round(v) for v in text1.box]}}  # the line that is there
    assert _shots(tmp_path, plan, capsys)[0] == 0


@pytest.mark.parametrize("y1, refused", [(1000, True), (991, True), (989, False)])
def test_focus_into_the_old_caption_band_is_refused(tmp_path, capsys, y1, refused):
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    plan["1"] = [{"phrase": 1, "focus": None}, {"phrase": 2, "focus": [100, 700, 600, y1]}, {"phrase": 3, "focus": None}]
    # the band starts at 1000: no focus within 10 px of it
    plan["3"][0] = {"phrase": 1, "focus": [100, 800, 600, 1000]}  # a card has no old caption: the same box is fine there
    code, out = _shots(tmp_path, plan, capsys)
    band = [e for e in out.err.splitlines() if "phụ đề cũ" in e]
    assert bool(band) is refused and all("câu 1 nhịp 2" in e and "1000" in e for e in band)
    assert ("1" in _ok_lines(tmp_path)) is not refused and not any("câu 3" in e and "phụ đề cũ" in e for e in out.err.splitlines())


@pytest.mark.parametrize("at, refused", [(0.2, False), (0.3, True)])
def test_a_focus_too_near_the_end_of_the_line_is_refused(tmp_path, capsys, at, refused):
    # line 1 ends at 3.9: the camera needs SNAP to arrive and HOLD on it before it pulls back for the cut, so the latest
    # word of a focus is 3.9 - 1.0 = 2.9 s; phrase 3 runs 2.6-3.8 s and 'at' is a share of it: 0.2 -> 2.84 s, 0.3 -> 2.96 s
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    plan["1"][2] = {"phrase": 3, "at": at, "focus": None, "mark": {"shape": "tick", "box": [150, 350, 450, 450]}}
    code, out = _shots(tmp_path, plan, capsys)
    late = [e for e in out.err.splitlines() if "chậm nhất" in e]
    assert (code == 2) is refused and len(late) == int(refused)
    assert ("1" in _ok_lines(tmp_path)) is not refused
    if refused:
        assert late[0].startswith("shots.json câu 1 nhịp 3: ") and "2,90 s của câu" in late[0]  # the line, the beat, the latest time
        assert len(out.err.splitlines()) == 1
    plan["1"][2] = {"phrase": 3, "at": at, "mark": {"shape": "tick", "box": [150, 350, 450, 450]}}  # no focus: a mark may be last
    assert _shots(tmp_path, plan, capsys)[0] == 0


def test_lines_with_motion_are_not_allowed(tmp_path, capsys):
    _shots_run(tmp_path)
    (tmp_path / "motion.json").write_text("{}")
    (tmp_path / "motion.bind.json").write_text('{"lines": [2]}')
    assert main(["shots", str(tmp_path), "--prep"]) == 0
    assert "câu 2 (" not in (tmp_path / "shots" / "phrases.txt").read_text(encoding="utf-8")
    assert not (tmp_path / "frames" / "grid" / "2.png").exists()
    code, out = _shots(tmp_path, _good_plan(tmp_path), capsys)
    assert code == 2 and [e for e in out.err.splitlines() if "câu 2" in e] and "hình động" in out.err
    assert list(_ok_lines(tmp_path)) == ["1", "3"]


def test_lines_without_a_voice_or_a_frame_are_not_allowed(tmp_path, capsys):
    _shots_run(tmp_path)
    (tmp_path / "frames.json").write_text(json.dumps([r for r in json.loads((tmp_path / "frames.json").read_text()) if r["id"] != 4]))
    script = json.loads((tmp_path / "script.vi.json").read_text())
    script.append({"id": 5, "phrases": ""})
    (tmp_path / "script.vi.json").write_text(json.dumps(script, ensure_ascii=False))
    assert main(["shots", str(tmp_path), "--prep"]) == 0  # line 4 has a voice but no frame yet: the cuts around it still hold
    text = (tmp_path / "shots" / "phrases.txt").read_text(encoding="utf-8")
    assert "câu 3 (7.70–11.60s" in text and "câu 4 (" not in text and "câu 5 (" not in text
    plan = _good_plan(tmp_path) | {"4": [{"phrase": 1, "focus": None}], "5": [{"phrase": 1, "focus": None}]}
    code, out = _shots(tmp_path, plan, capsys)
    assert code == 2 and all("không thuộc" in e for e in out.err.splitlines()) and list(_ok_lines(tmp_path)) == ["1", "2", "3"]


def test_pops_are_counted_over_the_whole_video(tmp_path, capsys):
    _shots_run(tmp_path)
    plan = _good_plan(tmp_path)
    pop = lambda phrase, text: {"phrase": phrase, "pop": {"text": text, "box": [100, 700, 300, 780]}}
    plan["1"] = [pop(1, "Máy chủ"), pop(2, "Hà Nội"), pop(3, "ngày đêm")]  # three: the most there may be
    plan["2"] = [pop(1, "Dữ liệu")] + plan["2"][1:]  # the fourth is the second line's
    code, out = _shots(tmp_path, plan, capsys)
    assert code == 2 and len(out.err.splitlines()) == 1 and "câu 2" in out.err and "tối đa 3 pop" in out.err
    assert list(_ok_lines(tmp_path)) == ["1", "3"]


def test_shots_needs_a_readable_shots_json(tmp_path, capsys):
    _shots_run(tmp_path)
    assert main(["shots", str(tmp_path)]) == 2 and "thiếu shots.json" in capsys.readouterr().err
    (tmp_path / "shots.json").write_text("{oops")
    assert main(["shots", str(tmp_path)]) == 2 and "shots.json" in capsys.readouterr().err
    (tmp_path / "shots.json").write_text("[]")
    assert main(["shots", str(tmp_path)]) == 2 and "object" in capsys.readouterr().err
    assert not (tmp_path / "shots" / "ok.json").exists()


def test_shots_names_a_missing_frame_file_like_render_does(tmp_path, capsys):
    _shots_run(tmp_path)
    (tmp_path / "frames" / "2.png").unlink()
    assert main(["shots", str(tmp_path), "--prep"]) == 2
    err = capsys.readouterr().err
    assert "frames/2.png" in err and "vshort visuals" in err


def test_a_broken_run_shape_is_not_a_doodle_to_draw(tmp_path, capsys):
    _shots_run(tmp_path)
    (tmp_path / "shapes").mkdir()
    (tmp_path / "shapes" / "rong.json").write_text(json.dumps({"name": "rỗng", "strokes": []}))  # parses, draws nothing
    plan = _good_plan(tmp_path)
    plan["2"][2] = {"phrase": 3, "doodle": {"shape": "rong", "box": [200, 700, 400, 800]}}
    code, out = _shots(tmp_path, plan, capsys)
    assert code == 2 and "Traceback" not in out.err and "doodle shape 'rong'" in out.err
    assert list(_ok_lines(tmp_path)) == ["1", "3"]


def test_the_stamp_follows_the_pictures_the_cards_and_the_animation(tmp_path):
    _shots_run(tmp_path)
    run = Run(tmp_path)
    stamp = lambda ids=(1, 2, 3): cli._shots_stamp(run, ids)
    before = stamp()
    assert before == stamp() == json.loads(json.dumps(before))  # unchanged: equal, also after a round trip through ok.json
    Image.new("RGB", (720, 1280), (1, 2, 3)).save(tmp_path / "frames" / "1.png")  # a re-patched still or a swapped photo
    after = stamp()
    assert after != before and after["pictures"]["1"] != before["pictures"]["1"]
    assert after["pictures"]["2"] == before["pictures"]["2"] and stamp((2, 3)) == cli._shots_stamp(run, ["2", "3"])
    assert stamp((2, 3)) != stamp((2,))  # a line's own picture and card are in
    before = after
    (tmp_path / "visuals" / "3.svg").write_text(SHOT_CARD.replace("Cập nhật", "Cập nhật lại"), encoding="utf-8")
    after = stamp()
    assert after != before and after["cards"]["3"] != before["cards"]["3"] and after["pictures"] == before["pictures"]
    assert list(after["cards"]) == ["3"] and stamp((1, 2))["cards"] == {}  # which lines are cards
    before = after
    (tmp_path / "motion.json").write_text("{}")
    (tmp_path / "motion.bind.json").write_text('{"lines": [4, 2]}')  # a re-bind that animates lines
    after = stamp()
    assert after != before and after["animated"] == [2, 4]
    (tmp_path / "motion.bind.json").write_text('{"lines": [2, 4, 5]}')
    assert stamp()["animated"] == [2, 4, 5] != after["animated"]


@pytest.mark.parametrize("write", [None, "{oops", "[]"])
def test_a_plan_that_is_gone_or_unreadable_takes_its_ok_json_with_it(tmp_path, capsys, write):
    _shots_run(tmp_path)
    assert _shots(tmp_path, _good_plan(tmp_path), capsys)[0] == 0 and (tmp_path / "shots" / "ok.json").exists()
    (tmp_path / "shots.json").unlink()
    if write:
        (tmp_path / "shots.json").write_text(write)
    assert main(["shots", str(tmp_path)]) == 2
    assert not (tmp_path / "shots" / "ok.json").exists()  # render must not go on with the beats of a plan that is not there


def test_ok_json_is_written_before_the_sheet_is_drawn(tmp_path, capsys, monkeypatch):
    _shots_run(tmp_path)

    def boom(lines):
        raise RuntimeError("sheet")

    monkeypatch.setattr(cli, "_shots_sheet", boom)
    with pytest.raises(RuntimeError):
        _shots(tmp_path, _good_plan(tmp_path), capsys)
    assert list(_ok_lines(tmp_path)) == ["1", "2", "3"]  # the verdicts are not lost with the sheet


# ---- render follows shots/ok.json ----

STALE = {  # what a fix-up of the translation, the pictures or the timeline does after `vshort shots`
    "script": lambda p: (p / "script.vi.json").write_text(json.dumps(
        [{"id": i, "phrases": t.replace("Hà Nội", "Đà Nẵng")} for i, t in SHOT_SAY.items()]), encoding="utf-8"),
    "picture": lambda p: Image.new("RGB", (720, 1280), (1, 2, 3)).save(p / "frames" / "1.png"),
    "card": lambda p: (p / "visuals" / "3.svg").write_text(SHOT_CARD.replace("hôm nay", "hôm qua"), encoding="utf-8"),
    "timeline": lambda p: (p / "timeline.json").write_text(json.dumps({"total": 15.6, "placements": [
        {"id": i, "start": s + (0.1 if i == 2 else 0), "dur": d} for i, (s, d) in SHOT_AT.items()]})),
    "ok.json": lambda p: (p / "shots" / "ok.json").write_text("{oops"),
}


def _planned_run(tmp_path, capsys):
    _shots_run(tmp_path)
    write_silence(tmp_path / "narration.wav", 15.6)
    assert _shots(tmp_path, _good_plan(tmp_path), capsys)[0] == 0
    capsys.readouterr()
    return tmp_path


def shots_beats(rows, i):
    from vshort import shots
    from vshort.fit import Placement
    start, dur = SHOT_AT[i]
    return shots.beats(rows, SHOT_SAY[i], Placement(i, start, dur))


def test_shots_judges_the_camera_that_pulls_back_before_the_cut(tmp_path, capsys):
    _shots_run(tmp_path)
    plan = {"1": [{"phrase": 1, "focus": [100, 300, 500, 500]},
                  {"phrase": 2, "mark": {"shape": "tick", "box": [150, 350, 450, 450]}},
                  # on the screen at the focus (1.5x) this circle clears the phone's top bar; on the wide shot it does not
                  {"phrase": 3, "mark": {"shape": "circle", "box": [160, 150, 440, 330]}}]}
    code, out = _shots(tmp_path, plan, capsys)
    assert code == 2 and "câu 1 nhịp 3" in out.err and "thanh trên" in out.err  # covered only once the camera is back
    assert list(_ok_lines(tmp_path)) == []


def test_clean_cmd_writes_clean_mp4_and_its_summary(make_video, tmp_path):
    make_video(tmp_path, scenes=[(0, 1, "#F3EFE6")], captions=[]).rename(tmp_path / "source.mp4")
    (tmp_path / "captions.json").write_text("[]")
    assert main(["clean", str(tmp_path)]) == 0
    assert (tmp_path / "clean.mp4").exists() and Run(tmp_path).done("clean")
    assert json.loads((tmp_path / "clean.json").read_text())["boxes"] == []

