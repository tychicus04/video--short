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
    return tmp_path


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
    assert all(s in err for s in ["9", "900", "visuals/", "source"])
    assert not (tmp_path / "frames").exists() and not (tmp_path / "frames.json").exists()
    assert not Run(tmp_path).done("visuals")


def test_visuals_cmd_rejects_unknown_patch_ids(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [1, 7], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 2
    assert "[7]" in capsys.readouterr().err and not (tmp_path / "frames").exists()


def test_visuals_cmd_reports_unreadable_files_with_the_other_problems(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3, 4), scenes=(0, 0, 1))
    (tmp_path / "visuals").mkdir()
    (tmp_path / "visuals" / "3.svg").write_text("<svg")
    (tmp_path / "visuals" / "4.jpg").write_bytes(b"not a jpeg")
    (tmp_path / "visuals.json").write_text(json.dumps([
        {"kind": "patch", "ids": [7], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "n"},
        {"kind": "svg", "id": 3, "file": "visuals/3.svg", "source": "https://a.example", "accessed": "2026-10-31",
         "note": "n"},
        {"kind": "photo", "id": 4, "file": "visuals/4.jpg", "source": "https://a.example", "accessed": "2026-10-31",
         "credit": "Nguồn: A", "note": "n"},
    ]))
    assert main(["visuals", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "[7]" in err and "visuals/3.svg" in err and "visuals/4.jpg" in err  # one run shows all three
    assert not (tmp_path / "frames").exists() and not (tmp_path / "frames.json").exists()


def test_visuals_cmd_rejects_bad_json(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1,), scenes=(0,))
    for text in ("{oops", '{"kind": "patch"}'):
        (tmp_path / "visuals.json").write_text(text)
        assert main(["visuals", str(tmp_path)]) == 2
        assert "visuals.json" in capsys.readouterr().err
    assert not (tmp_path / "frames").exists()


def test_visuals_cmd_groups_and_replaces(tmp_path):
    _visuals_run(tmp_path)
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "99.png").write_bytes(b"stale")
    (tmp_path / "visuals").mkdir()
    Image.new("RGB", (500, 300), (30, 120, 60)).save(tmp_path / "visuals" / "4.jpg")
    box = [96, 96, 404, 144]
    (tmp_path / "visuals.json").write_text(json.dumps([
        {"kind": "patch", "ids": [1, 3], "box": box, "text": "tin-tuc.example", "note": "địa chỉ sai"},
        {"kind": "photo", "id": 4, "file": "visuals/4.jpg", "source": "https://a.example/p", "accessed": "2026-10-31",
         "credit": "Nguồn: A", "note": "ảnh báo cáo"},
    ]))
    assert main(["visuals", str(tmp_path)]) == 0
    rows = json.loads((tmp_path / "frames.json").read_text())
    assert [r["id"] for r in rows] == [1, 3, 4] and [r["group"] for r in rows] == ["s0", "s0", "v4"]
    assert all(r["file"] == f"frames/{r['id']}.png" for r in rows)
    assert not (tmp_path / "frames" / "99.png").exists() and Run(tmp_path).done("visuals")
    for i in (1, 3):
        before, after = _png(tmp_path / "stills" / f"{i}.png"), _png(tmp_path / "frames" / f"{i}.png")
        assert np.abs(before[96:144, 96:404] - after[96:144, 96:404]).max() > 0
        before[96:144, 96:404] = after[96:144, 96:404] = 0
        assert np.array_equal(before, after)
    f4 = _png(tmp_path / "frames" / "4.png")
    assert f4.shape == (1280, 720, 3) and np.abs(f4 - _png(tmp_path / "stills" / "4.png")).max() > 0

    for text in ("[]", None):  # nothing to do: an empty list and an absent file both give the stills back
        (tmp_path / "visuals.json").unlink()
        if text:
            (tmp_path / "visuals.json").write_text(text)
        assert main(["visuals", str(tmp_path)]) == 0
        rows = json.loads((tmp_path / "frames.json").read_text())
        assert [r["group"] for r in rows] == ["s0", "s0", "s1"]
        for i in (1, 3, 4):
            assert np.array_equal(_png(tmp_path / "frames" / f"{i}.png"), _png(tmp_path / "stills" / f"{i}.png"))


def test_visuals_cmd_reference_replaces_a_patched_line(tmp_path):
    _visuals_run(tmp_path, ids=(1, 2), scenes=(0, 0))
    (tmp_path / "visuals").mkdir()
    (tmp_path / "visuals" / "2.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280"><rect x="100" y="300" width="200" '
        'height="200" fill="#4a4a4a"/></svg>')
    (tmp_path / "visuals.json").write_text(json.dumps([
        {"kind": "patch", "ids": [1, 2], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "địa chỉ sai"},
        {"kind": "svg", "id": 2, "file": "visuals/2.svg", "source": "https://a.example", "accessed": "2026-10-31",
         "note": "n"},
    ]))
    assert main(["visuals", str(tmp_path)]) == 0
    assert [r["group"] for r in json.loads((tmp_path / "frames.json").read_text())] == ["s0", "v2"]
    f2 = _png(tmp_path / "frames" / "2.png")
    assert tuple(f2[0, 0]) == (238, 234, 226) and tuple(f2[400, 200]) == (74, 74, 74) and f2[96:144, 96:404].min() > 200


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


def _render_run(tmp_path, frame_ids):
    (tmp_path / "frames").mkdir()
    for i, c in zip((1, 3), ((200, 30, 30), (30, 30, 200))):
        Image.new("RGB", (720, 1280), c).save(tmp_path / "frames" / f"{i}.png")
    (tmp_path / "timeline.json").write_text(json.dumps(
        {"total": 3.0, "placements": [{"id": 1, "start": 0.2, "dur": 1.0}, {"id": 3, "start": 1.5, "dur": 1.0}]}))
    (tmp_path / "frames.json").write_text(json.dumps(
        [{"id": i, "file": f"frames/{i}.png", "group": f"s{i}"} for i in frame_ids]))
    (tmp_path / "script.vi.json").write_text(json.dumps([{"id": 1, "phrases": "a"}, {"id": 3, "phrases": "b"}]))
    write_silence(tmp_path / "narration.wav", 3.0)


def test_render_cmd_uses_the_frames_of_the_placed_lines(tmp_path, capsys):
    _render_run(tmp_path, (1, 2, 3))  # a frame without a voice is just not shown
    assert main(["render", str(tmp_path)]) == 0
    assert (tmp_path / "final.mp4").exists() and Run(tmp_path).done("render")
    assert str(tmp_path / "final.mp4") in capsys.readouterr().out


def test_render_cmd_names_the_lines_without_a_frame(tmp_path, capsys):
    _render_run(tmp_path, (1,))
    (tmp_path / "stills.json").write_text(json.dumps([{"id": i, "t": 1.0, "scene": 0} for i in (1, 3)]))
    assert main(["render", str(tmp_path)]) == 2  # the still exists, only the frame is missing
    assert capsys.readouterr().err == "frames.json thiếu các câu: 3 (chạy lại `vshort visuals`)\n"
    assert not (tmp_path / "final.mp4").exists()


def test_render_cmd_sends_lines_without_a_still_back_to_stills(tmp_path, capsys):
    _render_run(tmp_path, (1,))
    for stills in ([{"id": 1, "t": 1.0, "scene": 0}], None):  # 3 is not in stills.json, or there is no stills.json
        (tmp_path / "stills.json").unlink(missing_ok=True)
        if stills:
            (tmp_path / "stills.json").write_text(json.dumps(stills))
        assert main(["render", str(tmp_path)]) == 2
        assert capsys.readouterr().err == ("frames.json thiếu các câu: 3 "
                                           "(chạy lại `vshort stills`, rồi vs-visuals và `vshort visuals`)\n")


def test_render_cmd_names_missing_frame_files_and_keeps_the_old_video(tmp_path, capsys):
    _render_run(tmp_path, (1, 3))
    (tmp_path / "frames" / "3.png").unlink()
    (tmp_path / "final.mp4").write_bytes(b"good")
    assert main(["render", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "thiếu file khung hình: frames/3.png (chạy lại `vshort visuals`)\n"
    assert (tmp_path / "final.mp4").read_bytes() == b"good" and not Run(tmp_path).done("render")


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


def test_old_motion_file_is_rejected_plainly(tmp_path, capsys):
    _motion_run(tmp_path)
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


def test_visuals_cmd_rejects_a_reference_on_an_animated_line(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "motion.json").write_text("{}")
    (tmp_path / "motion.bind.json").write_text(json.dumps({"lines": [3]}))
    (tmp_path / "visuals").mkdir()
    Image.new("RGB", (500, 300)).save(tmp_path / "visuals" / "3.jpg")
    (tmp_path / "visuals.json").write_text(json.dumps([{"kind": "photo", "id": 3, "file": "visuals/3.jpg",
        "source": "https://a.example/p", "accessed": "2026-11-01", "credit": "Nguồn: A", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 2
    assert "hình động" in capsys.readouterr().err


def test_visuals_cmd_still_patches_an_animated_line(tmp_path):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "motion.json").write_text("{}")
    (tmp_path / "motion.bind.json").write_text(json.dumps({"lines": [3]}))
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [3], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 0


def test_render_cmd_rejects_a_stale_motion_file(tmp_path, capsys):
    _render_run(tmp_path, (1, 3))
    (tmp_path / "final.mp4").write_bytes(b"good")
    (tmp_path / "motion.json").write_text(json.dumps({"lines": [3, 5], "note": "n", "scenes": []}))
    assert main(["render", str(tmp_path)]) == 2
    assert "vshort motion" in capsys.readouterr().err and (tmp_path / "final.mp4").read_bytes() == b"good"


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


def test_render_cmd_rejects_a_script_changed_after_motion(tmp_path, capsys):
    _goi_tin_run(tmp_path)
    assert main(["motion", str(tmp_path)]) == 0
    script = json.loads((tmp_path / "script.vi.json").read_text())
    script[1]["phrases"] = "Bạn ngồi quán cà phê, | mở điện thoại | và kết nối gói tin."  # same phrase count
    (tmp_path / "script.vi.json").write_text(json.dumps(script, ensure_ascii=False))
    (tmp_path / "final.mp4").write_bytes(b"good")
    assert main(["render", str(tmp_path)]) == 2
    assert "vshort motion" in capsys.readouterr().err and (tmp_path / "final.mp4").read_bytes() == b"good"


def test_render_cmd_names_animated_lines_missing_from_the_timeline(tmp_path, capsys):
    _goi_tin_run(tmp_path)
    assert main(["motion", str(tmp_path)]) == 0
    tl = json.loads((tmp_path / "timeline.json").read_text())
    tl["placements"] = [p for p in tl["placements"] if p["id"] != 3]
    (tmp_path / "timeline.json").write_text(json.dumps(tl))
    assert main(["render", str(tmp_path)]) == 2
    assert "vshort timeline" in capsys.readouterr().err


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
