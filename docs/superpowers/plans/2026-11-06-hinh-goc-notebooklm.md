# Hình gốc NotebookLM: kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hình của cả video là chính video NotebookLM đang chạy, đã xóa phụ đề Anh theo từng khung, co giãn từng câu cho vừa lời
Việt. Không còn ảnh tĩnh có máy quay, ẩn dụ, hình động, nhịp hình hay thẻ tư liệu.

**Architecture:**
- `vshort clean RUN` (mới, `plates.py`) ghi `RUN/clean.mp4` sạch phụ đề, sạch watermark.
- `vshort/retime.py` (mới, thuần) tính cho mỗi câu đoạn nguồn → đoạn đích, tốc độ và phần giữ khung.
- `render.render_pieces` dựng bằng một đồ thị ffmpeg, như `spike_retime.py`: các đoạn, ảnh vá đè lên, phụ đề ASS, outro.
- `sound.cues` đặt hiệu ứng ở những chỗ chuyển cảnh lớn.
- `vs-visuals` chỉ còn vá chữ.
- Toàn bộ phần hình tự vẽ bị xóa.

**Tech Stack:** Python 3.12, numpy, Pillow, ffmpeg, torch (LaMa, CPU) đã có, pytest. Không thêm gói nào.

**Spec:** `docs/superpowers/specs/2026-11-06-hinh-goc-notebooklm-design.md`.
- Bản thử đã chạy: `docs/superpowers/specs/2026-11-06-hinh-goc-thu/spike_retime.py`. Đó là đồ thị ffmpeg mà Tai đã xem, tham khảo
  được nhưng đừng bê nguyên.
- Ảnh vệt cần hết: `vet-o-trong.jpg`.

## Global Constraints

- **Repo:**
  - Làm thẳng trên `main`, không nhánh, không worktree.
  - Add file theo tên, không dùng `commit -a`.
  - Một phiên khác cũng đang sửa `main` (`vshort/publish.py`, `tests/test_publish.py` có thể đang dở). **Không đụng hai file đó.**
  - Trước mỗi lần push: chạy `git fetch` rồi `git status -sb`.
    - Cây sạch thì `git pull --rebase`.
    - Cây bẩn vì file của phiên kia thì chỉ push khi không bị chậm hơn `origin/main`. Bị chậm thì `git pull --rebase --autostash`.
  - Dòng cuối commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Test:**
  - `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest -q`.
  - Web: `cd web && npm run build && npm run lint`.
  - `tests/conftest.py` chốt `auto.CLAUDE=["false"]`.
- **Giữ nguyên các lựa chọn cũ của Tai:**
  - phụ đề `render.build_ass` (hộp xám, Patrick Hand, `SUB_BOTTOM`), câu đầu là tiêu đề hiện trọn;
  - không logo góc, chỉ có outro `assets/brand/anm-outro.mp4`, mờ chồng `XF = 0.4` s từ khung cuối;
  - −14 LUFS (`sound.master`), BT.709 (`setparams` như `render_video` hiện nay);
  - tối đa 3 tiếng hiệu ứng (`sound.UNDER`, `sound.SPACE`), không nhạc nền, không neon;
  - không khoanh, không zoom, không máy quay dưới bất kỳ dạng nào.
- **Co giãn** (spec mục 1):
  - `FAST = 1.5`;
  - lời Việt dài hơn thì phát 1x rồi giữ khung;
  - giữ quá `SLOW_AFTER = 1.5` s thì phát chậm tới `SLOW = 1.25` lần trước.
- **Chuẩn chất lượng:** không kém `source.mp4`. Mọi lời Anh đều có lời Việt.
- **Video dở trên pve2 lúc deploy:**
  - chạy tiếp theo quy trình mới, bỏ qua mốc và file của hình động/nhịp hình;
  - `vshort clean` chạy nếu chưa có mốc `clean`.

## Review Focus

1. **Video nền tối** (NetamLoader, phụ đề sáng trên nền tối): `vshort clean` vẫn sạch, không để lại ô sáng. Task 1 đo trên
   netamloader.
2. **Đoạn nguồn kết thúc ở khung gần trắng** (đầu một cảnh sơ đồ mới): không bao giờ giữ khung gần trắng. Task 2 có
   `test_blank_hold_frame_steps_back_to_a_drawn_one`.
3. **Video đang dở lúc deploy** có mốc `plates`, `motion`, `shots` cũ nhưng chưa có `clean`: `_build` phải chạy `clean`, không đụng
   file hình động. Task 7 có `test_old_run_gets_clean_and_ignores_motion_marks`.
4. **Câu vá mà chữ sai đã có sẵn từ đầu câu** (chữ vẽ từ câu trước): ảnh vá hiện từ đầu câu. Chữ sai hiện giữa câu thì video chạy
   tới lúc đó. Task 4 có hai test.
5. **Câu cuối chạy lấn vào logo NotebookLM:** đoạn nguồn bị cắt ở `stop`, không có khung logo Gemini nào. Task 2 có
   `test_last_line_stops_before_notebooklm_logo`.

---

### Task 1: `vshort clean`: xóa phụ đề Anh theo từng khung (có cổng kiểm)

**Cổng kiểm:** task này làm **trước tiên**. Nếu không cách nào qua được bước 6, **dừng cả kế hoạch** và báo Tai. Báo kèm các con số
và ảnh đo được, đừng làm tiếp các task sau.

**Files:**
- Modify: `vshort/plates.py`. Thêm `clean`, `scene_changes`, và chuyển `WATERMARK` từ `render.py` sang đây.
  `scene_cuts`, `_text_columns`, `_lama` giữ lại. `build_plates`, `Plate`, `_clean_time`, `_moving` để Task 7 xóa.
- Modify: `vshort/cli.py`. Thêm `cmd_clean` và subparser `clean`.
  - `cmd_stills` thôi gọi `clean_video`. Nó đòi phải có sẵn `RUN/clean.mp4`, thiếu thì báo
    "thiếu clean.mp4 (chạy `vshort clean`)" với mã `BAD_INPUT`.
- Test: `tests/test_plates.py`.

**Interfaces:**
- Produces:
  - `plates.clean(src: Path, captions: list[Fragment], out: Path, lama_path: Path, inpaint: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None) -> dict`
    - Ghi `out` cùng khổ, cùng fps, cùng độ dài với `src`. Phụ đề trong `captions` bị xóa, watermark xóa bằng `WATERMARK`.
    - Trả về tóm tắt có thể ghi JSON: `{"method": str, "seconds": float, "boxes": [...]}`.
    - Đầu vào `captions` là `RUN/captions.json`, chỉ gồm phụ đề thật. Nhãn sơ đồ đã bị bỏ ở bước `text`, nên **không** được xóa
      nhãn.
  - `plates.scene_changes(video: Path, lag: float = 0.5) -> list[tuple[float, float]]`: các cặp (giây, độ mạnh) của chỗ chuyển
    cảnh, **kể cả chuyển cảnh mờ dần**. Cách đo: so mỗi khung với khung trước nó `lag` giây.
  - `vshort clean RUN`: ghi `RUN/clean.mp4`, ghi tóm tắt vào `RUN/clean.json`, rồi `run.mark("clean")`.

- [ ] **Bước 1: viết test cho interface**, không phụ thuộc cách làm.

```python
def test_clean_removes_a_caption_over_moving_line_art(tmp_path):
    # video 2 s, 720x1280, 30 fps: giấy kem có gradient trôi 1 px/khung và một nét chì chéo đi qua vùng y 900–962;
    # từ 0.5 tới 1.5 s có ô phụ đề xám D6DEE2 với "chữ" tối ở y 900–962, x 150–570; truth.mp4 là cùng video không có ô
    src, truth = _caption_video(tmp_path)
    caps = [Fragment(0, 0.5, 1.5, 900, 962, "to process it,")]
    plates.clean(src, caps, tmp_path / "clean.mp4", LAMA, inpaint=_oracle(truth))  # oracle: trả đúng vùng của truth.mp4 tại khung đó
    for t in (0.2, 0.7, 1.0, 1.3, 1.8):
        out, ok = frame_at(tmp_path / "clean.mp4", t, gray=True), frame_at(truth, t, gray=True)
        assert np.abs(out[880:990].astype(int) - ok[880:990]).mean() < 4   # không còn ô, không vệt
        assert np.abs(out[:800].astype(int) - ok[:800]).mean() < 2         # phần khác không bị đụng

def test_clean_erases_the_watermark_and_keeps_length(tmp_path): ...   # probe(out).duration == probe(src).duration ± 1 khung

def test_scene_changes_sees_a_dissolve(tmp_path):
    # cảnh xám 60 từ 0–1 s, mờ dần 1.0–1.5 s sang xám 180, giữ tới 3 s; lúc 2.2 s có một hình nhỏ (5 % khung) bật ra
    times = [t for t, _ in plates.scene_changes(_dissolve_video(tmp_path))]
    assert len(times) == 1 and 1.0 <= times[0] <= 1.6
```

`_oracle(truth)` trả về vùng của `truth` tại khung đang vá. Vì vậy cách nào chỉ dán một miếng vá cho cả đoạn có nét chì đang trôi
sẽ **trượt** test đầu. Đó là chủ ý.

- [ ] **Bước 2: chạy, xác nhận trượt.**

Run: `… pytest tests/test_plates.py -q`. Expected: FAIL với `AttributeError: module 'vshort.plates' has no attribute 'clean'`.

- [ ] **Bước 3: làm `scene_changes`.**
  - Khung xám nhỏ (`[::4, ::4]`), 10 khung/s. Lấy trung bình |khung t − khung t−lag|.
  - Lấy các đỉnh cục bộ trên ngưỡng, cách nhau ≥ 1 s.
  - Chọn ngưỡng sao cho hình nhỏ bật ra không tính là chuyển cảnh, và Rails tìm ra chỗ chuyển tranh chì → sơ đồ ở ~10 s.

- [ ] **Bước 4: đo các cách xóa** trên Rails, BOSSAI (pve2, `~/notebooklm-videos/<slug>`) và netamloader (Mac,
  `~/notebooklm-videos/netamloader`). Đo theo thứ tự từ rẻ tới đắt; cách đầu tiên qua bước 6 thì dùng.
  - (a) **Một miếng vá cho mỗi (cảnh thật, dải phụ đề), khi viền quanh ô đứng yên.**
    - Cảnh thật cắt theo `scene_changes`.
    - Đứng yên nghĩa là vòng 8 px quanh ô gần như không đổi suốt cảnh.
    - Ví dụ Rails 10–62 s: sơ đồ trên giấy, dải phụ đề ở đáy không có nét nào.
  - (b) **Cảnh có chuyển động:** đo xem vòng quanh ô có dịch hay phóng **cùng một kiểu** không (phase correlation trên vòng). Nếu có,
    vá một lần mỗi cảnh rồi biến hình miếng vá theo chuyển động đo được.
  - (c) **Dự phòng:** LaMa ở khung mốc mỗi ~1 s, trộn tuyến tính giữa hai mốc, mép mềm vài px.
    - Thử thêm LaMa ở nửa độ phân giải khi lỗ chỉ nằm trên giấy.
    - Thử 4 tiến trình × 6 luồng so với 1 × 24 luồng.
    - Đã đo trên pve2: một lần LaMa mất 4,6 s với khung cắt 304 × 720, và 12,9 s với 560 × 720.

  Các cách được trộn với nhau theo từng cảnh. Ghi cách đã chọn cho mỗi ô vào tóm tắt `method`/`boxes`.

- [ ] **Bước 5: làm `plates.clean` và `cmd_clean`** theo cách đã chọn.
  - Đọc khung bằng `media.iter_frames(gray=False)`, sửa bằng numpy, đẩy rawvideo qua ffmpeg, như `render_video` đang làm.
  - Dùng `-vf WATERMARK`, `-crf 12`, `yuv420p`.
  - Ô phủ thêm `0.1` s trước và sau mỗi mảnh phụ đề, để bắt khung phụ đề hiện dần.
  - Nếu chọn cách (c), ghi `# ponytail:` nêu trần thời gian và hướng nâng cấp.

- [ ] **Bước 6: kiểm đạt trên cả 3 video.** Ghi số liệu vào commit message.
  1. **Sạch:**
     - ảnh ghép khung mỗi 0,5 s, và mỗi 0,1 s quanh từng chỗ trong `scene_changes`;
     - không còn chữ Anh, ô nhạt hay vết cắt ngang hình;
     - đặc biệt ở 4 s và 30 s của Rails, chỗ `vet-o-trong.jpg` từng lộ.
  2. **Màu:** với mỗi ô và mỗi khung lấy mẫu, |trung bình vùng vá − trung bình vòng 8 px ngoài ô| ≤ 3 mức xám, ở phân vị 95.
  3. **Không biến dạng:** ở một ô đè lên nét vẽ, xem 3 s liền ở 30 khung/s (xuất mp4 cắt vùng đó rồi xem từng khung). Trung bình
     |vùng vá khung n − khung n−1| không được lớn hơn của vòng ngoài ô cộng 2.
  4. **Thời gian:** wall time trên pve2 ≤ 10 phút cho video dài nhất trong 3 video.

- [ ] **Bước 7: chạy toàn bộ test, rồi commit**:
  `git add vshort/plates.py vshort/cli.py tests/test_plates.py` +
  `git commit -m "feat(clean): old captions removed frame by frame …"`.

---

### Task 2: `retime.py`: đoạn nguồn → đoạn đích

**Files:**
- Create: `vshort/retime.py`
- Test: `tests/test_retime.py`

**Interfaces:**
- Consumes: `script.Sentence`, `fit.Placement`, `stills.BLANK`, `media.iter_frames`.
- Produces:

```python
FAST, SLOW, SLOW_AFTER, STEP = 1.5, 1.25, 1.5, 0.1

@dataclass(frozen=True)
class Piece:
    id: int
    src: float       # s trong clean.mp4: hình của câu bắt đầu
    src_end: float   # s trong clean.mp4: khung cuối được phát, rồi giữ nó
    dst: float       # s trong final.mp4
    dst_end: float
    speed: float     # giây nguồn mỗi giây đích khi đang phát (>1 nhanh, <1 chậm)
    hold: float      # s giữ khung src_end ở cuối
    dropped: float   # s đuôi nguồn bị bỏ vì vượt FAST

def pieces(lines: list[Sentence], placements: list[Placement], total: float, stop: float,
           blank: Callable[[float], bool] = lambda t: False) -> list[Piece]
def to_output(ps: list[Piece], t: float) -> float | None   # giờ nguồn → giờ đích; None nếu rơi vào đuôi bị bỏ hay ngoài mọi đoạn
def blank_at(video: Path, fps: float = 10) -> Callable[[float], bool]   # độ lệch chuẩn xám < stills.BLANK ở mẫu gần nhất
```

**Quy tắc:**
- `lines` là `script.merged(...)`, cùng id và cùng thứ tự với `placements` (assert).
- **Đoạn nguồn:** `[0 nếu i == 0 else lines[i].start, lines[i+1].start]`. Câu cuối kết thúc ở `min(lines[-1].end, stop)`. Mọi mốc
  bị kẹp ≤ `stop`.
- **Đoạn đích:** `[0 nếu i == 0 else placements[i].start, placements[i+1].start or total]`.
- Gọi S là độ dài đoạn nguồn, T là độ dài đoạn đích:
  - S ≥ T: `speed = min(S/T, FAST)`, `src_end = src + speed*T`, `dropped = S − speed*T`.
  - S < T và T − S ≤ SLOW_AFTER: `speed = 1`, `hold = T − S`.
  - Còn lại: `speed = max(S/T, 1/SLOW)`, `hold = T − S/speed`.
- **Khung giữ gần trắng** (chỉ xét khi `hold > 0`): lùi `src_end` từng `STEP` tới khung đầu tiên không trắng, nhưng không lùi quá
  `src`. Rồi tính lại `hold = T − (src_end − src)/speed`. Cả đoạn trắng thì để nguyên.

- [ ] **Bước 1: viết test.** Giá trị kỳ vọng chính xác tới 1e-6:

```python
def test_shorter_vietnamese_speeds_up():                    # S=6, T=5 → speed 1.2, hold 0, dropped 0, src_end = src+6
def test_speed_is_capped_and_the_tail_dropped():            # S=9, T=4 → speed 1.5, src_end = src+6, dropped 3
def test_longer_vietnamese_plays_at_1x_then_holds():        # S=4, T=5 → speed 1, hold 1.0
def test_long_hold_slows_down_first():                      # S=4, T=7 → speed 0.8, hold 2.0
def test_first_line_starts_at_zero():                       # lines[0].start = 0.1 → src 0.0; placements[0].start = 0.2 → dst 0.0
def test_last_line_stops_before_notebooklm_logo():          # lines[-1].end = 81.07, stop = 79.7 → src_end ≤ 79.7
def test_blank_hold_frame_steps_back_to_a_drawn_one():      # S=4, T=5, blank(t) = t > src+3.5 → src_end = src+3.5, hold 1.5
def test_pieces_tile_the_output():                          # dst[i+1] == dst_end[i], dst_end[-1] == total, dst[0] == 0
def test_a_very_short_line_is_still_a_valid_piece():        # T = 0.3, S = 3 → speed 1.5, dropped 2.55, dst_end > dst
def test_to_output_maps_and_skips_dropped_tails():          # t trong đoạn → dst + (t−src)/speed; t trong đuôi bỏ → None
def test_rails_numbers_match_the_spike():                   # 16 câu Rails (số trong spike: câu 7 S 7.20 → T 5.50 → speed 1.31)
```

- [ ] **Bước 2: chạy, xác nhận trượt** (`ModuleNotFoundError: vshort.retime`).
- [ ] **Bước 3: làm `retime.py`** theo quy tắc trên.
- [ ] **Bước 4: chạy, xác nhận qua.**
- [ ] **Bước 5: commit**: `git add vshort/retime.py tests/test_retime.py`.

---

### Task 3: hiệu ứng âm thanh ở chỗ chuyển cảnh lớn

**Files:**
- Modify: `vshort/sound.py`. Thay `cues(segs, scenes)`; chưa ai gọi nó cho tới Task 5.
- Test: `tests/test_sound.py`. Thay các test của `cues` cũ.

**Interfaces:**
- Consumes: `plates.scene_changes` (Task 1), `retime.Piece`, `retime.to_output` (Task 2).
- Produces: `sound.cues(changes: list[tuple[float, float]], ps: list[Piece]) -> list[Cue]` và `NAMES = ("whoosh", "pop", "whoosh")`.

**Quy tắc:**
- Đổi giờ nguồn sang giờ đích bằng `to_output`.
- Bỏ những chỗ ra `None` và những chỗ nằm trong `ps[0]`.
- Chọn tham theo độ mạnh, chỗ mạnh nhất trước. Mỗi chỗ phải cách mọi chỗ đã chọn ≥ `SPACE`. Tối đa 3.
- Xếp theo giờ rồi đặt tên lần lượt theo `NAMES`.

- [ ] **Bước 1: viết test.**
  - `test_three_strongest_changes_get_effects_in_time_order`: 5 chỗ với độ mạnh khác nhau → đúng 3 chỗ mạnh nhất, tên
    whoosh/pop/whoosh theo giờ.
  - `test_no_effect_in_the_title_line_nor_in_a_dropped_tail`.
  - `test_changes_closer_than_space_keep_the_stronger`.
- [ ] **Bước 2: chạy, xác nhận trượt.**
- [ ] **Bước 3: làm.** Xóa `cues` cũ và docstring nói về canvas/thẻ.
- [ ] **Bước 4: chạy, xác nhận qua.**
- [ ] **Bước 5: commit**: `git add vshort/sound.py tests/test_sound.py`.

---

### Task 4: `vs-visuals` chỉ vá chữ; giờ chữ sai bắt đầu hiện

**Files:**
- Modify: `vshort/visuals.py`.
  - `validate` từ chối `kind` khác `"patch"` với lỗi: `kind 'svg' không còn dùng: chỉ còn 'patch' (vá chữ sai)`.
  - Thêm `appear_time`.
  - `svg_frame`, `pencil`, `ui_problems` để Task 7 xóa cùng chỗ gọi.
- Modify: `vshort/cli.py:cmd_visuals`.
  - Chỉ còn chỗ vá; bỏ `motion.clashes`.
  - `frames.json` chỉ gồm các câu có vá: `{"id", "file": "frames/<id>.png", "from": <giờ nguồn>}`.
- Modify: `claude/agents/vs-visuals.md`.
  - Chỉ vá chữ **sai dữ kiện** so với brief hay lời Việt: số, phiên bản, tên, ngày.
  - Không vá chữ chỉ lệch cách nói. Chữ tiếng Anh đúng thì giữ.
  - Bỏ toàn bộ phần `svg`/`photo`/tư liệu thật.
- Test: `tests/test_visuals.py`, `tests/test_cli.py` (phần visuals).

**Interfaces:**
- Consumes: `RUN/clean.mp4` (Task 1), `stills.json` (`t` của từng câu), `script.merged`.
- Produces:
  - `visuals.appear_time(video: Path, a: float, b: float, box: tuple[int, int, int, int], still: np.ndarray) -> float`:
    - mẫu 10 khung/s trong `[a, b]`; `d(t)` = trung bình |vùng `box` xám của khung t − cùng vùng của `still`|;
    - `d(a) ≤ SAME = 6` thì trả `a` (chữ đã có sẵn);
    - không thì trả `max(a, t − 0.1)` với t đầu tiên mà `d(t) ≤ 0.75 · d(a)`;
    - không có t nào thì trả `b`.
  - `cmd_visuals` lấy `a` là đầu đoạn nguồn của câu (0 với câu đầu, như `retime`), `b` là `stills.json` `t`. `box` là hộp bao mọi
    chỗ vá của câu đó.

- [ ] **Bước 1: viết test.**
  - `test_appear_time_when_text_is_drawn_mid_line`: vùng trống tới 1.0 s rồi hiện chữ → trả về 0.9 ± 0.1.
  - `test_appear_time_when_text_is_there_from_the_start`: trả về `a`.
  - `test_validate_rejects_svg_and_photo`.
  - `test_cmd_visuals_writes_only_patched_lines_with_from`.
- [ ] **Bước 2: chạy, xác nhận trượt.**
- [ ] **Bước 3: làm.**
- [ ] **Bước 4: chạy toàn bộ test.** Test cũ về `svg`/`photo` thì xóa; test cũ về `patch_text` phải còn qua.
- [ ] **Bước 5: commit** các file trên, add theo tên.

---

### Task 5: dựng video bằng đồ thị ffmpeg (`render_pieces`) và nối vào `vshort render`

**Files:**
- Modify: `vshort/render.py`. Thêm `render_pieces`. Code cũ (`segments`, `render_video`…) để Task 7 xóa.
- Modify: `vshort/cli.py:cmd_render`. Viết lại.
- Test: `tests/test_render.py`, `tests/test_cli.py` (phần render).

**Interfaces:**
- Consumes:
  - `retime.pieces`, `retime.to_output`, `retime.blank_at` (Task 2);
  - `sound.cues` (Task 3), `plates.scene_changes` (Task 1);
  - `frames.json` có `from` (Task 4);
  - `render.build_ass`, `fit.phrase_times`, `sound.master`, `stills.NLM_OUTRO`.
- Produces: `render.render_pieces(ps: list[Piece], clean: Path, stills: list[tuple[Path, float, float]], ass: Path, audio: Path, total: float, out: Path, outro: Path | None = OUTRO) -> None`
  - `stills` là (ảnh, hiện từ, tới) theo giờ đích.
  - Đồ thị:
    1. mỗi đoạn `trim → setpts=(PTS-STARTPTS)/speed → tpad=stop_mode=clone:stop_duration=hold → fps=30 → trim=duration=dst_end-dst`;
    2. `concat`;
    3. ảnh vá đè lên bằng `overlay` với `enable='between(t,from,to)'`;
    4. `ass` (cwd là thư mục của ass, như `render_video`);
    5. `scale=out_color_matrix=bt709…,setparams…`;
    6. nối outro: kéo dài khung cuối thêm `XF` rồi `xfade=fade:duration=XF:offset=total`;
    7. tiếng: `apad`, `-t total + độ dài outro`.
  - Ghi ra file tạm rồi `os.replace`, như `render_video`.
  - Vẫn ghi `RUN/pieces.json` (danh sách `asdict(Piece)`) cho reviewer và lời nhắn cuối.

`cmd_render` mới:
1. đọc `timeline.json`, `script.vi.json`, `sentences.en.json`, rồi `merged`;
2. đòi `clean.mp4`, thiếu thì báo "chạy `vshort clean`" với mã `BAD_INPUT`;
3. tính `stop = probe(source.mp4).duration − NLM_OUTRO`;
4. tính `pieces`, ghi `pieces.json`;
5. ảnh vá: dùng `frames.json`, quy `from` sang giờ đích bằng `to_output`. Nếu `None` hay vượt `src_end` thì lấy đầu phần giữ
   khung. "tới" là `dst_end` của câu;
6. `build_ass(phrase_times(...))`;
7. `cues(scene_changes(clean), pieces)` → `sfx.json` → `sound.master` → `mix.wav`;
8. `render_pieces`;
9. `mark("render")`.

Lệnh này không còn kiểm `motion`, `shots`.

- [ ] **Bước 1: viết test** trên video tổng hợp có màu mã hóa giờ.
  - `clean.mp4` 10 s, 720×1280, 30 fps, mức xám `= 10 + 20·floor(t)`.
  - Outro tổng hợp 0,5 s.

```python
def test_render_pieces_shows_the_right_source_second(tmp_path):  # đoạn speed 1.5: đích 1.0 s → nguồn 1.5 s → mức 30
def test_render_pieces_holds_the_last_played_frame(tmp_path):   # trong phần hold: mức của src_end
def test_render_pieces_overlays_a_patched_still_only_in_its_window(tmp_path):  # ảnh đỏ: có trong [from,to), không có trước from
def test_render_pieces_length_and_bt709(tmp_path):              # duration ≈ total + 0.5 ± 1 khung; color_space=bt709
def test_cmd_render_writes_pieces_json_and_needs_clean(tmp_path)
```

- [ ] **Bước 2: chạy, xác nhận trượt.**
- [ ] **Bước 3: làm `render_pieces` và `cmd_render`.**
- [ ] **Bước 4: chạy toàn bộ test.**
- [ ] **Bước 5: thử thật trên Rails ở pve2,** bản sao tạm, không đè `final.mp4`.
  - Kết quả phải giống bản thử: 8 câu tua 1,1–1,3 lần, giữ ≤ 0,5 s (trừ câu chốt).
  - Thời gian dựng phải ≤ thời gian `render_video` cũ.
- [ ] **Bước 6: commit.**

---

### Task 6: lời kêu gọi không lặp

**Files:**
- Modify: `vshort/script.py:check_script`. Thêm `RATIO = 2.5`.
- Modify: `claude/agents/vs-translator.md`, luật 2.
- Test: `tests/test_script.py`.

**Quy tắc kiểm** (bỏ qua câu đầu, vì câu đầu là tiêu đề):
- Số từ tiếng Anh của một câu là tổng số từ của câu đó và các câu tiếng Anh để trống liền sau nó. Đó cũng là phần thời gian nó
  nhận theo `merged`.
- Nếu `syllables(phrases) > RATIO × số từ tiếng Anh` thì báo lỗi:
  `Câu {id}: lời Việt {n} âm tiết, gấp {r:.1f} lần câu Anh ({w} từ): đừng nối ý mà video tiếng Anh đã nói ở câu khác (lời kêu gọi, câu chốt)`.

**Luật 2 mới trong `vs-translator.md`:**
- Giữ ý "brief thắng khi sai dữ kiện".
- Đổi phần câu móc/câu chốt/lời kêu gọi thành: *"Chỉ thêm câu chốt hay lời kêu gọi của brief khi video tiếng Anh không nói ý đó ở
  bất kỳ câu nào. Đã nói ở câu khác thì không nối thêm vào câu cuối."*

- [ ] **Bước 1: viết test.**
  - `test_rails_closing_line_with_repeated_call_to_action_fails`: chép nguyên câu 16 của Rails, tiếng Anh 15 từ, tiếng Việt như trong
    spec.
  - `test_ordinary_line_passes`.
  - `test_title_line_is_exempt`.
- [ ] **Bước 2: chạy, xác nhận trượt.**
- [ ] **Bước 3: làm.**
- [ ] **Bước 4: chạy `vshort check` trên 5 video cũ ở `~/notebooklm-videos` trên Mac.** Không được thêm lỗi tỉ lệ nào. Có thì nâng
  `RATIO` và ghi số đã đo vào commit.
- [ ] **Bước 5: commit.**

---

### Task 7: quy trình `auto`, CLI và xóa phần hình tự vẽ

**Files:**
- Modify: `vshort/auto.py`.
  - `_flow`: bỏ `_an_du` và luồng `_design`.
  - `_build`: `tts` song song với `clean → stills → visuals`, rồi `timeline`, rồi `render`.
  - `_fix`: chỉ còn `visuals` và `translator`. Danh sách `unmark` thành
    `"approve_script", "tts", "timeline", "render", "stills", "visuals"`.
  - `read_review`: `agent` chỉ còn một trong `("visuals", "translator", "none")`.
  - `_finish`:
    - bỏ các dòng hình động, nhịp hình, hình mới;
    - thêm dòng "Co giãn: câu X giữ 2,3 s; câu Y bỏ đuôi 1,2 s" từ `pieces.json`. Chỉ ghi câu giữ > 2 s hay bỏ đuôi > 0,5 s; không
      có thì ghi "không câu nào phải giữ hay bỏ đuôi".
  - Xóa: `_an_du`, `_design`, `_canvas`, `_motion`, `_no_motion`, `publish_shapes`, `git` (nếu không còn ai dùng), `_shots*`,
    `_check_shots`, `_vshort_shots`, phần dự phòng nhịp hình của `_vshort_render`, các prompt `AN_DU`, `MOTION_*`, `NHIP`, phần
    `motion`/`shots` của `FIX_HOW`, và `TIMEOUT` của 3 agent bị xóa.
- Modify: `vshort/cli.py`. Xóa `cmd_motion`, `cmd_shots` và mọi helper `_shots*`/`_ShotLines`/`_motion`/`_bind`/`_said`/`_beat_plan`,
  `cmd_plates`, `SHOT_KINDS`, các import thừa. `cmd_status`: bước `clean` thay `plates`, bỏ `motion`.
- Modify: `vshort/render.py`. Xóa `Segment`, `segments`, `_kinds`, `planned_camera`, `last_focus`, `_camera`, `_half_fade`,
  `view`, `draw`, `_Planned`, `render_video`, `clean_video`, cùng các hằng chỉ chúng dùng. Giữ `build_ass` và các hàm của nó,
  `end_card`, `export_outro`, `_logo`.
- Modify: `vshort/plates.py`. Xóa `build_plates`, `Plate`, `_clean_time`, `_moving` nếu cách đã chọn ở Task 1 không dùng.
- Modify: `vshort/visuals.py`. Xóa `svg_frame`, `pencil`, `ui_problems` và phần chỉ chúng dùng.
- Delete:
  - `vshort/motion.py`, `kit.py`, `shapes.py`, `shots.py`, `cards.py`, `camera.py`;
  - `tests/test_motion.py`, `test_kit.py`, `test_shapes.py`, `test_shots.py`, `test_cards.py`, `test_camera.py`, `test_examples.py`,
    `test_props.py`;
  - `examples/motion/`, `assets/shapes/`;
  - `claude/agents/vs-an-du.md`, `vs-motion.md`, `vs-nhip.md`.
- Modify: `scripts/update-server.sh`. Sau vòng `ln -sf` thêm
  `find "$HOME/.claude/agents" -maxdepth 1 -name 'vs-*.md' -xtype l -delete`.
- Mac: `rm ~/.claude/agents/vs-an-du.md ~/.claude/agents/vs-motion.md ~/.claude/agents/vs-nhip.md`. Đây là các symlink sẽ treo.
- Test: `tests/test_auto.py`, `test_cli.py`, `test_render.py`, `test_plates.py`, `test_visuals.py`.

**Interfaces:**
- Consumes: mọi thứ từ Task 1–6.
- Produces: các bước của một video, theo đúng tên mốc mà Task 8 dùng: `research`, `brief_check`, `approve_brief`, `source`, `fetch`,
  `detect`, `transcribe`, `text`, `translate`, `approve_script`, `clean`, `stills`, `visuals_agent`, `visuals`, `tts`, `timeline`,
  `render`, `review<r>`, `fix<r>_visuals`, `fix<r>_translator`, `fixed<r>`, `cover`.

- [ ] **Bước 1: viết test.**
  - `test_build_order_clean_stills_visuals_then_timeline_render`: ghi lại thứ tự `run_vshort`.
  - `test_old_run_gets_clean_and_ignores_motion_marks`: run có mốc `plates`, `motion`, `shots`, `motion_design` nhưng không có
    `clean` → `_build` chạy `clean` và không gọi agent nào ngoài `vs-visuals`.
  - `test_fix_round_routes_only_visuals_and_translator`.
  - `test_finish_reports_long_holds_from_pieces_json`.
- [ ] **Bước 2: chạy, xác nhận trượt.**
- [ ] **Bước 3: sửa `auto.py`, `cli.py`.**
- [ ] **Bước 4: xóa file và code** theo danh sách trên.
- [ ] **Bước 5: kiểm không còn dấu vết.**
  - Lệnh: `grep -rnE "motion|shots|cards|\bkit\b|shapes|camera|an_du|an-du|nhip|vs-nhip|vs-motion|vs-an-du" vshort tests claude scripts`.
  - Chỉ được còn những chỗ hợp lý, như "motion" trong tên biến về chuyển động video của `plates.py`.
  - Kiểm cả `~/.claude/skills/kallaway-style` không import `vshort`. Đã kiểm 06/11: không import.
- [ ] **Bước 6: chạy toàn bộ test.**
- [ ] **Bước 7: commit.** Dùng `git add` và `git rm` theo tên.

---

### Task 8: soát cuối, bàn điều khiển, skill, tài liệu

**Files:**
- Modify: `claude/agents/vs-reviewer.md`. Viết lại danh sách kiểm theo spec mục 7.
  - Đầu vào: `final.mp4`, `source.mp4`, `narration.wav`, `timeline.json`, `pieces.json`, `frames.json` (câu vá, `from`),
    `visuals.json`, `stills.json`, `script.vi.json`, `brief.vi.md`.
  - **Kiểm 1:** chữ phụ đề Anh, ô vá nhạt, vết cắt, watermark. Khung mỗi 0,5 s, và mỗi 0,1 s quanh các `dst` trong `pieces.json`.
  - **Kiểm 2:** chỗ nối hai câu và câu có `speed` lớn nhất: 6 khung liền, không giật.
  - **Kiểm 3:** khung gần trắng, giữ ngưỡng std 8.
  - **Kiểm 4:** lặng dài, giữ như cũ.
  - **Kiểm 5:** hình khớp lời.
  - **Kiểm 6:** chữ Anh trong hình trái lời Việt → `agent: "visuals"`.
  - **Kiểm 7:** phụ đề khớp lời.
  - **Kiểm 8:** `hold > 2` trong `pieces.json`. Bỏ qua câu có trong `frames.json`. Lời bị độn → `translator`, còn lại → `none`.
  - Bỏ mọi kiểm hình động, nhịp hình, tư liệu vẽ lại.
  - `agent` ∈ `visuals | translator | none`.
- Modify: `vshort/auto.py`. Prompt `REVIEW`/`RECHECK`/`FIX_HOW` khớp danh sách trên.
- Modify: `vshort/stages.py`.
  - `STAGES` build: "Gemini đọc, xóa phụ đề Anh từng khung, vá chữ sai".
  - `STAGES` render: "Co giãn video gốc theo lời, ghép giọng, phụ đề, outro".
  - `STEPS_OF`: notebooklm `("source", "fetch")`; build `("clean", "stills", "visuals", "visuals_agent", "tts")`; render
    `("timeline", "render")`.
  - Bỏ `SIDE` và logic của nó.
  - `WHAT_FIX = {"visuals": "chữ sai", "translator": "bản dịch"}`.
  - `LABELS`: bỏ motion/shots; `visuals_agent`: "Soát chữ sai trong hình".
  - `DEFAULT_SECONDS` build/render: đặt theo số đo ở Task 1/5.
- Modify: `vshort/queue.py`, `STEPS`:
  - `("clean", "Xóa phụ đề cũ")` thay `plates`;
  - bỏ `motion`, `shots`;
  - `visuals` → "Vá chữ sai".
- Modify: `web/src/Stages.tsx:31`: chỉ còn `'chưa ước được'`.
- Modify: `claude/skills/video-short/SKILL.md`:
  - mô tả skill: bỏ "hình động vẽ tay…, tư liệu thật vẽ lại", thay bằng "hình là video NotebookLM co giãn theo lời, xóa phụ đề Anh
    từng khung, vá chữ sai";
  - mã 20: bỏ `an-du.md`;
  - mã 0: bỏ "đoạn hình động", thêm "co giãn".
- Modify: `DESIGN.md`, ghi chú đầu: trỏ sang spec 2026-11-06 và nói hình động/nhịp hình đã bỏ.
- Test: `tests/test_stages.py`, `test_queue.py`, `test_auto.py`, `test_web.py` nếu có tên chặng.

- [ ] **Bước 1: sửa test** về tên chặng và bước cho khớp danh sách trên. Chạy, xác nhận trượt.
- [ ] **Bước 2: sửa code, agent, skill, tài liệu.**
- [ ] **Bước 3: chạy toàn bộ test, rồi `cd web && npm run build && npm run lint`.**
- [ ] **Bước 4: commit.**

---

### Task 9: deploy và kiểm cuối trên 3 video

- [ ] **Bước 1: push, rồi deploy.**
  - Lệnh: `ssh pve2 'systemd-run --user --unit vshort-update --collect -E PATH="$PATH" ~/video-pipeline/scripts/update-server.sh'`.
  - Chờ `journalctl --user -u vshort-update` in "đã cập nhật X → Y".
  - Kiểm `~/.claude/agents` trên pve2 không còn link treo.
- [ ] **Bước 2: tạo bản sao thử trên pve2.** Video cũ không bị đụng.
  - Lệnh cho mỗi `slug` của Rails (`critical-rails-flaw-lets-attackers-write-server-files-via`), BOSSAI
    (`phan-tich-chien-dich-tan-cong-mang-su-dung-12-ai-agents-tai`) và ClawHub (`hugging-face-clawhub-phat-tan-ma-doc-tro-ly-ai-co-the-bi`):
    `cp -a ~/notebooklm-videos/<slug> ~/thu-hinh-goc/<slug>`.
  - Trong bản sao, xóa các mục `svg`/`photo` của `visuals.json`.
  - Nếu câu chốt có lời kêu gọi lặp (`vshort check` báo lỗi tỉ lệ), sửa `script.vi.json` của bản sao về đúng câu chốt rồi chạy lại
    `vshort tts`. Chỉ câu đổi bị đọc lại. Ghi lại câu nào đã sửa.
- [ ] **Bước 3: dựng.**
  - Trong mỗi bản sao: `vshort clean`, `stills`, `visuals`, `timeline`, `render`. Ghi thời gian từng bước.
  - Rồi chạy `vs-reviewer` bằng `claude -p` như `auto._review` vòng 0, và ghi chi phí.
- [ ] **Bước 4: đưa về Mac.**
  - `rsync` mỗi `final.mp4` và `source.mp4` về `~/Movies/vshort-thu/<tên>/`.
  - Báo Tai: đường dẫn, kết luận reviewer, thời gian `clean` và `render`, chi phí ước cho một video mới, các câu phải giữ hay bỏ đuôi.
- [ ] **Bước 5: cập nhật memory.**
  - Ghi vào `hinh-goc-notebooklm.md`: trạng thái deploy, số đo, việc còn chờ Tai.
  - Xóa hoặc đánh dấu bỏ `nhip-hinh-feature.md` và `motion-metaphor-branch.md`.
