# Hình động một khung, dựng từ brief — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đoạn cơ chế thành một khung hình liền mạch A→Z, vẽ theo nhịp từ brief (chạy song song lúc NotebookLM gen), dùng thư viện hình nét tay lớn dần qua các video; sau khi duyệt bản dịch chỉ còn gắn nhịp vào câu.

**Architecture:** `motion.json` đổi sang dạng mới: **một** cảnh gồm `things` + `beats` (nhịp), không có mốc câu — agent viết từ brief. File thứ hai `motion.bind.json` (viết sau khi có `script.vi.json`) gắn mỗi nhịp vào một mốc `{line, phrase, at}` hoặc bỏ nhịp. `vshort motion RUN --design` kiểm bản thiết kế với thời gian ước lượng (3 s/nhịp); `vshort motion RUN` kiểm cả hai file rồi ghép. `motion.timed()` trả về đúng một `Scene` như hiện nay, nên `render.py` gần như không đổi. Hình mới là dữ liệu nét (`kind: "shape"`), không phải mã: `vshort/shapes.py` đọc/kiểm/thu nhỏ vào hộp; `kit` vẽ bằng `_stroke` sẵn có. `auto.py` chạy agent thiết kế trong một luồng song song với `fetch…translate`, gọi agent gắn nhịp trong `_build`, và cuối run commit + push `assets/shapes/`.

**Tech Stack:** Python 3.12, Pillow, numpy, pytest, git CLI. Không thêm thư viện.

**Spec:** `docs/superpowers/specs/2026-11-02-hinh-dong-mot-khung-design.md`

## Global Constraints

- Đoạn cơ chế là **một cảnh**; không có `scenes` nhiều cảnh nữa. Dạng `motion.json` cũ bỏ hẳn; hai ví dụ trong `examples/motion/` chuyển sang dạng mới.
- Tối đa **7** thứ được đếm cùng hiện (`MAX_SEEN = 7`; cách đếm giữ như cũ: `path`, `crack`, `dot` không nhãn không tính). Tối đa **6** nhịp (`MAX_BEATS`). Tối thiểu **2** nhịp còn lại sau khi gắn, nếu không thì dùng ảnh tĩnh.
- Một chấm đỏ `actor` (bắt buộc, `kind: "dot"`) vẽ ở nhịp 1, không được `hide` hay `move` có `vanish`: nó đi xuyên suốt đoạn.
- Thứ của các nhịp trước **lùi lại** khi nhịp sau không nhắc tới nó: màu pha về giấy (`DIM = 0.55`), cỡ và vị trí giữ nguyên (để kiểm chồng hình vẫn đúng). Nhịp nào nhắc lại (có act trên nó) thì nó sáng lại. `actor` không bao giờ lùi.
- Vùng an toàn mới `kit.SAFE = (40, 96, 680, 1050)`: tránh logo góc trên phải (x 481–704, y 24–80).
- Hình thư viện: `assets/shapes/<slug>.json` = `{"name": "<tên tiếng Việt>", "strokes": [[[x, y], …], …]}`, tọa độ trong ô 0–100; 1–12 nét, mỗi nét 2–40 điểm. Slug `[a-z0-9-]+`. Không có chữ trong hình.
- Thư viện **chỉ thêm**: hình mới của run nằm ở `RUN/shapes/<slug>.json`; trùng slug với thư viện mà khác nội dung là lỗi ("đặt tên mới"). Mỗi run chép mọi hình nó dùng vào `RUN/shapes/`.
- Cuối run (`_finish`): chép hình mới của run vào `assets/shapes/`, `git add assets/shapes`, commit **chỉ** đường dẫn đó, `git pull --rebase --autostash`, `git push`. Lỗi git không làm hỏng video: thêm một dòng vào lời nhắn cuối.
- Không thêm điểm dừng duyệt. Agent `vs-motion` giữ `model: sonnet`, làm cả hai việc (thiết kế, gắn nhịp) bằng hai lời giao khác nhau.
- Luật an toàn và luật nhãn giữ nguyên. Lúc thiết kế, chữ hợp lệ = chữ trong `brief.vi.md` + `COMMON`; lúc gắn, chữ hợp lệ = chữ lời đọc của `lines` + `COMMON`. Nhãn trượt thì `motion.bind.json` được đổi nhãn qua `"labels": {"<id>": "<nhãn mới>"}`.
- Test không gọi `claude`, NotebookLM hay `git push` thật.

## Review Focus

- NotebookLM đọc các bước khác thứ tự brief: mốc các nhịp giữ lại phải tăng dần theo thời gian, nếu không thì `vshort motion` báo lỗi để agent bỏ nhịp lệch → test `test_bind_rejects_out_of_order_beats` ở Task 3.
- NotebookLM bỏ hẳn một bước: nhịp bị bỏ, thứ của nhịp đó hiện cùng nhịp giữ lại kế tiếp (không hiện trước lời) → test `test_dropped_beat_things_appear_with_next_beat` ở Task 3.
- Run cũ còn `motion.json` dạng nhiều cảnh (video dở từ trước bản này): `vshort motion` báo một dòng rõ ràng "dạng cũ", không traceback → test `test_old_format_is_rejected_plainly` ở Task 2.
- Thiết kế xong nhưng agent chưa kịp chạy khi run dừng duyệt bản dịch: luồng thiết kế phải được chờ xong trước khi dừng, không bị bỏ dở → test `test_design_runs_alongside_fetch_and_finishes_before_script_stop` ở Task 5.
- `git push` lỗi (mất mạng, xung đột): video vẫn xong, lời nhắn cuối nói rõ hình chưa lên repo → test `test_shape_publish_failure_is_reported_not_fatal` ở Task 5.

---

### Task 1: Thư viện hình và kiểu `shape` trong kit

**Files:**
- Create: `vshort/shapes.py`
- Modify: `vshort/kit.py` (`SAFE`, `BOXED`, `_shape`, thêm `DIM`)
- Create: `tests/test_shapes.py`
- Modify: `tests/test_kit.py`
- Create: `assets/shapes/.gitkeep`

**Interfaces:**
- Produces:
  - `shapes.LIBRARY: Path` = `<repo>/assets/shapes`
  - `shapes.problems(doc, slug: str) -> list[str]` — lỗi của một file hình (tiếng Việt, mỗi lỗi một dòng).
  - `shapes.find(slug: str, run_dir: Path | None) -> dict | None` — `RUN/shapes/<slug>.json` trước, rồi thư viện.
  - `shapes.check_run(run_dir: Path) -> list[str]` — kiểm mọi hình trong `RUN/shapes/`, gồm luật chỉ thêm (trùng slug thư viện mà khác nội dung).
  - `shapes.strokes_in_box(doc: dict, box) -> list[list[tuple[float, float]]]` — thu ô 0–100 vào `box`, giữ tỉ lệ, căn giữa.
  - `shapes.sheet(run_dir: Path) -> Image.Image` — mỗi hình mới của run vẽ trong ô 240×240 kèm tên, để agent xem.
  - kit: `"shape"` thuộc `BOXED`; thing `{"kind": "shape", "shape": "<slug>", "box": [...], "strokes": [...]}` (`strokes` đã thu vào hộp, do `motion` điền trước khi vẽ). Nhãn nằm trên khung như `server`.
  - `kit.DIM = 0.55`, `kit.SAFE = (40, 96, 680, 1050)`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_shape_file_rules():
    ok = {"name": "bộ nhớ", "strokes": [[[10, 10], [90, 10], [90, 90]]]}
    assert shapes.problems(ok, "bo-nho") == []
    assert shapes.problems(ok, "Bộ Nhớ")                                   # slug sai
    assert shapes.problems({"name": "x", "strokes": []}, "x")              # 0 nét
    assert shapes.problems({"name": "x", "strokes": [[[0, 0]]] * 13}, "x")  # 13 nét, nét 1 điểm
    assert shapes.problems({"name": "x", "strokes": [[[0, 0], [101, 5]]]}, "x")  # ra ngoài ô

def test_run_shape_cannot_change_library_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(shapes, "LIBRARY", tmp_path / "lib")
    (tmp_path / "lib").mkdir(); (tmp_path / "run" / "shapes").mkdir(parents=True)
    a = {"name": "nhân", "strokes": [[[0, 0], [100, 100]]]}
    (tmp_path / "lib" / "nhan.json").write_text(json.dumps(a))
    (tmp_path / "run" / "shapes" / "nhan.json").write_text(json.dumps(a | {"strokes": [[[0, 100], [100, 0]]]}))
    assert any("đặt tên mới" in p for p in shapes.check_run(tmp_path / "run"))

def test_strokes_fit_box_keeping_aspect():
    pts = shapes.strokes_in_box({"name": "x", "strokes": [[[0, 0], [100, 50]]]}, [100, 100, 300, 400])
    xs, ys = zip(*pts[0])
    assert min(xs) == 100 and max(xs) == 300 and max(ys) - min(ys) == 100  # rộng 200, cao 100, căn giữa dọc
```

`tests/test_kit.py` thêm: một thing `shape` với `strokes` được vẽ ra (khung khác giấy trong hộp) và `kit.SAFE[1] == 96`.

- [ ] **Step 2: Chạy, xác nhận hỏng** — `uv run pytest tests/test_shapes.py tests/test_kit.py -q` → FAIL (`No module named 'vshort.shapes'`).
- [ ] **Step 3: Viết `vshort/shapes.py` và sửa `kit`** theo Interfaces. `_shape` với `kind == "shape"` trả `[(pts, 3, 0) for pts in thing["strokes"]]`. Sheet dùng `kit._stroke` trên `kit._paper()`.
- [ ] **Step 4: Chạy lại** — cùng lệnh → PASS; `uv run pytest -q` toàn bộ vẫn qua (ví dụ cũ còn nằm trong SAFE mới: hộp sớm nhất của coruna có y0 = 170).
- [ ] **Step 5: Commit** — `git add vshort/shapes.py vshort/kit.py tests/test_shapes.py tests/test_kit.py assets/shapes/.gitkeep && git commit -m "feat: shape library of hand-drawn strokes; kit draws kind shape; safe area clears the top-right logo"`

### Task 2: `motion.json` dạng nhịp — kiểm thiết kế và xem trước

**Files:**
- Modify: `vshort/motion.py` (thay `validate`/`timed`/`sheet`/`estimate` cũ; bỏ `MAX_SCENES`; `MAX_SEEN = 7`)
- Modify: `tests/test_motion.py` (viết lại)

**Interfaces:**
- Consumes: `shapes.find`, `shapes.strokes_in_box`, `kit.Act`, `kit.draw`.
- Produces — định dạng `motion.json`:

```json
{"note": "…", "idea": "một câu: cả khung nói gì", "actor": "atk",
 "things": [{"id": "srv", "kind": "server", "box": [...], "label": "máy chủ", "beat": 1, "at": 0.2}, …],
 "beats": [{"idea": "gói tin tới máy chủ",
            "acts": [{"do": "move", "thing": "atk", "path": "wire", "at": 0.5, "dur": 1.2}]}, …]}
```

  `beat` là số thứ tự nhịp (đếm từ 1) lúc thing bắt đầu vẽ; `at` 0–1 trong nhịp (mặc định 0). Act nằm trong nhịp của nó, `at` 0–1. Các trường thing/act khác giữ như cũ (`to`, `path`, `say`, `vanish`, `dur`, `color`, `url`, `icon`, `arrow`).
  - `motion.design_problems(doc, said: set[str], run_dir: Path | None) -> list[str]` — mọi lỗi của thiết kế; `[]` khi qua. Gồm kiểm thing/act cũ, `actor`, số nhịp 1–6, hình `shape` tìm được, và `_order_problems` trên thời gian ước lượng.
  - `motion.brief_words(brief_md: str) -> set[str]`
  - `motion.timed(doc, starts: list[float | None], end: float, run_dir: Path | None) -> Scene` — `starts[k]` là giây bắt đầu nhịp `k+1` (`None` = nhịp bị bỏ), `end` là giây hết đoạn. Thêm act `dim`/`undim` tự động theo luật Global Constraints. Điền `strokes` cho thing `shape`.
  - `motion.estimated(doc) -> tuple[list[float], float]` — nhịp k bắt đầu ở `3.0 * k`, hết ở `3.0 * len(beats)` (`BEAT_EST = 3.0`).
  - `motion.design_sheet(doc, run_dir) -> Image.Image` — một hàng, mỗi cột là khung cuối mỗi nhịp (thời gian ước lượng): đọc trái sang phải thấy A→Z.
  - kit: `Act.do` thêm `"dim"`; `_draw_thing` pha màu (cả nét lẫn nhãn) về `PAPER` theo `DIM` khi đang lùi.

- [ ] **Step 1: Viết test hỏng** (dùng một thiết kế mẫu 3 nhịp trong test: `atk` dot đỏ, `srv` server, `mem` shape `bo-nho` từ `tmp_path/shapes`)

```python
def test_design_ok_and_actor_rules(design, tmp_path):
    assert motion.design_problems(design, WORDS, tmp_path) == []
    bad = design | {"beats": design["beats"] + [{"idea": "x", "acts": [{"do": "hide", "thing": "atk", "at": 0}]}]}
    assert any("actor" in p for p in motion.design_problems(bad, WORDS, tmp_path))

def test_more_than_seven_things_is_clutter(design, tmp_path): ...   # 8 box có nhãn → lỗi "tối đa 7"
def test_more_than_six_beats_rejected(design, tmp_path): ...
def test_unknown_shape_rejected(design, tmp_path): ...               # "shape": "khong-co" → lỗi nêu slug
def test_label_word_outside_brief_rejected(design, tmp_path): ...

def test_old_format_is_rejected_plainly(tmp_path):
    probs = motion.design_problems({"lines": [1], "note": "n", "scenes": []}, WORDS, tmp_path)
    assert probs == ["motion.json dạng cũ (scenes): viết lại theo dạng nhịp (beats)"]

def test_earlier_beat_dims_and_comes_back(design, tmp_path):
    sc = motion.timed(design, [0.0, 3.0, 6.0], 9.0, tmp_path)
    dims = [(a.do, a.thing) for a in sc.acts if a.do in ("dim", "undim")]
    assert ("dim", "srv") in dims and ("undim", "srv") in dims   # nhịp 3 có act "red" trên srv
    assert all(t != "atk" for _, t in dims)

def test_design_sheet_has_one_column_per_beat(design, tmp_path):
    img = motion.design_sheet(design, tmp_path)
    assert img.width > 3 * motion.SHEET_W
```

- [ ] **Step 2: Chạy, xác nhận hỏng** — `uv run pytest tests/test_motion.py -q` → FAIL.
- [ ] **Step 3: Viết lại các hàm trong `vshort/motion.py`** theo Interfaces. Tái dùng `_thing_problems`/`_act_problems` (đổi tham số mốc: không còn `_cue_problems`, thay bằng kiểm `beat` 1..n và `at` 0–1). `dim` là act từ đầu nhịp không nhắc tới thing, kéo `kit.TURN` giây; `undim` khi nhịp sau nhắc lại.
- [ ] **Step 4: Chạy lại** — `uv run pytest tests/test_motion.py tests/test_kit.py -q` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: motion.json is one canvas of beats written from the brief; earlier beats dim, the red actor runs through"`

### Task 3: Gắn nhịp vào lời — `motion.bind.json`

**Files:**
- Modify: `vshort/motion.py`
- Modify: `tests/test_motion.py`

**Interfaces:**
- Consumes: Task 2.
- Produces — định dạng `motion.bind.json`:

```json
{"lines": [4, 5, 6, 7, 8], "note": "…",
 "beats": [{"line": 4, "phrase": 1}, {"line": 5, "phrase": 2, "at": 0.3}, null, …],
 "labels": {"bug": "lỗi"}}
```

  Một phần tử mỗi nhịp, đúng thứ tự; `null` = bỏ nhịp.
  - `motion.bind_problems(doc, bind, script: list[dict], run_dir, visuals: list | None = None) -> list[str]` — luật `lines` cũ (liền nhau, không câu tiêu đề, không quá nửa video, va chạm visuals), số phần tử = số nhịp, mỗi mốc nằm trong `lines`, nhịp giữ lại đầu tiên ở câu `lines[0]` cụm 1, các mốc tăng dần, còn ≥ 2 nhịp, nhãn (sau khi áp `labels`) qua kiểm chữ lời đọc.
  - `motion.bound(doc, bind) -> dict` — thiết kế đã áp `labels`, kèm `lines` của bind (để `cli`/`render`/`visuals.clashes` dùng như `doc["lines"]` cũ).
  - `motion.bind_timed(doc, bind, placements: list[Placement], script, run_dir) -> Scene` — đổi mốc ra giây bằng `phrase_fracs` như cũ rồi gọi `timed`; `end` = hết câu cuối của `lines`. `Scene.lines` = `bind["lines"]`.
  - `motion.bind_sheet(doc, bind, script, run_dir) -> Image.Image` — như `design_sheet` nhưng theo `estimate(script)`.
  - `motion.estimate(script)` giữ nguyên.

- [ ] **Step 1: Viết test hỏng**

```python
def test_bind_ok(design, script, tmp_path): assert motion.bind_problems(design, BIND, script, tmp_path) == []

def test_bind_rejects_out_of_order_beats(design, script, tmp_path):
    b = BIND | {"beats": [{"line": 4}, {"line": 6}, {"line": 5}]}
    assert any("tăng dần" in p for p in motion.bind_problems(design, b, script, tmp_path))

def test_fewer_than_two_beats_left_is_an_error(design, script, tmp_path): ...   # [ {line 4}, null, null ]

def test_dropped_beat_things_appear_with_next_beat(design, script, tmp_path):
    b = BIND | {"beats": [{"line": 4}, None, {"line": 6}]}
    sc = motion.bind_timed(design, b, estimate(script), script, tmp_path)
    t_beat3 = ...  # giây của câu 6 cụm 1 theo estimate
    assert all(a.t0 >= t_beat3 - motion.LEAD_IN for a in sc.acts if a.thing in BEAT2_THINGS and a.do == "draw")
    assert not [a for a in sc.acts if a in BEAT2_ACTS]

def test_labels_override_must_use_spoken_words(design, script, tmp_path): ...
def test_first_kept_beat_must_open_the_stretch(design, script, tmp_path): ...    # nhịp đầu ở câu 5 → lỗi
```

- [ ] **Step 2: Chạy, xác nhận hỏng.**
- [ ] **Step 3: Viết các hàm** theo Interfaces. Thứ của nhịp bị bỏ: `beat` của nó dời sang nhịp giữ lại kế tiếp (`at = 0`); thứ của nhịp bỏ ở cuối thì không vẽ, và act nhắc tới nó cũng bỏ.
- [ ] **Step 4: Chạy lại** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: motion.bind.json ties each beat to a spoken cue; out-of-order or missing steps are dropped"`

### Task 4: Lệnh `vshort motion` hai chế độ, render và hai ví dụ

**Files:**
- Modify: `vshort/cli.py` (`_motion`, `_said`, `cmd_motion`, chỗ `render` dùng `motion.timed`, parser thêm `--design`)
- Modify: `vshort/render.py` (chỉ nếu cần đổi kiểu `scenes`; `Scene` vẫn như cũ)
- Modify: `examples/motion/coruna.json`, `examples/motion/goi-tin.json`; Create: `examples/motion/coruna.bind.json`, `examples/motion/goi-tin.bind.json`
- Modify: `tests/test_cli.py`, `tests/test_render.py`; Create: `tests/test_examples.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `vshort motion RUN --design`: đọc `motion.json` + `brief.vi.md`, kiểm `shapes.check_run` và `design_problems`, ghi `RUN/motion/design.png` và `RUN/shapes/sheet.png` (nếu có hình mới); in `"<n> nhịp; ảnh để xem: …"`; mã 0/2. Không đánh dấu `motion`.
  - `vshort motion RUN`: như trên cộng `motion.bind.json` + `script.vi.json`; chép hình thư viện đã dùng vào `RUN/shapes/`; ghi `RUN/motion/sheet.png`, `motion/lines.json`; in `"1 khung, <k>/<n> nhịp, câu a–b; ảnh để xem: …"`; đánh dấu `motion`. `motion.json` là `null` → như cũ ("Không có hình động.").
  - `cli._motion(run)` trả thiết kế đã `bound()` (có `lines`) để `visuals`/`render` dùng như trước; render gọi `motion.bind_timed(...)` và có `scenes = [scene]`.

- [ ] **Step 1: Viết test hỏng** — trong `test_cli.py`: `--design` qua với thiết kế mẫu và in `"3 nhịp"`; thiếu `motion.bind.json` khi chạy không `--design` → mã 2, lỗi "thiếu motion.bind.json"; chạy đủ thì `RUN/shapes/bo-nho.json` được chép về từ thư viện. `test_examples.py`: mỗi ví dụ `examples/motion/<x>.json` + `.bind.json` + `.script.json` qua `bind_problems` và dựng được `bind_sheet`. `test_render.py`: một đoạn hai câu cùng khung không có mờ chồng ở giữa (khung giữa hai câu khác khung đầu chỉ ở chỗ đang vẽ, không pha ảnh tĩnh).
- [ ] **Step 2: Chạy, xác nhận hỏng.**
- [ ] **Step 3: Sửa `cli.py`, chuyển hai ví dụ sang dạng nhịp** (coruna: 3 cảnh cũ thành 3 nhịp trên một khung, giữ ý: điện thoại + trang web → sandbox ba tầng bị xuyên → dữ liệu bay về hacker; goi-tin: 2 nhịp). Bố cục lại cho vừa một khung và ≤ 7 thứ.
- [ ] **Step 4: Chạy lại** — `uv run pytest -q` → toàn bộ PASS. Mở `bind_sheet` của hai ví dụ (lưu vào scratchpad) và tự xem khung cuối đọc được như sơ đồ.
- [ ] **Step 5: Commit** — `git commit -m "feat: vshort motion --design checks the brief's canvas; the full check binds it to the narration; examples move to beats"`

### Task 5: `vshort auto` — thiết kế song song, gắn nhịp trong build, đưa hình lên repo

**Files:**
- Modify: `vshort/auto.py`
- Modify: `tests/test_auto.py`

**Interfaces:**
- Consumes: lệnh `vshort motion RUN --design` / `vshort motion RUN` (Task 4).
- Produces:
  - Hằng `MOTION_DESIGN` (lời giao: đọc `brief.vi.md` mục "Cơ chế từng bước" và "Lưu ý độ chính xác", viết `motion.json`, hình mới vào `RUN/shapes/`, chạy `vshort motion RUN --design` tới mã 0) và `MOTION_BIND` (đọc `motion.json`, `script.vi.json`, viết `motion.bind.json`, chạy `vshort motion RUN` tới mã 0). Bỏ `MOTION` cũ.
  - Bước `motion_design`: chạy trong `ThreadPoolExecutor(1)` ngay sau bước `source`, song song với `fetch`/`detect`/`transcribe`/`text`/`translate`; được chờ (`.result()`) trước khi `raise Stop(WAIT_SCRIPT…)` và trước `_build`. Lỗi agent ở luồng này không dừng run: ghi `motion.json` thành `null` qua `_no_motion` khi tới build.
  - `_motion(run, prompt, step)` giữ chữ ký; trong `_build` gọi với `MOTION_BIND` và step `motion_bind`. `_no_motion` đổi tên cả `motion.bind.json` → `motion.bind.loi.json`.
  - `FIX_HOW["motion"]` = "Sửa motion.json và/hoặc motion.bind.json; được thêm hình mới vào RUN/shapes/, không sửa hình đã có trong thư viện; tự chạy `vshort motion` tới khi mã 0."
  - `publish_shapes(run: Run) -> str` — chép `RUN/shapes/*.json` chưa có trong `shapes.LIBRARY` vào đó, rồi `git add assets/shapes`, `git commit -m "shapes: <slug run>: <các slug>" -- assets/shapes`, `git pull --rebase --autostash`, `git push`. Trả một dòng cho lời nhắn cuối ("Hình mới lên repo: a, b" / "Không có hình mới" / "Hình mới chưa lên repo: <lỗi git ngắn>"). Gọi git qua hàm `git(args) -> tuple[int, str]` để test thay được.
  - `_finish` thêm dòng của `publish_shapes` vào lời nhắn.

- [ ] **Step 1: Viết test hỏng** (fixture `flow` sẵn có; `Fakes.claude` cho agent `vs-motion` ghi file giả)

```python
def test_design_runs_alongside_fetch_and_finishes_before_script_stop(flow): ...
    # agent vs-motion (bước motion_design) được gọi đúng 1 lần trước WAIT_SCRIPT; state có motion_design; chạy lại không gọi lần 2
def test_build_binds_motion_with_bind_prompt(flow): ...          # lời giao chứa "motion.bind.json"; step motion_bind
def test_failed_design_falls_back_to_no_motion_at_build(flow): ...
def test_publish_shapes_commits_only_shape_files(tmp_path, monkeypatch): ...   # lệnh git nhận đúng pathspec assets/shapes
def test_shape_publish_failure_is_reported_not_fatal(flow, monkeypatch): ...   # git push mã 1 → done, lời nhắn có "chưa lên repo"
```

- [ ] **Step 2: Chạy, xác nhận hỏng** — `uv run pytest tests/test_auto.py -q`.
- [ ] **Step 3: Sửa `auto.py`** theo Interfaces; sửa các test cũ còn nhắc `MOTION`/`motion_agent`.
- [ ] **Step 4: Chạy lại** — `uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: vshort auto draws the motion canvas from the brief while NotebookLM works, binds it after translation, and pushes new shapes"`

### Task 6: Lời dặn agent và tài liệu

**Files:**
- Modify: `claude/agents/vs-motion.md` (viết lại: hai việc, dạng nhịp, thư viện hình, luật chống rối, chấm đỏ xuyên suốt, cách gắn nhịp khi NotebookLM gộp/bỏ/đảo bước)
- Modify: `claude/agents/vs-reviewer.md` (soát: một khung liền, khung cuối đọc như sơ đồ, không rối, hình mới đúng phong cách)
- Modify: `DESIGN.md` (bước hình động), `.claude/skills/video-short` không đổi (lời nhắn cuối tự có dòng hình mới).

- [ ] **Step 1:** Viết lại `vs-motion.md`: giữ mục An toàn nguyên văn; thay "Việc 2 — chia cảnh" bằng "nhịp trên một khung"; thêm "Vẽ hình mới" (ô 0–100, ≤ 12 nét, nét tay đơn giản, không chữ, xem `RUN/shapes/sheet.png`, tra `assets/shapes/` trước khi vẽ); thêm "Gắn nhịp" (một mốc mỗi nhịp, `null` để bỏ, bỏ nhịp lệch thứ tự, nhịp đầu ở câu đầu đoạn, `labels` khi nhãn trượt). Các ví dụ trỏ tới `examples/motion/*.json` + `*.bind.json`.
- [ ] **Step 2:** Sửa `vs-reviewer.md` và `DESIGN.md`.
- [ ] **Step 3:** `uv run pytest -q` → PASS (không đổi code).
- [ ] **Step 4: Commit** — `git commit -m "docs: vs-motion draws one canvas from the brief and binds it later; reviewer checks it reads A to Z"`

### Task 7: Nghiệm thu trên video `linux-tcp-cve-2026-98432`

**Files:** chỉ `~/notebooklm-videos/linux-tcp-cve-2026-98432/` (không đổi repo, trừ hình mới đưa lên thư viện).

- [ ] **Step 1:** Giữ bản cũ: chép `final.mp4` → `final.3canh.mp4`, `motion.json` → `motion.3canh.json`.
- [ ] **Step 2:** Gọi agent `vs-motion` với `MOTION_DESIGN` cho run này; xác nhận `vshort motion RUN --design` mã 0 và có ít nhất một hình mới trong `RUN/shapes/` (ví dụ `bo-nho` hoặc `nhan`).
- [ ] **Step 3:** Gọi `vs-motion` với `MOTION_BIND`; `vshort motion RUN` mã 0, `lines` là 4–8.
- [ ] **Step 4:** `vshort render RUN`; đo: không có mờ chồng giữa câu 4 và 8 (so khung giữa câu với khung `motion/sheet.png`), khung cuối câu 8 thấy đủ năm bước.
- [ ] **Step 5:** Gọi `publish_shapes` một lần bằng tay hoặc qua `_finish`, xác nhận commit chỉ có `assets/shapes/…` và đã push.
- [ ] **Step 6:** Báo Tai hai đường dẫn (`final.3canh.mp4`, `final.mp4`) để so.
