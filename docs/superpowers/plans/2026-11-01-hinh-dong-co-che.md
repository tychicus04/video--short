# Hình động giải thích cơ chế (Animated Mechanism Explainers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stills of the lines that explain an attack's mechanism with hand-drawn animated scenes (things draw themselves on paper, a red dot does what the voice says), built from a scene file an agent writes.

**Architecture:** A new agent `vs-motion` writes `RUN/motion.json`: the animated lines and 1–4 scenes, each a list of things from a fixed kit plus actions, every time given as a cue (line, phrase, fraction) rather than seconds. `vshort motion` validates it (clutter, safe area, label words, safety) and draws a preview sheet. `vshort visuals` refuses references on animated lines but still patches their stills (the fallback). `vshort render` resolves cues to seconds from `timeline.json` and draws animated lines frame by frame with `vshort/kit.py` (no camera), crossfading with the stills around them.

**Tech Stack:** Python 3.12 (uv), numpy, pillow, imageio-ffmpeg (libx264, libass), pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-01-hinh-dong-co-che-design.md` (amends `DESIGN.md` and `docs/superpowers/specs/2026-10-31-hinh-theo-loi-design.md`). Look target: `docs/superpowers/specs/2026-11-01-hinh-dong-v2.png`; spike code to port the drawing from: `prototype/hinh-dong/anim.py`, `prototype/hinh-dong/anim2.py`.

## Global Constraints

- At most one animated stretch per video: consecutive spoken lines, never the first spoken line (the title), at most half of the video. 1–4 scenes, each one or more whole consecutive lines.
- At most 4 things visible at once in a scene; a thing and its label count as one; paths, cracks and unlabelled dots do not count.
- Labels ≤ 20 characters, one line, drawn no smaller than em 32 px; everything inside x 40–680, y 60–1050 (clear of the subtitle band y 1094–1206 and the watermark corner).
- Only dots (the attacker, a packet) and icons (data being carried) may move.
- Label words come from the stretch's narration, the kit's common-noun list, single letters/digits, or `.example`/`.test`/`.invalid` names. No CVE, exploit, tool, function or process names, no commands, no code, no real web address.
- Colours as v2: paper `visuals.PAPER` (238, 234, 226), ink (62, 62, 68), red (196, 48, 40) = attacked, green (60, 140, 80) = legitimate/safe, blue (70, 110, 160) = protection layer, grey (150, 150, 155) page lines. Labels in Patrick Hand.
- Animated lines: no camera zoom/pan; crossfades as today (`render.XF` 0.4 s). Subtitles unchanged.
- Animation failure never blocks the video: the lines fall back to their stills.
- CPU only; render cost about 0.13 s per animated frame (v2 spike) is fine.
- Work directly on `main` in `~/video-pipeline`; one commit per task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Code and comments in English in the existing terse style; user-facing messages and agent/skill docs in Vietnamese. Agent/skill docs are edited under `claude/` and copied to `~/.claude/agents/` and `~/.claude/skills/video-short/`.
- Tests: `uv run pytest -q` from `~/video-pipeline`; never pipe test output into `tail`/`grep`.

## Review Focus

1. TTS is re-run and every line gets longer or shorter → the animation still lands on the same words, because cues resolve against the new `timeline.json` (Task 2 test `test_timed_follows_the_voice`).
2. A short line (≈0.8 s) carrying several actions → every action ends inside its line, none shorter than 0.3 s (Task 2 test `test_acts_end_inside_their_line`).
3. The script is edited after `vshort motion` (a line emptied or renumbered) → `vshort render` exits 2 and names `vshort motion`, never a traceback or a scene on the wrong line (Task 4 test `test_render_cmd_rejects_a_stale_motion_file`).
4. The agent writes a label with a technique or tool name, or a real domain in `url` → rejected with the word named (Task 2 test `test_validate_reports`, cases `label-word`, `url`).
5. An animated stretch between two stills, or a reference right after it → the stills still never repeat their neighbour's camera move and the reference keeps zooming only (Task 3 test `test_animated_shots_leave_the_camera_rotation_alone`).

---

### Task 1: Drawing kit

**Files:**
- Create: `vshort/kit.py`
- Test: `tests/test_kit.py`

**Interfaces:**
- Produces:
  - `W, H, SS = 720, 1280, 2`; `INK, RED, GREEN, BLUE, GRAY` (values in Global Constraints); `COLORS = {"ink": INK, "red": RED, "green": GREEN, "blue": BLUE}`
  - `SAFE = (40, 60, 680, 1050)`; `LABEL_EM, SMALL_EM, MIN_LABEL_EM, MAX_LABEL = 44, 34, 32, 20`
  - `DRAW, TURN, HIDE, MOVE = 0.8, 0.6, 0.4, 1.2` (seconds: draw-on, turn red, erase, default move/bounce)
  - `BOXED = {"phone", "computer", "server", "box", "wall"}` (take `box`), `POINTED = {"person", "icon", "dot", "text", "crack"}` (take `xy`), plus `"path"` (takes `points`); `ICONS = {"key", "message", "wallet", "file", "lock", "mail"}`; `MOVERS = {"dot", "icon"}`
  - `@dataclass Act(do: str, thing: str, t0: float, t1: float, to: tuple[float, float] | None = None, path: list[tuple[float, float]] | None = None, say: str = "", vanish: bool = False)`; `do` ∈ `draw | move | bounce | red | pulse | hide`
  - `bbox(thing: dict) -> tuple[float, float, float, float]`: the extent of the thing **including its label** (and the stand of a computer)
  - `label_em(thing: dict) -> int`: em the label is drawn at. Inside a `box`: `LABEL_EM` shrunk until the text fits the box width minus 2 × 16 px, `0` when it does not fit at `MIN_LABEL_EM`. Elsewhere fixed: `SMALL_EM` for icon/dot labels, `LABEL_EM` for the rest (`bbox` then keeps them in `SAFE`)
  - `draw(things: list[dict], acts: list[Act], t: float) -> PIL.Image.Image`: the 720×1280 RGB frame at time `t`

Thing dicts (validated in Task 2): `id`, `kind`, optional `label`, optional `color` (`ink` default; dots default `red`); `box: [x0, y0, x1, y1]` for `BOXED`; `xy: [x, y]` centre for `POINTED`; `points: [[x, y], …]` and optional `arrow: bool` for `path`; `icon` for icons; optional `url` for `phone`/`computer` (draws an address bar holding it and grey page lines under it, like v2 scene 1). `text` is a free label at `xy` (its `label` is the text). Label placement: above the box for `phone`/`computer`/`server`/`wall`, centred inside for `box` (moved up to make room when a `red` act brings a `say` line under it), below for `person`/`icon`/`dot`. A label takes the thing's colour; a wall is a blue dashed outline.

Drawing rules (port the helpers from `prototype/hinh-dong/anim.py` — `ease`, `wobble`, `stroke`, `rrect`, `dot`, `along` — and the small-layer `write` and the key/bubble/wallet shapes from `anim2.py`; draw at `SS`× on paper grain and downsample with LANCZOS):
- A thing is invisible before its `draw` act; outline and label appear over `DRAW` seconds (stroke by path length, text wiped left to right).
- `hide` erases the thing by reversing its draw-on over `[t0, t1]`; a `move` with `vanish` erases it over the last `HIDE` seconds of the move.
- `red` redraws the outline and label in red over `[t0, t1]` and writes `say` under the label.
- `move` goes from the mover's position at `t0` to `to`, or along `path` from its first point to its last, eased; a `to` move flies in a shallow arc like the icons of v2 scene 3. `bounce` goes towards `to` and back (sine). Movers keep their last position.
- `pulse` gives a dot the breathing glow ring of v2 from `t0` on.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_kit.py
from vshort.kit import Act, H, RED, W, bbox, draw, label_em

PHONE = {"id": "p", "kind": "phone", "box": [180, 170, 540, 1010], "label": "trang web hợp pháp", "color": "green",
         "url": "tin-tuc.example"}
DOT = {"id": "d", "kind": "dot", "xy": [400, 550], "label": "mã độc"}


def _ink(img, box):  # pixels clearly darker than paper inside box
    a = np.asarray(img.crop(box).convert("L")).astype(int)
    return int((a < 180).sum())


def test_nothing_shows_before_its_draw_act():
    img = draw([PHONE], [Act("draw", "p", 1.0, 1.8)], 0.5)
    assert img.size == (W, H) and _ink(img, (0, 0, W, H)) == 0


def test_draw_on_grows_then_holds():
    acts = [Act("draw", "p", 0.0, 0.8)]
    half, done, later = (_ink(draw([PHONE], acts, t), (0, 0, W, H)) for t in (0.4, 0.8, 3.0))
    assert 0 < half < done and abs(done - later) < 0.02 * done


def test_bbox_includes_the_label_above_a_phone():
    x0, y0, x1, y1 = bbox(PHONE)
    assert y0 < 170 - 20 and y1 >= 1010 and x0 <= 180 and x1 >= 540


def test_label_em_shrinks_then_gives_up():
    assert label_em({**PHONE, "label": "A"}) == 44
    # Patrick Hand "trang web hợp pháp" is 304 px at em 44, 221 px at em 32
    assert 32 <= label_em({"id": "b", "kind": "box", "box": [300, 300, 600, 400], "label": "trang web hợp pháp"}) < 44
    assert label_em({"id": "b", "kind": "box", "box": [300, 300, 480, 400], "label": "trang web hợp pháp"}) == 0


def test_move_ends_at_the_target_and_vanish_erases():
    acts = [Act("draw", "d", 0, 0.8), Act("move", "d", 1.0, 2.0, to=(200, 300))]
    img = draw([DOT], acts, 2.5)
    assert _red(img, (185, 285, 215, 315)) and not _red(img, (385, 535, 415, 565))
    gone = draw([DOT], [acts[0], Act("move", "d", 1.0, 2.0, to=(200, 300), vanish=True)], 2.5)
    assert not _red(gone, (185, 285, 215, 315))


def test_red_turns_the_outline_red():
    acts = [Act("draw", "p", 0, 0.8), Act("red", "p", 1.0, 1.6, say="đã bị chiếm")]
    assert not _red(draw([PHONE], acts, 0.9), (170, 160, 550, 1020))
    assert _red(draw([PHONE], acts, 2.0), (170, 160, 550, 1020))
```

`_red(img, box)` is a helper: any pixel within 40 of `RED` in every channel. Add `import numpy as np`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_kit.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'vshort.kit'`).

- [ ] **Step 3: Implement `vshort/kit.py`** with the interfaces and drawing rules above. Cache the paper grain (`lru_cache`) and fonts; a frame of the Coruna scene 2 (Task 2 example) must draw in under 0.3 s.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_kit.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vshort/kit.py tests/test_kit.py
git commit -m "feat: hand-drawn animation kit (things draw on, dots move, layers turn red)"
```

---

### Task 2: Scene file — validate, time, preview

**Files:**
- Create: `vshort/motion.py`, `examples/motion/coruna.json`, `examples/motion/coruna.script.json`, `examples/motion/goi-tin.json`, `examples/motion/goi-tin.script.json`
- Modify: `vshort/fit.py` (add `phrase_fracs`, use it in `phrase_times`)
- Test: `tests/test_motion.py`, `tests/test_fit.py`

**Interfaces:**
- Consumes: `kit.Act`, `kit.bbox`, `kit.label_em`, `kit.draw`, `kit.SAFE`, `kit.BOXED`, `kit.POINTED`, `kit.MOVERS`, `kit.ICONS`, `kit.COLORS`, `kit.MAX_LABEL`, `kit.DRAW`, `kit.TURN`, `kit.HIDE`, `kit.MOVE`; `fit.Placement`, `fit.GAP`; `script.syllables`; `visuals.SAFE_TLDS`, `visuals._strip_marks`
- Produces:
  - `fit.phrase_fracs(phrases: str) -> list[tuple[float, float]]`: start/end fraction of each `|` phrase of a line, by syllable share (the same weights `phrase_times` uses)
  - `motion.COMMON: frozenset[str]` — lower-case syllables always allowed in labels: `điện thoại máy tính chủ dữ liệu hệ thống hacker kẻ tấn công nghe lén mạng trình duyệt người dùng nạn nhân gói tin tệp mật khẩu nhắn ví tiền thư khóa đã bị chiếm lấy cắp trang web an toàn lõi lớp bảo vệ`
  - `@dataclass motion.Scene(lines: list[int], things: list[dict], acts: list[kit.Act])`
  - `motion.load(path: Path) -> dict | None` — `None` for a missing file or JSON `null`; raises `ValueError` on invalid JSON
  - `motion.lines(doc) -> set[int]` — the int ids in `doc["lines"]`, `set()` for anything malformed
  - `motion.clashes(items: list, lines: set[int]) -> list[str]` — one message per `svg`/`photo` item of `visuals.json` whose `id` is animated
  - `motion.validate(doc, script: list[dict], visuals: list | None = None) -> list[str]` — every problem, one Vietnamese line each, `[]` when fine
  - `motion.estimate(script: list[dict]) -> list[fit.Placement]` — spoken lines back to back at `SYL = 0.2` s per syllable, `fit.GAP` apart
  - `motion.timed(doc: dict, placements: list[fit.Placement], script: list[dict]) -> list[Scene]` — `Scene.things` are the thing dicts as written; `Scene.acts` holds one `draw` act per thing (from its `when`), then the file's acts in order, all in seconds on the video timeline
  - `motion.sheet(doc: dict, script: list[dict]) -> PIL.Image.Image` — one row per scene, its frames at 25/50/75/100 % of the scene (estimated timing), 240 px wide each, scene number at the row start

`motion.json` format:

```json
{"lines": [7, 8, 9], "note": "vì sao chọn các câu này",
 "scenes": [{"lines": [7, 8, 9], "idea": "một ý, một dòng",
             "things": [{"id": "phone", "kind": "phone", "box": [180, 170, 540, 1010], "label": "…", "when": {"line": 7}}],
             "acts": [{"do": "pulse", "thing": "bug", "when": {"line": 9}}]}]}
```

- A cue `when` is `{"line": id, "phrase": n, "at": f}`: `phrase` is 1-based (default 1), `at` is the fraction 0–1 of that phrase (default 0). It resolves to `p.start + p.dur * (f0 + (f1 - f0) * at)` with `(f0, f1) = phrase_fracs(line)[phrase - 1]`. A thing's `when` (default: its scene's first line) is its `draw` act.
- Acts: `move` (`to: [x, y]` xor `path: <id of a path thing>`, optional `vanish: true`), `bounce` (`to`), `red` (optional `say`), `pulse` (dots only), `hide`; optional `dur` in seconds (0 < dur ≤ 5). Defaults: draw `DRAW`, red `TURN`, hide `HIDE`, move/bounce `MOVE`; pulse lasts to the scene's end.
- Every act except `pulse` ends at `min(t0 + dur, max(line_end, t0 + 0.3))`, `line_end = p.start + p.dur` of the cue's line.

`validate` reports (each message starts `motion.json`, Vietnamese, names the scene/thing/act):
- not an object with `lines`, a non-empty `note` and `scenes`;
- `lines` not consecutive spoken lines of `script` (rows with empty `phrases` are skipped), or includes the first spoken line, or holds more than half of the script's syllables (`# ponytail: syllables stand in for seconds; the timeline does not exist yet`);
- `scenes` not 1–4, or their `lines` not splitting `lines` in order;
- a thing: unknown `kind`, missing/ill-typed geometry, duplicate `id` in its scene, unknown `icon`/`color`, `bbox` (or a path point, or a move target) outside `SAFE`, label empty/multi-line/over `MAX_LABEL` characters/`label_em == 0`, a `url` that does not end in `SAFE_TLDS`;
- a label or `say` word not allowed: tokens split on whitespace, `_strip_marks`, lower-cased; allowed when in the narration tokens of `lines`, in `COMMON`, a single letter or digit, or a dotted name ending in `SAFE_TLDS`;
- a cue whose `line` is not in its scene, `phrase` out of range, `at` outside 0–1;
- an act on an unknown thing, `move`/`bounce` on a non-mover, `pulse` on a non-dot, `say` on anything but `red`, `to` and `path` both or neither on `move`, an act before its thing's `draw` or after its `hide` (compared on `estimate` timing);
- more than 4 counted things visible at once, computed on `timed(doc, estimate(script), script)` at every draw time (a thing stays visible until its `hide` ends or its `vanish` move ends);
- `clashes(visuals, lines(doc))` when `visuals` is given.

Structural problems stop the later checks for that scene, so one bad field does not cascade into a traceback.

The two examples are the acceptance targets and the agent's worked examples (Task 5). Write them exactly:

`examples/motion/coruna.script.json`: a copy of `~/notebooklm-videos/coruna-darksword-en/script.vi.json` (rows `id`, `phrases`, `note`).

`examples/motion/coruna.json` — `{"lines": [7, 8, 9, 10, 11, 12, 13], "note": "Câu 7–13 nói mã độc đi từ trang web, qua sandbox, tới lõi rồi lấy dữ liệu.", "scenes": [...]}` with:

| Scene `lines` | things (`id` kind geometry label/extra `when`) | acts (`do` thing extra `when`) |
|---|---|---|
| `[7, 8, 9]` idea "trang web hợp pháp mang mã độc" | `phone` phone box [180,170,540,1010] "trang web hợp pháp" green url "tin-tuc.example" {7} · `bug` dot xy [400,550] "mã độc" {8, phrase 2} | pulse bug {9} |
| `[10, 11, 12]` idea "mã độc thoát sandbox, leo xuống lõi" | `safari` box [120,160,600,350] "Safari" {10} · `system` box [120,430,600,620] "Hệ thống" {10, at 0.4} · `kernel` box [120,700,600,890] "Lõi (kernel)" {10, at 0.8} · `sandbox` wall box [95,135,625,375] "sandbox" blue {10, phrase 2} · `bug` dot xy [500,255] {10, phrase 2, at 0.5} · `crack1` crack xy [500,375] {11, phrase 2, at 0.5} · `crack2` crack xy [500,700] {12, phrase 2} | bounce bug to [500,350] {10, phrase 3} · move bug to [500,525] {11, phrase 3} · red system {11, phrase 3, at 0.6} · move bug to [500,795] {12, phrase 3} · red kernel say "đã bị chiếm" {12, phrase 4} |
| `[13]` idea "dữ liệu bay sang hacker" | `phone` phone box [60,260,300,960] "điện thoại" {13} · `hacker` box [440,500,660,680] "hacker" {13, at 0.1} · `key` icon key xy [180,400] "mật khẩu" {13, phrase 4} · `msg` icon message xy [180,600] "tin nhắn" {13, phrase 5} · `wallet` icon wallet xy [180,800] "ví tiền" {13, phrase 5, at 0.45} | red phone {13, phrase 2} · move key to [550,590] vanish {13, phrase 4, at 0.2} · move msg to [550,590] vanish {13, phrase 5, at 0.2} · move wallet to [550,590] vanish {13, phrase 5, at 0.7} |

`examples/motion/goi-tin.script.json` (hypothetical topic, the spec's A→B example):

```json
[{"id": 1, "phrases": "Wi-Fi quán cà phê có thể làm lộ tin nhắn của bạn", "note": ""},
 {"id": 2, "phrases": "Máy A gửi tin nhắn | tới máy B | thành từng gói tin nhỏ.", "note": ""},
 {"id": 3, "phrases": "Trên Wi-Fi không mã hóa, | kẻ nghe lén ở giữa | chép lại được từng gói tin.", "note": ""},
 {"id": 4, "phrases": "Vì vậy hãy dùng kết nối có mã hóa, | như trang web có ổ khóa | hoặc mạng riêng ảo.", "note": ""},
 {"id": 5, "phrases": "Mã hóa biến gói tin | thành thứ kẻ nghe lén | không đọc được.", "note": ""}]
```

`examples/motion/goi-tin.json` — `{"lines": [2, 3], "note": "Câu 2–3 nói gói tin đi từ A tới B và bị nghe lén.", "scenes": [...]}`:

| Scene `lines` | things | acts |
|---|---|---|
| `[2]` idea "gói tin đi từ A tới B" | `a` computer box [50,420,250,640] "A" {2} · `b` computer box [470,420,670,640] "B" {2, phrase 2} · `wire` path points [[255,510],[465,510]] arrow {2, phrase 2, at 0.3} · `pkt` dot xy [255,510] "gói tin" blue {2, phrase 3} | move pkt path wire {2, phrase 3, at 0.2} |
| `[3]` idea "kẻ nghe lén chép gói tin" | `a`, `b`, `wire` as above, all {3} · `spy` person xy [360,800] "kẻ nghe lén" {3, phrase 2} · `pkt` dot xy [255,510] blue {3} · `copy` dot xy [360,510] red {3, phrase 3} | move pkt path wire {3, phrase 3} · move copy to [360,700] vanish {3, phrase 3, at 0.2} |

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fit.py
def test_phrase_fracs_split_by_syllables():
    assert phrase_fracs("một hai | ba") == [(0.0, 2 / 3), (2 / 3, 1.0)]
    assert phrase_fracs("một") == [(0.0, 1.0)]

# tests/test_motion.py
EX = Path(__file__).resolve().parent.parent / "examples" / "motion"

@pytest.mark.parametrize("name", ["coruna", "goi-tin"])
def test_examples_are_valid(name):
    doc = json.loads((EX / f"{name}.json").read_text())
    assert validate(doc, json.loads((EX / f"{name}.script.json").read_text())) == []

def test_timed_follows_the_voice():
    doc, script = _ex("goi-tin")
    slow = [Placement(i, s, d) for i, s, d in [(1, 0.2, 3), (2, 3.5, 4), (3, 7.8, 4), (4, 12.1, 5), (5, 17.4, 3)]]
    fast = [Placement(p.id, p.start / 2, p.dur / 2) for p in slow]
    t_slow = [a.t0 for sc in timed(doc, slow, script) for a in sc.acts]
    t_fast = [a.t0 for sc in timed(doc, fast, script) for a in sc.acts]
    assert t_fast == pytest.approx([t / 2 for t in t_slow])
    pkt = next(a for a in timed(doc, slow, script)[0].acts if a.do == "move")  # {2, phrase 3, at 0.2}
    f0, f1 = phrase_fracs(script[1]["phrases"])[2]
    assert pkt.t0 == pytest.approx(3.5 + 4 * (f0 + (f1 - f0) * 0.2))

def test_acts_end_inside_their_line():
    doc, script = _ex("coruna")
    pl = [Placement(r["id"], 10 + r["id"], 0.8) for r in script if r["phrases"].strip()]
    for sc in timed(doc, pl, script):
        for a in sc.acts:
            if a.do != "pulse":
                assert a.t1 - a.t0 >= 0.3 - 1e-9
                assert a.t1 <= max(_line_end(pl, a, sc), a.t0 + 0.3) + 1e-9

@pytest.mark.parametrize("case, edit, needle", [
    ("label-word", lambda d: d["scenes"][0]["things"][1].update(label="CVE-2025-24201"), "cve-2025-24201"),
    ("url", lambda d: d["scenes"][0]["things"][0].update(url="apple.com"), "apple.com"),
    ("crowded", lambda d: d["scenes"][1]["things"].append(
        {"id": "x", "kind": "box", "box": [200, 920, 520, 1000], "label": "dữ liệu", "when": {"line": 10}}), "4"),
    ("subtitle-band", lambda d: d["scenes"][0]["things"][0].update(box=[180, 170, 540, 1150]), "1050"),
    ("mover", lambda d: d["scenes"][1]["acts"].append({"do": "move", "thing": "safari", "to": [300, 300],
                                                       "when": {"line": 11}}), "safari"),
    ("title", lambda d: d.update(lines=[1, *d["lines"]]), "tiêu đề"),
    ("cue", lambda d: d["scenes"][0]["acts"][0]["when"].update(phrase=9), "phrase"),
    ("split", lambda d: d["scenes"][0].update(lines=[7, 9]), "lines"),
])
def test_validate_reports(case, edit, needle):
    doc, script = _ex("coruna")
    edit(doc)
    assert any(needle in p.lower() for p in validate(doc, script)), case

def test_validate_rejects_a_reference_on_an_animated_line():
    doc, script = _ex("coruna")
    refs = [{"kind": "svg", "id": 9, "file": "visuals/a.svg"}, {"kind": "svg", "id": 4, "file": "visuals/b.svg"},
            {"kind": "patch", "ids": [8, 9]}]
    assert [p for p in validate(doc, script, refs) if "9" in p] and not [p for p in clashes(refs, {7, 8, 9}) if "4" in p]

def test_load_treats_null_and_missing_as_no_animation(tmp_path):
    assert load(tmp_path / "motion.json") is None
    (tmp_path / "motion.json").write_text("null")
    assert load(tmp_path / "motion.json") is None
    (tmp_path / "motion.json").write_text("{oops")
    with pytest.raises(ValueError):
        load(tmp_path / "motion.json")

def test_sheet_has_a_row_per_scene():
    doc, script = _ex("coruna")
    img = sheet(doc, script)
    assert img.width >= 4 * 240 and img.height >= 3 * 420
```

`_ex(name)` loads an example and its script; `_line_end(pl, a, sc)` is the end of the placement of the line whose span holds `a.t0` within `sc.lines`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_fit.py tests/test_motion.py`
Expected: FAIL (`phrase_fracs` / `vshort.motion` not defined).

- [ ] **Step 3: Implement `fit.phrase_fracs`, `vshort/motion.py` and the four example files** as specified above. `phrase_times` keeps its behaviour (first line whole) and uses `phrase_fracs` for the others.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_fit.py tests/test_motion.py`
Expected: PASS. Then open `sheet(...)` of both examples saved to the scratch dir and check by eye that they read like `docs/superpowers/specs/2026-11-01-hinh-dong-v2.png` (gọn, nhãn to, không chạm nhau). Adjust example coordinates only, not the rules, if something overlaps.

- [ ] **Step 5: Commit**

```bash
git add vshort/fit.py vshort/motion.py examples/motion tests/test_fit.py tests/test_motion.py
git commit -m "feat: motion.json scene files: validated, timed by line and phrase, previewed as a sheet"
```

---

### Task 3: Render animated lines

**Files:**
- Modify: `vshort/render.py` (`Segment`, `segments`, `_kinds`, `_camera`, `view`, `render_video`)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `kit.draw`, `motion.Scene`
- Produces:
  - `Segment(id, start, end, file, group, scene: int | None = None)`
  - `segments(placements, frames, run_dir, total, animated: dict[int, int] | None = None) -> list[Segment]` — a line in `animated` (line id → scene index) gets `group=f"m{k}"`, `scene=k`
  - `view(segs, t) -> list[tuple[Segment, float, tuple[float, float, float]]]` (first element is now the segment, not its file)
  - `render_video(segs, ass, narration, total, out, scenes: list[motion.Scene] = ()) -> None`
- `_kinds`: an `m…` group gets kind `-1` and does not advance the still rotation; `_camera` of kind `-1` is `(1.0, W / 2, H / 2)`. `render_video` draws an animated part with `kit.draw(scene.things, scene.acts, t)` and no camera, and draws a scene once per frame when both crossfade parts are the same scene.

- [ ] **Step 1: Write the failing tests**

```python
def test_animated_shots_leave_the_camera_rotation_alone():
    assert _kinds(["s0", "m0", "s1", "s2"]) == [0, -1, 1, 2]
    assert _kinds(["s0", "m0", "m1", "v4", "s1"]) == [0, -1, -1, 0, 1]  # the reference zooms against the last reference

def test_segments_mark_animated_lines(tmp_path):
    pl = [Placement(1, 0.2, 1.0), Placement(3, 1.5, 1.0), Placement(4, 2.8, 1.0)]
    frames = [{"id": i, "file": f"frames/{i}.png", "group": "s0"} for i in (1, 3, 4)]
    segs = segments(pl, frames, tmp_path, 4.3, {3: 0, 4: 0})
    assert [(s.group, s.scene) for s in segs] == [("s0", None), ("m0", 0), ("m0", 0)]

def test_render_video_draws_the_scene_on_animated_lines(tmp_path):
    Image.new("RGB", (W, H), "white").save(tmp_path / "w.png")
    segs = [Segment(1, 0, 1, tmp_path / "w.png", "s0"), Segment(2, 1, 2.5, tmp_path / "w.png", "m0", 0)]
    scene = Scene([2], [{"id": "d", "kind": "dot", "xy": [360, 500]}], [Act("draw", "d", 1.2, 1.6)])
    ass = tmp_path / "subs.ass"
    ass.write_text(build_ass([(0, 2.5, "a")]), encoding="utf-8")
    write_silence(tmp_path / "n.wav", 2.5)
    render_video(segs, ass, tmp_path / "n.wav", 2.5, tmp_path / "out.mp4", [scene])
    early, late = frame_at(tmp_path / "out.mp4", 0.5), frame_at(tmp_path / "out.mp4", 2.2)
    assert early[490:510, 350:370].min() > 200          # white still, no dot
    r, g, b = late[500, 360].astype(int)
    assert r > 150 and g < 90 and b < 90                 # the red dot on paper
```

Update the existing tests that read `view(...)`'s first element as a file (`test_one_scene_crossfades_the_image_but_not_the_camera`, `test_short_segment_clamps_crossfade`, `test_reference_shots_only_zoom_and_keep_the_credit_line_in_view`) to compare segments (`segs[1]`, or `.file`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_render.py`
Expected: FAIL (`segments()` takes no `animated`, `_kinds` gives `m0` a camera move).

- [ ] **Step 3: Implement the render changes** listed in Interfaces.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_render.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vshort/render.py tests/test_render.py
git commit -m "feat: render draws animated lines from their scene, without camera, crossfading with the stills"
```

---

### Task 4: `vshort motion`, references refused on animated lines, render uses the scenes

**Files:**
- Modify: `vshort/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `motion.load`, `motion.validate`, `motion.lines`, `motion.clashes`, `motion.timed`, `motion.sheet`; `render.segments(..., animated)`, `render.render_video(..., scenes)`
- Produces:
  - `vshort motion RUN` (`cmd_motion`): no `motion.json` or `null` → prints `Không có hình động.`, deletes a stale `motion/`, marks `motion`, exit 0. Invalid JSON → exit 2 `motion.json không phải JSON hợp lệ: …`. Problems from `validate(doc, script, visuals.json items if the file exists)` → each on stderr, exit 2, step not marked. Otherwise writes `motion/sheet.png`, prints `<n> cảnh, câu <first>–<last>; ảnh để xem: <path>`, marks `motion`, exit 0.
  - `vshort visuals`: adds `clashes(items, lines(motion doc))` to its problems (a `patch` on an animated line stays fine and is applied to that line's frame as before).
  - `vshort render`: when `motion.json` holds a doc, `validate(doc, script)` problems → stderr ending with ` (chạy lại \`vshort motion\`)`, exit 2, old `final.mp4` kept; otherwise `timed(doc, placements, script)` → `animated` map → `segments(...)` and `render_video(..., scenes)`.
  - `vshort status` order: `new fetch detect text plates tts stills motion visuals timeline render`.

- [ ] **Step 1: Write the failing tests**

```python
def test_motion_cmd_without_a_file_means_no_animation(tmp_path, capsys):
    (tmp_path / "script.vi.json").write_text(json.dumps([{"id": 1, "phrases": "a"}]))
    (tmp_path / "motion").mkdir()
    assert main(["motion", str(tmp_path)]) == 0
    assert "Không có hình động." in capsys.readouterr().out
    assert Run(tmp_path).done("motion") and not (tmp_path / "motion").exists()

def test_motion_cmd_lists_every_problem(tmp_path, capsys):
    _motion_run(tmp_path)  # copies examples/motion/coruna(.script).json into the run
    doc = json.loads((tmp_path / "motion.json").read_text())
    doc["scenes"][0]["things"][1]["label"] = "WebKit"
    doc["scenes"][0]["things"][0]["url"] = "apple.com"
    (tmp_path / "motion.json").write_text(json.dumps(doc))
    assert main(["motion", str(tmp_path)]) == 2
    err = capsys.readouterr().err.lower()
    assert "webkit" in err and "apple.com" in err and not Run(tmp_path).done("motion")

def test_motion_cmd_writes_the_sheet(tmp_path, capsys):
    _motion_run(tmp_path)
    assert main(["motion", str(tmp_path)]) == 0
    assert (tmp_path / "motion" / "sheet.png").exists() and "3 cảnh, câu 7–13" in capsys.readouterr().out

def test_visuals_cmd_rejects_a_reference_on_an_animated_line(tmp_path, capsys):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "motion.json").write_text(json.dumps({"lines": [3], "note": "n", "scenes": []}))
    (tmp_path / "visuals").mkdir()
    Image.new("RGB", (500, 300)).save(tmp_path / "visuals" / "3.jpg")
    (tmp_path / "visuals.json").write_text(json.dumps([{"kind": "photo", "id": 3, "file": "visuals/3.jpg",
        "source": "https://a.example/p", "accessed": "2026-11-01", "credit": "Nguồn: A", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 2
    assert "hình động" in capsys.readouterr().err

def test_visuals_cmd_still_patches_an_animated_line(tmp_path):
    _visuals_run(tmp_path, ids=(1, 3), scenes=(0, 0))
    (tmp_path / "motion.json").write_text(json.dumps({"lines": [3], "note": "n", "scenes": []}))
    (tmp_path / "visuals.json").write_text(json.dumps(
        [{"kind": "patch", "ids": [3], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "n"}]))
    assert main(["visuals", str(tmp_path)]) == 0

def test_render_cmd_rejects_a_stale_motion_file(tmp_path, capsys):
    _render_run(tmp_path, (1, 3))
    (tmp_path / "final.mp4").write_bytes(b"good")
    (tmp_path / "motion.json").write_text(json.dumps({"lines": [3, 5], "note": "n", "scenes": []}))
    assert main(["render", str(tmp_path)]) == 2
    assert "vshort motion" in capsys.readouterr().err and (tmp_path / "final.mp4").read_bytes() == b"good"
```

Update `test_status_lists_every_step_in_order` to the new order.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_cli.py`
Expected: FAIL (`invalid choice: 'motion'`, visuals accepts the photo, render ignores `motion.json`).

- [ ] **Step 3: Implement `cmd_motion` and the `visuals`/`render`/`status` changes** listed in Interfaces.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vshort/cli.py tests/test_cli.py
git commit -m "feat: vshort motion checks the scene file; visuals and render respect the animated lines"
```

---

### Task 5: Agents, skill and docs

**Files:**
- Create: `claude/agents/vs-motion.md`
- Modify: `claude/agents/vs-researcher.md`, `claude/agents/vs-visuals.md`, `claude/agents/vs-reviewer.md`, `claude/skills/video-short/SKILL.md`, `DESIGN.md`, `PROMPT.md`
- Copy to: `~/.claude/agents/` and `~/.claude/skills/video-short/`

**Interfaces:**
- Consumes: `vshort motion RUN` (exit codes and output of Task 4), `examples/motion/*.json`, `motion.COMMON`, the kit vocabulary of Task 1.

Content each file must carry (Vietnamese, matching the existing agents' tone and structure):

- `vs-motion.md` (frontmatter `name: vs-motion`, `tools: Read, Write, Bash`, `model: sonnet`, description "Bước "hình động" của /video-short — …"):
  - Inputs: `RUN/script.vi.json`, `RUN/brief.vi.md` (mục "Cơ chế từng bước"), `RUN/sentences.en.json`. Writes only `RUN/motion.json`.
  - Choose the one stretch of consecutive lines whose voice explains the mechanism; none → write `null`. Rules of Global Constraints, stated plainly: one idea per scene, ≤ 4 things, big short labels, only the attacker and the carried data move, every action on the word that says it.
  - The full `motion.json` format of Task 2 (things, cues, acts, defaults), the kit vocabulary and the common-noun list, coordinates in px on 720×1280 inside x 40–680, y 60–1050.
  - Both examples by path (`~/video-pipeline/examples/motion/coruna.json`, `goi-tin.json`) with one line on what each scene shows; read them before writing.
  - Safety section (spec "An toàn"): concept level, labels from the narration, no CVE/exploit/tool/function names, no commands or code, `.example` names only, no step a viewer could repeat, nothing the voice does not say; a generic middle layer is allowed when the voice says "từng bước".
  - Loop: run `cd ~/video-pipeline && uv run vshort motion RUN` until exit 0, then Read `RUN/motion/sheet.png` and fix anything crowded or touching. Return: lines, scenes, the idea of each scene.
- `vs-researcher.md`: new brief section **Cơ chế từng bước** after "Ví dụ mô phỏng": 3–5 numbered steps, one sentence each (what goes where, which layer it gets past, what it takes), concept level, no names of vulnerabilities/techniques/tools, no code or commands; a topic with no mechanism writes "Không có". The English brief names it **How it works, step by step**.
- `vs-visuals.md`: lines listed in `RUN/motion.json` (`lines`) already have animation: never pick them for `svg`/`photo` (`vshort visuals` refuses), but still patch wrong text on their stills (they are the fallback).
- `vs-reviewer.md`: inputs add `motion.json`; new check: for every scene, frames at each act's time (from `timeline.json` and the cues) — the dot does what the line says when it says it, ≤ 4 things, labels readable and clear of the subtitle band, nothing that teaches an attack (= lỗi nặng), strokes and crossfades smooth; list the stretch (lines, scenes, idea of each) in `review.md`.
- `SKILL.md`:
  - description and intro mention hình động; design line adds the new spec.
  - Step 2 auto mode: the self-check also reads "Cơ chế từng bước" against the safety rule (concept level, no names, no code) and fixes it.
  - Step 3 fetch prompt adds: `Walk through its 'How it works, step by step' section in order, unless it says None.`
  - New step **Hình động** after Dịch sát and before Hình theo lời (may run while tts/plates/stills run; must finish before vs-visuals): give `vs-motion` the `$RUN`; then run `vshort motion $RUN` yourself; non-zero → `mv $RUN/motion.json $RUN/motion.loi.json`, run `vshort motion $RUN` again (no file = no animation, exit 0) and tell Tai why. Renumber the later steps.
  - Final answer adds the animated stretch (lines, scenes, idea of each) or "không có hình động" with the reason.
- `DESIGN.md`: the header blockquote also points to `docs/superpowers/specs/2026-11-01-hinh-dong-co-che-design.md` (hình động cho đoạn giải thích cơ chế).
- `PROMPT.md`: the final-answer line adds "đoạn hình động (câu, cảnh)".

- [ ] **Step 1: Write the six files** as above.

- [ ] **Step 2: Check the agent docs against the code**

Run: `cd ~/video-pipeline && grep -n "motion" claude/agents/*.md claude/skills/video-short/SKILL.md && uv run vshort motion --help`
Expected: every field, kind, act and default named in `vs-motion.md` exists in `vshort/motion.py`/`vshort/kit.py` (compare by reading both); the `--help` lists the `run` argument.

- [ ] **Step 3: Sync and commit**

```bash
cp claude/agents/vs-*.md ~/.claude/agents/ && cp claude/skills/video-short/SKILL.md ~/.claude/skills/video-short/
git add claude DESIGN.md PROMPT.md
git commit -m "docs: vs-motion writes the scenes, briefs carry the mechanism steps, review checks the animation"
```

---

### Task 6: Acceptance on the real Coruna run and the A→B example

Done by the controller (not a subagent): it touches Tai's run folder.

**Files:**
- Modify: `~/notebooklm-videos/coruna-darksword-en/` (`motion.json`, `motion/`, `final.mp4`, `review.md`); backup to `prev-v5/`

- [ ] **Step 1: Back up v5**

Run: `cd ~/notebooklm-videos/coruna-darksword-en && mkdir -p prev-v5 && cp final.mp4 review.md visuals.json prev-v5/`
Expected: `prev-v5/final.mp4` exists.

- [ ] **Step 2: Scene file and checks**

Run: `cp ~/video-pipeline/examples/motion/coruna.json ~/notebooklm-videos/coruna-darksword-en/motion.json && cd ~/video-pipeline && uv run vshort motion ~/notebooklm-videos/coruna-darksword-en && uv run vshort visuals ~/notebooklm-videos/coruna-darksword-en`
Expected: `3 cảnh, câu 7–13; …` then the usual visuals line, both exit 0.

- [ ] **Step 3: Render**

Run: `cd ~/video-pipeline && uv run vshort render ~/notebooklm-videos/coruna-darksword-en` (background, long timeout)
Expected: exit 0, `final.mp4` 66.0 s.

- [ ] **Step 4: Look**

Extract frames at the start, middle and end of each scene (cue times from `timeline.json`) and across the cuts at lines 7 and 14; compare with `docs/superpowers/specs/2026-11-01-hinh-dong-v2.png`: same scenes, dot on the words of v2, subtitles unchanged, crossfades clean. Save `motion.sheet` of `examples/motion/goi-tin.json` and look at it.

- [ ] **Step 5: Review**

Dispatch `vs-reviewer` (model as in its frontmatter) on the run; it rewrites `review.md`. Report its verdict and the scp command to Tai.
