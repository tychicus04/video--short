"""`vshort <command> <run_dir>`: every pipeline step as a command that can be re-run."""
import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from vshort.captions import Fragment, detect_fragments, write_sheets
from vshort.fit import Placement, build_narration, phrase_times, place, too_long
from vshort.media import probe
from vshort.plates import Plate, build_plates, scene_cuts
from vshort.render import build_ass, compose, outro_cut
from vshort.run import Run, config, set_config
from vshort.script import Sentence, budget, check_script, group_sentences, merge_text
from vshort.tts import Clip, QuotaExceeded, gemini_speaker, load_api_key, measured_rate, synth_script

ROOT = Path(__file__).resolve().parent.parent
OK, FAILED, BAD_INPUT, TOO_LONG, AUTH, QUOTA = 0, 1, 2, 3, 4, 75
RELOGIN = (
    "NotebookLM đã hết phiên đăng nhập. Trên Mac chạy `notebooklm login`, rồi scp storage_state.json sang server:\n"
    "  scp ~/.notebooklm/profiles/default/storage_state.json tai@pve2:~/.notebooklm/profiles/default/\n"
    "Sau đó chạy lại lệnh này."
)


def run_notebooklm(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["uv", "run", "notebooklm", *args], cwd=Path(config()["notebooklm_dir"]).expanduser(),
                          capture_output=True, text=True)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _notebooklm(args: list[str]) -> tuple[subprocess.CompletedProcess, int]:
    cp = run_notebooklm(args)
    if cp.returncode == 0:
        return cp, OK
    out = (cp.stdout + cp.stderr).lower()
    if "not logged in" in out or "notebooklm login" in out or "auth" in out:
        _err(RELOGIN)
        return cp, AUTH
    _err(cp.stderr or cp.stdout)
    return cp, FAILED


def _json(stdout: str) -> dict:
    return json.loads(stdout[stdout.index("{"):])  # the CLI may print a "Matched: …" line first


def _speech(phrases: str) -> str:
    """What the voice says = what the subtitles show, without the | and * markup."""
    return " ".join(phrases.replace("|", " ").replace("*", "").split())


def _sentences(run: Run) -> list[Sentence]:
    return [Sentence(**s) for s in run.read("sentences.en.json")]


def cmd_new(a) -> int:
    run = Run(Path(a.runs_dir or config()["runs_dir"]).expanduser() / a.slug)
    run.path.mkdir(parents=True, exist_ok=True)
    run.write("run.json", {"slug": a.slug, "notebook_id": a.notebook or "", "kicker": a.kicker, "title": a.title})
    run.mark("new")
    print(run.path)
    return OK


def cmd_fetch(a) -> int:
    run = Run(a.run)
    meta = run.read("run.json")
    nb = a.notebook or meta["notebook_id"]
    if not nb:
        _err("Thiếu --notebook")
        return BAD_INPUT
    meta["notebook_id"] = nb
    run.write("run.json", meta)
    prompt = [a.prompt] if a.prompt else []  # steers NotebookLM to follow the approved brief
    cp, code = _notebooklm(["generate", "video", "--format", "short", "--language", "en", "-n", nb, "--no-wait", "--json",
                            *prompt])
    if code:
        return code
    task = _json(cp.stdout)["task_id"]
    cp, code = _notebooklm(["artifact", "wait", task, "-n", nb, "--timeout", "2400", "--json"])
    if code:
        return code
    if _json(cp.stdout).get("status") != "completed":
        _err(f"NotebookLM chưa tạo xong video: {cp.stdout.strip()}")
        return FAILED
    cp, code = _notebooklm(["download", "video", "-n", nb, "-a", task, "--force", str(run.file("source.mp4"))])
    if code:
        return code
    meta["artifact_id"] = task
    run.write("run.json", meta)
    run.mark("fetch")
    return OK


def cmd_detect(a) -> int:
    run = Run(a.run)
    frags = detect_fragments(run.file("source.mp4"))
    run.write("fragments.json", [asdict(f) for f in frags])
    sheets = write_sheets(run.file("source.mp4"), frags, run.file("sheets"))
    print(f"{len(frags)} mảnh phụ đề; ảnh để đọc: " + ", ".join(map(str, sheets)))
    run.mark("detect")
    return OK


def cmd_text(a) -> int:
    run = Run(a.run)
    frags = [Fragment(**f) for f in run.read("fragments.json")]
    texts = {int(k): v for k, v in run.read("fragments_text.json").items()}
    captions = merge_text(frags, texts)
    run.write("captions.json", [asdict(f) for f in captions])
    sents = group_sentences(captions)
    run.write("sentences.en.json", [asdict(s) for s in sents])
    rate = config()["syllables_per_sec"]
    for s in sents:
        print(f"{s.id}\t{s.end - s.start:5.2f}s\ttối đa {budget(s, rate)} âm tiết\t{s.en}")
    run.mark("text")
    return OK


def cmd_check(a) -> int:
    run = Run(a.run)
    probs = check_script(_sentences(run), run.read("script.vi.json"), config()["syllables_per_sec"])
    for p in probs:
        _err(p)
    if probs:
        return BAD_INPUT
    print("Kịch bản tiếng Việt hợp lệ.")
    return OK


def cmd_plates(a) -> int:
    run = Run(a.run)
    captions = [Fragment(**f) for f in run.read("captions.json")]
    plates = build_plates(run.file("source.mp4"), captions, run.file("plates"), ROOT / "models" / "big-lama.pt")
    for p in plates:
        print(f"{p.name} {p.start:.2f}-{p.end:.2f} {p.method}" + (" (cảnh có chuyển động: cần soát)" if p.moving else ""))
    run.mark("plates")
    return OK


def cmd_tts(a) -> int:
    run = Run(a.run)
    cfg = config()
    lines = [(row["id"], _speech(row["phrases"])) for row in run.read("script.vi.json")]
    speak = gemini_speaker(load_api_key(Path(cfg["env_file"]).expanduser()), cfg["tts_model"], cfg["voice"])
    try:
        clips = synth_script(lines, run.file("tts"), speak, tag=f"{cfg['tts_model']}|{cfg['voice']}")
    except QuotaExceeded:
        _err("Hết hạn mức Gemini TTS trong ngày (gói miễn phí: 10 lần/ngày cho mỗi model). "
             "Đợi hạn mức hồi lại rồi chạy lại lệnh này.")
        return QUOTA
    except ValueError as e:
        _err(str(e))
        return FAILED
    run.write("tts.json", [{"id": c.id, "path": str(c.path), "duration": c.duration} for c in clips])
    if len(clips) >= 5:
        rate = round(measured_rate(clips, lines), 2)
        set_config("syllables_per_sec", rate)
        print(f"Tốc độ đọc đo được: {rate} âm tiết/giây (đã lưu vào config.toml)")
    run.mark("tts")
    return OK


def cmd_fit(a) -> int:
    run = Run(a.run)
    src = run.file("source.mp4")
    captions = [Fragment(**f) for f in run.read("captions.json")]
    cut = outro_cut(captions, scene_cuts(src), probe(src).duration)
    clips = [Clip(c["id"], Path(c["path"]), c["duration"]) for c in run.read("tts.json")]
    placements = place(_sentences(run), clips, cut, config()["max_tempo"])
    run.write("placements.json", {"cut": cut, "placements": [asdict(p) for p in placements]})
    build_narration(placements, clips, cut, run.file("narration.wav"))
    run.mark("fit")
    if long := too_long(placements):
        _err("Câu quá dài so với khung thời gian, cần rút gọn: " + ", ".join(map(str, long)))
        return TOO_LONG
    return OK


def cmd_render(a) -> int:
    run = Run(a.run)
    meta, fitted = run.read("run.json"), run.read("placements.json")
    cut = fitted["cut"]
    phrases = phrase_times([Placement(**p) for p in fitted["placements"]], run.read("script.vi.json"))
    s, e, t = phrases[-1]
    phrases[-1] = (s, max(e, cut), t)  # keep the box up to the end: it hides the old low captions
    ass = run.file("subs.ass")
    ass.write_text(build_ass(phrases, meta["kicker"], meta["title"], cut), encoding="utf-8")
    pj = run.file("plates/plates.json")
    plates = [Plate(**p) for p in json.loads(pj.read_text())] if pj.exists() else []
    compose(run.file("source.mp4"), run.file("narration.wav"), ass, plates, run.file("plates"), cut,
            run.file("final.mp4"))
    run.mark("render")
    print(run.file("final.mp4"))
    return OK


def cmd_status(a) -> int:
    run = Run(a.run)
    steps = ["new", "fetch", "detect", "text", "plates", "tts", "fit", "render"]
    for s in steps:
        print(f"{'✓' if run.done(s) else '·'} {s}")
    return OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vshort", description="Video ngắn NotebookLM → lồng tiếng Việt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new")
    p.add_argument("slug")
    p.add_argument("--kicker", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--notebook")
    p.add_argument("--runs-dir")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("fetch")
    p.add_argument("run")
    p.add_argument("--notebook")
    p.add_argument("--prompt", help="video description passed to NotebookLM")
    p.set_defaults(fn=cmd_fetch)
    for name, fn in [("detect", cmd_detect), ("text", cmd_text), ("check", cmd_check), ("plates", cmd_plates),
                     ("tts", cmd_tts), ("fit", cmd_fit), ("render", cmd_render), ("status", cmd_status)]:
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
