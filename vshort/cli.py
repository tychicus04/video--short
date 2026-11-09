"""`vshort <command> <run_dir>`: every pipeline step as a command that can be re-run."""
import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from vshort import auto, cms, cover, publish, retime, sound
from vshort.captions import Fragment, detect_fragments, write_sheets
from vshort.fit import Placement, build_narration, phrase_times, sequence, total
from vshort.media import frame_at, probe
from vshort.plates import clean, scene_changes, scene_cuts
from vshort.render import OUTRO, build_ass, export_outro, export_title, render_pieces
from vshort.run import Run, config
from vshort.scene import SceneError, check, load_scene, phrase_table, resolve
from vshort.script import (Sentence, check_brief, check_neon, check_numbers, check_script, check_style,
                           group_sentences, mechanism_steps, merge_text, merged)
from vshort.stills import NLM_OUTRO, contact_sheet, grid_image, pick_still, scene_of
from vshort.tts import (Clip, QuotaExceeded, clip_paths, gemini_speaker, load_api_key, synth_lines, synth_script,
                        zerotts_speaker)
from vshort.visuals import appear_time, patch_text, validate

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


def style_of(run: Run) -> str:
    """"neon" or "old". Only `vshort auto --style neon` writes the key; a run without it is the NotebookLM flow."""
    meta = run.read("run.json") if run.file("run.json").exists() else {}
    return "neon" if meta.get("style") == "neon" else "old"


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
    brief = run.file("brief.vi.md")
    if style_of(run) == "neon":  # the narration is written from the brief: no English to check it against
        probs = check_neon(script, brief.read_text(encoding="utf-8")) + check_style(script)
    else:
        sents = _sentences(run)
        probs = check_script(sents, script) + check_style(script) + check_numbers(sents, script)
    if brief.exists():
        probs += check_brief(script, brief.read_text(encoding="utf-8"))
    for p in probs:
        _err(p)
    if probs:
        return BAD_INPUT
    print("Kịch bản tiếng Việt hợp lệ.")
    return OK


def cmd_clean(a) -> int:
    run = Run(a.run)
    captions = [Fragment(**f) for f in run.read("captions.json")]
    info = clean(run.file("source.mp4"), captions, run.file("clean.mp4"), ROOT / "models" / "big-lama.pt")
    run.write("clean.json", info)
    print(f"clean.mp4: {len(info['boxes'])} dải phụ đề, "
          f"{sum(len(b['plates']) for b in info['boxes'])} lần vá, {info['seconds']:.0f} s")
    run.mark("clean")
    return OK


def cmd_stills(a) -> int:
    run = Run(a.run)
    clean = run.file("clean.mp4")
    if not clean.exists():
        _err("thiếu clean.mp4 (chạy `vshort clean`)")
        return BAD_INPUT
    lines = merged(_sentences(run), run.read("script.vi.json"))
    cuts = scene_cuts(clean)
    stop = probe(run.file("source.mp4")).duration - NLM_OUTRO
    out = run.file("stills")
    (out / "grid").mkdir(parents=True, exist_ok=True)
    rows, tiles = [], []
    for s in lines:
        t = pick_still(clean, s.start, s.end, cuts, stop)
        img = Image.fromarray(frame_at(clean, t))
        img.save(out / f"{s.id}.png")
        grid_image(img).save(out / "grid" / f"{s.id}.png")
        tiles.append((s.id, img))
        rows.append({"id": s.id, "t": round(t, 3), "scene": scene_of(t, cuts)})
    contact_sheet(tiles).save(out / "sheet.png")
    run.write("stills.json", rows)
    run.mark("stills")
    print(f"{len(rows)} ảnh tĩnh; ảnh để xem: {out / 'sheet.png'}")
    return OK


def cmd_cover(a) -> int:
    run = Run(a.run)
    if a.candidates:
        rows = cover.candidates(run.path)
        for r in rows:
            print(f"{r['n']}\t{r['size'][0]}×{r['size'][1]}\t{r['page']}")
        print(f"ảnh để xem: {run.file('cover/sheet.jpg')}" if rows else "không nguồn nào có ảnh đủ lớn")
        return OK
    try:
        info = cover.make(run.path)
    except (OSError, ValueError, KeyError) as e:
        _err(f"không làm được ảnh đại diện: {e}")
        return BAD_INPUT
    run.mark("cover")
    print(f"{run.file('cover/thumb-16x9.jpg')}\n{run.file('cover/thumb-9x16.jpg')}\n"
          + (f"nguồn: {info['page']}" if info["from"] == "source" else "ảnh từ video"))
    try:
        print(f"xuất: {cover.package(run.path)}")
    except OSError as e:
        _err(f"không xếp được thư mục xuất: {e}")
        return BAD_INPUT
    return OK


def cmd_visuals(a) -> int:
    """The patched stills: frames/<id>.png for every line with a wrong text, and frames.json saying from when (source
    seconds) each replaces the video; every other line plays the video."""
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
    probs = validate(items, {s["id"] for s in stills}, run.path)
    probs += [f"thiếu stills/{s['id']}.png (chạy lại `vshort stills`)" for s in stills
              if not run.file(f"stills/{s['id']}.png").exists()]
    patched = sorted({i for it in items if not probs for i in it["ids"]})
    if patched and not run.file("clean.mp4").exists():
        probs.append("thiếu clean.mp4 (chạy `vshort clean`)")
    for p in probs:
        _err(p)
    if probs:
        return BAD_INPUT
    lines = merged(_sentences(run), run.read("script.vi.json"))
    start = {s.id: 0.0 if k == 0 else s.start for k, s in enumerate(lines)}  # where retime starts the line's picture
    at = {s["id"]: s["t"] for s in stills}
    frames = []  # drawn in memory first: a failure must leave the previous frames/ and frames.json as they were
    try:
        for i in patched:
            still = Image.open(run.file(f"stills/{i}.png")).convert("RGB")
            img, boxes = still, [it["box"] for it in items if i in it["ids"]]
            for it in items:
                if i in it["ids"]:
                    img = patch_text(img, tuple(it["box"]), it["text"], it.get("bold", False))
            box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
            shown = appear_time(run.file("clean.mp4"), start.get(i, at[i]), at[i], box, np.asarray(still.convert("L")))
            frames.append((i, img, round(shown, 3)))
    except Exception as e:  # any drawing error: report it, touch nothing
        _err(f"không dựng được khung hình {i}: {e}")
        return FAILED
    out = run.file("frames")
    shutil.rmtree(out, ignore_errors=True)  # a rerun must not keep frames of lines that are gone
    out.mkdir()
    for i, img, _ in frames:
        img.save(out / f"{i}.png")
    run.write("frames.json", [{"id": i, "file": f"frames/{i}.png", "from": shown} for i, _, shown in frames])
    run.mark("visuals")
    print(f"{len(frames)} câu có chữ vá" + (": " + ", ".join(f"câu {i} từ {s:.1f} s" for i, _, s in frames) if frames else ""))
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
    """final.mp4: NotebookLM's own video (clean.mp4) retimed line by line to the Vietnamese voice, patched stills over the
    lines with a wrong text, the spoken title typed into the magazine's bar, its logo, subtitles, three accents on the biggest
    changes of scene, the outro."""
    run = Run(a.run)
    clean = run.file("clean.mp4")
    if not clean.exists():
        _err("thiếu clean.mp4 (chạy `vshort clean`)")
        return BAD_INPUT
    fitted = run.read("timeline.json")
    placements = [Placement(**p) for p in fitted["placements"]]
    script = run.read("script.vi.json")
    lines = {s.id: s for s in merged(_sentences(run), script)}
    if missing := [p.id for p in placements if p.id not in lines]:
        _err("timeline.json có câu không còn lời: " + ", ".join(map(str, missing)) + " (chạy lại `vshort tts` rồi `vshort timeline`)")
        return BAD_INPUT
    frames = run.read("frames.json") if run.file("frames.json").exists() else []
    if any("from" not in f for f in frames):
        _err("frames.json kiểu cũ (chạy lại `vshort visuals`)")
        return BAD_INPUT
    if gone := [f["file"] for f in frames if not run.file(f["file"]).exists()]:
        _err("thiếu file khung hình: " + ", ".join(gone) + " (chạy lại `vshort visuals`)")
        return BAD_INPUT
    stop = probe(run.file("source.mp4")).duration - NLM_OUTRO
    ps = retime.pieces([lines[p.id] for p in placements], placements, fitted["total"], stop, retime.blank_at(clean))
    run.write("pieces.json", [asdict(p) for p in ps])
    by_id, stills = {p.id: p for p in ps}, []
    for f in frames:
        if (p := by_id.get(f["id"])) is None:  # a patched line that is no longer said
            continue
        held = p.dst + (p.src_end - p.src) / p.speed  # the wrong text first shows in a dropped tail: from the hold on
        shown = p.dst if f["from"] <= p.src else min(retime.to_output([p], f["from"]) or held, held)
        stills.append((run.file(f["file"]), shown, p.dst_end))
    phrases, first = phrase_times(placements, script), placements[0]
    title = run.file("title.mov")  # the spoken title typed into the magazine's bar, not also as a subtitle
    said = next(row["phrases"] for row in script if row["id"] == first.id)
    if export_title(_speech(said), first.start, first.start + first.dur, title):
        phrases = phrases[1:]
    else:
        title = None
    ass = run.file("subs.ass")
    ass.write_text(build_ass(phrases), encoding="utf-8")
    if not OUTRO.exists():
        export_outro()
    fx = sound.cues(scene_changes(clean), ps)
    run.write("sfx.json", [asdict(c) for c in fx])
    sound.master(run.file("narration.wav"), fx, fitted["total"], run.file("mix.wav"))
    render_pieces(ps, clean, stills, ass, run.file("mix.wav"), fitted["total"], run.file("final.mp4"), title=title)
    run.mark("render")
    print(run.file("final.mp4"))
    return OK


def cmd_scene(a) -> int:
    """`--table`: the numbered phrases and the brief's mechanism steps, what the scene agent writes scene.json against.
    Otherwise: scene.json timed to the voice into scene.resolved.json, if it passes every check; the problems, one a line, if not."""
    run = Run(a.run)
    need = ["timeline.json", "script.vi.json", "brief.vi.md"] + ([] if a.table else ["scene.json"])
    if gone := [f for f in need if not run.file(f).exists()]:
        _err("thiếu " + ", ".join(gone) + " (chạy lại các bước trước)")
        return BAD_INPUT
    timeline = run.read("timeline.json")
    table = phrase_table(timeline, run.read("script.vi.json"))
    brief = run.file("brief.vi.md").read_text(encoding="utf-8")
    if a.table:
        for p in table:
            print(f"{p.i}  {p.start:.2f}  {p.text}")
        print()
        print("\n".join(mechanism_steps(brief)))
        return OK
    first = timeline["placements"][0]
    try:
        rt = resolve(load_scene(run.read("scene.json")), table, _speech(table[0].text), timeline["total"],
                     (first["start"], first["start"] + first["dur"]))
    except json.JSONDecodeError as e:
        _err(f"scene.json không phải JSON: {e}")
        return BAD_INPUT
    except SceneError as e:
        for p in e.problems:
            _err(p)
        return BAD_INPUT
    if problems := check(rt, brief):
        for p in problems:
            _err(p)
        return BAD_INPUT
    run.write("scene.resolved.json", rt)
    run.mark("scene")
    print(run.file("scene.resolved.json"))
    return OK


def cmd_outro(a) -> int:
    export_outro(Path(a.out))
    print(Path(a.out).resolve())
    return OK


def cmd_status(a) -> int:
    run = Run(a.run)
    steps = ["new", "fetch", "detect", "text", "clean", "tts", "stills", "visuals", "timeline", "render"]
    for s in steps:
        print(f"{'✓' if run.done(s) else '·'} {s}")
    if (st := auto.get_state(run))["state"] != "none":
        print(f"auto: {st['state']}" + (f" — {st['message']}" if st["message"] else ""))
    return OK


def cmd_approve(a) -> int:
    run = Run(a.run)
    if a.what == "brief":
        if (style_of(run) != "neon"  # neon has no English brief: no video is made from one
                and run.file("brief.vi.md").stat().st_mtime > run.file("brief.en.md").stat().st_mtime):
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
        run.write("run.json", run.read("run.json") | {"topic": a.topic, "auto": a.auto}
                  | ({"style": "neon"} if a.style == "neon" else {}))
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


def cmd_cms(a) -> int:
    """Send a finished video to the CMS (publish.send). In the background unless --foreground: a 30 MB video and the
    CMS's AI take a minute or more, the page must not wait on it."""
    run_dir = Path(a.run)
    if not a.foreground:
        if pid := publish.sender(run_dir):
            _err(f"`vshort cms` đang gửi {run_dir} (pid {pid})")
            return BAD_INPUT
        with open(run_dir / "auto.log", "a") as log:
            child = subprocess.Popen([sys.executable, "-u", "-m", "vshort.cli", "cms", str(run_dir), "--foreground",
                                      *(["--recreate"] if a.recreate else [])],
                                     cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        print(f"đang gửi lên CMS ở nền (pid {child.pid}); kết quả: {run_dir / publish.FILE}")
        return OK
    if (lock := publish.acquire(run_dir)) is None:
        _err(f"`vshort cms` đang gửi {run_dir}")
        return BAD_INPUT
    try:
        rec = publish.send(run_dir, recreate=a.recreate)
    finally:
        publish.release(lock)
    print(f"cms: {rec['state']}" + (f" — {rec['message']}" if rec.get("message") else "")
          + (f"\n{rec['link']}" if rec.get("link") else "") + (f"\n{rec['warning']}" if rec.get("warning") else ""))
    return FAILED if rec["state"] == "error" else OK


def cmd_cms_probe(a) -> int:
    """What cms.toml needs, read from one article like the ones vshort makes (and the CMS's lists). Never the token."""
    s, missing = cms.load(a.env, ids=False)
    if s is None:
        _err("\n".join(missing))
        return BAD_INPUT

    def show(title: str, fn) -> None:
        print(title)
        try:
            fn()
        except cms.CmsError as e:
            print(f"  không đọc được: {e.message}")

    def profile() -> None:
        x = cms.gql(s, cms.PROFILE, {})["auth_profile"]
        print(f"  {x['id']} {x['user_name']}")
        for u in x.get("userDepartments") or []:
            print(f"  phòng ban {u['department']['id']} {u['department']['name']}")

    def article() -> None:
        x = cms.gql(s, cms.SAMPLE, {"id": a.article_id})["articles_detail"]
        wf = x.get("workflow") or {}
        print(f"  {x['id']} {x.get('title')!r}\n  department_id = {x['department_id']}, article_type_id = "
              f"{x['article_type_id']}, workflow_id = {x.get('workflow_id')} ({wf.get('name')}, workflow_type_id "
              f"{wf.get('workflow_type_id')})")
        for c in x.get("articleCategories") or []:
            print(f"  chuyên mục {c['category_id']} {(c.get('category') or {}).get('name')}" + (" (chính)" if c.get("is_major") else ""))
        for g in x.get("articleGenres") or []:
            print(f"  thể loại {g['article_genre_id']} {(g.get('articleGenre') or {}).get('name')}" + (" (chính)" if g.get("is_major") else ""))
        print(f"  icon_id = {x.get('icon_id')} ({(x.get('icon') or {}).get('name')})  ← \"Loại bài viết\"")
        for k in x.get("articleKinds") or []:
            print(f"  kinds: article_kind_id {k['article_kind_id']} (1 ảnh, 2 video, 3 audio…)")
        print("  từ khóa: " + ", ".join((t.get("tag") or {}).get("name") or "" for t in x.get("articleTags") or []))
        workflows.update(department=x["department_id"], type=x["article_type_id"])

    def private() -> None:
        b = {"filters": [f"department_id:=({workflows['department']})", f"type_id:=({workflows['type']})",
                         "workflow_type_id:=(1)"]}
        for w in cms.gql(s, cms.WORKFLOWS, {"b": b})["workflows_all"]:
            print(f"  {w['id']} {w['name']} (type_id {w['type_id']}, workflow_type_id {w['workflow_type_id']}, "
                  f"sub_type_id {w.get('sub_type_id')})")

    def types() -> None:
        for x in cms.gql(s, cms.ARTICLE_TYPES, {})["article_types_all"]:
            print(f"  {x['id']} {x['name']} (phòng ban {x['department_id']})")

    def zernio() -> None:
        for z in cms.gql(s, cms.ZERNIO, {})["zernio_accounts"]:
            print(f"  {z['platform']} {z['id']} @{z.get('username')} {z.get('displayName')!r}"
                  + (" (cần đăng nhập lại)" if z.get("needsReauth") else ""))

    workflows = {"department": s.department_id, "type": 1}
    show(f"Người đứng tên (act_as {s.act_as}) trên {s.env} ({s.api}):", profile)
    show(f"Bài {a.article_id}:", article)
    show("Chặng cá nhân (private_workflow_id):", private)
    show("Loại bài viết (icon_id):", types)
    show("Tài khoản Zernio:", zernio)
    return OK


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
    for name, fn in [("detect", cmd_detect), ("text", cmd_text), ("check", cmd_check), ("clean", cmd_clean),
                     ("tts", cmd_tts), ("stills", cmd_stills), ("visuals", cmd_visuals),
                     ("timeline", cmd_timeline),
                     ("render", cmd_render), ("status", cmd_status), ("cover", cmd_cover)]:
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(fn=fn)
        if name == "cover":
            p.add_argument("--candidates", action="store_true", help="gather the sources' lead images for an agent to pick")
    p = sub.add_parser("scene", help="kịch bản hình của kiểu neon: `--table` in bảng cụm và các bước cơ chế để viết scene.json")
    p.add_argument("run")
    p.add_argument("--table", action="store_true")
    p.set_defaults(fn=cmd_scene)
    p = sub.add_parser("outro", help="vẽ lại outro logo ANM ra mp4; mọi video render sau đó ghép file này vào cuối")
    p.add_argument("out", nargs="?", default=str(OUTRO))
    p.set_defaults(fn=cmd_outro)
    p = sub.add_parser("approve")
    p.add_argument("run")
    p.add_argument("what", choices=["brief", "script"])
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("auto")
    p.add_argument("target", help="slug của video mới (cùng --topic) hoặc thư mục RUN đang làm")
    p.add_argument("--topic")
    p.add_argument("--auto", action="store_true", help="không dừng duyệt brief (vẫn dừng duyệt bản dịch)")
    p.add_argument("--style", choices=["old", "neon"], default="old",
                   help="kiểu video của video mới (cùng --topic); chạy tiếp thì kiểu nằm trong run.json")
    p.add_argument("--runs-dir")
    p.add_argument("--foreground", action="store_true")
    p.set_defaults(fn=cmd_auto)
    p = sub.add_parser("cms", help="gửi video đã xong lên CMS: bài cá nhân, đề xuất mạng xã hội (không đăng)")
    p.add_argument("run")
    p.add_argument("--recreate", action="store_true", help="bài cũ đã bị xóa hoặc không chắc đã tạo: tạo bài mới")
    p.add_argument("--foreground", action="store_true")
    p.set_defaults(fn=cmd_cms)
    p = sub.add_parser("cms-probe", help="in các id cần điền vào cms.toml, đọc từ một bài mẫu")
    p.add_argument("article_id", type=int)
    p.add_argument("--env", choices=cms.ENVS)
    p.set_defaults(fn=cmd_cms_probe)
    p = sub.add_parser("wait")
    p.add_argument("run")
    p.add_argument("--poll", type=float, default=15)
    p.set_defaults(fn=cmd_wait)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
