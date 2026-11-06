"""`vshort <command> <run_dir>`: every pipeline step as a command that can be re-run."""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from vshort import auto, cards, cms, cover, motion, publish, render, shapes, shots, sound
from vshort.captions import Fragment, detect_fragments, write_sheets
from vshort.fit import Placement, build_narration, phrase_fracs, phrase_times, sequence, total
from vshort.media import frame_at, probe
from vshort.plates import Plate, build_plates, clean, scene_cuts
from vshort.render import OUTRO, build_ass, clean_video, export_outro, render_video, segments
from vshort.run import Run, config
from vshort.script import (Sentence, check_brief, check_numbers, check_script, check_style, group_sentences,
                           merge_text, merged)
from vshort.stills import NLM_OUTRO, _label, contact_sheet, grid_image, pick_still, scene_of
from vshort.textfit import FONTS
from vshort.tts import (Clip, QuotaExceeded, clip_paths, gemini_speaker, load_api_key, synth_lines, synth_script,
                        zerotts_speaker)
from vshort.visuals import SUBTITLE, patch_text, pencil, svg_frame, ui_problems, validate

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
    sents = _sentences(run)
    probs = check_script(sents, script) + check_style(script) + check_numbers(sents, script)
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
        probs += [] if probs else motion.ui_problems(doc)  # not in `vshort render`: older canvases still render
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
        probs += [] if probs else motion.ui_problems(motion.bound(doc, bind))  # the bind's labels may be longer
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
            continue
        if it["kind"] == "svg":  # a photo is laid out clear of them by pencil()
            probs += [f"visuals.json mục {n} (svg): {p}" for p in ui_problems(refs[it["id"]])]
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


SHOT_KINDS = {"still": "ảnh NotebookLM", "svg": "thẻ tư liệu", "photo": "ảnh tư liệu"}
CELL_W, CELL_H = 180, 320  # a beat on shots/sheet.png


@dataclass
class _ShotLines:
    """What a beat plan stands on: the script, the timeline, the frames, and which lines may have beats."""
    script: list[dict]
    place: dict[int, Placement]
    seg: dict[int, render.Segment]  # the render's own: a line runs from the cut before it to the cut after it
    kind: dict[int, str]  # the lines that may have beats -> "still" | "svg" | "photo"
    cards: dict[int, Path]  # the svg of each card line
    plate_top: int  # the old captions start here on a NotebookLM still


def _shots_lines(run: Run) -> _ShotLines | None:
    """The lines that may have beats = those with words, not animated, with a frame and a place in the timeline; None (after
    saying why) when a file is missing or broken."""
    for name, redo in (("script.vi.json", ""), ("timeline.json", " (chạy `vshort timeline`)"), ("frames.json", " (chạy `vshort visuals`)")):
        if not run.file(name).exists():
            _err(f"thiếu {name}{redo}")
            return None
    script, fitted, frames = run.read("script.vi.json"), run.read("timeline.json"), run.read("frames.json")
    placements = [Placement(**p) for p in fitted["placements"]]
    have = {f["id"] for f in frames}
    rows = frames + [{"id": p.id, "file": "", "group": ""} for p in placements if p.id not in have]  # the cuts need every voice
    seg = {s.id: s for s in segments(placements, rows, run.path, fitted["total"])}
    doc = _motion(run)
    bind = _bind(run) if doc is not None and doc is not BAD_JSON else None
    items = _load(run, "visuals.json")
    if any(x is BAD_JSON for x in (doc, bind, items)):
        return None
    refs = _refs(items)
    group = {f["id"]: f["group"] for f in frames}
    spoken = {r["id"] for r in script if r["phrases"].strip()}
    kind = {i: _shot_kind(group[i], refs.get(i)) for i in sorted((spoken & set(group) & set(seg)) - motion.lines(bind))}
    if gone := [f["file"] for f in frames if f["id"] in kind and not run.file(f["file"]).exists()]:
        _err("thiếu file khung hình: " + ", ".join(gone) + " (chạy lại `vshort visuals`)")
        return None
    plates = run.read("plates/plates.json") if run.file("plates/plates.json").exists() else []
    return _ShotLines(script, {p.id: p for p in placements}, seg, kind,
                      {i: run.file(refs[i]["file"]) for i, k in kind.items() if k == "svg"},
                      min([p["y"] for p in plates if p["y"] < SUBTITLE[1]], default=SUBTITLE[1]))


def _refs(items) -> dict[int, dict]:
    """The references of visuals.json (a card or a photo) by line id."""
    return {it["id"]: it for it in items if isinstance(it, dict) and it.get("kind") in ("svg", "photo")
            and isinstance(it.get("file"), str)} if isinstance(items, list) else {}


def _shot_kind(group: str, ref: dict | None) -> str:
    """"still" (a NotebookLM picture), "svg" (a card) or "photo"; a reference whose visuals.json item is gone counts as a photo."""
    return "still" if group.startswith("s") else (ref or {}).get("kind", "photo")


def _crc(path: Path) -> int | None:
    try:
        return zlib.crc32(path.read_bytes())
    except OSError:
        return None


def _quiet(run: Run, name: str):
    """RUN/name as JSON; None when it is missing, null or not JSON (the commands that own it say so)."""
    try:
        return motion.load(run.file(name))
    except ValueError:
        return None


def _shots_stamp(run: Run, ids) -> dict:
    """What the beats of lines `ids` stand on: their words, where the voice puts them, the frames and the bytes of each
    frame, the cards' SVGs (the keys of "cards" are the card lines) and the lines that are animated. `shots/ok.json` is
    only good for as long as this is what it was when it was written."""
    want = {int(i) for i in ids}  # ok.json's keys are strings
    frames = run.read("frames.json")
    bind = _quiet(run, "motion.bind.json") if _quiet(run, "motion.json") is not None else None
    refs = _refs(_quiet(run, "visuals.json"))
    mine = [f for f in frames if f["id"] in want]
    return {"script": {str(r["id"]): r["phrases"] for r in run.read("script.vi.json") if r["id"] in want},
            "timeline": [p for p in run.read("timeline.json")["placements"] if p["id"] in want],
            "frames": frames,
            "pictures": {str(f["id"]): _crc(run.file(f["file"])) for f in mine},
            "cards": {str(f["id"]): _crc(run.file(refs[f["id"]]["file"])) for f in mine
                      if _shot_kind(f["group"], refs.get(f["id"])) == "svg"},
            "animated": sorted(motion.lines(bind))}


def _a_piece_a_line(reveal: dict[str, list[dict]]) -> str:
    """reveal.json as JSON with one piece of a card to a line: a card has dozens, and an agent reads this."""
    cards_ = [f' "{i}": [\n' + ",\n".join("  " + json.dumps(q, ensure_ascii=False) for q in rows) + "\n ]" for i, rows in reveal.items()]
    return "{" + ",\n".join(cards_) + "\n}\n" if cards_ else "{}\n"


def _shots_prep(run: Run, w: _ShotLines) -> int:
    """The files an agent plans the beats from: the words with their times, when a card writes each element, the frames
    under a grid, the shapes it may draw."""
    out = run.file("shots")
    out.mkdir(exist_ok=True)
    (run.file("frames") / "grid").mkdir(exist_ok=True)  # `vshort visuals` made frames/, or there is no line to plan
    say = {r["id"]: r["phrases"] for r in w.script}
    text, reveal = [], {}
    for i, k in w.kind.items():
        p, seg = w.place[i], w.seg[i]
        text.append(f"câu {i} ({seg.start:.2f}–{seg.end:.2f}s, ảnh frames/{i}.png, {SHOT_KINDS[k]})")
        for n, ((f0, _), phrase) in enumerate(zip(phrase_fracs(say[i]), say[i].split("|")), 1):
            text.append(f"  cụm {n} @{p.start + f0 * p.dur:.2f}s: {_speech(phrase)}")
        grid_image(Image.open(seg.file).convert("RGB")).save(run.file(f"frames/grid/{i}.png"))
        if k == "svg":
            try:
                pieces = cards.Card(w.cards[i], seg.start, seg.end, render.XF).pieces
            except Exception as e:  # agent-made file: any decoder error is a bad card
                _err(f"câu {i}: không đọc được {w.cards[i].name}: {e}")
                return BAD_INPUT
            reveal[str(i)] = [{"t0": round(q.t0, 3), "t1": round(q.t1, 3), "border": q.border,
                               "box": [math.floor(q.box[0]), math.floor(q.box[1]), math.ceil(q.box[2]), math.ceil(q.box[3])]}
                              for q in pieces]
    text.append(f"Dải phụ đề cũ trên ảnh NotebookLM bắt đầu ở y {w.plate_top}: đừng cận vào đó.")
    (out / "phrases.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    (out / "reveal.json").write_text(_a_piece_a_line(reveal), encoding="utf-8")
    shapes.sheet(run.path, library=True).save(out / "shapes.png")
    print(f"{len(w.kind)} câu được lên nhịp\nđọc: {out / 'phrases.txt'}, {out / 'reveal.json'}\n"
          f"xem: {out / 'shapes.png'}, {run.file('frames/grid')}/<câu>.png")
    return OK


def _touch(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _shots_line(run: Run, w: _ShotLines, i: int, rows: list[dict]):
    """(problems, (id, beats, segment, how to draw a frame of it at t)) for one line whose beats have the right form."""
    seg, p = w.seg[i], w.place[i]
    bs = shots.beats(rows, next(r["phrases"] for r in w.script if r["id"] == i), p)
    try:
        if w.kind[i] == "svg":
            card = cards.Card(w.cards[i], seg.start, seg.end, render.XF)
            cap, final, pieces, base = cards.cap(card), card.frame(seg.end), card.pieces, card.frame
            ref = final
        else:
            final, ref, pieces = Image.open(seg.file).convert("RGB"), None, []
            cap, base = shots.MAX_ZOOM_STILL, lambda t: final
    except Exception as e:  # agent-made file: any decoder error
        return [f"shots.json câu {i}: không đọc/vẽ được {w.cards.get(i, seg.file).name}: {e}"], None

    def cam(t):
        return render.planned_camera(bs, t, seg.start, seg.end, cap)

    probs = shots.gap_problems(i, seg.start, seg.end, shots.changes(bs, [q.t0 for q in pieces]))
    probs += shots.image_problems(i, bs, final, cam, run.path, end=seg.end, ref=ref)
    for n, b in enumerate(bs, 1):
        who = f"shots.json câu {i} nhịp {n}: "
        focus = b.focus if isinstance(b.focus, tuple) else None  # None and KEEP frame nothing
        if w.kind[i] == "still" and focus and focus[3] > w.plate_top - 10:
            probs.append(who + f"focus {list(focus)} xuống tới y {focus[3]}, vào dải phụ đề cũ của ảnh NotebookLM (bắt đầu ở "
                         f"y {w.plate_top}; focus phải kết thúc trên y {w.plate_top - 10}): đừng cận vào đó")
        if b.focus is not shots.KEEP and b.t > (latest := render.last_focus(seg.end)):  # null is a focus too: it moves the camera
            probs.append(who + f"focus muộn quá: lời của nhịp lúc {shots._secs(b.t - seg.start)} s của câu ({round(b.t, 3)} s), mà "
                         f"camera phải tới nơi và giữ khung {shots._secs(shots.HOLD)} s trước khi kéo về toàn cảnh cho chỗ cắt sang câu sau; "
                         f"nhịp có focus phải ở chậm nhất {shots._secs(latest - seg.start)} s của câu ({round(latest, 3)} s): "
                         "dời nhịp sớm hơn hoặc bỏ focus (mark, doodle, pop thì được ở cuối câu)")
        for what, box in (("focus", focus), ("mark", b.mark and b.mark["box"])):
            late = [q.t1 for q in pieces if box and _touch(box, q.box) and b.t - shots.LEAD < q.t1 - 1e-9]
            if late:
                start, done = b.t - shots.LEAD, max(late)  # reveal.json counts in absolute seconds: say both
                probs.append(who + f"{what} box {list(box)} bắt đầu lúc {shots._secs(start - seg.start)} s của câu "
                             f"({round(start, 3)} s như shots/reveal.json), dòng chưa viết tới: thẻ viết xong chỗ đó lúc "
                             f"{shots._secs(done - seg.start)} s của câu ({round(done, 3)} s như shots/reveal.json): "
                             "dời nhịp muộn hơn hoặc chọn dòng đã viết")
    return probs, (i, bs, seg, lambda t: render.draw(shots.draw_overlays(base(t), bs, t, run.path, ref=ref), *cam(t)))


def _drawn(b: shots.Beat) -> float:
    """How long after its start a beat's marks are all there: drawn on, bounced in, and the camera arrived."""
    return max([shots.DRAW] * (b.mark is not None or b.doodle is not None) + [shots.POP_T] * (b.pop is not None)
               + [shots.SNAP] * (b.focus is not shots.KEEP))


def _shots_sheet(lines: list[tuple[int, list[shots.Beat], render.Segment, object]]) -> Image.Image:
    """A row per line, a cell per beat: the frame as rendered when the beat's marks are drawn, with `line.beat` on it."""
    img = Image.new("RGB", (max([len(bs) for _, bs, _, _ in lines], default=1) * CELL_W, max(len(lines), 1) * CELL_H), "white")
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 22)
    for row, (i, bs, seg, frame) in enumerate(lines):
        for n, b in enumerate(bs, 1):
            cell = frame(min(b.t - shots.LEAD + _drawn(b), seg.end)).resize((CELL_W, CELL_H), Image.LANCZOS)
            d = ImageDraw.Draw(cell)
            d.rectangle((0, 0, CELL_W - 1, CELL_H - 1), outline=(150, 150, 150))
            _label(d, (6, 4), f"{i}.{n}", font)
            img.paste(cell, ((n - 1) * CELL_W, row * CELL_H))
    return img


def cmd_shots(a) -> int:
    """`--prep`: the files the beats are planned from. Without: shots.json checked line by line; the good lines go to
    shots/ok.json (what render uses) and every line is drawn on shots/sheet.png."""
    run = Run(a.run)
    if (w := _shots_lines(run)) is None:
        return BAD_INPUT
    if a.prep:
        return _shots_prep(run, w)
    ok = run.file("shots/ok.json")
    if not run.file("shots.json").exists():
        ok.unlink(missing_ok=True)  # a plan that is gone or unreadable leaves no verdicts for render to go on with
        _err("thiếu shots.json: chạy `vshort shots --prep`, đọc shots/phrases.txt rồi viết kế hoạch nhịp vào shots.json")
        return BAD_INPUT
    try:
        doc = json.loads(run.file("shots.json").read_text(encoding="utf-8"))
    except ValueError as e:
        ok.unlink(missing_ok=True)
        _err(f"shots.json không phải JSON hợp lệ: {e}")
        return BAD_INPUT
    probs = shots.schema_problems(doc, w.script, set(w.kind), lambda s: (d := shapes.find(s, run.path)) is not None and not shapes.problems(d, s))
    if not isinstance(doc, dict):
        ok.unlink(missing_ok=True)
        for p in probs:
            _err(p)
        return BAD_INPUT
    broken = {int(m[1]) for p in probs if (m := re.match(r"shots\.json câu (-?\d+)", p))}  # the form is wrong: nothing more to check
    rows_of = {}
    for k, v in doc.items():
        try:
            rows_of[int(k)] = v
        except ValueError:  # schema_problems has named the key
            pass
    plans, good = [], {}
    for i, rows in sorted(rows_of.items()):
        if i in broken or i not in w.kind:
            continue
        found, plan = _shots_line(run, w, i, rows)
        probs += found
        plans += [plan] if plan else []
        if not found:
            good[i] = rows
    out = run.file("shots")
    out.mkdir(exist_ok=True)
    run.write("shots/ok.json", {"stamp": _shots_stamp(run, good), "lines": {str(i): rows for i, rows in good.items()}})
    for p in probs:  # the verdicts are on disk and said before the sheet, which can fail on its own
        _err(p)
    _shots_sheet(plans).save(out / "sheet.png")
    if probs:
        return BAD_INPUT
    print(f"nhịp hình: {len(good)} câu, {sum(map(len, good.values()))} nhịp; ảnh để xem: {out / 'sheet.png'}")
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


def _beat_plan(run: Run, placements: list[Placement], script: list[dict], frames: list[dict]):
    """({line id: beats}, {line id: svg of a card line}) of the lines `vshort shots` passed; both empty with no
    shots/ok.json. None (after saying why) when its stamp is not what the run's files give now: the beats were timed
    and checked against other words, pictures, cards or timeline."""
    path = run.file("shots/ok.json")
    if not path.exists():
        return {}, {}
    try:
        ok = json.loads(path.read_text(encoding="utf-8"))
        lines, fresh = ok["lines"], _shots_stamp(run, ok["lines"]) == ok["stamp"]
    except (OSError, ValueError, KeyError, TypeError):  # not what `vshort shots` writes
        fresh = False
    if not fresh:
        _err("kịch bản hoặc khung hình đã đổi sau lần kiểm nhịp hình cuối (chạy lại `vshort shots`)")
        return None
    say, at, refs = {r["id"]: r["phrases"] for r in script}, {p.id: p for p in placements}, _refs(_quiet(run, "visuals.json"))
    planned = {int(i): tuple(shots.beats(rows, say[int(i)], at[int(i)])) for i, rows in lines.items()}
    return planned, {f["id"]: run.file(refs[f["id"]]["file"]) for f in frames
                     if f["id"] in planned and _shot_kind(f["group"], refs.get(f["id"])) == "svg"}


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
        if probs := shapes.check_run(run.path) + motion.bind_problems(doc, bind, script, run.path, style=False):
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
    if (plan := _beat_plan(run, placements, script, frames)) is None:
        return BAD_INPUT
    ass = run.file("subs.ass")
    ass.write_text(build_ass(phrase_times(placements, script)), encoding="utf-8")
    if not OUTRO.exists():
        export_outro()
    segs = segments(placements, frames, run.path, fitted["total"], animated, *plan)
    fx = sound.cues(segments(placements, frames, run.path, fitted["total"], animated), scenes)  # a planned reference is still one
    run.write("sfx.json", [asdict(c) for c in fx])
    sound.master(run.file("narration.wav"), fx, fitted["total"], run.file("mix.wav"))
    render_video(segs, ass, run.file("mix.wav"), fitted["total"], run.file("final.mp4"), scenes, OUTRO, run_dir=run.path)
    run.mark("render")
    print(run.file("final.mp4"))
    return OK


def cmd_outro(a) -> int:
    export_outro(Path(a.out))
    print(Path(a.out).resolve())
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
    for name, fn in [("detect", cmd_detect), ("text", cmd_text), ("check", cmd_check), ("plates", cmd_plates),
                     ("clean", cmd_clean),
                     ("tts", cmd_tts), ("stills", cmd_stills), ("motion", cmd_motion), ("visuals", cmd_visuals), ("shots", cmd_shots),
                     ("timeline", cmd_timeline),
                     ("render", cmd_render), ("status", cmd_status), ("cover", cmd_cover)]:
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(fn=fn)
        if name == "motion":
            p.add_argument("--design", action="store_true", help="check the canvas against the brief, before the voice")
        if name == "shots":
            p.add_argument("--prep", action="store_true", help="write the files the beats are planned from")
        if name == "cover":
            p.add_argument("--candidates", action="store_true", help="gather the sources' lead images for an agent to pick")
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
