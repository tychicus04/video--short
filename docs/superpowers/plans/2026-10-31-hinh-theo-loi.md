# Hình theo lời (Video Follows the Voice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the output video on the Vietnamese voice's timeline: sentences back to back, each shown as a clean NotebookLM still (or a redrawn real reference) with smooth sub-pixel camera motion and crossfades, wrong on-screen text patched.

**Architecture:** `vshort timeline` lays TTS clips back to back (replaces `fit`). `vshort stills` renders a caption-free, watermark-free `clean.mp4` from the source plus plates and picks one "fully drawn" still per spoken line. A new agent `vs-visuals` writes `visuals.json` (text patches, SVG redraws, photo references); `vshort visuals` turns stills + that file into one frame image per line. `vshort render` draws every output frame in Python (PIL affine transform, crossfades) and pipes it to ffmpeg with the existing ASS subtitles and the narration.

**Tech Stack:** Python 3.12 (uv), numpy, pillow, imageio-ffmpeg (libass, libx264), torch CPU + LaMa (unchanged plates), cairosvg (new, uses the system libcairo), pytest.

**Spec:** `docs/superpowers/specs/2026-10-31-hinh-theo-loi-design.md` (amends `DESIGN.md`).

## Global Constraints

- Server: headless Ubuntu 26.04, CPU only, no Playwright/Chromium; ffmpeg only via `imageio_ffmpeg.get_ffmpeg_exe()` (`vshort.media.FF`).
- Free only: no Gemini image calls. TTS stays one call per script; `timeline` must not call TTS.
- Video 720×1280, 30 fps. Subtitle style from commit `63cee33` is unchanged (Patrick Hand em 50, box centred at y=1150).
- Keep visual content that must stay readable (credit lines, patched text) out of the subtitle band y 1094–1206 and the watermark corner x 524–704, y 1232–1264.
- No voice tempo change, no per-sentence syllable budget, no "too long" loop (exit code 3 disappears).
- Never print, log or write `GEMINI_API_KEY`.
- Work directly on `main` in `~/video-pipeline`; one commit per task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Agent/skill docs are edited in the repo (`claude/…`) and copied to `~/.claude/agents/` and `~/.claude/skills/video-short/`. Docs and user-facing messages in Vietnamese; code and comments in English, matching the existing terse style.
- Run tests with `uv run pytest -q` from `~/video-pipeline`; never pipe test output into `tail`/`grep`.

## Review Focus

1. A line whose English window is entirely blank paper or a fade-in → its still must come from the drawn part of the same scene (Task 2 test `test_pick_still_widens_from_a_blank_window`).
2. Consecutive lines from the same NotebookLM scene → one continuous camera move, no jump at the sentence boundary (Task 4 test `test_camera_continues_across_lines_of_one_scene`).
3. A very short line (≈0.8 s, "Giả sử") → crossfades shrink so the line's own image is still fully visible (Task 4 test `test_short_segment_clamps_crossfade`).
4. A malformed `visuals.json` from the agent (unknown id, box off-frame, missing file, missing source) → exit 2 listing every problem, no frames written (Task 3 test `test_visuals_cmd_rejects_bad_items`).
5. Reference photos of any shape (wide 1600×900, tiny 200×300) → fit inside the frame, credit line readable and clear of the subtitle band (Task 3 test `test_pencil_fits_any_photo`).

---

### Task 1: Back-to-back timeline, drop the timing-fit machinery

**Files:**
- Modify: `vshort/fit.py`, `vshort/cli.py`, `vshort/script.py`, `vshort/tts.py`, `vshort/run.py`, `vshort/render.py` (delete `outro_cut`), `vshort/plates.py` (delete `first_blank`), `config.toml`
- Test: `tests/test_fit.py`, `tests/test_script.py`, `tests/test_cli.py`, `tests/test_render.py`, `tests/test_plates.py`, `tests/test_tts.py`

**Interfaces:**
- Produces: `fit.Placement(id: int, start: float, dur: float)`; `fit.GAP = 0.3`, `fit.LEAD = 0.2`, `fit.TAIL = 0.5`; `fit.sequence(clips: list[Clip]) -> list[Placement]`; `fit.total(placements: list[Placement]) -> float`; `fit.build_narration(placements, clips, total, out_wav) -> None`; `fit.phrase_times(placements, script) -> list[tuple[float, float, str]]` (unchanged behaviour); `script.check_script(sentences, script) -> list[str]` (no `rate`); CLI `vshort timeline RUN` writing `timeline.json = {"total": float, "placements": [{"id", "start", "dur"}]}` and `narration.wav`, marking step `timeline`.
- Removes: `place`, `too_long`, `TOO_LONG`, `cmd_fit`/`fit` subcommand, `script.budget`, `tts.measured_rate`, `run.set_config`, `plates.first_blank`, `render.outro_cut`, config keys `syllables_per_sec` and `max_tempo`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fit.py (replace the place/too_long/tempo tests)
def test_sequence_lays_clips_back_to_back():
    clips = [Clip(1, Path("a"), 2.0), Clip(3, Path("b"), 1.0), Clip(4, Path("c"), 1.5)]
    p = sequence(clips)
    assert [(x.id, round(x.start, 2), x.dur) for x in p] == [(1, 0.2, 2.0), (3, 2.5, 1.0), (4, 3.8, 1.5)]
    assert round(total(p), 2) == 5.8

def test_build_narration_places_clips(tmp_path):  # adapt the old test: no tempo, a 1.1 s clip lasts 1.1 s
    ...
    assert not loud[: int(0.45 * 24000)].any() and loud[int(0.6 * 24000)] and loud[int(2.5 * 24000)]
    assert not loud[int(3.2 * 24000):].any()

# tests/test_script.py
def test_long_sentence_is_fine_but_wide_phrase_is_not():
    s = [Sentence(1, 0, 3, "a"), Sentence(2, 3, 3.5, "b")]
    long_ok = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "một hai ba bốn năm sáu bảy tám chín mười mười một"}]
    assert check_script(s, long_ok) == []
    wide = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "chữ " * 40}]
    assert any("vượt" in p for p in check_script(s, wide))

# tests/test_cli.py: test_check_exit_2 now fails on an empty first line; add
def test_timeline_writes_back_to_back_narration(tmp_path):
    # two 1.0 s tone WAVs in tts.json for ids 1 and 3, script.vi.json with id 2 empty
    assert main(["timeline", str(tmp_path)]) == 0
    t = json.loads((tmp_path / "timeline.json").read_text())
    assert [p["id"] for p in t["placements"]] == [1, 3] and abs(t["total"] - 3.0) < 1e-6  # 0.2+1+0.3+1+0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_fit.py tests/test_script.py tests/test_cli.py`
Expected: FAIL (`sequence`/`total` not defined, `check_script` still takes `rate`, no `timeline` command).

- [ ] **Step 3: Implement**

`sequence`: first clip starts at `LEAD`, each next at previous end + `GAP`, in the order given (the script order; `cmd_tts` already skips empty lines). `total` = last end + `TAIL`. `build_narration` drops `atempo`. `cmd_text` prints `id  start–end  en` (no budget). `cmd_tts` stops measuring/saving the reading rate. `cmd_render` keeps the old `compose` path until Task 4 rewrites it; it is not run in between. Remove `syllables_per_sec` and `max_tempo` from `config.toml` and commit `config.toml` (this also ends the "tts rewrites config.toml" problem). Delete the tests of every removed function.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass (plus the existing xfail).

- [ ] **Step 5: Commit**

`git add -A vshort tests config.toml && git commit -m "feat: lay the Vietnamese voice back to back; drop per-sentence timing fit"`

---

### Task 2: Clean video and one still per spoken line

**Files:**
- Create: `vshort/stills.py`
- Modify: `vshort/render.py` (add `clean_video`), `vshort/cli.py` (add `stills`), `tests/conftest.py` (add frame kind `drawn`)
- Test: `tests/test_stills.py`, move `test_plate_applies_from_its_first_frame` from `tests/test_render.py` to it

**Interfaces:**
- Consumes: `plates.Plate`, `plates.scene_cuts(video) -> list[float]`, `script.merged(sentences, script) -> list[Sentence]` (merged windows: a line's window includes the emptied English sentences after it).
- Produces: `render.clean_video(src: Path, plates: list[Plate], plates_dir: Path, end: float, out: Path) -> None` (delogo `x=524:y=1232:w=180:h=32` + frame-exact plate overlays, exactly the current `compose` logic, video only, `-t end`, libx264 crf 12); `stills.pick_still(video: Path, a: float, b: float, cuts: list[float]) -> float`; `stills.scene_of(t: float, cuts: list[float]) -> int`; CLI `vshort stills RUN` writing `clean.mp4`, `stills/<id>.png` (720×1280 RGB), `stills/grid/<id>.png` (same image with a light 40 px grid, coordinates labelled every 80 px — the agent reads patch boxes off it), `stills/sheet.png` (all stills small, each labelled with its id), `stills.json = [{"id": int, "t": float, "scene": int}]` in script order, marking step `stills`.

- [ ] **Step 1: Write the failing tests**

conftest kind `drawn`: cream page, and from `t0 + 1.0` a dark bar `f[300:700, 200:520] = 60`.

```python
def test_pick_still_prefers_the_fully_drawn_frame(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "drawn")], captions=[])
    assert 1.0 <= pick_still(v, 0.0, 2.0, []) < 2.0

def test_pick_still_widens_from_a_blank_window(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "drawn"), (2, 3, "#202020")], captions=[])
    assert 1.0 <= pick_still(v, 0.0, 0.8, [2.0]) < 2.0  # window is blank paper; same scene, not the next one

def test_pick_still_skips_the_frames_right_after_a_cut(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "drawn")], captions=[])
    t = pick_still(v, 0.9, 2.0, [1.0])
    assert t >= 1.25

def test_stills_cmd_one_still_per_spoken_line(make_video, tmp_path):
    # sentences 1..3, script id 2 empty, plates.json = [] -> stills.json ids [1, 3], PNGs exist, sheet exists
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_stills.py`
Expected: FAIL (`vshort.stills` missing).

- [ ] **Step 3: Implement**

`pick_still`: sample the clean video in gray at 10 fps over `[a, b)`, skipping 0.25 s after and 0.1 s before every cut; score = std of the gray frame; return the time of the best score, preferring the later frame when scores are within 1 %. If the best score is below 8 (blank paper), repeat over the whole scene containing `(a+b)/2`. `cmd_stills`: `clean_video` up to the end of the last merged window, then one `pick_still` per merged line, `frame_at(clean.mp4, t)` for the images. `compose` is now unused but stays until Task 4 replaces `render`.

- [ ] **Step 4: Run the whole suite** — `uv run pytest -q`, all pass.

- [ ] **Step 5: Commit** — `git commit -m "feat: clean video and one fully drawn still per spoken line"`

---

### Task 3: Frames from stills, text patches and redrawn references

**Files:**
- Create: `vshort/visuals.py`
- Modify: `vshort/cli.py` (add `visuals`), `pyproject.toml` + `uv.lock` (`uv add cairosvg`), `scripts/setup_assets.sh`
- Test: `tests/test_visuals.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `stills.json`, `stills/<id>.png` (Task 2).
- Produces: `visuals.PAPER = (238, 234, 226)`; `visuals.validate(items: list[dict], ids: set[int], run_dir: Path) -> list[str]`; `visuals.patch_text(img: Image.Image, box: tuple[int, int, int, int], text: str) -> Image.Image`; `visuals.pencil(photo: Image.Image, credit: str) -> Image.Image`; `visuals.svg_frame(path: Path) -> Image.Image`; CLI `vshort visuals RUN` reading `visuals.json` (absent file = `[]`) and writing `frames/<id>.png` + `frames.json = [{"id": int, "file": "frames/<id>.png", "group": str}]` (group `s<scene>` for a still, `v<id>` for a reference), marking step `visuals`.
- `visuals.json` item shapes (the agent contract, copy into Task 5's agent doc):
  - `{"kind": "patch", "ids": [7, 8], "box": [x0, y0, x1, y1], "text": "tin-tuc.example", "note": "…"}`
  - `{"kind": "svg", "id": 21, "file": "visuals/21.svg", "source": "https://…", "accessed": "2026-10-31", "note": "…"}`
  - `{"kind": "photo", "id": 14, "file": "visuals/14.jpg", "source": "https://…", "accessed": "2026-10-31", "credit": "Nguồn: …", "note": "…"}`

- [ ] **Step 1: Write the failing tests**

```python
def test_patch_text_replaces_the_label():  # cream image, old dark text drawn in (100, 100, 400, 140)
    out = np.asarray(patch_text(img, (96, 96, 404, 144), "tin-tuc.example"))
    assert old-text ink mask and new ink mask differ, new ink exists inside the box,
           pixels outside the box are unchanged, and the box's median colour is within 6 of the page colour

def test_pencil_fits_any_photo():
    for size in [(1600, 900), (200, 300)]:
        f = np.asarray(pencil(Image.new("RGB", size, "gray"), "Nguồn: Google"))
        assert f.shape == (1280, 720, 3)
        assert credit ink exists in rows 960–1080 and rows 1094–1280 are all PAPER-coloured (±6)

def test_svg_frame_resolves_patrick_hand():
    # same <text>Cập nhật phần mềm</text> with font-family "Patrick Hand" vs "DejaVu Sans": both draw ink, ink widths differ

def test_visuals_cmd_rejects_bad_items(tmp_path, capsys):
    # stills.json ids [1, 3]; visuals.json = unknown id 9, box [0, 0, 900, 50], svg file missing, photo without source
    assert main(["visuals", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert all(s in err for s in ["9", "900", "visuals/", "source"]) and not (tmp_path / "frames").exists()

def test_visuals_cmd_groups_and_replaces(tmp_path):
    # stills ids [1, 3, 4] scenes [0, 0, 1]; photo for id 4; patch on ids [1, 3]
    # -> frames.json groups ["s0", "s0", "v4"]; frames/1.png differs from stills/1.png inside the box only
    # and an empty visuals.json gives frames identical to the stills
```

- [ ] **Step 2: Run tests to verify they fail** — `uv run pytest -q tests/test_visuals.py tests/test_cli.py`, FAIL.

- [ ] **Step 3: Implement**

`setup_assets.sh`: also fetch `BeVietnamPro-Bold.ttf` (patch text, and the old-caption font of the synthetic test videos in `conftest.py`), then copy `assets/fonts/*.ttf` to `~/.local/share/fonts/vshort/` and run `fc-cache -f` so cairosvg resolves `Patrick Hand` and `Be Vietnam Pro`. `patch_text`: fill with the median colour of the box's 2 px border, ink colour = 5th-percentile darkest colour inside the original box, Be Vietnam Pro Bold sized to fit (height ≤ 60 % of the box, width ≤ box − 8 px), centred. `pencil`: gray → invert → GaussianBlur(10) → colour dodge, fitted inside 640×920 centred at (360, 520) on a PAPER canvas, thin grey frame, credit in Patrick Hand em 26 centred under the photo, never below y 1080. `svg_frame`: cairosvg to 720×1280 PNG, alpha-composited onto PAPER. Validation runs before anything is written.

- [ ] **Step 4: Run the whole suite** — `uv run pytest -q`, all pass.

- [ ] **Step 5: Commit** — `git commit -m "feat: frames from stills with text patches, SVG redraws and pencil photos"`

---

### Task 4: Smooth motion render

**Files:**
- Modify: `vshort/render.py` (replace `compose` with the functions below), `vshort/cli.py` (`render` reads `timeline.json` + `frames.json`; `status` lists `new fetch detect text plates tts stills visuals timeline render`)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `timeline.json` (Task 1), `frames.json` (Task 3), `build_ass`, `phrase_times`.
- Produces: `render.XF = 0.4`, `render.ZOOM = 1.08`; `@dataclass Segment(id: int, start: float, end: float, file: Path, group: str)`; `render.segments(placements, frames: list[dict], run_dir: Path, total: float) -> list[Segment]` (`frames[i]["file"]` is relative to the run folder); `render.view(segs: list[Segment], t: float) -> list[tuple[Path, float, tuple[float, float, float]]]` (the 1–2 images visible at `t` with their blend weight and camera `(scale, cx, cy)`); `render.draw(img: Image.Image, scale: float, cx: float, cy: float) -> Image.Image`; `render.render_video(segs, ass: Path, narration: Path, total: float, out: Path) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_motion_is_subpixel_smooth():
    # one 4 s segment of a white image with a 2 px black vertical line at x=360
    xs = [dark-column centroid of draw(img, *camera) for each frame at 30 fps]
    d = np.diff(xs)
    assert np.abs(d).max() < 1.5 and np.abs(d[5:-5]).min() > 0.05  # moves every frame, never jumps a pixel step

def test_camera_continues_across_lines_of_one_scene():
    # two segments, same group "s0", different files: camera at boundary−1/30 s and boundary+1/30 s differs by < 0.5 px

def test_short_segment_clamps_crossfade():
    # segments 0–3 s, 3–3.8 s, 3.8–7 s in three groups: at t = 3.4 the middle image has weight 1.0

def test_render_video_duration_audio_and_subs(tmp_path):
    # two solid-colour frames, timeline with 2 placements, one subtitle phrase
    # -> duration ≈ total (±0.1), has an audio stream, middle of seg 1 is colour A, of seg 2 colour B,
    #    frame_at(out, t)[1112, 360] is the light subtitle box
```

- [ ] **Step 2: Run tests to verify they fail** — `uv run pytest -q tests/test_render.py`, FAIL.

- [ ] **Step 3: Implement**

Segment boundaries sit in the middle of the gap between two voices (first segment starts at 0, last ends at `total`). A shot = a run of consecutive segments with the same `group`; shot `j` moves by kind `j % 4`: zoom in 1.0→`ZOOM`, zoom out `ZOOM`→1.0, pan left→right at `ZOOM`, pan right→left at `ZOOM`, linear in time over the shot extended by `XF/2` on both sides. Inside a shot, a new image crossfades in over `XF` centred on the boundary while the camera keeps moving; between shots both images and cameras crossfade. Each crossfade is clamped to a third of the shorter neighbouring segment. `draw` = `Image.transform(size, AFFINE, …, resample=BICUBIC)` so motion is sub-pixel. `render_video` pipes raw RGB frames at 30 fps into ffmpeg (`-f rawvideo -pix_fmt rgb24 -s 720x1280 -r 30 -i -`, narration as input 1, `ass=…:fontsdir=…`, libx264 crf 18 preset medium yuv420p, aac 128k, `+faststart`, `-t total`), caching decoded images by path.

- [ ] **Step 4: Run the whole suite** — `uv run pytest -q`, all pass.

- [ ] **Step 5: Commit** — `git commit -m "feat: render stills with smooth camera moves and crossfades on the voice timeline"`

---

### Task 5: Agents, skill and docs

**Files:**
- Create: `claude/agents/vs-visuals.md`
- Modify: `claude/agents/vs-translator.md`, `claude/agents/vs-reviewer.md`, `claude/skills/video-short/SKILL.md`, `DESIGN.md`, `PROMPT.md` (only if it names removed steps)

- [ ] **Step 1: `vs-visuals.md`** (frontmatter `model: sonnet`, tools `Read, Write, Bash, WebSearch`). Inputs: `RUN` with `stills/sheet.png`, `stills/<id>.png`, `stills/grid/<id>.png`, `script.vi.json`, `brief.vi.md`, `sources.md`. Job, in order: (1) find on-screen text that contradicts the Vietnamese line or the brief → `patch` items, same box on every still of that scene, replacement text generic (`.example`), never a real site; English labels that are not wrong stay; (2) pick 3–5 lines where a real reference helps trust or understanding → `svg` (UI screens, report headlines, timelines; viewBox `0 0 720 1280`, transparent background, grey pencil-like strokes `#4a4a4a`, light cyan accent, `Patrick Hand` for hand lettering and `Be Vietnam Pro` for UI text, real Vietnamese iOS labels, exact words and numbers from the source, a small credit line drawn inside the image above y 1080) or `photo` (downloaded with `curl` from official or press pages into `RUN/visuals/`, `credit` filled); never copy repo names/URLs that lead to exploit code, write what was left out in `note`; (3) write `RUN/visuals.json` with the shapes from Task 3, run `cd ~/video-pipeline && uv run vshort visuals RUN` until exit 0, open each `frames/<id>.png` it made and fix anything that looks pasted-in or misaligned. Return: one line per item.
- [ ] **Step 2: `vs-translator.md`**: drop the syllable budget, "vừa khung", and "chỉ sửa các id quá dài" rules; input table is `id, khung giây, câu tiếng Anh`; keep faithful translation, brief-wins, title rule, phrase splitting, iOS labels.
- [ ] **Step 3: `vs-reviewer.md`**: inputs `timeline.json`, `frames.json`, `visuals.json`; checks: no old English caption or watermark in any frame; motion smooth (look at 6 consecutive frames at three places); no near-blank frame; no pause in `narration.wav` longer than 0.8 s except at the ends; every `svg`/`photo` item's words and numbers match its `source`; every `patch` reads naturally with no visible seam; subtitles match `script.vi.json`.
- [ ] **Step 4: `SKILL.md`**: after the translator, run in parallel: `vshort tts` | `vshort plates` → `vshort stills` → `vs-visuals` → (agent runs `vshort visuals`); then `vshort timeline`, `vshort render`, `vs-reviewer`. Remove the `fit`/exit-3 loop. Final answer to Tai also lists `visuals.json` items (patches and references with sources).
- [ ] **Step 5: `DESIGN.md`**: step list and non-goals point to the new spec (illustrations are no longer untouched; "Khớp giây" becomes "hình theo lời").
- [ ] **Step 6: Verify and sync**

Run: `grep -rn "vshort fit\|max_tempo\|syllables_per_sec\|âm tiết tối đa\|kicker" claude DESIGN.md PROMPT.md vshort`
Expected: no output. Then copy the four agent files plus `vs-visuals.md` to `~/.claude/agents/` and `SKILL.md` to `~/.claude/skills/video-short/`; `diff -r claude/agents ~/.claude/agents | grep -v "^Only in /home/tai/.claude"` prints nothing.

- [ ] **Step 7: Commit** — `git commit -m "docs: vs-visuals agent and the voice-led pipeline in skill and agents"`

---

### Task 6: End-to-end on Coruna

- [ ] **Step 1:** `uv run vshort stills ~/notebooklm-videos/coruna-darksword-en`; look at `stills/sheet.png`: 20 drawn stills, none near-blank, no English caption.
- [ ] **Step 2:** Dispatch `vs-visuals` (general-purpose agent following `claude/agents/vs-visuals.md` if the session predates the new agent) on the run. Expected: patches for "untrusted-site.com" and "iOS 18.7.6+", 3–5 references, `vshort visuals` exit 0.
- [ ] **Step 3:** `uv run vshort timeline …` (no TTS call: script unchanged) and `uv run vshort render …`. Expected: `final.mp4` ≈ 66 s (sum of clips + gaps + lead/tail).
- [ ] **Step 4:** Dispatch the reviewer (Opus) following `claude/agents/vs-reviewer.md`. Expected: verdict "Đạt"; fix and re-render on any "Cần sửa" finding that is a code defect.
- [ ] **Step 5:** Report to Tai: duration before/after, the list of patches and references with sources, the review verdict, the scp command.
