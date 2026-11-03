"""`vshort <command> <run_dir>`: every pipeline step as a command that can be re-run."""
import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageOps

from vshort import auto, motion, shapes
from vshort.captions import Fragment, detect_fragments, write_sheets
from vshort.fit import Placement, build_narration, phrase_times, sequence, total
from vshort.media import frame_at, probe
from vshort.plates import Plate, build_plates, scene_cuts
from vshort.render import OUTRO, build_ass, clean_video, render_video, segments
from vshort.run import Run, config
from vshort.script import Sentence, check_brief, check_script, check_style, group_sentences, merge_text, merged
from vshort.stills import NLM_OUTRO, contact_sheet, grid_image, pick_still, scene_of
from vshort.tts import (Clip, QuotaExceeded, clip_paths, gemini_speaker, load_api_key, synth_lines, synth_script,
                        zerotts_speaker)
from vshort.visuals import patch_text, pencil, svg_frame, validate

ROOT = Path(__file__).resolve().parent.parent
OK, FAILED, BAD_INPUT, AUTH, QUOTA = 0, 1, 2, 4, 75
WAIT_BRIEF, WAIT_SCRIPT = 20, 21  # `vshort auto` stopped for Tai to approve the brief / the translation
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
    script = run.read("script.vi.json")
    probs = check_script(_sentences(run), script) + check_style(script)
    if run.file("brief.vi.md").exists():
        probs += check_brief(script, run.file("brief.vi.md").read_text(encoding="utf-8"))
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


def cmd_stills(a) -> int:
    run = Run(a.run)
    if not run.file("plates/plates.json").exists():  # an empty list is fine: no captions to remove
        _err("thiếu plates/plates.json — chạy `vshort plates` trước")
        return BAD_INPUT
    plates = [Plate(**p) for p in run.read("plates/plates.json")]
    lines = merged(_sentences(run), run.read("script.vi.json"))
    clean = run.file("clean.mp4")
    clean_video(run.file("source.mp4"), plates, run.file("plates"), lines[-1].end, clean)
    cuts = scene_cuts(clean)
    stop = probe(run.file("source.mp4")).duration - NLM_OUTRO
    out = run.file("stills")
    (out / "grid").mkdir(parents=True, exist_ok=True)
    rows, shots = [], []
    for s in lines:
        t = pick_still(clean, s.start, s.end, cuts, stop)
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


BAD_JSON = object()


def _load(run: Run, name: str):
    """RUN/name, or None when it is missing or null; prints why and returns BAD_JSON on bad JSON."""
    try:
        return motion.load(run.file(name))
    except ValueError as e:
        _err(f"{name} không phải JSON hợp lệ: {e}")
        return BAD_JSON


def _motion(run: Run):
    """motion.json (the canvas), or None when the video has no animation; BAD_JSON on bad JSON."""
    return _load(run, "motion.json")


def _bind(run: Run):
    """motion.bind.json (the canvas tied to the lines), or None when the video has no animation or it is not bound
    yet; BAD_JSON on bad JSON."""
    return _load(run, "motion.bind.json") if run.file("motion.json").exists() else None


def _said(bind: dict, script: list[dict]) -> dict[str, str]:
    """The words of the animated lines, as checked by `vshort motion`."""
    text = {str(r["id"]): r["phrases"] for r in script}
    return {str(i): text.get(str(i), "") for i in bind["lines"]}


def _used_shapes(run: Run, doc: dict) -> None:
    """Copy every library shape the canvas uses into RUN/shapes: the video can be rebuilt as it was."""
    for th in doc["things"]:
        if th["kind"] == "shape" and not run.file(f"shapes/{th['shape']}.json").exists():
            run.file("shapes").mkdir(exist_ok=True)
            shutil.copy(shapes.LIBRARY / f"{th['shape']}.json", run.file(f"shapes/{th['shape']}.json"))


def cmd_motion(a) -> int:
    """`--design`: the canvas against the brief (before the voice). Without: the canvas bound to the lines."""
    run = Run(a.run)
    out = run.file("motion")
    doc = _motion(run)
    if doc is BAD_JSON:
        return BAD_INPUT
    if doc is None:
        shutil.rmtree(out, ignore_errors=True)  # a sheet of an animation that is gone must not be looked at
        print("Không có hình động.")
        if not a.design:
            run.mark("motion")
        return OK
    probs = shapes.check_run(run.path)
    if a.design:
        brief = run.file("brief.vi.md")
        said = motion.brief_words(brief.read_text(encoding="utf-8")) if brief.exists() else set()
        probs += motion.design_problems(doc, said, run.path)
    elif isinstance(doc, dict) and "scenes" in doc:
        probs.append(motion.OLD)
    else:
        bind = _bind(run)
        if bind is BAD_JSON:
            return BAD_INPUT
        if bind is None:
            _err("thiếu motion.bind.json: gắn từng nhịp vào câu đọc (sau khi duyệt bản dịch)")
            return BAD_INPUT
        src = run.file("visuals.json")
        try:
            refs = json.loads(src.read_text(encoding="utf-8")) if src.exists() else None
        except ValueError:
            refs = None  # `vshort visuals` reports a broken visuals.json itself
        script = run.read("script.vi.json")
        probs += motion.bind_problems(doc, bind, script, run.path, refs if isinstance(refs, list) else None)
    for p in probs:
        _err(p)
    if probs:
        return BAD_INPUT
    out.mkdir(exist_ok=True)
    if a.design:
        motion.design_sheet(doc, run.path).save(out / "design.png")
        look = [out / "design.png"]
        if list(run.file("shapes").glob("*.json")):
            shapes.sheet(run.path).save(run.file("shapes/sheet.png"))
            look.append(run.file("shapes/sheet.png"))
        print(f"{len(doc['beats'])} nhịp; ảnh để xem: {', '.join(map(str, look))}")
        return OK
    _used_shapes(run, doc)
    motion.bind_sheet(doc, bind, script, run.path).save(out / "sheet.png")
    run.write("motion/lines.json", _said(bind, script))  # render checks the canvas still sits on these words
    kept = sum(c is not None for c in bind["beats"])
    print(f"1 khung, {kept}/{len(doc['beats'])} nhịp, câu {bind['lines'][0]}–{bind['lines'][-1]}; "
          f"ảnh để xem: {out / 'sheet.png'}")
    run.mark("motion")
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
    if (doc := _motion(run)) is BAD_JSON or (bind := _bind(run) if doc is not None else None) is BAD_JSON:
        return BAD_INPUT
    probs += motion.clashes(items, motion.lines(bind))
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
    frames = []  # drawn in memory first: a failure must leave the previous frames/ and frames.json as they were
    try:
        for s in stills:
            i = s["id"]
            if i in refs:  # a reference replaces the still, patches included
                img, group = refs[i], f"v{i}"
            else:
                img, group = Image.open(run.file(f"stills/{i}.png")).convert("RGB"), f"s{s['scene']}"
                for p in patches:
                    if i in p["ids"]:
                        img = patch_text(img, tuple(p["box"]), p["text"], p.get("bold", False))
            frames.append((i, img, group))
    except Exception as e:  # any drawing error: report it, touch nothing
        _err(f"không dựng được khung hình {i}: {e}")
        return FAILED
    out = run.file("frames")
    shutil.rmtree(out, ignore_errors=True)  # a rerun must not keep frames of lines that are gone
    out.mkdir()
    rows = []
    for i, img, group in frames:
        img.save(out / f"{i}.png")
        rows.append({"id": i, "file": f"frames/{i}.png", "group": group})
    run.write("frames.json", rows)
    run.mark("visuals")
    print(f"{len(rows)} khung hình: {len(refs)} hình tư liệu, {len(patches)} chỗ vá chữ")
    return OK


def _tts_lines(run: Run) -> list[tuple[int, str]]:
    return [(row["id"], _speech(row["phrases"])) for row in run.read("script.vi.json") if row["phrases"].strip()]


def _tts_tag(cfg: dict) -> str:
    return f"{cfg['tts_model']}|{cfg['voice']}|{cfg.get('tts_style', '')}"


def _zerotts_tag(cfg: dict) -> str:
    return f"zerotts|{cfg['zerotts_voice']}"


def cmd_tts(a) -> int:
    run = Run(a.run)
    cfg = config()
    lines, out, local = _tts_lines(run), run.file("tts"), _zerotts_tag(cfg)
    try:
        if lines and all(p.exists() for p in clip_paths(lines, out, local)):
            clips = synth_lines(lines, out, None, local)  # read by ZeroTTS on a day Gemini was out: keep that voice
        else:
            speak = gemini_speaker(load_api_key(Path(cfg["env_file"]).expanduser()), cfg["tts_model"], cfg["voice"],
                                   cfg.get("tts_style", ""))
            clips = synth_script(lines, out, speak, tag=_tts_tag(cfg))
    except QuotaExceeded:
        print(f"Hết hạn mức Gemini TTS trong ngày: đọc bằng ZeroTTS (giọng {cfg['zerotts_voice']}).")
        try:
            clips = synth_lines(lines, out, zerotts_speaker(Path(cfg["zerotts_model"]).expanduser(),
                                                            cfg["zerotts_voice"]), local)
        except (OSError, subprocess.CalledProcessError) as e:  # not installed, no weights, or it crashed
            why = e.stderr.decode(errors="replace").strip() if isinstance(e, subprocess.CalledProcessError) else ""
            _err("Hết hạn mức Gemini TTS trong ngày (gói miễn phí: 10 lần/ngày cho mỗi model) và ZeroTTS không chạy được "
                 f"({why.splitlines()[-1] if why else e}). Đợi hạn mức hồi lại rồi chạy lại lệnh này.")
            return QUOTA
    except ValueError as e:
        _err(str(e))
        return FAILED
    run.write("tts.json", [{"id": c.id, "path": str(c.path), "duration": c.duration} for c in clips])
    run.mark("tts")
    return OK


def cmd_timeline(a) -> int:
    run = Run(a.run)
    rows = run.read("tts.json")
    made = [Path(c["path"]).name for c in rows]  # clip names carry the ids and a hash of the text they were made from
    lines, cfg = _tts_lines(run), config()
    if made not in ([p.name for p in clip_paths(lines, run.file("tts"), tag)] for tag in (_tts_tag(cfg), _zerotts_tag(cfg))):
        _err("giọng đọc cũ không khớp kịch bản — chạy lại `vshort tts`")
        return BAD_INPUT
    clips = [Clip(c["id"], Path(c["path"]), c["duration"]) for c in rows]
    placements = sequence(clips)
    end = total(placements)
    run.write("timeline.json", {"total": end, "placements": [asdict(p) for p in placements]})
    build_narration(placements, clips, end, run.file("narration.wav"))
    run.mark("timeline")
    return OK


def cmd_render(a) -> int:
    run = Run(a.run)
    fitted = run.read("timeline.json")
    placements = [Placement(**p) for p in fitted["placements"]]
    frames = run.read("frames.json")
    ids = {p.id for p in placements}
    if missing := sorted(ids - {f["id"] for f in frames}):
        stills = {s["id"] for s in run.read("stills.json")} if run.file("stills.json").exists() else set()
        redo = "`vshort visuals`"
        if not stills.issuperset(missing):  # the line has no still yet, or the script changed after `vshort stills`
            redo = "`vshort stills`, rồi vs-visuals và " + redo
        _err("frames.json thiếu các câu: " + ", ".join(map(str, missing)) + f" (chạy lại {redo})")
        return BAD_INPUT
    if gone := [f["file"] for f in frames if f["id"] in ids and not run.file(f["file"]).exists()]:
        _err("thiếu file khung hình: " + ", ".join(gone) + " (chạy lại `vshort visuals`)")
        return BAD_INPUT
    script = run.read("script.vi.json")
    doc = _motion(run)
    if doc is BAD_JSON:
        return BAD_INPUT
    scenes = []
    if doc is not None:
        if isinstance(doc, dict) and "scenes" in doc:
            _err(f"{motion.OLD} (rồi chạy lại `vshort motion`)")
            return BAD_INPUT
        if (bind := _bind(run)) is BAD_JSON:
            return BAD_INPUT
        if bind is None:
            _err("thiếu motion.bind.json (chạy lại `vshort motion`)")
            return BAD_INPUT
        if probs := shapes.check_run(run.path) + motion.bind_problems(doc, bind, script, run.path):
            for p in probs:
                _err(p)
            _err("motion.json không còn khớp kịch bản (chạy lại `vshort motion`)")
            return BAD_INPUT
        checked = run.file("motion/lines.json")
        if not checked.exists() or run.read("motion/lines.json") != _said(bind, script):
            _err("kịch bản đã đổi sau lần kiểm hình động cuối (chạy lại `vshort motion`)")
            return BAD_INPUT
        if missing := sorted(set(bind["lines"]) - ids):
            _err("timeline.json thiếu các câu có hình động: " + ", ".join(map(str, missing))
                 + " (chạy lại `vshort tts` rồi `vshort timeline`)")
            return BAD_INPUT
        scenes = [motion.bind_timed(doc, bind, placements, script, run.path)]
    animated = {i: k for k, sc in enumerate(scenes) for i in sc.lines}
    ass = run.file("subs.ass")
    ass.write_text(build_ass(phrase_times(placements, script)), encoding="utf-8")
    render_video(segments(placements, frames, run.path, fitted["total"], animated), ass, run.file("narration.wav"),
                 fitted["total"], run.file("final.mp4"), scenes, OUTRO)
    run.mark("render")
    print(run.file("final.mp4"))
    return OK


def cmd_status(a) -> int:
    run = Run(a.run)
    steps = ["new", "fetch", "detect", "text", "plates", "tts", "stills", "motion", "visuals", "timeline", "render"]
    for s in steps:
        print(f"{'✓' if run.done(s) else '·'} {s}")
    if (st := auto.get_state(run))["state"] != "none":
        print(f"auto: {st['state']}" + (f" — {st['message']}" if st["message"] else ""))
    return OK


def cmd_approve(a) -> int:
    run = Run(a.run)
    if a.what == "brief":
        if run.file("brief.vi.md").stat().st_mtime > run.file("brief.en.md").stat().st_mtime:
            _err("brief.vi.md mới hơn brief.en.md — cập nhật bản tiếng Anh trước (NotebookLM làm video từ bản tiếng Anh)")
            return BAD_INPUT
    else:
        if run.file("script.proposed.json").exists():
            _err("còn script.proposed.json — chép bản đề xuất vào script.vi.json hoặc xóa nó trước")
            return BAD_INPUT
        if code := cmd_check(a):
            return code
    run.mark(f"approve_{a.what}")
    return OK


def cmd_auto(a) -> int:
    if a.topic:  # a new video: `vshort auto <slug> --topic …`
        existing = Path(a.runs_dir or config()["runs_dir"]).expanduser() / a.target
        if (existing / "run.json").exists():
            _err(f"đã có video {existing} — chạy tiếp bằng `vshort auto {existing}`, hoặc chọn slug khác")
            return BAD_INPUT
        if code := cmd_new(argparse.Namespace(slug=a.target, notebook=None, runs_dir=a.runs_dir)):
            return code
        run = Run(Path(a.runs_dir or config()["runs_dir"]).expanduser() / a.target)
        run.write("run.json", run.read("run.json") | {"topic": a.topic, "auto": a.auto})
    else:
        run = Run(a.target)
    if not a.foreground:  # a video takes ~1.5 h: run on after the session or ssh that started it is gone
        if pid := auto.locked_by(run):
            _err(f"`vshort auto` đang chạy cho {run.path} (pid {pid})")
            return BAD_INPUT
        with open(run.file("auto.log"), "a") as log:
            child = subprocess.Popen([sys.executable, "-u", "-m", "vshort.cli", "auto", str(run.path), "--foreground"],
                                     cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        auto.set_state(run, "running", pid=child.pid)
        print(f"{run.path}\nđang chạy nền (pid {child.pid}); log: {run.file('auto.log')}; chờ: `vshort wait {run.path}`")
        return OK
    if not auto.acquire_lock(run):
        _err(f"`vshort auto` đang chạy cho {run.path} (pid {run.file('auto.lock').read_text().strip()})")
        return BAD_INPUT
    try:
        return auto.run_auto(run)
    finally:
        auto.release_lock(run)


def cmd_wait(a) -> int:
    run = Run(a.run)
    while (st := auto.get_state(run))["state"] == "running":
        if not auto.alive_run(run):
            print(f"error\n`vshort auto` đã dừng giữa chừng (máy tắt hoặc bị dừng) — chạy lại `vshort auto {run.path}` "
                  f"để làm tiếp; log: {run.file('auto.log')}")
            return FAILED
        time.sleep(a.poll)
    if st["state"] == "none":
        _err("chưa chạy `vshort auto` cho thư mục này")
        return BAD_INPUT
    print(st["state"] + (f"\n{st['message']}" if st["message"] else ""))
    return {"done": OK, "wait_brief": WAIT_BRIEF, "wait_script": WAIT_SCRIPT}.get(st["state"], FAILED)


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
                     ("tts", cmd_tts), ("stills", cmd_stills), ("motion", cmd_motion), ("visuals", cmd_visuals), ("timeline", cmd_timeline),
                     ("render", cmd_render), ("status", cmd_status)]:
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(fn=fn)
        if name == "motion":
            p.add_argument("--design", action="store_true", help="check the canvas against the brief, before the voice")
    p = sub.add_parser("approve")
    p.add_argument("run")
    p.add_argument("what", choices=["brief", "script"])
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("auto")
    p.add_argument("target", help="slug của video mới (cùng --topic) hoặc thư mục RUN đang làm")
    p.add_argument("--topic")
    p.add_argument("--auto", action="store_true", help="không dừng duyệt brief (vẫn dừng duyệt bản dịch)")
    p.add_argument("--runs-dir")
    p.add_argument("--foreground", action="store_true")
    p.set_defaults(fn=cmd_auto)
    p = sub.add_parser("wait")
    p.add_argument("run")
    p.add_argument("--poll", type=float, default=15)
    p.set_defaults(fn=cmd_wait)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
