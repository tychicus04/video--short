# Hình động kể bằng ẩn dụ đời thường — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đoạn cơ chế kể bằng một cảnh đời thường (người đi lại, đồ vật được đưa/kẹp/cắm/mở, ✓/✗), có máy quay theo lời, đạo cụ vẽ sẵn chuẩn nét; ẩn dụ do một agent Sonnet ngắn viết và Tai duyệt cùng brief.

**Architecture:** Giữ bộ vẽ PIL (`vshort/kit.py`) và `motion.json` một khung. Thêm: phép biến đổi máy quay áp lên mọi nét trong `kit.draw` (`view = (cx, cy, z)`); `vshort/camera.py` tính các mốc máy quay từ vùng các thứ mỗi nhịp đụng tới; loại thứ mới `figure` (người đi được, có vai), `check`, `cross`; `shape` và `figure` di chuyển được; act mới `attach`, `open`, `close`; nhãn hai vế `means`; đầu bút chì; luật "không có quãng chết". Bộ đạo cụ là dữ liệu nét trong `assets/shapes/`, sinh bằng một script từ các nét cơ bản. Luồng `auto` thêm bước `an_du` (agent `vs-an-du`) trước điểm dừng duyệt brief; brief thêm bước 0 "Bình thường: …".

**Tech Stack:** Python 3.12, Pillow, numpy, pytest. Không thêm thư viện.

**Spec:** `docs/superpowers/specs/2026-11-03-hinh-dong-an-du-design.md` (nối tiếp `2026-11-02-hinh-dong-mot-khung-design.md`). Bản phác Tai đã duyệt: `docs/superpowers/specs/2026-11-03-hinh-dong-an-du-phac.html` (tọa độ và nét trong `<script>` là chuẩn nhìn).

## Global Constraints

- Làm trong một git worktree tách từ `main` (superpowers:using-git-worktrees). Thư mục chính đang có thay đổi dở của phiên khác (`vshort/cli.py`, `vshort/script.py`, `vshort/captions.py`, `vshort/plates.py`, `vshort/stills.py`, vài test): không đụng, không commit chúng. Kế hoạch này không cần sửa `vshort/cli.py`.
- Một khung A→Z, không cắt cảnh; luật cũ giữ nguyên: `MAX_SEEN = 7`, `MAX_BEATS = 6`, ≥ 2 nhịp còn lại sau khi gắn, `actor` vẽ ở nhịp 1 và không `hide`/`vanish`/lùi, `kit.SAFE = (40, 96, 680, 1050)`, nhãn tối đa `MAX_LABEL = 20` ký tự.
- Máy quay: `kit.FULL = (360.0, 573.0, 1.0)` là toàn khung (tâm vùng an toàn, phóng 1×: vẽ y như hiện nay). Phóng trong 1×–2× (`camera.MAX_ZOOM = 2.0`).
- Không có quãng nào dài quá `motion.MAX_QUIET = 1.5` s mà không có gì đang vẽ ra, di chuyển, đổi màu, mở/đóng, lùi/sáng lại hay máy quay đang đi; `pulse` không tính.
- Đoạn cơ chế tối đa `motion.MAX_SHARE = 0.55` số âm tiết lời đọc (thay cho "nửa video").
- Nhãn và `say`: chữ trong lời/brief + `COMMON` + chữ trong `RUN/an-du.md`. `means` (vế kỹ thuật): chỉ chữ trong lời/brief + `COMMON`.
- Ẩn dụ nằm ở `RUN/an-du.md`, không vào `brief.en.md`, không gửi NotebookLM. Không đổi giọng đọc, phụ đề, bản dịch, tư liệu, màu, font, nền, logo.
- Đạo cụ: dữ liệu nét (ô 0–100, 1–12 nét, 2–40 điểm/nét, không chữ), thư viện chỉ thêm. Không mặt cười, không biểu cảm hoạt hình.
- Agent mới `vs-an-du` ghim `model: sonnet`; `vs-researcher` vẫn Haiku; `vs-motion` vẫn Sonnet; `vs-reviewer` vẫn Opus.
- Test không gọi `claude`, NotebookLM hay `git push` thật (chốt `auto.CLAUDE = ["false"]` trong `tests/conftest.py` giữ nguyên).
- Thông báo lỗi cho agent viết bằng tiếng Việt, một dòng mỗi lỗi, theo giọng các thông báo hiện có trong `vshort/motion.py`.

## Review Focus

- Một đồ vật đã `attach` vào người, rồi người đi tiếp: đồ vật phải đi theo, kể cả khi người cũng đang được `attach` vào thứ khác; `attach` tạo vòng phải bị từ chối → `test_attached_thing_follows_its_moving_parent`, `test_attach_rules` ở Task 3.
- Thứ di chuyển ra khỏi vùng nhịp của nó giữa chừng: vùng máy quay của nhịp phải chứa cả chỗ bắt đầu và chỗ tới, nên chỗ tới vẫn nằm trong vùng an toàn trên màn hình → `test_camera_focus_covers_where_a_mover_goes` ở Task 2.
- Cảnh cũ không dùng tính năng mới (hai ví dụ `coruna`, `goi-tin`): vẫn gắn và vẽ được, khung cuối về đúng `FULL` → `test_example_binds_and_draws` (sẵn có) và `test_timed_scene_ends_on_the_full_canvas` ở Task 2.
- `means` dùng chữ kỹ thuật brief có mà lời đọc không nói: bước gắn báo lỗi và sửa được bằng `motion.bind.json` `"means": {"<id>": "<chữ trong lời>" | ""}` → `test_bind_means_override` ở Task 5.
- Run không có `an-du.md` (brief "Không có", hoặc agent ẩn dụ lỗi): kiểm hình động vẫn chạy như cũ, không coi thiếu file là lỗi → `test_missing_metaphor_file_adds_no_words` ở Task 5, `test_an_du_failure_does_not_stop_the_run` ở Task 8.

---

### Task 1: Máy quay trong bộ vẽ

**Files:**
- Create: `vshort/camera.py`, `tests/test_camera.py`
- Modify: `vshort/kit.py` (`draw`, `_draw_thing`, `_stroke`, `_write`, chấm), `tests/test_kit.py`

**Interfaces:**
- Produces:
  - `kit.FULL: tuple[float, float, float] = (360.0, 573.0, 1.0)`; `kit.screen(view, x: float, y: float) -> tuple[float, float]` = `((x − cx)·z + 360, (y − cy)·z + 573)`.
  - `kit.draw(things, acts, t, view: tuple[float, float, float] = FULL) -> Image.Image`: mọi điểm nét (sau `_wobble`, tính trong tọa độ khung gốc), tâm nhãn, chấm đi qua `screen`; độ dày nét, bán kính chấm và cỡ chữ nhân `z`. Nền giấy không biến đổi.
  - `camera.MAX_ZOOM = 2.0`, `PAD = 40`, `MOVE_S = 0.8`, `OUT_S = 1.2`, `OUT_LEAD = 2.0`.
  - `camera.view(box: tuple[float, float, float, float]) -> tuple[float, float, float]`: box nới `PAD` mỗi phía; `z = clamp(min(640 / bw, 954 / bh), 1, MAX_ZOOM)` (640 × 954 là cỡ vùng an toàn); tâm = tâm box, rồi kẹp `cx ∈ [360/z, 720 − 360/z]`, `cy ∈ [573/z, 1280 − 707/z]` (không lộ ngoài khung; ở 1× luôn ra `FULL`).
  - `camera.keys(spans: list[tuple[float, float]], boxes: list[tuple | None], lead: float) -> list[tuple[float, float, float, float]]` (mỗi mốc `(t, cx, cy, z)`): `(spans[0][0] − lead, v0)`; với mỗi nhịp i ≥ 1: `(s_i, v_{i−1})`, `(min(s_i + MOVE_S, e_i), v_i)`; cuối: `t_out = max(s_last + MOVE_S, s_last + 0.5·(e_last − s_last), e_last − OUT_LEAD)`, thêm `(t_out, v_last)`, `(t_out + OUT_S, FULL)`. `boxes[i] is None` → `FULL`.
  - `camera.at(keys, t) -> tuple[float, float, float]`: trước mốc đầu = mốc đầu, sau mốc cuối = mốc cuối, giữa hai mốc nội suy bằng `kit.ease`.

- [ ] **Step 1: Write the failing tests** (`tests/test_camera.py`, thêm vào `tests/test_kit.py`)

```python
from vshort import camera, kit
from vshort.kit import FULL, SAFE

def test_full_view_is_identity():
    assert camera.view(SAFE) == FULL
    assert kit.screen(FULL, 123, 456) == (123, 456)

def test_small_box_zooms_to_max_and_centres():
    v = camera.view((200, 300, 300, 400))
    assert v == (250.0, 350.0, 2.0)
    assert kit.screen(v, 250, 350) == (360.0, 573.0)

def test_view_never_shows_past_the_canvas():
    assert camera.view((40, 96, 140, 196)) == (180.0, 286.5, 2.0)

def test_keys_glide_between_beats_and_pull_back():
    ks = camera.keys([(0, 5), (5, 10)], [(200, 300, 300, 400), None], lead=0.35)
    assert ks[0] == (-0.35, 250.0, 350.0, 2.0) and ks[-1] == (9.2, *FULL)
    assert camera.at(ks, 2.0) == (250.0, 350.0, 2.0)
    assert 1.0 < camera.at(ks, 5.4)[2] < 2.0
    assert camera.at(ks, 6.0) == FULL

# tests/test_kit.py
def test_view_moves_and_enlarges_the_ink():
    acts = [Act("draw", "d", 0.0, 0.8)]
    img = draw([DOT | {"xy": [250, 350]}], acts, 2.0, view=(250.0, 350.0, 2.0))
    assert _ink(img, (330, 543, 390, 603)) > 0 and _ink(img, (240, 340, 260, 360)) == 0
```

- [ ] **Step 2:** `uv run pytest tests/test_camera.py tests/test_kit.py -q` → FAIL (`camera` chưa có, `draw` không nhận `view`).
- [ ] **Step 3:** Viết `vshort/camera.py` và thêm `view` vào `kit.draw` theo Interfaces. Phép biến đổi đặt ở một chỗ (`screen`) và được gọi trong `_stroke`, `_write`, chỗ vẽ chấm; `_wobble` vẫn chạy trên tọa độ gốc để nét không rung khác đi khi phóng.
- [ ] **Step 4:** `uv run pytest -q` → toàn bộ PASS (mặc định `view=FULL` nên mọi test cũ không đổi).
- [ ] **Step 5:** Commit `feat(motion): camera transform in the kit`.

### Task 2: Mốc máy quay cho mỗi cảnh

**Files:**
- Modify: `vshort/motion.py` (`Scene`, `timed`, `_sheet`, `design_problems`), `vshort/render.py:273`, `tests/test_motion.py`

**Interfaces:**
- Consumes: `camera.keys`, `camera.at`, `camera.view`, `kit.draw(..., view)` (Task 1).
- Produces:
  - `Scene.cams: list[tuple[float, float, float, float]]` (trường mới, mặc định `[]`; `[]` nghĩa là `FULL` suốt).
  - `timed()` điền `cams = camera.keys([span của từng nhịp giữ lại], boxes, LEAD_IN)`. `boxes[i]` = `beat["view"]` nếu nhịp có, không thì hợp `kit.bbox` của mọi thứ trong `touched[k]` (thứ di chuyển: bbox ở vị trí lúc đầu và lúc cuối nhịp, tính bằng `kit._position`).
  - Nhịp có thể có `"view": [x0, y0, x1, y1]` (tùy chọn) để ghi đè; phải nằm trong `SAFE`, `x0 < x1`, `y0 < y1`.
  - `render.py` và `_sheet` vẽ `kit.draw(sc.things, sc.acts, t, camera.at(sc.cams, t) if sc.cams else kit.FULL)`.

- [ ] **Step 1: Write the failing tests** (dùng fixture `design` sẵn có)

```python
def test_timed_scene_ends_on_the_full_canvas(design, tmp_path):
    sc = motion.timed(design, *motion.estimated(design), tmp_path)
    assert len(sc.cams) == 1 + 2 * (len(design["beats"]) - 1) + 2
    assert sc.cams[-1][1:] == kit.FULL

def test_camera_focus_covers_where_a_mover_goes(design, tmp_path):
    sc = motion.timed(design, *motion.estimated(design), tmp_path)
    v = camera.at(sc.cams, 5.0)  # giữa nhịp 2: atk đã tới (520, 680)
    x, y = kit.screen(v, 520, 680)
    assert kit.SAFE[0] <= x <= kit.SAFE[2] and kit.SAFE[1] <= y <= kit.SAFE[3]

def test_beat_view_overrides_and_is_checked(design, tmp_path):
    ok = json.loads(json.dumps(design)); ok["beats"][0]["view"] = [100, 200, 400, 500]
    assert motion.design_problems(ok, WORDS, tmp_path) == []
    bad = json.loads(json.dumps(design)); bad["beats"][0]["view"] = [0, 0, 10, 10]
    assert any("view" in p for p in motion.design_problems(bad, WORDS, tmp_path))
```

- [ ] **Step 2:** `uv run pytest tests/test_motion.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces; thêm kiểm `view` vào vòng kiểm từng nhịp của `design_problems` (thông báo: `motion.json nhịp {k}: view phải là [x0, y0, x1, y1] trong {AREA}`).
- [ ] **Step 4:** `uv run pytest -q` → PASS (gồm `tests/test_examples.py`, `tests/test_render.py`).
- [ ] **Step 5:** Commit `feat(motion): each beat framed by the camera, pull back at the end`.

### Task 3: Người đi được, đồ vật di chuyển và được gắn, dấu ✓/✗

**Files:**
- Modify: `vshort/kit.py`, `vshort/motion.py`, `tests/test_kit.py`, `tests/test_motion.py`

**Interfaces:**
- Produces:
  - `kit.POINTED |= {"figure", "check", "cross"}`; `kit.MOVERS = {"dot", "icon", "figure", "shape"}`.
  - `figure`: `xy` là tâm thân; vẽ như bản phác (đầu tròn r 24 ở (0, −70), thân bo tròn từ (−36, 40) qua vai (0, −40) tới (36, 40), hai chân tới y + 92). `role` tùy chọn: `"guard"` (thêm mũ lưỡi trai), `"attacker"` (thêm mũ trùm; màu mặc định `red`). Nhãn ở (x, y + 125). `bbox`: rx 40, trên 112, dưới 92 (cộng nhãn). `TOP["figure"] = 112`.
  - Đi bộ: khi vị trí đổi so với 0,05 s trước, thân nhún lên tới 6 px và chân đung đưa ±12°, 2 bước/giây. `kit._legs(x: float, y: float, swing: float) -> list[list[tuple[float, float]]]` (swing ∈ [−1, 1]; 0 = đứng, đối xứng).
  - `shape` di chuyển theo tâm hộp: `move`/`bounce` `to` là tâm mới; nét dời theo.
  - `check` / `cross`: `xy` là tâm, cỡ khoảng 56 px, nét 5, màu mặc định `green` / `red`, không nhãn; không tính vào `MAX_SEEN`.
  - `kit.Act` thêm `on: str = ""`, `offset: tuple[float, float] | None = None`. Act `attach` (`{"do": "attach", "thing": id, "on": id, "offset": [dx, dy], "at", "dur"}`, mặc định `dur = kit.MOVE`): trong khoảng act, thứ đó trượt (ease) từ chỗ đang đứng tới `vị trí(on) + offset`; sau đó đi theo `on` cho tới một `move`/`bounce` sau của chính nó.
  - `kit._position(thing, acts, t, by_id: dict[str, dict] | None = None)`; `kit.draw` dựng `by_id` từ `things`.
  - `actor` được là `dot` hoặc `figure`.
  - Dáng "đưa tay" trong danh sách đạo cụ của spec: không làm riêng; `attach` (đồ vật trượt từ người này sang người kia) đã cho thấy
    việc đưa/nhận. Thêm khi một cảnh thật cần mà `attach` không diễn được.

- [ ] **Step 1: Write the failing tests**

```python
FIG = {"id": "f", "kind": "figure", "xy": [200, 300], "label": "kỹ sư"}
KEY = {"id": "k", "kind": "icon", "icon": "key", "xy": [600, 600]}

def test_attached_thing_follows_its_moving_parent():
    acts = [Act("draw", "f", 0, 0.8), Act("draw", "k", 0, 0.8),
            Act("attach", "k", 0.0, 0.5, on="f", offset=(0, 5)), Act("move", "f", 1.0, 2.0, to=(500, 300))]
    by_id = {"f": FIG, "k": KEY}
    assert kit._position(KEY, acts, 2.5, by_id) == (500, 305)

def test_standing_legs_are_symmetric_walking_legs_are_not():
    (l0, r0), (l1, r1) = kit._legs(0, 0, 0.0), kit._legs(0, 0, 1.0)
    assert [(-x, y) for x, y in l0] == r0 and [(-x, y) for x, y in l1] != r1

def test_check_and_cross_draw_in_their_colours():
    img = draw([{"id": "c", "kind": "check", "xy": [300, 300]}, {"id": "x", "kind": "cross", "xy": [500, 300]}],
               [Act("draw", "c", 0, 0.8), Act("draw", "x", 0, 0.8)], 2.0)
    assert _colour(img, (260, 260, 340, 340), GREEN) and _red(img, (460, 260, 540, 340))

def test_shape_prop_moves_by_its_centre(tmp_path): ...  # shape box [100,100,200,200], move to (400, 400): ink quanh (400, 400), không còn quanh (150, 150)

# tests/test_motion.py
def test_attach_rules(design, tmp_path):  # attach lên thứ không di chuyển được → lỗi có "attach"; A on B và B on A → lỗi có "vòng"
def test_figure_can_be_the_actor(design, tmp_path):  # đổi atk thành figure role attacker → design_problems == []
```

(`_colour` là phiên bản tổng quát của `_red` trong `tests/test_kit.py`.)

- [ ] **Step 2:** `uv run pytest tests/test_kit.py tests/test_motion.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces. Trong `motion.py`: `KINDS` có kind mới; `ACTS` thêm `"attach"`; `DUR["attach"] = kit.MOVE`; `_act_problems` kiểm `attach` (`on` là id một thứ di chuyển được, khác `thing`; `offset` là `[x, y]`; không tạo vòng theo chuỗi `on`), `move`/`bounce` cho mọi `kit.MOVERS` (thông báo "chỉ dot, icon, figure, shape"), `role` chỉ cho `figure` và thuộc `{"guard", "attacker"}`, `check`/`cross` không nhãn; `_actor_problems` nhận `dot` hoặc `figure`; `timed()` chép `on`/`offset` vào `kit.Act`; `_order_problems` truyền `by_id` cho `kit._position`.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(motion): walking figures, moving props, attach, check and cross marks`.

### Task 4: Đạo cụ có phần mở/đóng

**Files:**
- Modify: `vshort/shapes.py`, `vshort/kit.py`, `vshort/motion.py`, `tests/test_shapes.py`, `tests/test_kit.py`, `tests/test_motion.py`

**Interfaces:**
- Produces:
  - File hình có thể có `"hinge": {"strokes": [i, …], "pivot": [x, y], "turn": độ}` hoặc `{"strokes": […], "pivot": […], "squash": f}`: các nét đó xoay `turn` độ (−180…180, khác 0) quanh `pivot`, hoặc co ngang theo `x` của `pivot` còn `f` (0,05…0,95) lần, khi mở hết. `shapes.problems` kiểm: chỉ số nét hợp lệ và không trùng, `pivot` trong ô 0–100, đúng một trong `turn`/`squash`.
  - `shapes.hinge_in_box(doc, box) -> dict | None`: hinge với `pivot` đổi sang px khung, cùng phép co/dời như `strokes_in_box` (tách phép đó ra một hàm chung `_fit(doc, box) -> tuple[float, float, float]`).
  - Act `open` / `close` (mặc định `dur = kit.OPEN = 0.8`), chỉ trên `shape` có hinge; `timed()` gắn `hinge` vào thing như đang gắn `strokes`. Mức mở 0–1 tính như `_dimmed`.

- [ ] **Step 1: Write the failing tests**

```python
def test_hinge_rules():  # nét 99 → lỗi "hinge"; có cả turn lẫn squash → lỗi; pivot [120, 0] → lỗi
def test_hinge_in_box_moves_the_pivot_with_the_strokes():
    doc = {"name": "barie", "strokes": [[[0, 50], [100, 50]]], "hinge": {"strokes": [0], "pivot": [0, 50], "turn": -80}}
    assert shapes.hinge_in_box(doc, (100, 100, 300, 300))["pivot"] == (100.0, 200.0)
def test_open_turns_the_hinged_strokes(): ...  # tay barie nằm ngang y 200 từ x 100 tới 300; sau open: có mực trong (90, 0, 140, 190), không còn mực quanh (280, 200)
def test_open_needs_a_hinged_shape(design, tmp_path):  # open trên "mem" (bo-nho, không hinge) → lỗi có "hinge"
```

- [ ] **Step 2:** `uv run pytest tests/test_shapes.py tests/test_kit.py tests/test_motion.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(motion): props with a hinge open and close`.

### Task 5: Nhãn hai vế, chữ của ẩn dụ, đầu bút

**Files:**
- Modify: `vshort/kit.py`, `vshort/motion.py`, `tests/test_kit.py`, `tests/test_motion.py`

**Interfaces:**
- Produces:
  - Thing có thể có `means` (cần `label`): dòng thứ hai `"= {means}"` cỡ `SMALL_EM`, cách nhãn `1.1·em` phía dưới; với `BOXED` trừ `box`, nhãn dời lên `1.1·SMALL_EM` để dòng `means` không đè hộp. `kit.bbox` tính cả dòng này.
  - `timed()` thêm act `plain` cho mỗi thứ có `means`, lúc bắt đầu nhịp giữ lại kế tiếp sau nhịp của nó (dài `kit.TURN`); dòng `means` mờ dần theo `plain`. Không có nhịp kế tiếp → không có `plain`.
  - `motion._metaphor(run_dir: Path | None) -> set[str]`: `_words` của `run_dir / "an-du.md"`; không có file → `set()`.
  - `_text_problems(what, text, said, extra: frozenset | set = frozenset())`: chữ hợp lệ thêm `extra`. `label`, `say` dùng `extra = _metaphor(run_dir)`; `means` không dùng.
  - `COMMON` thêm: `thẻ chìa bảo vệ cửa barie tòa nhà phòng két sắt phong bì hòm kiện hàng xe giao camera rào bảng tên danh sách quét bản sao kẹp cho vào đúng sai tầng cầu thang nhân viên kỹ sư khách`.
  - `motion.bind.json` thêm `"means": {"<id có means>": "<chữ mới>" | ""}` (`""` bỏ vế kỹ thuật), xử lý trong `bound()` như `labels`.
  - Đầu bút: `kit._tip(d, pts, p, view, seed)`; khi một thứ đang vẽ ra (0 < phần đã vẽ < 1), vẽ một cây bút chì nhỏ (thân dày 6 px, dài 22 px, nghiêng 60° lên phải, nối bằng nét 3 px tới đầu bút) tại điểm nét đầu tiên của thứ đó đang vẽ tới.

- [ ] **Step 1: Write the failing tests**

```python
def test_means_line_shows_then_goes_plain():  # thing figure label "thẻ" means "chứng chỉ": có mực ở dòng dưới nhãn lúc t=1; act plain 2.0–2.6 → không còn mực ở dòng đó lúc t=3
def test_metaphor_words_may_label_but_not_mean(design, tmp_path):
    (tmp_path / "an-du.md").write_text("cổng soát vé = chứng chỉ")   # "soát", "vé" không có trong COMMON
    d = json.loads(json.dumps(design)); d["things"][1]["label"] = "soát vé"
    assert motion.design_problems(d, WORDS, tmp_path) == []
    d["things"][1]["means"] = "chứng chỉ"          # có trong an-du.md nhưng không có trong WORDS
    assert any("means" in p for p in motion.design_problems(d, WORDS, tmp_path))
    d["things"][1]["means"] = "bộ nhớ"
    assert motion.design_problems(d, WORDS, tmp_path) == []
def test_missing_metaphor_file_adds_no_words(tmp_path):
    assert motion._metaphor(tmp_path) == set() and motion._metaphor(None) == set()
def test_timed_adds_plain_at_the_next_kept_beat(design, tmp_path):  # means trên srv (nhịp 1) → act plain lúc bắt đầu nhịp 2
def test_bind_means_override(design, tmp_path):  # means không có trong lời → lỗi; "means": {"srv": ""} → hết lỗi
def test_pen_tip_shows_only_while_drawing():
    line = {"id": "l", "kind": "path", "points": [[100, 600], [600, 600]]}
    acts = [Act("draw", "l", 0.0, 1.0)]
    assert _ink(draw([line], acts, 0.5), (345, 560, 385, 595)) > 0
    assert _ink(draw([line], acts, 1.5), (345, 560, 385, 595)) == 0
```

- [ ] **Step 2:** `uv run pytest tests/test_kit.py tests/test_motion.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces. `design_problems` và `bind_problems` có sẵn `run_dir`, nên tự gọi `_metaphor(run_dir)`: không đổi chữ ký hai hàm này, không sửa `vshort/cli.py`.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(motion): two-part metaphor labels, metaphor words, pencil tip`.

### Task 6: Không có quãng chết, đoạn cơ chế tới 55 %

**Files:**
- Modify: `vshort/motion.py`, `tests/test_motion.py`, có thể cả `examples/motion/coruna*.json`, `examples/motion/goi-tin*.json`

**Interfaces:**
- Produces:
  - `motion.MAX_QUIET = 1.5`; `_quiet_problems(sc: Scene, end: float) -> list[str]`: các khoảng bận = `[a.t0, a.t1]` của mọi act trừ `pulse`, cộng các khoảng giữa hai mốc `cams` liền nhau mà view khác nhau; xét từ act `draw` sớm nhất tới `end`; mỗi khoảng trống > `MAX_QUIET` thành một dòng `motion.json: {a:.1f}–{b:.1f} s không có gì chuyển động ({b − a:.1f} s, tối đa {MAX_QUIET}); thêm hành động cho nhịp đó`. Gọi ở cuối `design_problems` (thời gian ước lượng) và `bind_problems` (thời gian ước lượng theo lời), cùng chỗ `_order_problems`.
  - `motion.MAX_SHARE = 0.55` thay luật "nửa video" trong `_lines_problems`; thông báo: `motion.bind.json: đoạn hình động dài hơn 55 % video (tính theo số âm tiết lời đọc)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_quiet_stretch_is_reported(design, tmp_path):
    d = json.loads(json.dumps(design)); d["beats"][1]["acts"] = []    # nhịp 2 chỉ còn vẽ mem: ~2,2 s đứng im
    assert any("không có gì chuyển động" in p for p in motion.design_problems(d, WORDS, tmp_path))
def test_pulse_does_not_count_as_motion(design, tmp_path):  # thay acts nhịp 2 bằng một pulse trên atk → vẫn báo
def test_mechanism_may_take_55_percent(design, tmp_path):  # script mà lines chiếm 52 % âm tiết → không lỗi; 60 % → lỗi có "55 %"
```

- [ ] **Step 2:** `uv run pytest tests/test_motion.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces.
- [ ] **Step 4:** `uv run pytest -q`. Nếu `tests/test_examples.py` trượt vì quãng chết trong `coruna`/`goi-tin`: thêm act (vd. `pulse` không tính, nên thêm `move` ngắn của actor, hoặc dời `at`) vào ví dụ cho tới khi PASS; không nới `MAX_QUIET`.
- [ ] **Step 5:** Commit `feat(motion): no dead time in the mechanism, stretch up to 55 %`.

### Task 6b: Máy quay trôi chậm, hình đi trước lời 0,2 s (luật từ `kallaway-style`, Tai chọn 03/11)

**Files:**
- Modify: `vshort/camera.py`, `vshort/motion.py` (`_starts`, `_quiet_problems`), `tests/test_camera.py`, `tests/test_motion.py`

**Interfaces:**
- Produces:
  - `camera.DRIFT = 0.03`: trong `keys`, từ lúc một nhịp đã khung xong (cuối cú lướt, hoặc mốc đầu với nhịp 1) tới lúc nhịp sau bắt đầu
    (hay tới `t_out` với nhịp cuối), zoom tăng dần từ `z` lên `z · (1 + DRIFT)` cùng tâm (tâm kẹp lại theo `view` ở zoom mới). Mốc của
    cú lùi ra cuối và `FULL` cuối không trôi.
  - `motion.LEAD_WORD = 0.2`: trong `_starts`, mọi mốc nhịp giữ lại **sau nhịp đầu** lùi sớm `LEAD_WORD` s.
  - `_quiet_problems` không tính các khoảng chỉ có trôi (giữa hai mốc cùng tâm mà zoom khác nhau ≤ `DRIFT`).

- [ ] **Step 1: Write the failing tests**

```python
def test_camera_drifts_while_a_beat_holds():
    ks = camera.keys([(0, 5), (5, 10)], [(200, 300, 300, 400), None], lead=0.35)
    assert camera.at(ks, 1.0)[2] < camera.at(ks, 4.9)[2] <= 2.0 * (1 + camera.DRIFT) + 1e-9
    assert ks[-1] == (9.2, *kit.FULL)
def test_beats_after_the_first_start_a_little_before_their_words(design, tmp_path): ...  # bind_timed: nhịp 2 bắt đầu sớm 0,2 s so với mốc cụm của nó; nhịp 1 đúng mốc
def test_drift_alone_is_still_quiet(design, tmp_path): ...  # như test_a_quiet_stretch_is_reported: vẫn báo dù máy quay trôi
```

- [ ] **Step 2:** `uv run pytest tests/test_camera.py tests/test_motion.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces; sửa `test_keys_glide_between_beats_and_pull_back` nếu mốc giữa đổi vì trôi (giá trị đầu/cuối giữ).
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(motion): slow camera drift, picture leads the word by 0.2 s`.

### Task 7: Bộ đạo cụ đời thường (Tai duyệt)

**Files:**
- Create: `scripts/props.py`, `assets/shapes/{the-nhan-vien,may-quet,bang-ten,barie,cua,toa-nha,phong,chot-bao-ve,ket-sat,hom-thu,kien-hang,xe-giao-hang,camera-an-ninh,hang-rao,cau-thang}.json`, `tests/test_props.py`

**Interfaces:**
- Consumes: định dạng hình + `hinge` (Task 4), `shapes.sheet`, `kit._stroke`.
- Produces: 15 hình thư viện. `barie` có `hinge` `turn` (tay barie quay lên −78° quanh gốc); `cua` và `ket-sat` có `hinge` `squash` (cánh co về bản lề). `name` tiếng Việt: thẻ nhân viên, máy quét, bảng tên, barie, cửa, tòa nhà, phòng, chốt bảo vệ, két sắt, hòm thư, kiện hàng, xe giao hàng, camera an ninh, hàng rào, cầu thang.

- [ ] **Step 1: Write the failing test**

```python
PROPS = ["the-nhan-vien", "may-quet", "bang-ten", "barie", "cua", "toa-nha", "phong", "chot-bao-ve", "ket-sat",
         "hom-thu", "kien-hang", "xe-giao-hang", "camera-an-ninh", "hang-rao", "cau-thang"]

def test_props_are_in_the_library_and_valid():
    for slug in PROPS:
        doc = shapes.find(slug, None)
        assert doc is not None and shapes.problems(doc, slug) == []
    assert {s for s in PROPS if "hinge" in shapes.find(s, None)} == {"barie", "cua", "ket-sat"}
```

- [ ] **Step 2:** `uv run pytest tests/test_props.py -q` → FAIL.
- [ ] **Step 3:** Viết `scripts/props.py`: các nét cơ bản (`line`, `rect`, `rrect`, `circle`, `arc`, lấy mẫu đều trong ô 0–100), mỗi đạo cụ là một hàm ngắn trả về `name`, `strokes`, `hinge`. Chạy `uv run python scripts/props.py` thì ghi các file vào `assets/shapes/` (không ghi đè file đã có: báo lỗi và dừng) và ghi tờ xem trước `assets/shapes/props-sheet.png` (dựng bằng `shapes.sheet` trên một thư mục tạm, cộng một hàng vẽ ba hình có hinge ở trạng thái mở). Nét theo bản phác (`docs/superpowers/specs/2026-11-03-hinh-dong-an-du-phac.html`: thẻ, máy quét, bảng tên, barie, chốt bảo vệ, tòa nhà, phòng): gọn, nhận ra ở cỡ nhỏ, không chữ, không mặt.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5: Checkpoint Tai.** Đưa Tai `assets/shapes/props-sheet.png`; sửa theo ý Tai (sửa trong script, chạy lại sau khi xóa file vừa sinh) tới khi Tai duyệt. Không làm Task 9–10 trước khi Tai duyệt.
- [ ] **Step 6:** Commit `feat(shapes): everyday props kit` (gồm `props-sheet.png`).

### Task 8: Ẩn dụ trong luồng: bước 0, agent `vs-an-du`, điểm dừng brief

**Files:**
- Create: `claude/agents/vs-an-du.md`
- Modify: `vshort/auto.py` (`TIMEOUT`, `BRIEF_CHECK`, `MOTION_DESIGN`, prompt mới `AN_DU`, hàm mới `_an_du`, `_flow`), `claude/agents/vs-researcher.md`, `claude/skills/video-short/SKILL.md`, `tests/test_auto.py`, `~/.claude/CLAUDE.md` (ngoài repo)

**Interfaces:**
- Produces:
  - `RUN/an-du.md`: dòng đầu `# Ẩn dụ đời thường`; `Cảnh: <một câu>`; bảng `| khái niệm kỹ thuật | đồ vật |`; `Từng bước:` đánh số 0…n, mỗi bước cơ chế của brief ứng với một hành động trong cảnh. Brief "Không có" mục cơ chế → file chỉ có `Không có`.
  - `vs-an-du.md`: frontmatter `name: vs-an-du`, `model: sonnet`, `tools: Read, Write, Bash`. Lời dặn ngắn (đích dưới $0,5/lượt): đọc `RUN/brief.vi.md` (mục "Cơ chế từng bước", "Lưu ý độ chính xác"), `ls ~/video-pipeline/assets/shapes/` và `name` của từng file; chọn **một** cảnh vẽ được bằng đạo cụ có sẵn (cộng `figure`, `icon`, `check`, `cross`); giữ mọi điều kiện của "Lưu ý độ chính xác" (không thành "ai cũng vào được"); không trẻ con; không chi tiết đủ để làm lại tấn công; ghi `RUN/an-du.md` theo dạng trên. Không đọc nguồn, không gọi NotebookLM.
  - `auto.TIMEOUT["vs-an-du"] = 600`; `AN_DU = "RUN={run}. Đọc {run}/brief.vi.md, viết {run}/an-du.md."`.
  - `auto._an_du(run: Run) -> None`: như `_design`: `run_claude(run, "an_du", "vs-an-du", …)`; `AgentError` → in một dòng, không dừng run; luôn `run.mark("an_du")`.
  - `_flow`: sau khối research và sau `brief_check` (khi `--auto`), trước điểm dừng brief: `if not run.done("an_du"): _an_du(run)`. Lời nhắn `WAIT_BRIEF`: `Duyệt brief: {p}/brief.vi.md (sửa thì sửa cả brief.en.md) và ẩn dụ {p}/an-du.md, rồi \`vshort approve {p} brief\` và \`vshort auto {p}\`.`
  - `MOTION_DESIGN` thêm: đọc `{run}/an-du.md` (ẩn dụ đã duyệt, nếu có) và dựng cảnh theo đúng ẩn dụ đó.
  - `BRIEF_CHECK` thêm: mục cơ chế có bước 0 "Bình thường: …" (bản Anh "0. Normally: …") trừ khi ghi "Không có".
  - `vs-researcher.md`: mục **Cơ chế từng bước** mở bằng `0. Bình thường: <cách hệ thống làm đúng, một câu>` rồi 3–5 bước như cũ (bước 0 không tính vào 3–5); bản Anh `0. Normally: …`.
  - `SKILL.md` bước 3, mã 20: dán `brief.vi.md` (tiêu đề lên đầu) **và** `an-du.md` nếu có; Tai sửa ẩn dụ → sửa `an-du.md` (không đụng `brief.en.md`).
  - `~/.claude/CLAUDE.md`: dòng ngoại lệ các agent `vs-*` thêm `vs-an-du` giữ Sonnet (Tai chọn 03/11/2026: ẩn dụ là phần khó nhất về độ chính xác).

- [ ] **Step 1: Write the failing tests** (`tests/test_auto.py`, theo cách các test `_design` hiện có giả lập `run_claude`)

```python
def test_an_du_runs_before_the_brief_stop(...):   # run mới, research đã xong: _flow gọi agent "vs-an-du" rồi Stop WAIT_BRIEF; lời nhắn có "an-du.md"
def test_an_du_failure_does_not_stop_the_run(...): # run_claude ném AgentError → vẫn tới Stop WAIT_BRIEF, state.json có "an_du"
def test_an_du_is_not_asked_twice(...):            # "an_du" đã đánh dấu → không gọi lại
```

- [ ] **Step 2:** `uv run pytest tests/test_auto.py -q` → FAIL.
- [ ] **Step 3:** Làm theo Interfaces (mã trong `auto.py`; văn bản trong ba file `.md` của repo; một dòng trong `~/.claude/CLAUDE.md`).
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(auto): everyday metaphor written before the brief stop; brief step 0` (không gồm `~/.claude/CLAUDE.md`, file đó ngoài repo).

### Task 9: Lời dặn `vs-motion`, `vs-reviewer` và ví dụ chuẩn LXD

**Files:**
- Create: `examples/motion/the-nhan-vien.json`, `examples/motion/the-nhan-vien.bind.json`, `examples/motion/the-nhan-vien.script.json`
- Modify: `claude/agents/vs-motion.md`, `claude/agents/vs-reviewer.md`, `tests/test_examples.py`

**Interfaces:**
- Consumes: mọi trường/act mới của Task 1–6, đạo cụ Task 7.
- Produces:
  - Ví dụ `the-nhan-vien`: cảnh LXD của bản phác, viết bằng `motion.json` mới: bước 0 kỹ sư cắm chìa, máy quét ✓; tòa nhà, barie, chốt bảo vệ, bảng tên; kẻ gian (`figure` `role: attacker`, actor) lấy bản sao thẻ (`attach`), kẹp sau thẻ mình, cắm chìa của chính hắn; máy quét ✓ thẻ đầu; mũi tên `path` `arrow` so thẻ với bảng: ✗ thẻ hắn, ✓ thẻ kỹ sư; barie `open`; phòng `red` lần lượt, tầng nền `red`. `means` ở lần đầu: thẻ = chứng chỉ công khai, chìa = khóa riêng, bảng tên = danh sách tin cậy, phòng = máy ảo. `.script.json` là câu 1–15 của `~/notebooklm-videos/lxd-microcloud-cvss10/script.vi.json` (bản Tai đã duyệt); `.bind.json` gắn 6 nhịp vào câu 3–8.
  - `test_examples.py` thêm `"the-nhan-vien"` vào danh sách tham số.
  - `vs-motion.md`: đọc `RUN/an-du.md` trước, dựng đúng ẩn dụ đó (không có file thì dựng như cũ); ưu tiên đạo cụ thư viện, chỉ vẽ hình mới khi thư viện thiếu; mô tả `figure`/`role`, thứ di chuyển mới, `attach`, `open`/`close`, `check`/`cross`, `means`, `view` (thường để code tự tính), luật quãng chết 1,5 s; bảng "động từ → chuyển động" (lấy/sao chép → `attach` một bản sao; gửi/chuyển → `path` có `arrow` và thứ đó
    chạy theo; kiểm tra/so → mũi tên `path` + `check`/`cross`; chặn → `bounce` + `cross`; mở/vượt qua → `open`; chiếm → `red`; lấy cắp →
    icon bay theo `path` về kẻ tấn công; tập trung vào một chỗ → `view` của nhịp) và màu mang nghĩa (đỏ = tấn công/sai, xanh lá =
    đúng/an toàn, xanh lơ chỉ cho lớp bảo vệ; tối đa hai màu nhấn mỗi khung); chỗ hỏng phải thành một hành động nhìn thấy; bước 0 là nhịp đầu; ví dụ chuẩn đọc trước thêm `the-nhan-vien`. Danh sách chữ được phép trong mục An toàn thêm từ đời thường mới và chữ của `an-du.md`.
  - `vs-reviewer.md` mục 9: bỏ "không camera zoom/trượt trên hình động"; thêm: máy quay theo lời, không giật, không chóng mặt, khung cuối lùi ra toàn khung và đọc được; ẩn dụ khớp `an-du.md` và "Lưu ý độ chính xác" của brief (ở `--auto` đây là lần soát duy nhất); chỗ hỏng hiện thành hành động; không trông trẻ con; không có quãng đứng im.

- [ ] **Step 1:** Thêm `"the-nhan-vien"` vào tham số `test_example_binds_and_draws` → `uv run pytest tests/test_examples.py -q` FAIL (chưa có file).
- [ ] **Step 2:** Viết ba file ví dụ (tọa độ lấy từ `<script>` của bản phác, đổi sang `box`/`xy` trong `SAFE`). `uv run pytest tests/test_examples.py -q` → PASS. Dựng `bind_sheet` ra một PNG tạm, mở xem từng cột: không chồng hình, nhãn không đè, khung cuối đọc được; sửa tới khi đạt.
- [ ] **Step 3:** Sửa `vs-motion.md` và `vs-reviewer.md` theo Interfaces.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `docs(agents): vs-motion builds the approved metaphor; reviewer checks it; LXD example`.

### Task 10: Nghiệm thu trên vụ LXD

**Files:**
- Modify: chỉ trong `~/notebooklm-videos/lxd-microcloud-cvss10/` (dữ liệu run, không thuộc repo) và một thư mục tạm cho lần thử `vs-an-du`.

- [ ] **Step 1:** Giữ bản cũ để so: trong RUN, `cp final.mp4 final.cu.mp4`; đổi tên `motion.json`, `motion.bind.json`, `review.md`, `review.json` thành `*.cu.*`.
- [ ] **Step 2:** Viết `RUN/an-du.md` theo dạng ở Task 8, nội dung lấy từ bảng đổi của bản phác (thẻ nhân viên, chìa, máy quét + bảo vệ + bảng tên, tòa nhà/phòng/tầng nền) và câu 3 làm bước 0.
- [ ] **Step 3:** Chạy agent vẽ khung rồi gắn nhịp, tắt advisor để đo đúng chi phí trên Mac: `cd ~/video-pipeline && CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1 claude -p --agent vs-motion --output-format json "<MOTION_DESIGN với RUN>"`, rồi cũng vậy với `MOTION_BIND`. Ghi `total_cost_usd` của hai lượt. `uv run vshort motion RUN` → mã 0.
- [ ] **Step 4:** `uv run vshort timeline RUN && uv run vshort render RUN` → có `final.mp4` mới.
- [ ] **Step 5:** `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1 claude -p --agent vs-reviewer "<REVIEW với RUN>"`; đọc phần hình động của `review.md`. Đạt khi không còn lỗi hình động và các tiêu chí ở mục "Ví dụ nghiệm thu" của spec đều có; chi phí `vs-motion` (Step 3) ≤ $2,79.
- [ ] **Step 6:** Thử `vs-an-du` trên hai brief: chép `brief.vi.md` của `lxd-microcloud-cvss10` và của `linux-tcp-cve-2026-98432` vào hai thư mục tạm, chạy `claude -p --agent vs-an-du "RUN=<tmp>. Đọc <tmp>/brief.vi.md, viết <tmp>/an-du.md."`, ghi chi phí (đích < $0,5).
- [ ] **Step 7: Checkpoint Tai.** Đưa Tai: `final.cu.mp4` và `final.mp4` (lệnh `scp` nếu chạy trên server), kết luận soát, chi phí, hai file `an-du.md` thử. Tai duyệt → xong; Tai chê → ghi lại điều chê, sửa ở task tương ứng (luật trong `vshort/motion.py` hay lời dặn agent), chạy lại từ Step 3.
