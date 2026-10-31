# Video Short Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One Claude Code command `/video-short <topic>` that researches a topic, gets Tai's approval on the brief, generates an English NotebookLM short, and turns it into a Vietnamese-dubbed vertical video with clean fixed subtitles.

**Architecture:** A Python package `vshort` (in `~/video-pipeline/`) holds every deterministic step as a CLI subcommand that reads/writes JSON in a run folder `~/notebooklm-videos/<slug>/`. A skill (`~/.claude/skills/video-short/`) orchestrates the steps and hands the four judgment steps to subagents (research/brief, reading captions, translating/fitting, final review). Prototype code in `~/video-pipeline/prototype/` (detect.py, plates.py, render.py) is the starting point for tasks 2, 4 and 7.

**Tech Stack:** Python 3.12 (uv), numpy, pillow, imageio-ffmpeg (bundled ffmpeg with libass/libx264), torch CPU + LaMa `big-lama.pt`, google-genai, pytest. NotebookLM via `uv run notebooklm` in `~/Document/notebooklm-py-main`.

**Spec:** `~/video-pipeline/DESIGN.md`

## Global Constraints

- Server is headless Ubuntu 26.04, CPU only; no system ffmpeg — always use `imageio_ffmpeg.get_ffmpeg_exe()`.
- NotebookLM CLI: `cd ~/Document/notebooklm-py-main && uv run notebooklm …`; video: `generate video --format short --language en`.
- `GEMINI_API_KEY` comes from env, else from `~/Document/notebooklm-py-main/.env`. Never print, log, or write it anywhere.
- Input video: 720×1280, 30 fps, ~60 s; scenes nearly static.
- Style (from v4): font Be Vietnam Pro (ExtraBold for subs/title, Bold for kicker); libass em factor `EM = 1000/1526`; caption em 40, LINE_H 58, PAD_X 28, PAD_Y 26, MIN_BOX_W 480, MAX_TEXT_W 620, box colour `&H121212&`, highlight yellow `&H00D4FF&`, box bottom `SUB_BOTTOM = 1204`; title bar 0–104 px with yellow 3 px rule at 101; kicker em 20 at y 30; title em ≤ 38 fit to W−48 at y 70.
- First sentence shows whole; every other sentence shows as one-line phrases split with `|`; `*word*` = highlight.
- Watermark delogo box `x=524:y=1232:w=180:h=32`.
- Only checkpoint: Tai approves brief + title. Everything after runs unattended.
- Vietnamese follows the approved brief where the English narration conflicts; every such change is reported.
- Gemini quota-frugal: one TTS call per sentence; re-synthesize only sentences whose text changed; quota error stops resumably.
- Max voice tempo-up 1.10× (natural speed); otherwise the translator shortens the sentence.
- Run folder: `~/notebooklm-videos/<slug>/`; final file `final.mp4`.

## Review Focus

1. NotebookLM session expired mid-run → `vshort fetch` exits 4 with "đăng nhập lại trên Mac rồi scp storage_state.json"; rerun continues (Task 8 test).
2. Gemini quota exhausted halfway through TTS → finished clips kept, exit 75, rerun synthesizes only the missing ones (Task 5 test).
3. A non-caption UI label detected as a fragment (e.g. a button "Tải về và cài đặt") or the same caption repeated across a scene cut → empty text drops it, identical consecutive texts merge (Task 3 test).
4. A Vietnamese sentence still too long after shortening → never above 1.10× tempo; it spills into following silence and the next sentence starts no earlier than 0.1 s after; listed in review (Task 6 test).
5. A scene that moves (no static plate possible) → plate still produced from the scene's middle frame but flagged `moving: true` and listed in review (Task 4 test).

---

### Task 1: Project setup and media helpers

**Files:**
- Create: `~/video-pipeline/pyproject.toml`, `~/video-pipeline/.gitignore`, `~/video-pipeline/config.toml`, `~/video-pipeline/scripts/setup_assets.sh`, `~/video-pipeline/vshort/__init__.py`, `~/video-pipeline/vshort/media.py`, `~/video-pipeline/tests/conftest.py`
- Test: `~/video-pipeline/tests/test_media.py`

**Interfaces:**
- Produces: `vshort.media.FF: str`; `probe(video: Path) -> Probe` (`Probe(width:int, height:int, fps:float, duration:float)`); `iter_frames(video: Path, *, fps: float|None=None, crop: tuple[int,int,int,int]|None=None, gray: bool=True, start: float|None=None, end: float|None=None) -> Iterator[tuple[float, np.ndarray]]` (crop = w,h,x,y); `frame_at(video: Path, t: float, gray: bool=False) -> np.ndarray` (output-side seek, exact frame).
- Produces (tests, `conftest.py`): fixture `make_video(tmp_path, scenes, captions, fps=30) -> Path`: `scenes = [(start, end, "#RRGGBB" | "moving")]` (`"moving"` = grey background with a black 120 px square sliding 200 px across), `captions = [(start, end, y_center, text)]` burned with ASS (BorderStyle 3, light-grey box `&HE6E6E6&`, dark text), 720×1280, silent AAC track; helpers `wav_bytes(seconds: float) -> bytes` (silent 24 kHz mono 16-bit WAV) and `write_silence(path: Path, seconds: float)`.

- [ ] **Step 1:** `git init ~/video-pipeline`; `pyproject.toml` with package `vshort`, script `vshort = "vshort.cli:main"`, deps `numpy pillow imageio-ffmpeg torch google-genai`, dev dep `pytest`; torch from index `https://download.pytorch.org/whl/cpu` (`[[tool.uv.index]] explicit = true` + `[tool.uv.sources]`). `.gitignore`: `.venv/ models/ assets/fonts/ __pycache__/`. `config.toml`: `tts_model = "gemini-3.8-flash-tts"`, `voice = "Charon"`, `syllables_per_sec = 5.0`, `max_tempo = 1.10`, `env_file = "~/Document/notebooklm-py-main/.env"`, `notebooklm_dir = "~/Document/notebooklm-py-main"`, `runs_dir = "~/notebooklm-videos"`.
- [ ] **Step 2:** `scripts/setup_assets.sh` downloads `BeVietnamPro-{Bold,ExtraBold}.ttf` from `https://github.com/google/fonts/raw/main/ofl/bevietnampro/` into `assets/fonts/` and `big-lama.pt` from `https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt` into `models/`; idempotent (skips existing files). Run it, then `uv sync`.
- [ ] **Step 3: Write failing tests** in `tests/test_media.py`:

```python
def test_probe(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=[])
    p = probe(v)
    assert (p.width, p.height) == (720, 1280) and p.fps == 30 and abs(p.duration - 2) < 0.05

def test_iter_frames_crop_and_times(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    frames = list(iter_frames(v, crop=(10, 10, 0, 0)))
    assert len(frames) == 60 and frames[0][1].shape == (10, 10)
    assert frames[0][1].mean() < 20 and frames[45][1].mean() > 235 and abs(frames[45][0] - 1.5) < 1e-6

def test_frame_at_exact(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    assert frame_at(v, 1.02, gray=True).mean() > 235
```

- [ ] **Step 4:** Run `cd ~/video-pipeline && uv run pytest tests/test_media.py -q` → FAIL (import error).
- [ ] **Step 5:** Implement `media.py` (raw-video pipe from ffmpeg like `prototype/detect.py`; `probe` parses `ffmpeg -i` stderr for `Video: … WxH`, `fps`, `Duration`).
- [ ] **Step 6:** Run tests → PASS. Commit `feat: project setup and media helpers`.

### Task 2: Caption fragment detection and reading sheets

**Files:**
- Create: `~/video-pipeline/vshort/captions.py`
- Test: `~/video-pipeline/tests/test_captions.py`

**Interfaces:**
- Consumes: `iter_frames`, `frame_at` (Task 1).
- Produces: `@dataclass Fragment(i: int, start: float, end: float, y0: int, y1: int, text: str|None = None)`; `find_bands(video: Path) -> list[tuple[int,int]]`; `detect_fragments(video: Path) -> list[Fragment]` (sorted by time, `i` from 0, one per on-screen caption; no fragment for stretches without a caption); `write_sheets(video: Path, frags: list[Fragment], out_dir: Path, per_sheet: int = 22) -> list[Path]` (each crop labelled with `i`, from the fragment's middle frame).

Band finding (replaces prototype's hard-coded A/B): sample 6 fps grey frames; per pixel ink = `< 90`; a row is "caption-like" when ink in that row toggles on/off between consecutive samples in ≥ 5 % of samples while art lines stay put; merge caption-like rows within 12 px into bands, pad 8 px each side, keep bands 40–120 px tall. Fragment segmentation: as `prototype/detect.py` (active band = band with most ink if > 150 px; new fragment when active band changes or band mean-abs-diff > 6).

- [ ] **Step 1: Write failing tests:**

```python
CAPS = [(0.0, 0.5, 930, "How can an iPhone"), (0.5, 1.0, 930, "be taken over"),
        (1.0, 1.5, 1147, "without a single"), (1.5, 2.0, 1147, "click?")]

def test_find_bands(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=CAPS)
    bands = find_bands(v)
    assert len(bands) == 2
    assert bands[0][0] < 930 < bands[0][1] and bands[1][0] < 1147 < bands[1][1]

def test_detect_fragments_times_and_bands(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "#EDEDED")], captions=CAPS)
    fr = detect_fragments(v)
    assert len(fr) == 4
    assert [round(f.start, 2) for f in fr] == [0.0, 0.5, 1.0, 1.5]
    assert fr[2].y0 < 1147 < fr[2].y1

def test_write_sheets(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=CAPS)
    sheets = write_sheets(v, detect_fragments(v), tmp_path / "sheets", per_sheet=3)
    assert len(sheets) == 2 and all(s.exists() for s in sheets)
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Real-video check:** `uv run python -c "from vshort.captions import detect_fragments; f=detect_fragments(Path('~/notebooklm-videos/coruna-darksword-short.mp4').expanduser()); print(len(f), f[1].start, f[-1].end)"` → about 60–64 fragments, `f[1]` ≈ 1.40 s, last end ≈ 57.13 (compare `prototype/detect.py` output: fragment boundaries 1.40, 2.33, …, 57.13).
- [ ] **Step 6:** Commit `feat: caption fragment detection`.

### Task 3: Fragment text, sentences, and Vietnamese script checks

**Files:**
- Create: `~/video-pipeline/vshort/script.py`, `~/video-pipeline/vshort/textfit.py`
- Test: `~/video-pipeline/tests/test_script.py`

**Interfaces:**
- Consumes: `Fragment` (Task 2).
- Produces: `merge_text(frags: list[Fragment], texts: dict[int, str]) -> list[Fragment]` (drops empty text, merges consecutive identical texts into one fragment spanning both); `@dataclass Sentence(id: int, start: float, end: float, en: str)` where `end` = next sentence's start (last: last fragment end); `group_sentences(frags) -> list[Sentence]` (sentence ends at a fragment whose text ends with `.`, `?`, `!`, `…`); `syllables(text: str) -> int` (whitespace tokens with a letter/digit; `*` and `|` ignored); `budget(s: Sentence, rate: float) -> int` = `floor((s.end - s.start) * rate * 0.95)`; `check_script(sentences, script: list[dict], rate: float) -> list[str]` (problems, Vietnamese messages).
- `textfit.py` produces `text_width(text: str, em: int = 40) -> float` (PIL `getlength` with ExtraBold at size `em`, `*`/`|` stripped) — reused by Task 7.
- Script file `script.vi.json` schema (written by the translator agent): `[{"id": 1, "phrases": "Cụm một | cụm hai", "note": ""}]`; `note` non-empty when the Vietnamese departs from the English (why).

`check_script` problems: missing/extra ids; first sentence contains `|`; any phrase of a later sentence wider than `MAX_TEXT_W = 620` at em 40; `syllables(phrases) > budget(sentence, rate)`; unbalanced `*`.

- [ ] **Step 1: Write failing tests:**

```python
def test_merge_drops_ui_label_and_scene_cut_duplicate():
    fr = [Fragment(0, 0, 1, 900, 960), Fragment(1, 1, 1.1, 900, 960), Fragment(2, 1.1, 2, 900, 960),
          Fragment(3, 2, 2.2, 900, 960)]
    out = merge_text(fr, {0: "It starts", 1: "on a page.", 2: "on a page.", 3: ""})
    assert [(f.start, f.end, f.text) for f in out] == [(0, 1, "It starts"), (1, 2, "on a page.")]

def test_group_sentences_windows():
    fr = [Fragment(0, 0, 1, 0, 0, "Imagine"), Fragment(1, 1, 2, 0, 0, "this."), Fragment(2, 2, 3.5, 0, 0, "Update now!")]
    s = group_sentences(fr)
    assert [(x.start, x.end, x.en) for x in s] == [(0, 2, "Imagine this."), (2, 3.5, "Update now!")]

def test_budget_and_syllables():
    assert syllables("Đó là tấn công | *Zero-click.*") == 5
    assert budget(Sentence(1, 0.0, 2.0, "x"), rate=5.0) == 9

def test_check_script_reports_problems():
    s = [Sentence(1, 0, 3, "a"), Sentence(2, 3, 4, "b")]
    probs = check_script(s, [{"id": 1, "phrases": "Câu đầu | bị chia", "note": ""},
                             {"id": 2, "phrases": "một hai ba bốn năm sáu bảy tám chín mười", "note": ""}], rate=5.0)
    assert any("câu đầu" in p.lower() for p in probs) and any("quá dài" in p for p in probs)
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: sentences and script checks`.

### Task 4: Scene cuts and clean plates

**Files:**
- Create: `~/video-pipeline/vshort/plates.py`
- Test: `~/video-pipeline/tests/test_plates.py`

**Interfaces:**
- Consumes: `iter_frames`, `frame_at` (Task 1); `Fragment` (Task 2).
- Produces: `scene_cuts(video: Path) -> list[float]` (frame times where 180×320 grey mean-abs-diff to previous frame > 25); `@dataclass Plate(name: str, x: int, y: int, start: float, end: float, method: str, moving: bool)` (`method` ∈ `"clean"`, `"lama"`); `build_plates(video: Path, frags: list[Fragment], out_dir: Path, lama_path: Path, cover: tuple[int,int] = (1094, 1204), inpaint: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None) -> list[Plate]` (`inpaint(img_rgb, mask) -> img_rgb`; default loads LaMa from `lama_path`) — writes `out_dir/<name>.png` (patch only) and `out_dir/plates.json`.

Rules: a fragment needs a plate only if its band `(y0, y1)` is not inside `cover`. Group such fragments by scene window (cuts) and band. For each group: x-range = text columns (prototype `text_columns`) ± 26 px; source = a frame inside the same scene window whose band has no caption ink (`method="clean"`), else LaMa on the window's middle frame with context rows `y0-244 … y1+224` rounded to multiples of 8 (`method="lama"`). `moving` = mean-abs-diff between window start/mid/end frames outside the band > 3.0. Plate window = the scene window ∩ [first fragment start, last fragment end] of the group.

- [ ] **Step 1: Write failing tests** (LaMa replaced by a stub callable injected via `build_plates(..., inpaint=fn)` keyword, default loads the TorchScript model):

```python
def test_scene_cuts(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    assert [round(t, 2) for t in scene_cuts(v)] == [1.0]

def test_clean_frame_preferred_and_cover_band_skipped(make_video, tmp_path):
    caps = [(0.0, 1.5, 930, "Top caption"), (1.5, 2.0, 1150, "Low caption")]  # 1.5-2.0: band 930 clean
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda *a: 1/0)
    assert len(plates) == 1 and plates[0].method == "clean" and plates[0].start == 0.0

def test_lama_used_and_moving_flagged(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "moving")], captions=[(0, 1, 930, "Always on"), (1, 2, 930, "Still here")])
    calls = []
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"),
                          inpaint=lambda img, mask: calls.append(1) or img)
    assert calls and plates[0].method == "lama" and plates[0].moving
```


- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (LaMa call as in `prototype/plates.py`). **Step 4:** Run → PASS.
- [ ] **Step 5: Real-video check (slow, ~1 min):** `build_plates` on the Coruna original → 5–6 plates, `update`-scene plate `method == "clean"`, none `moving`; eyeball `plates/*.png` (no caption letters left).
- [ ] **Step 6:** Commit `feat: scene cuts and clean plates`.

### Task 5: Gemini TTS with cache and quota stop

**Files:**
- Create: `~/video-pipeline/vshort/tts.py`
- Test: `~/video-pipeline/tests/test_tts.py`

**Interfaces:**
- Produces: `load_api_key(env_file: Path) -> str` (env `GEMINI_API_KEY` first, else `KEY=VALUE` lines of the file; raises `RuntimeError("Không tìm thấy GEMINI_API_KEY")` — message never contains a key); `class QuotaExceeded(Exception)`; `class Speaker(Protocol): def __call__(self, text: str) -> bytes` (returns WAV bytes); `gemini_speaker(api_key: str, model: str, voice: str) -> Speaker`; `@dataclass Clip(id: int, path: Path, duration: float)`; `synth_all(lines: list[tuple[int, str]], out_dir: Path, speak: Speaker, tag: str) -> list[Clip]` (file name `<id>-<sha1(tag+text)[:10]>.wav`; existing file = cached, no call); `measured_rate(clips: list[Clip], lines) -> float` (total syllables / total seconds).

`gemini_speaker`: `client.models.generate_content(model=model, contents=text, config=GenerateContentConfig(response_modalities=["AUDIO"], speech_config=SpeechConfig(voice_config=VoiceConfig(prebuilt_voice_config=PrebuiltVoiceConfig(voice_name=voice)), language_code="vi")))`; take the first `part.inline_data`; if its `mime_type` is raw PCM (`audio/L16…` / `audio/pcm…`) wrap with `wave` (mono, 16-bit, rate from `rate=` in the mime type, default 24000). Map HTTP 429 / `RESOURCE_EXHAUSTED` to `QuotaExceeded`. Text is sent as-is (style comes from the voice); no instruction text is prepended.

- [ ] **Step 1: Write failing tests:**

```python
def test_cache_skips_existing(tmp_path):
    calls = []
    speak = lambda text: calls.append(text) or wav_bytes(1.0)
    synth_all([(1, "Xin chào bạn")], tmp_path, speak, tag="v1")
    clips = synth_all([(1, "Xin chào bạn")], tmp_path, speak, tag="v1")
    assert len(calls) == 1 and abs(clips[0].duration - 1.0) < 0.01

def test_quota_stops_and_keeps_finished(tmp_path):
    def speak(text):
        if text == "hai": raise QuotaExceeded()
        return wav_bytes(0.5)
    with pytest.raises(QuotaExceeded):
        synth_all([(1, "một"), (2, "hai"), (3, "ba")], tmp_path, speak, tag="t")
    assert len(list(tmp_path.glob("1-*.wav"))) == 1 and not list(tmp_path.glob("2-*.wav"))

def test_load_api_key_never_leaks(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OTHER=1\nGEMINI_API_KEY=secret123\n")
    assert load_api_key(tmp_path / ".env") == "secret123"
    with pytest.raises(RuntimeError) as e:
        load_api_key(tmp_path / "missing.env")
    assert "secret" not in str(e.value)
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Live smoke (1 API call):** list models whose name contains `tts` (`client.models.list()`), confirm `config.toml`'s `tts_model` exists (else set the newest flash TTS model shown) and synthesize "Xin chào, đây là giọng đọc thử." → WAV of 1–4 s. Print only model names and duration.
- [ ] **Step 6:** Commit `feat: gemini tts with cache`.

### Task 6: Timing fit and narration track

**Files:**
- Create: `~/video-pipeline/vshort/fit.py`
- Test: `~/video-pipeline/tests/test_fit.py`

**Interfaces:**
- Consumes: `Sentence` (Task 3), `Clip` (Task 5), `syllables` (Task 3).
- Produces: `@dataclass Placement(id: int, start: float, dur: float, tempo: float, overflow: float)`; `place(sentences, clips, cut: float, max_tempo: float = 1.10) -> list[Placement]` — start = sentence start (but ≥ previous end + 0.1); available = next sentence start (last: `cut`) − start; `tempo = min(max(1.0, clip/available), max_tempo)`; `dur = clip / tempo`; `overflow = max(0, start + dur − next_start)`; `too_long(placements, tol: float = 0.25) -> list[int]` (ids with overflow > tol); `build_narration(placements, clips, total: float, out_wav: Path)` (ffmpeg `atempo` per clip when tempo > 1, numpy mix into silence of length `total` at 24 kHz); `phrase_times(placements, script: list[dict]) -> list[tuple[float, float, str]]` — first sentence one entry; others split on `|`, each phrase's span proportional to its syllables within `[start, start+dur]`; then each entry's end = next entry's start (no gaps), first entry starts at 0.0, last ends at `placements[-1].start + dur`.

- [ ] **Step 1: Write failing tests:**

```python
S = [Sentence(1, 0.0, 3.0, "a"), Sentence(2, 3.0, 5.0, "b")]

def test_place_tempo_capped_and_overflow():
    clips = [Clip(1, Path("x"), 2.0), Clip(2, Path("y"), 2.6)]
    p = place(S, clips, cut=5.0)
    assert p[0].tempo == 1.0 and abs(p[1].tempo - 1.10) < 1e-9
    assert abs(p[1].overflow - (2.6 / 1.10 - 2.0)) < 1e-6 and too_long(p) == [2]

def test_next_sentence_waits_for_spill():
    clips = [Clip(1, Path("x"), 3.6), Clip(2, Path("y"), 1.0)]
    p = place(S, clips, cut=6.0)
    assert p[1].start >= p[0].start + p[0].dur + 0.1 - 1e-9

def test_phrase_times_contiguous():
    p = [Placement(1, 0.5, 2.0, 1.0, 0.0), Placement(2, 3.0, 1.0, 1.0, 0.0)]
    out = phrase_times(p, [{"id": 1, "phrases": "Câu đầu trọn vẹn"}, {"id": 2, "phrases": "một hai | ba bốn"}])
    assert out[0][0] == 0.0 and out[0][2] == "Câu đầu trọn vẹn"
    assert [round(x[0], 2) for x in out[1:]] == [3.0, 3.5] and out[0][1] == out[1][0]
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: timing fit and narration`.

### Task 7: Render (title, subtitles, plates, watermark, cut, new voice)

**Files:**
- Create: `~/video-pipeline/vshort/render.py`
- Test: `~/video-pipeline/tests/test_render.py`

**Interfaces:**
- Consumes: `text_width` (Task 3), `Plate` (Task 4), `phrase_times` output (Task 6), `scene_cuts` (Task 4), `Fragment` (Task 2).
- Produces: `build_ass(phrases: list[tuple[float,float,str]], kicker: str, title: str, cut: float) -> str` (layout exactly as `prototype/render.py` v4: balanced wrap for the whole first sentence, single line otherwise, box bottom `SUB_BOTTOM`, `fs(em) = round(em / EM)`); `outro_cut(frags: list[Fragment], cuts: list[float], duration: float) -> float` (first scene cut ≥ last fragment end; else `duration`); `compose(src: Path, narration: Path, ass: Path, plates: list[Plate], plates_dir: Path, cut: float, out: Path) -> None` (filtergraph: `delogo` → overlays with `enable='between(t,start,end)'` → `ass` with `fontsdir=assets/fonts`; `-t cut`; audio = narration with 0.25 s fade-out; libx264 crf 18, aac 128k, `+faststart`).

- [ ] **Step 1: Write failing tests:**

```python
def test_build_ass_layout():
    a = build_ass([(0, 2, "Câu mở đầu dài dài dài dài dài dài dài dài dài dài dài dài dài dài"), (2, 3, "*Zero-click.*")],
                  "CORUNA & DARKSWORD", "iPhone bị hack chỉ vì mở 1 trang web", cut=3.0)
    assert "Style: Cap,Be Vietnam Pro ExtraBold,61," in a          # fs(40)
    assert "{\\1c&H00D4FF&}Zero-click." in a
    assert a.count("Dialogue: 2,0:00:00.00,0:00:02.00,Cap") >= 2     # first sentence wraps to ≥2 lines

def test_outro_cut():
    assert outro_cut([Fragment(0, 0, 57.13, 0, 0, "x")], [10.2, 57.3], 60.35) == 57.3
    assert outro_cut([Fragment(0, 0, 50.0, 0, 0, "x")], [10.2], 60.0) == 60.0

def test_compose_output(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 3, "#F3EFE6")], captions=[])
    wav = tmp_path / "n.wav"; write_silence(wav, 3.0)
    ass = tmp_path / "s.ass"; ass.write_text(build_ass([(0, 2.5, "Xin chào")], "K", "Tiêu đề", 2.5), encoding="utf-8")
    out = tmp_path / "o.mp4"
    compose(v, wav, ass, [], tmp_path, cut=2.5, out=out)
    p = probe(out)
    assert abs(p.duration - 2.5) < 0.1 and frame_at(out, 1.0)[1150, 150].max() < 40   # dark sub box (x 120-600), clear of the text
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (port `prototype/render.py`, drop the Coruna-specific `SUBS`/`FRAGS`/iOS patch). **Step 4:** Run → PASS. **Step 5:** Commit `feat: render`.

### Task 8: Run folder, state and CLI

**Files:**
- Create: `~/video-pipeline/vshort/run.py`, `~/video-pipeline/vshort/cli.py`
- Test: `~/video-pipeline/tests/test_cli.py`

**Interfaces:**
- Consumes: everything above; `config.toml`.
- Produces: `Run(path: Path)` with `.state: dict` persisted in `state.json`, `.done(step: str) -> bool`, `.mark(step: str)`; files in the run folder: `run.json` (`slug`, `notebook_id`, `kicker`, `title`), `brief.vi.md`, `brief.en.md`, `sources.md`, `source.mp4`, `fragments.json`, `sheets/`, `fragments_text.json` (`{"<i>": "text"}`), `sentences.en.json`, `script.vi.json`, `tts/`, `narration.wav`, `placements.json`, `plates/`, `subs.ass`, `final.mp4`, `review.md`.
- CLI `vshort <cmd> <run_dir>`; exit 0 ok, 2 bad input (message lists problems), 3 too-long sentences (prints ids), 4 NotebookLM auth, 75 quota:
  - `new <slug> --kicker K --title T` → creates run folder + run.json.
  - `fetch <run> --notebook ID` → `notebooklm generate video -n ID --format short --language en --no-wait --json`, `artifact wait <task> -n ID --timeout 2400`, `download video -n ID <run>/source.mp4`; output containing "Not logged in"/auth error → exit 4 with the re-login hint.
  - `detect <run>` → fragments.json + sheets/.
  - `text <run>` → reads fragments_text.json → sentences.en.json; prints each sentence with window seconds and syllable budget (rate from config).
  - `check <run>` → `check_script`; exit 2 with problems.
  - `plates <run>`, `tts <run>` (updates `syllables_per_sec` in config.toml from `measured_rate` after ≥ 5 clips), `fit <run>` (writes placements.json, narration.wav; exit 3 if `too_long`), `render <run>` (subs.ass + final.mp4), `status <run>`.

- [ ] **Step 1: Write failing tests** (subprocess calls to `notebooklm` go through `vshort.cli.run_notebooklm(args) -> CompletedProcess`, monkeypatched):

```python
def test_fetch_auth_error_exit_4(tmp_path, monkeypatch, capsys):
    main(["new", "demo", "--kicker", "K", "--title", "T", "--runs-dir", str(tmp_path)])
    monkeypatch.setattr(cli, "run_notebooklm", lambda a: CompletedProcess(a, 1, "", "Not logged in."))
    assert main(["fetch", str(tmp_path / "demo"), "--notebook", "abc"]) == 4
    assert "scp storage_state.json" in capsys.readouterr().err

def test_state_resume(tmp_path):
    r = Run(tmp_path); r.mark("detect")
    assert Run(tmp_path).done("detect") and not Run(tmp_path).done("tts")

def test_check_exit_2(tmp_path):
    (tmp_path / "sentences.en.json").write_text('[{"id": 1, "start": 0, "end": 1, "en": "Hi."}]')
    (tmp_path / "script.vi.json").write_text('[{"id": 1, "phrases": "một hai ba bốn năm sáu bảy tám", "note": ""}]')
    assert main(["check", str(tmp_path)]) == 2
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (argparse). **Step 4:** Run full suite `uv run pytest -q` → PASS. **Step 5:** Commit `feat: run state and cli`.

### Task 9: Skill and subagents

**Files:**
- Create: `~/.claude/skills/video-short/SKILL.md`, `~/.claude/agents/vs-researcher.md`, `~/.claude/agents/vs-transcriber.md`, `~/.claude/agents/vs-translator.md`, `~/.claude/agents/vs-reviewer.md`

**Interfaces:**
- Consumes: the `vshort` CLI (Task 8) via `cd ~/video-pipeline && uv run vshort …`; notebooklm CLI.
- Agent frontmatter: researcher, transcriber, translator `model: sonnet`; reviewer `model: opus`. Tools: researcher `WebSearch, Bash, Read, Write`; transcriber `Read, Write`; translator `Read, Write, Bash`; reviewer `Read, Bash, Write`.

SKILL.md flow (each line = one orchestrator action):
1. `vs-researcher`: research (primary reports first), create notebook `"<Chủ đề> – Video Short"`, add sources, write `brief.vi.md` (Tai's template, see `prototype/brief_c01.md`), `brief.en.md` (faithful English), `sources.md`, propose kicker + title.
2. **Show brief + title to Tai; wait for approval or edits. This is the only stop.**
3. `vshort new` → add `brief.en.md` as text source → `vshort fetch`.
4. `vshort detect` → `vs-transcriber` reads `sheets/*.png`, writes `fragments_text.json` (exact English; non-caption UI text → `""`) → `vshort text`.
5. `vs-translator` gets `sentences.en.json` (with budgets), `brief.vi.md`, `sources.md`; writes `script.vi.json` following Global Constraints (brief wins on conflicts, `note` explains each departure, Vietnamese iOS menu labels, phrases never split a word); loop `vshort check` until exit 0.
6. `vshort plates` (can run in background during 5).
7. `vshort tts` (exit 75 → tell Tai quota ran out, how to resume, stop) → `vshort fit`; exit 3 → translator shortens only those ids, `vshort check`, `vshort tts`, `vshort fit`; max 2 rounds, then continue and report.
8. `vshort render` → `vs-reviewer`: samples frames every 0.5 s around cuts and phrase changes, confirms no old caption visible, subtitle text = script, lists picture-vs-script mismatches and all `note`s, writes `review.md`.
9. Reply to Tai: path of `final.mp4`, the `scp tai@pve2:… ~/Downloads/` command (Mac terminal, no `!`), summary of `review.md`.

- [ ] **Step 1:** Write the five files. **Step 2: Verify:** `claude` lists `/video-short` and the four agents (start a fresh session, `/agents`), and SKILL.md commands match `uv run vshort --help`. **Step 3:** Commit agent/skill copies into `~/video-pipeline/claude/` (`cp`), `git commit -m "feat: video-short skill and agents"`.

### Task 10: Acceptance run

- [ ] **Step 1:** Run `/video-short "Phân tích kỹ thuật bộ công cụ khai thác Zero-Click Coruna và DarkSword trên iOS"` reusing notebook `2d87bbc0` (researcher may skip research and adapt brief C01). Tai approves the brief.
- [ ] **Step 2:** Expected: `~/notebooklm-videos/<slug>/final.mp4` 720×1280, Vietnamese voice, no English caption visible (reviewer check), subtitles fixed at the bottom, title bar, no watermark, no Gemini outro, `review.md` lists every `note`. Count Gemini TTS calls ≤ sentences + re-synth count.
- [ ] **Step 3:** Hand `final.mp4` to Tai with the scp command; collect feedback for a follow-up plan.
