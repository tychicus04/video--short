import json
from subprocess import CompletedProcess

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
    (tmp_path / "script.vi.json").write_text('[{"id": 1, "phrases": "một hai ba bốn năm sáu bảy tám", "note": ""}]')
    assert main(["check", str(tmp_path)]) == 2


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
