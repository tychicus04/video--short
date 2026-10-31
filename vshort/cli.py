"""`vshort <command> <run_dir>`: every pipeline step as a command that can be re-run."""
import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageOps

from vshort.captions import Fragment, detect_fragments, write_sheets
from vshort.fit import Placement, build_narration, phrase_times, sequence, total
from vshort.media import frame_at
from vshort.plates import Plate, build_plates, scene_cuts
from vshort.render import build_ass, clean_video, compose
from vshort.run import Run, config
from vshort.script import Sentence, check_script, group_sentences, merge_text, merged
from vshort.stills import contact_sheet, grid_image, pick_still, scene_of
from vshort.tts import Clip, QuotaExceeded, gemini_speaker, load_api_key, synth_script
from vshort.visuals import patch_text, pencil, svg_frame, validate

ROOT = Path(__file__).resolve().parent.parent
OK, FAILED, BAD_INPUT, AUTH, QUOTA = 0, 1, 2, 4, 75
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
    run.write("run.json", {"slug": a.slug, "notebook_id": a.notebook or ""})
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
    task = meta.get("artifact_id")  # a rerun continues the video already requested
    if not task:
        cp, code = _notebooklm(["generate", "video", "--format", "short", "--language", "en", "-n", nb, "--no-wait",
                                "--json", *prompt])
        if code:
            return code
        task = meta["artifact_id"] = _json(cp.stdout)["task_id"]
        run.write("run.json", meta)
    cp, code = _notebooklm(["artifact", "wait", task, "-n", nb, "--timeout", "2400", "--json"])
    if code:
        return code
    if _json(cp.stdout).get("status") != "completed":
        _err(f"NotebookLM chưa tạo xong video: {cp.stdout.strip()}")
        return FAILED
    cp, code = _notebooklm(["download", "video", "-n", nb, "-a", task, "--force", str(run.file("source.mp4"))])
    if code:
        return code
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
    if missing := [f.i for f in frags if f.i not in texts]:
        _err("fragments_text.json thiếu các mảnh: " + ", ".join(map(str, missing)))
        return BAD_INPUT
    captions = merge_text(frags, texts)
    run.write("captions.json", [asdict(f) for f in captions])
    sents = group_sentences(captions)
    run.write("sentences.en.json", [asdict(s) for s in sents])
    for s in sents:
        print(f"{s.id}\t{s.start:.2f}–{s.end:.2f}\t{s.en}")
    run.mark("text")
    return OK


def cmd_check(a) -> int:
    run = Run(a.run)
    probs = check_script(_sentences(run), run.read("script.vi.json"))
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


def _plates(run: Run) -> list[Plate]:
    pj = run.file("plates/plates.json")
    return [Plate(**p) for p in json.loads(pj.read_text())] if pj.exists() else []


def cmd_stills(a) -> int:
    run = Run(a.run)
    lines = merged(_sentences(run), run.read("script.vi.json"))
    clean = run.file("clean.mp4")
    clean_video(run.file("source.mp4"), _plates(run), run.file("plates"), lines[-1].end, clean)
    cuts = scene_cuts(clean)
    out = run.file("stills")
    (out / "grid").mkdir(parents=True, exist_ok=True)
    rows, shots = [], []
    for s in lines:
        t = pick_still(clean, s.start, s.end, cuts)
        img = Image.fromarray(frame_at(clean, t))
        img.save(out / f"{s.id}.png")
        grid_image(img).save(out / "grid" / f"{s.id}.png")
        shots.append((s.id, img))
        rows.append({"id": s.id, "t": round(t, 3), "scene": scene_of(t, cuts)})
    contact_sheet(shots).save(out / "sheet.png")
    run.write("stills.json", rows)
    run.mark("stills")
    print(f"{len(rows)} ảnh tĩnh; ảnh để xem: {out / 'sheet.png'}")
    return OK


def cmd_visuals(a) -> int:
    run = Run(a.run)
    stills = run.read("stills.json")
    src = run.file("visuals.json")
    try:
        items = json.loads(src.read_text(encoding="utf-8")) if src.exists() else []
    except ValueError as e:
        _err(f"visuals.json không phải JSON hợp lệ: {e}")
        return BAD_INPUT
    if not isinstance(items, list):
        _err("visuals.json phải là một danh sách các mục")
        return BAD_INPUT
    ids = {s["id"] for s in stills}
    probs = validate(items, ids, run.path)
    probs += [f"thiếu stills/{s['id']}.png (chạy lại `vshort stills`)" for s in stills
              if not run.file(f"stills/{s['id']}.png").exists()]
    refs = {}
    for n, it in enumerate(items, 1):  # render every reference whose own item is fine, so a corrupt file shows up too
        if validate([it], ids, run.path) or it["kind"] == "patch":
            continue
        try:
            refs[it["id"]] = svg_frame(run.file(it["file"])) if it["kind"] == "svg" else pencil(
                ImageOps.exif_transpose(Image.open(run.file(it["file"]))), it["credit"])
        except Exception as e:  # agent-made file: any decoder error is a bad item
            probs.append(f"visuals.json mục {n} ({it['kind']}): không đọc/vẽ được {it['file']}: {e}")
    for p in probs:
        _err(p)
    if probs:
        return BAD_INPUT
    patches = [it for it in items if it["kind"] == "patch"]
    out = run.file("frames")
    shutil.rmtree(out, ignore_errors=True)  # a rerun must not keep frames of lines that are gone
    out.mkdir()
    rows = []
    for s in stills:
        i = s["id"]
        if i in refs:  # a reference replaces the still, patches included
            img, group = refs[i], f"v{i}"
        else:
            img, group = Image.open(run.file(f"stills/{i}.png")).convert("RGB"), f"s{s['scene']}"
            for p in patches:
                if i in p["ids"]:
                    img = patch_text(img, tuple(p["box"]), p["text"], p.get("bold", False))
        img.save(out / f"{i}.png")
        rows.append({"id": i, "file": f"frames/{i}.png", "group": group})
    run.write("frames.json", rows)
    run.mark("visuals")
    print(f"{len(rows)} khung hình: {len(refs)} hình tư liệu, {len(patches)} chỗ vá chữ")
    return OK


def cmd_tts(a) -> int:
    run = Run(a.run)
    cfg = config()
    lines = [(row["id"], _speech(row["phrases"])) for row in run.read("script.vi.json") if row["phrases"].strip()]
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
    run.mark("tts")
    return OK


def cmd_timeline(a) -> int:
    run = Run(a.run)
    clips = [Clip(c["id"], Path(c["path"]), c["duration"]) for c in run.read("tts.json")]
    placements = sequence(clips)
    end = total(placements)
    run.write("timeline.json", {"total": end, "placements": [asdict(p) for p in placements]})
    build_narration(placements, clips, end, run.file("narration.wav"))
    run.mark("timeline")
    return OK


def cmd_render(a) -> int:
    run = Run(a.run)
    fitted = run.read("timeline.json")
    cut = fitted["total"]
    phrases = phrase_times([Placement(**p) for p in fitted["placements"]], run.read("script.vi.json"))
    ass = run.file("subs.ass")
    ass.write_text(build_ass(phrases), encoding="utf-8")
    compose(run.file("source.mp4"), run.file("narration.wav"), ass, _plates(run), run.file("plates"), cut,
            run.file("final.mp4"))
    run.mark("render")
    print(run.file("final.mp4"))
    return OK


def cmd_status(a) -> int:
    run = Run(a.run)
    steps = ["new", "fetch", "detect", "text", "plates", "tts", "timeline", "render"]
    for s in steps:
        print(f"{'✓' if run.done(s) else '·'} {s}")
    return OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vshort", description="Video ngắn NotebookLM → lồng tiếng Việt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new")
    p.add_argument("slug")
    p.add_argument("--notebook")
    p.add_argument("--runs-dir")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("fetch")
    p.add_argument("run")
    p.add_argument("--notebook")
    p.add_argument("--prompt", help="video description passed to NotebookLM")
    p.set_defaults(fn=cmd_fetch)
    for name, fn in [("detect", cmd_detect), ("text", cmd_text), ("check", cmd_check), ("plates", cmd_plates),
                     ("tts", cmd_tts), ("stills", cmd_stills), ("visuals", cmd_visuals), ("timeline", cmd_timeline),
                     ("render", cmd_render), ("status", cmd_status)]:
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
