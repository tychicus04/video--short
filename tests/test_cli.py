import json
from subprocess import CompletedProcess

import numpy as np
from conftest import write_silence
from PIL import Image, ImageDraw

from vshort import cli
from vshort.cli import main
from vshort.run import Run
from vshort.tts import QuotaExceeded


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


def test_check_exit_2(tmp_path):
    (tmp_path / "sentences.en.json").write_text('[{"id": 1, "start": 0, "end": 1, "en": "Hi."}]')
    (tmp_path / "script.vi.json").write_text('[{"id": 1, "phrases": "", "note": ""}]')
    assert main(["check", str(tmp_path)]) == 2


def test_timeline_writes_back_to_back_narration(tmp_path):
    for i in (1, 3):
        write_silence(tmp_path / f"{i}.wav", 1.0)
    (tmp_path / "tts.json").write_text(json.dumps(
        [{"id": i, "path": str(tmp_path / f"{i}.wav"), "duration": 1.0} for i in (1, 3)]))
    (tmp_path / "script.vi.json").write_text(json.dumps(
        [{"id": 1, "phrases": "a"}, {"id": 2, "phrases": ""}, {"id": 3, "phrases": "b"}]))
    assert main(["timeline", str(tmp_path)]) == 0
    t = json.loads((tmp_path / "timeline.json").read_text())
    assert [p["id"] for p in t["placements"]] == [1, 3] and abs(t["total"] - 3.0) < 1e-6  # 0.2+1+0.3+1+0.5
    assert (tmp_path / "narration.wav").exists() and Run(tmp_path).done("timeline")


def test_tts_quota_exit_75(tmp_path, monkeypatch, capsys):
    (tmp_path / "script.vi.json").write_text('[{"id": 1, "phrases": "Xin | *chào*", "note": ""}]')
    monkeypatch.setattr(cli, "load_api_key", lambda p: "k")
    seen = []

    def speaker(key, model, voice):
        def speak(text):
            seen.append(text)
            raise QuotaExceeded()
        return speak

    monkeypatch.setattr(cli, "gemini_speaker", speaker)
    assert main(["tts", str(tmp_path)]) == 75
    assert seen == ["Xin chào."]  # the words the subtitles show, without | and *, closed with a full stop
    assert "chạy lại" in capsys.readouterr().err


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
        {"kind": "patch", "ids": [9], "box": [0, 0, 900, 50], "text": "x.example"},
        {"kind": "svg", "id": 1, "file": "visuals/1.svg", "source": "https://a.example", "accessed": "2026-10-31"},
        {"kind": "photo", "id": 3, "file": "visuals/3.jpg", "accessed": "2026-10-31", "credit": "Nguồn: A"},
    ]))
    assert main(["visuals", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert all(s in err for s in ["9", "900", "visuals/", "source"])
    assert not (tmp_path / "frames").exists() and not (tmp_path / "frames.json").exists()
    assert not Run(tmp_path).done("visuals")


def test_visuals_cmd_rejects_unreadable_files_before_writing(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "visuals").mkdir()
    (tmp_path / "visuals" / "3.svg").write_text("<svg")
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "svg", "id": 3, "file": "visuals/3.svg", "source": "https://a.example", "accessed": "2026-10-31"}]))
    assert main(["visuals", str(tmp_path)]) == 2
    assert "visuals/3.svg" in capsys.readouterr().err and not (tmp_path / "frames").exists()


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
        {"kind": "patch", "ids": [1, 3], "box": box, "text": "tin-tuc.example", "note": ""},
        {"kind": "photo", "id": 4, "file": "visuals/4.jpg", "source": "https://a.example/p", "accessed": "2026-10-31",
         "credit": "Nguồn: A", "note": ""},
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
        {"kind": "patch", "ids": [1, 2], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": ""},
        {"kind": "svg", "id": 2, "file": "visuals/2.svg", "source": "https://a.example", "accessed": "2026-10-31"},
    ]))
    assert main(["visuals", str(tmp_path)]) == 0
    assert [r["group"] for r in json.loads((tmp_path / "frames.json").read_text())] == ["s0", "v2"]
    f2 = _png(tmp_path / "frames" / "2.png")
    assert tuple(f2[0, 0]) == (238, 234, 226) and tuple(f2[400, 200]) == (74, 74, 74) and f2[96:144, 96:404].min() > 200
