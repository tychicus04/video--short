import io
import json
import shutil
import wave
from subprocess import CompletedProcess

import numpy as np
import pytest
from conftest import write_silence
from PIL import Image, ImageDraw

from vshort import cli, hf
from vshort.cli import main
from vshort.media import frame_at, probe
from vshort.render import OUTRO
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


def _long_voice(run, style):
    """14 sentences of 4.5 s: 63 s of speech, 70.2 s with fit's breaths, 72.7 s with the outro."""
    run.mkdir()
    _timeline_run(run, [{"id": k, "phrases": f"câu {k}"} for k in range(1, 15)])
    rows = json.loads((run / "tts.json").read_text())
    (run / "tts.json").write_text(json.dumps([r | {"duration": 4.5} for r in rows]))
    (run / "run.json").write_text(json.dumps({"slug": "x"} | style))
    assert main(["timeline", str(run)]) == 0
    return json.loads((run / "timeline.json").read_text())


def test_timeline_plays_a_neon_voice_faster_when_the_video_would_pass_70_s(tmp_path, capsys):
    t = _long_voice(tmp_path / "neon", {"style": "neon"})
    assert 1 < t["tempo"] <= 1.05 and 60 <= t["total"] + 2.5 <= 70  # final.mp4 = the voice + the 2.5 s outro
    assert t["placements"][0]["dur"] == pytest.approx(4.5 / t["tempo"])
    assert "nhanh hơn" in capsys.readouterr().out
    old = _long_voice(tmp_path / "old", {})
    assert old["tempo"] == 1.0 and old["total"] == pytest.approx(70.2)  # the NotebookLM flow has no such rule


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


def test_render_cmd_types_the_spoken_title_into_the_bar_instead_of_its_subtitle(tmp_path, make_video):
    _render_run(tmp_path, make_video)
    assert main(["render", str(tmp_path)]) == 0
    subs = (tmp_path / "subs.ass").read_text(encoding="utf-8")
    assert "Một câu" not in subs and "Hai" in subs  # line 1 is in the bar, not twice on screen
    assert (tmp_path / "title.mov").exists()
    box = frame_at(tmp_path / "final.mp4", 1.2)[688, 647].astype(int)
    assert np.abs(box - (32, 107, 136)).max() < 25  # the bar's teal box while line 1 is said


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

# ---- `vshort render` of a neon run: the diagram rendered by HyperFrames, the voice, three accents, the outro ----

def _neon_render_run(tmp_path, total=4.0):
    """A neon run at the end of `vshort scene`: scene.resolved.json and the voice; no clean.mp4, no English."""
    (tmp_path / "run.json").write_text('{"slug": "x", "style": "neon"}')
    rt = {"total": total, "title": None, "captions": [], "elements": [{"id": "n", "kind": "icon"}, {"id": "h", "kind": "hero"}],
          "actions": [{"t": 0.5, "do": "on", "ids": ["n"]}, {"t": 2.1, "do": "draw", "ids": ["h"], "d": 0.7},
                      {"t": 3.7, "do": "tone", "ids": ["n"], "to": "risk"}]}
    (tmp_path / "scene.resolved.json").write_text(json.dumps(rt))
    write_silence(tmp_path / "narration.wav", total)
    return rt


@pytest.fixture
def hyperframes(monkeypatch):
    """HyperFrames without node: the composition is only noted, validate finds nothing, render copies `.clip` to where it is told."""
    calls = {"written": [], "clip": None}
    monkeypatch.setattr(cli, "write_composition", lambda rt, d: calls["written"].append((rt, d)))
    monkeypatch.setattr(hf, "validate", lambda d: [])
    monkeypatch.setattr(hf, "render", lambda d, out, timeout=600: shutil.copy(calls["clip"], out))
    return calls


def test_render_cmd_neon_makes_the_final_from_the_rendered_diagram(tmp_path, make_video, hyperframes, capsys):
    rt = _neon_render_run(tmp_path)
    hyperframes["clip"] = make_video(tmp_path, scenes=[(0, 4, "#2BE3FF")], captions=[])
    assert main(["render", str(tmp_path)]) == 0
    out = tmp_path / "final.mp4"
    assert hyperframes["written"] == [(rt, tmp_path / "neon")] and str(out) in capsys.readouterr().out
    assert Run(tmp_path).done("render") and (tmp_path / "mix.wav").exists() and (tmp_path / "visuals.mp4").exists()
    assert abs(probe(out).duration - (4.0 + probe(OUTRO).duration)) < 0.1
    assert json.loads((tmp_path / "sfx.json").read_text()) == [{"name": "whoosh", "at": 0.5}, {"name": "pop", "at": 2.1},
                                                               {"name": "glitch", "at": 3.7}]
    assert np.abs(frame_at(out, 1.0)[640, 360].astype(int) - (0x2B, 0xE3, 0xFF)).max() < 12


def test_render_cmd_neon_stops_cleanly_when_hyperframes_fails(tmp_path, hyperframes, monkeypatch, capsys):
    _neon_render_run(tmp_path)
    for old in ("final.mp4", "visuals.mp4"):  # the last round's: a failed round must not leave them looking fresh
        (tmp_path / old).write_bytes(b"old")
    Run(tmp_path).mark("render")

    def boom(d, out, timeout=600):
        raise hf.HFError("HyperFrames render lỗi (mã 1):\nlint: gsap_infinite_repeat")

    monkeypatch.setattr(hf, "render", boom)
    assert main(["render", str(tmp_path)]) == 1
    assert not (tmp_path / "final.mp4").exists() and not (tmp_path / "visuals.mp4").exists() and not Run(tmp_path).done("render")
    assert "gsap_infinite_repeat" in capsys.readouterr().err


def test_render_cmd_neon_does_not_render_a_composition_that_does_not_validate(tmp_path, hyperframes, monkeypatch, capsys):
    _neon_render_run(tmp_path)
    monkeypatch.setattr(hf, "validate", lambda d: ['kit: unknown action "foo" at 2.85 s'])

    def never(d, out, timeout=600):
        raise AssertionError("rendered a page that does not validate")

    monkeypatch.setattr(hf, "render", never)
    assert main(["render", str(tmp_path)]) == 1
    assert 'unknown action "foo"' in capsys.readouterr().err and not (tmp_path / "final.mp4").exists()


def test_render_cmd_neon_refuses_visuals_of_the_wrong_length(tmp_path, make_video, hyperframes, capsys):
    _neon_render_run(tmp_path)
    hyperframes["clip"] = make_video(tmp_path, scenes=[(0, 3, "#2BE3FF")], captions=[])  # 3 s for a 4 s voice
    assert main(["render", str(tmp_path)]) == 1
    assert "visuals.mp4" in capsys.readouterr().err
    assert not (tmp_path / "visuals.mp4").exists() and not (tmp_path / "final.mp4").exists() and not Run(tmp_path).done("render")


@pytest.mark.parametrize("damage", ["scene.resolved.json", "narration.wav", "unreadable"])
def test_render_cmd_neon_names_what_is_missing_and_keeps_the_finished_video(tmp_path, hyperframes, capsys, damage):
    """The inputs are checked before anything is deleted: a finished video whose inputs are gone cannot be made again."""
    _neon_render_run(tmp_path)
    for done in ("final.mp4", "visuals.mp4"):
        (tmp_path / done).write_bytes(b"good")
    Run(tmp_path).mark("render")
    if damage == "unreadable":
        (tmp_path / "scene.resolved.json").write_text('{"total": ', encoding="utf-8")
    else:
        (tmp_path / damage).unlink()
    assert main(["render", str(tmp_path)]) == 2
    assert ("scene.resolved.json" if damage == "unreadable" else damage) in capsys.readouterr().err
    assert (tmp_path / "final.mp4").read_bytes() == b"good" and (tmp_path / "visuals.mp4").read_bytes() == b"good"
    assert Run(tmp_path).done("render") and hyperframes["written"] == []


@pytest.mark.skipif(not hf.available(), reason="chưa cài vshort/neon (npm ci)")
def test_render_cmd_neon_with_the_real_hyperframes(tmp_path):
    """Nothing stubbed: validate, then render under --strict (a lint error would stop it), on the kit's own sample scene."""
    from test_compose import small_scene
    rt = small_scene()
    _neon_render_run(tmp_path, rt["total"])
    (tmp_path / "scene.resolved.json").write_text(json.dumps(rt))
    assert main(["render", str(tmp_path)]) == 0
    assert abs(probe(tmp_path / "visuals.mp4").duration - rt["total"]) < 1 / 30
    assert abs(probe(tmp_path / "final.mp4").duration - (rt["total"] + probe(OUTRO).duration)) < 0.1
    assert [c["name"] for c in json.loads((tmp_path / "sfx.json").read_text())] == ["whoosh", "glitch"]
    assert frame_at(tmp_path / "final.mp4", 4.0)[400:1000].max() > 150  # the diagram is drawn (the nodes, the red one, the dot)


def test_status_lists_every_step_in_order(tmp_path, capsys):
    Run(tmp_path).mark("tts")
    assert main(["status", str(tmp_path)]) == 0
    marks = [ln.split() for ln in capsys.readouterr().out.splitlines()]
    assert marks == [[("✓" if s == "tts" else "·"), s]
                     for s in "new fetch detect text clean tts stills visuals timeline render".split()]


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


def test_auto_style_neon_is_written_to_run_json_and_only_then(tmp_path, monkeypatch):
    from vshort import auto
    monkeypatch.setattr(auto, "run_auto", lambda run: 0)
    assert main(["auto", "neon-one", "--topic", "X", "--style", "neon", "--runs-dir", str(tmp_path), "--foreground"]) == 0
    assert main(["auto", "old-one", "--topic", "X", "--runs-dir", str(tmp_path), "--foreground"]) == 0
    assert Run(tmp_path / "neon-one").read("run.json")["style"] == "neon"
    assert "style" not in Run(tmp_path / "old-one").read("run.json")
    assert (cli.style_of(Run(tmp_path / "neon-one")), cli.style_of(Run(tmp_path / "old-one"))) == ("neon", "old")
    assert cli.style_of(Run(tmp_path / "chưa")) == "old"  # no run.json at all
    assert main(["auto", str(tmp_path / "old-one"), "--style", "neon", "--foreground"]) == 0  # the flag lives in run.json
    assert cli.style_of(Run(tmp_path / "old-one")) == "old"


def _neon_run(tmp_path, phrases):
    (tmp_path / "run.json").write_text('{"slug": "x", "style": "neon"}')
    (tmp_path / "brief.vi.md").write_text("Tiêu đề (câu mở đầu)\nMột tiêu đề\nLời kêu gọi\nChia sẻ video.\n", encoding="utf-8")
    rows = [{"id": 1, "phrases": "Một tiêu đề", "note": ""}]
    rows += [{"id": i + 2, "phrases": p, "note": ""} for i, p in enumerate(phrases)]
    (tmp_path / "script.vi.json").write_text(json.dumps(rows), encoding="utf-8")  # and no sentences.en.json


def test_check_neon_run_checks_the_script_against_the_brief_not_english(tmp_path, capsys):
    _neon_run(tmp_path, [" | ".join(["Lời nói ngắn gọn thôi mà"] * 3)] * 13 + ["Chia sẻ video."])
    assert main(["check", str(tmp_path)]) == 0
    (tmp_path / "script.vi.json").write_text(json.dumps([{"id": 1, "phrases": "Khác", "note": ""}]))
    assert main(["check", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "tiêu đề của brief" in err and "giây" in err


def test_check_neon_run_still_holds_the_end_to_the_briefs_call_to_action(tmp_path, capsys):
    _neon_run(tmp_path, [" | ".join(["Lời nói ngắn gọn thôi mà"] * 3)] * 14)
    assert main(["check", str(tmp_path)]) == 2
    assert "lời kêu gọi" in capsys.readouterr().err


def test_approve_brief_of_a_neon_run_needs_no_english_brief(tmp_path):
    _neon_run(tmp_path, [])
    assert main(["approve", str(tmp_path), "brief"]) == 0 and Run(tmp_path).done("approve_brief")


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


def test_clean_cmd_writes_clean_mp4_and_its_summary(make_video, tmp_path):
    make_video(tmp_path, scenes=[(0, 1, "#F3EFE6")], captions=[]).rename(tmp_path / "source.mp4")
    (tmp_path / "captions.json").write_text("[]")
    assert main(["clean", str(tmp_path)]) == 0
    assert (tmp_path / "clean.mp4").exists() and Run(tmp_path).done("clean")
    assert json.loads((tmp_path / "clean.json").read_text())["boxes"] == []

