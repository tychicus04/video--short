# Bàn điều khiển giao diện mới, giai đoạn A — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bàn điều khiển `vshort-web` theo phong cách Clipcup, gồm:
- mỗi video hiện 10 chặng, kèm thời gian thật, thời gian còn lại và %;
- tab Đăng bài cho tải ảnh bìa Gemini lên.

**Architecture:**
- `vshort/timing.py` ghi giờ bắt đầu và kết thúc của từng bước vào `RUN/times.json`. Có hai chỗ móc: `auto.run_vshort`/`run_claude`
  và `Run.mark`.
- `vshort/stages.py` là hàm thuần. Nó biến `state.json` + `times.json` + `auto.json` và thời gian thường (trung vị 5 video gần nhất)
  thành 10 chặng, thời gian còn lại và %.
- `vshort/web.py` trả kết quả đó trong `/api/state` và `/api/runs/<slug>`, và nhận ảnh Gemini qua một lệnh ghi JSON.
- Giao diện React chỉ hiển thị, không tự tính.

**Tech Stack:**
- Python 3.12, Starlette, Pillow, pytest.
- React 19, Tailwind 4, shadcn, Vite.
- Không thêm thư viện.

**Spec:** `docs/superpowers/specs/2026-11-05-giao-dien-moi-va-dang-cms-design.md` (phần "Giai đoạn A"). Bản phác Tai đã duyệt:
https://claude.ai/artifact/GuGnqtfibBsV8AWYkoWEh5 (3 màn: Trang chủ, Video đang chạy, Video xong). Nếu không mở được bản phác thì
dùng bảng màu ở Global Constraints và mô tả màn hình trong spec.

## Global Constraints

- **Repo và commit**
  - Làm thẳng trên `main`, không tách nhánh hay worktree (Tai dặn). Mỗi task commit rồi `git push`.
  - Dòng cuối mỗi commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Thư viện và font**
  - Không thêm gói Python hay npm.
  - Font **Plus Jakarta Sans**, font của Clipcup, có bộ ký tự tiếng Việt (Google Fonts, giấy phép OFL).
    - Tải 3 file woff2 (vietnamese, latin-ext, latin; trục độ đậm 500–700) từ
      `https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500..700` vào `web/src/fonts/` và commit.
    - Nạp bằng `@font-face` trong `web/src/index.css`, chép `unicode-range` từ CSS của Google. Không thêm gói npm.
- **Chữ trên trang**
  - Mọi chữ hiện ra đều bằng tiếng Việt, gọi Tai là "bạn".
  - Thời gian ghi dạng "khoảng 21 phút", "dưới 1 phút", "lâu hơn thường lệ"; giờ dự kiến dạng "~14:33".
- **Lệnh ghi**
  - Mọi lệnh ghi đi qua `_post` trong `vshort/web.py`: cần mã truy cập, chỉ nhận `Content-Type: application/json`.
  - Ảnh Gemini gửi dạng base64 trong JSON. **Không** multipart, để giữ hàng rào CSRF.
- **Chặng và thời gian**
  - 10 chặng theo đúng thứ tự và nhãn của spec: Tìm hiểu, Duyệt brief, NotebookLM làm video, Lấy phụ đề, Dịch, Duyệt bản dịch,
    Giọng đọc và hình, Dựng video, Soát và sửa, Ảnh bìa và xuất.
  - Thời gian thường = trung vị của `HISTORY = 5` video xong gần nhất có `times.json`; thiếu thì dùng `DEFAULT_SECONDS`.
  - Chặng đang chạy còn lại = max(thường − đã chạy, `FLOOR = 60` s).
  - Không gộp thời gian chờ Tai vào một con số.
- **Ảnh Gemini**
  - Khổ `"9x16"` và `"16x9"`. Lệch tỉ lệ tối đa `RATIO_TOL = 0.05`.
  - Đổi sang JPEG, cạnh dài nhất ≤ `MAX_SIDE = 2048`. Ảnh gốc tối đa `MAX_UPLOAD = 15_000_000` byte.
  - Lưu tại `cover/gemini-9x16.jpg` và `cover/gemini-16x9.jpg`.
- **Bảng màu**: style đặt tên của Clipcup, đọc qua Figma MCP ngày 05/11/2026 ở màn Home `31324:1479` và Your Video `31335:2660`.
  Chỉ có giao diện tối. Ô ghi "(không có trong Clipcup)" là màu tự thêm để chữ đủ tương phản.

  | Vai trò | Màu |
  |---|---|
  | nền | `#0E1015` (Main Colors/Primary) |
  | thẻ | `#21232C` (Main Colors/DarkBlue) |
  | ô nằm trên thẻ (chip thời lượng, nút biểu tượng, ô nhập) | `#0E1015`, tức màu nền |
  | viền | Clipcup không dùng viền: các khối tách nhau bằng màu nền. Viền focus là vòng `#6723FF` |
  | chữ | `#FEFEFE` (Additional Colors/White) |
  | chữ phụ | `#9CA4AB` (Grayscale 60; 7,6:1 trên nền, 6,2:1 trên thẻ) |
  | chữ mờ | `#66707A` (Grayscale 80). Chỉ dùng cho số phụ (như tổng thời lượng), không dùng cho chữ cần đọc: chỉ 3,8:1 |
  | nhấn | nút `#6723FF` (Main Colors/third), chữ trên nút `#FEFEFE`; chữ tím trên nền tối `#B7A3FF` (không có trong Clipcup: `#6723FF` trên nền chỉ 3:1) |
  | xong | `#4ADE80` (Alerts/Success), dùng cho chữ, chấm, và nền huy hiệu ở 15 % độ đục |
  | chờ bạn | chữ `#FBBF24` trên `#2E2208` (không có trong Clipcup) |
  | lỗi | chấm và nền `#F41F52` (Alerts/Error); chữ lỗi `#F87171` (`#F41F52` trên thẻ chỉ 3,9:1) |

  - **Bo góc** (Clipcup): thẻ, ảnh thu nhỏ và nút nhỏ 8 px; nút chính và tab 12 px; huy hiệu dạng viên (30 px) chỉ cho nhãn nhỏ
    kiểu "Become Pro"; nút nổi tròn hẳn. Không có nút hay tab dạng viên thuốc.
  - **Tab**: một rãnh `#21232C`, bo 12 px, cao 50 px, chia đôi hoặc chia đều. Tab đang chọn có nền `#FEFEFE`, chữ `#21232C`
    đậm 14 px, bóng `-20px 10px 30px rgba(0,0,0,.25)`. Tab khác chữ `#FEFEFE` nửa đậm 14 px.
  - **Chữ** (thang của Clipcup, giãn chữ 0,5 %): 18/26 nửa đậm (tiêu đề khối); 16/24 đậm (tên mục); 14/22 nửa đậm hoặc đậm (nội dung);
    12/20 vừa hoặc nửa đậm (nút, phụ đề). Clipcup có cỡ 10/18 cho điện thoại; trên web chữ cần đọc không nhỏ hơn 12 px.
  - **Khoảng cách**: lề trang 24 px, giữa các khối 16 px, trong thẻ 8–12 px. Ảnh thu nhỏ phủ dải mờ
    `linear-gradient(to bottom, rgba(33,35,44,0), rgba(33,35,44,.94) 75%)` để chữ trên ảnh đọc được.
  - **Bóng**: nút nổi `0 10px 20px rgba(0,0,0,.2)`.
  - Tương phản chữ ≥ 4.5:1. Vùng bấm ≥ 44 px.
- **Kiểm và deploy**
  - Test Python: `.venv/bin/python -m pytest -q`. Giao diện: `cd web && npm run build && npm run lint`.
  - Test không gọi `claude` thật: `tests/conftest.py` đặt `auto.CLAUDE = ["false"]`.
  - Deploy chỉ bằng
    `ssh pve2 'systemd-run --user --unit vshort-update --collect -E PATH="$PATH" ~/video-pipeline/scripts/update-server.sh'`.
    Lệnh này đợi lúc không có video chạy.

## Review Focus

- **Video cũ không có `times.json`** (3 video đã xong, 5 thư mục chạy tay). Trang vẫn hiện 10 chặng theo `state.json`, thời gian
  thật để trống, không lỗi. → `test_view_without_times_uses_state_only` (Task 2).
- **Bước chết giữa chừng để lại giờ bắt đầu không có giờ kết thúc.** Lần chạy lại không được hiện "đã chạy 9 giờ".
  → `test_close_open_drops_unfinished_steps`, `test_run_auto_closes_open_steps_first` (Task 1).
- **`times.json` hỏng** (sửa tay, ghi dở). Danh sách và trang video vẫn mở được; coi như không có thời gian.
  → `test_read_broken_times_is_empty` (Task 1), `test_state_survives_broken_times` (Task 3).
- **Ảnh tải lên quá lớn, không phải ảnh, hoặc sai tỉ lệ.** Báo lỗi tiếng Việt rõ ràng, không ghi gì.
  → `test_save_gemini_refuses_*` (Task 4), `test_cover_upload_errors` (Task 4).
- **Bề ngang điện thoại (390 px).** Lưới video, danh sách chặng và tab xếp chồng hoặc xuống dòng, không cuộn ngang.
  → bước kiểm tay ở Task 9.

---

### Task 1: Ghi thời gian từng bước

**Files:**
- Create: `vshort/timing.py`
- Modify: `vshort/run.py` (`Run.mark`), `vshort/auto.py` (`run_vshort`, `run_claude`, `run_auto`, chỗ gọi `notebooklm(["source", …])` trong `_flow`)
- Test: `tests/test_timing.py`

**Interfaces:**
- Produces:
  - `timing.FILE = "times.json"`
  - `timing.start(run_dir: Path, step: str, now: float | None = None) -> None`: ghi `{"start": now}`. Bỏ `end` cũ. Giữ nguyên
    nếu bước đang mở (có `start`, chưa `end`).
  - `timing.end(run_dir: Path, step: str, now: float | None = None) -> None`: ghi `end`. Không có `start` thì chỉ ghi `end`.
  - `timing.read(run_dir: Path) -> dict[str, dict[str, float]]`: `{}` khi thiếu file, file hỏng hoặc không phải object.
  - `timing.close_open(run_dir: Path) -> None`: bỏ các bước có `start` mà chưa `end`.

- [ ] **Step 1: Write the failing tests** in `tests/test_timing.py`:
  - `test_start_end_round_trip`:
    - `start(d, "fetch", now=100)`, `end(d, "fetch", now=160)` → `read(d) == {"fetch": {"start": 100, "end": 160}}`.
    - `start(d, "fetch", now=200)` → `{"fetch": {"start": 200}}`.
  - `test_start_keeps_an_open_step`: `start(d, "cover", now=10)`, `start(d, "cover", now=50)` → `read(d)["cover"] == {"start": 10}`.
  - `test_close_open_drops_unfinished_steps`: chỉ bước mở bị bỏ; bước đã có `end` giữ nguyên.
  - `test_read_broken_times_is_empty`: file chứa `"{oops"` → `{}`. File chứa `[1]` → `{}`.
  - `test_mark_ends_the_step`: `Run(d).mark("tts")` → `read(d)["tts"]` có `end`.
  - `test_run_vshort_starts_its_step`: monkeypatch `vshort.cli.main` thành lambda trả 0;
    `auto.run_vshort(["render", str(d)])` → `read(d)["render"]` có `start`.
  - `test_run_claude_starts_its_step`: dùng fixture `claude` có sẵn trong `tests/test_auto.py` (chép mẫu nếu cần) →
    `read(run.path)["research"]` có `start`.
  - `test_run_auto_closes_open_steps_first`:
    - ghi sẵn `{"fetch": {"start": 1}}`;
    - monkeypatch `auto._flow` thành hàm đọc `timing.read` rồi trả 0;
    - trong lúc `_flow` chạy, `"fetch"` không còn trong times.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_timing.py`. Expected: FAIL (`No module named 'vshort.timing'`).

- [ ] **Step 3: Implement `vshort/timing.py`** with the four functions above.
  - Ghi nguyên file hoặc không ghi gì (file tmp rồi `replace`), như `Run._save`.
  - Đọc lại trước khi ghi.
  - Dùng một `threading.Lock` của module.
  - Ghi chú `# ponytail:` rằng hai tiến trình ghi cùng lúc có thể mất một mốc, như `state.json`; nếu thấy thiếu mốc thật thì
    chuyển sang `fcntl.flock`.

- [ ] **Step 4: Hook it**:
  - `Run.mark` gọi `timing.end(self.path, step)` sau khi lưu `state.json`. Import ngay trong hàm để tránh vòng import.
  - `auto.run_vshort(args)` gọi `timing.start(Path(args[1]), args[0])` khi `len(args) >= 2` và `Path(args[1]).is_dir()`.
  - `auto.run_claude` gọi `timing.start(run.path, step)` đầu hàm.
  - `_flow` gọi `timing.start(run.path, "source")` ngay trước lệnh `notebooklm source add`.
  - `run_auto` gọi `timing.close_open(run.path)` trước `set_state(run, "running")`.

- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q`. Expected: all pass, including the old tests.

- [ ] **Step 6: Commit** `feat(timing): record start and end of every step in RUN/times.json` and push.

### Task 2: 10 chặng, thời gian còn lại, phần trăm

**Files:**
- Create: `vshort/stages.py`
- Test: `tests/test_stages.py`

**Interfaces:**
- Consumes: `timing.read`, `timing.FILE` (Task 1).
- Produces:
  - `stages.STAGES: list[tuple[str, str, str]]`: `(key, label, what)` theo thứ tự.

    | key | label | what |
    |---|---|---|
    | `research` | Tìm hiểu | Tìm nguồn đáng tin, lập notebook, viết brief |
    | `brief` | Duyệt brief | Bạn đọc và duyệt brief; bỏ duyệt thì agent tự kiểm |
    | `notebooklm` | NotebookLM làm video | Nạp brief, chờ NotebookLM dựng video tiếng Anh, tải về |
    | `subtitles` | Lấy phụ đề | Tách và chép đúng từng chữ phụ đề tiếng Anh |
    | `translate` | Dịch | Dịch sát sang tiếng Việt, chia cụm phụ đề, tự kiểm |
    | `approve` | Duyệt bản dịch | Máy dừng ở đây chờ bạn đọc và duyệt |
    | `build` | Giọng đọc và hình | Gemini đọc, hình động, ảnh tĩnh, tư liệu thật |
    | `render` | Dựng video | Ghép giọng, hình, phụ đề, outro |
    | `review` | Soát và sửa | Xem từng khung, sửa tối đa 2 vòng |
    | `cover` | Ảnh bìa và xuất | Tiêu đề đăng, ảnh bìa, prompt Gemini, kéo về Mac |

  - `stages.STEPS_OF: dict[str, tuple[str, ...]]`:
    - `research: ("research",)`
    - `brief: ("approve_brief", "brief_check")`
    - `notebooklm: ("source", "fetch", "motion_design")`
    - `subtitles: ("detect", "transcribe", "text")`
    - `translate: ("translate",)`
    - `approve: ("approve_script",)`
    - `build: ("plates", "motion", "motion_bind", "stills", "visuals", "visuals_agent", "tts")`
    - `render: ("timeline", "render")`
    - `review: ()` (khớp theo `re.fullmatch(r"(review|fix|fixed)\d.*", step)`)
    - `cover: ("cover",)`
  - `stages.DEFAULT_SECONDS = {"research": 480, "brief": 300, "notebooklm": 900, "subtitles": 180, "translate": 240, "approve": 0,
    "build": 540, "render": 180, "review": 720, "cover": 60}`; `FLOOR = 60`; `HISTORY = 5`.
  - `stages.stage_of(step: str) -> str | None`.
  - `stages.span(times: dict, key: str) -> float | None`: max(`end`) − min(`start`) trên các bước của chặng có đủ hai mốc.
    `None` nếu không có bước nào đủ.
  - `stages.typical(history: list[dict]) -> dict[str, float]`: với mỗi chặng, trung vị (`statistics.median`) các `span` có được
    trong tối đa `HISTORY` phần tử đầu; không có thì `DEFAULT_SECONDS[key]`.
  - `stages.history(runs_dir: Path) -> list[dict]`: `timing.read` của tối đa `HISTORY` thư mục có `auto.json` `state == "done"`
    và có `times.json`, mới nhất trước (theo mtime của `auto.json`). Thư mục hỏng thì bỏ qua.
  - `stages.view(state: str, auto: bool, done: set[str], times: dict, typ: dict[str, float], now: float) -> dict`.
    `state` dùng giá trị Row của `queue.status`. Trả về:

    ```python
    {"stages": [{"key", "label", "what", "status",   # "done" | "running" | "you" | "error" | "next"
                 "seconds",                          # span thật (done) / đã chạy (running) / None
                 "typical",                          # typ[key]
                 "overdue",                          # bool, chỉ running
                 "steps"}],                          # chỉ chặng running: [{"step", "status": "done"|"running"|"next"}]
     "current": int | None,                          # chỉ số chặng running/you/error
     "percent": int,                                 # 0..100
     "eta": {"stop": str | None,                     # nhãn chặng chờ Tai kế tiếp
             "until_stop": int | None,               # giây; khi stop None: giây tới lúc xong
             "after_stop": int | None}}              # giây từ lúc duyệt tới lúc xong; None khi stop None
    ```

- [ ] **Step 1: Write the failing tests** in `tests/test_stages.py`. Mỗi test dựng `done`, `times` bằng tay, `typ = dict(DEFAULT_SECONDS)`.
  - `test_typical_is_the_median_of_recent_runs_else_default`:
    - ba history có span `notebooklm` 600/900/1500 → `typical(h)["notebooklm"] == 900`;
    - `typical([])["review"] == 720`.
  - `test_running_notebooklm_two_numbers`:
    - đầu vào: `state="running"`, `auto=True`; `done = {"research", "brief_check"}`;
      `times = {"source": {"start": 0}, "fetch": {"start": 10}}`; `now = 10 + 660` (đã chạy 670 s tính từ `source`);
    - chặng 2 `done`, chặng 3 `running` với `seconds == 670`;
    - `eta == {"stop": "Duyệt bản dịch", "until_stop": (900 - 670) + 180 + 240, "after_stop": 540 + 180 + 720 + 60}`;
    - `percent == round(100 * (480 + 300 + 670) / sum(DEFAULT_SECONDS.values()))`.
  - `test_overdue_stage_floors_and_flags`: như trên nhưng `now = 10 + 2000` → chặng 3 `overdue is True`;
    `until_stop == 60 + 180 + 240`; % của chặng đó tính tối đa bằng typical.
  - `test_waiting_for_translation_is_you`: `state="wait_script"` → chặng 6 `status == "you"`; `eta == {"stop": "Duyệt bản dịch",
    "until_stop": 0, "after_stop": 540 + 180 + 720 + 60}`.
  - `test_brief_stop_when_not_auto`: `state="running"`, `auto=False`, đang chạy `research` → `eta["stop"] == "Duyệt brief"`.
  - `test_fix_round_shows_review_not_render`: `done` có mọi bước tới `review0`, không có `render`;
    `times["fix1_motion"] = {"start": now - 30}` (đang mở) → chặng `review` là `running`, chặng `render` là `done`.
  - `test_finished_is_all_done`: `state="done"` → mọi chặng `done`, `percent == 100`,
    `eta == {"stop": None, "until_stop": None, "after_stop": None}`.
  - `test_error_marks_first_unfinished_stage`: `state="error"`, `done = {"research", "approve_brief"}` → chặng 3 `error`, các chặng
    sau `next`.
  - `test_view_without_times_uses_state_only`: `state="running"`, `times={}`, `done = {"research", "approve_brief", "source"}` →
    chặng 3 `running` (bước chưa xong đầu tiên là `fetch`), `seconds is None`, không lỗi.
  - `test_history_reads_recent_done_runs` (tmp dir có 7 run): chỉ lấy 5 run `done` có `times.json`, mới nhất trước.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_stages.py`. Expected: FAIL (`No module named 'vshort.stages'`).

- [ ] **Step 3: Implement `vshort/stages.py`.** Thuật toán `view`:
  1. **Chỉ số chặng hiện tại `cur`:**
     - `wait_brief` → `brief` (you); `wait_script` → `approve` (you); `done` → không có.
     - `running`: bước đang mở (có `start`, chưa `end`) có `start` muộn nhất → chặng của nó. Không có bước mở thì lấy chặng của bước
       chưa xong đầu tiên theo thứ tự `STEPS_OF` (auto thì bỏ `approve_brief`; chặng `review` coi là xong khi đã có `review0`).
     - `error`, `dead` → chặng của bước chưa xong đầu tiên, status `error`.
     - `queued`, `idle` → không có chặng hiện tại. Chặng nào có đủ bước trong `done` thì `done`, còn lại `next`.
  2. Các chặng trước `cur` là `done`, sau `cur` là `next`.
  3. **`seconds`:**
     - chặng `done`: `span(times, key)`;
     - chặng `running`: `now` − min(`start`) trên các bước của chặng có `start`, hoặc `None`.
  4. **Thời gian còn lại của chặng running:** `max(typ − seconds, FLOOR)`. Không có `seconds` thì dùng `typ`.
  5. **ETA:** chặng chờ Tai kế tiếp là `brief` (khi chưa auto và chưa qua) hoặc `approve` (khi chưa qua).
     - `until_stop` = phần còn lại của chặng hiện tại + `typ` các chặng nằm giữa. Đang ở chính chặng chờ thì bằng 0.
     - `after_stop` = tổng `typ` các chặng sau chặng chờ.
     - Không còn chặng chờ thì `stop None`, `until_stop` = tổng còn lại tới xong, `after_stop None`.
  6. **`percent`** = round(100 × (Σ `typ` các chặng done + min(`seconds`, `typ`) của chặng running) / Σ `typ` cả 10 chặng).
     Kẹp trong 0–99 trừ khi `state == "done"`.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_stages.py`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(stages): ten stages, time left and percent from state and times` and push.

### Task 3: API trả chặng và thời gian

**Files:**
- Modify: `vshort/queue.py` (`rows`, `status`), `vshort/web.py` (`run_detail`)
- Test: `tests/test_queue.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: `stages.history`, `stages.typical`, `stages.view`, `timing.read`.
- Produces:
  - **Row thêm `"progress"`:** `{"percent": int, "n": int (1–10), "label": str, "status": str, "eta": dict}` cho row
    `running`, `wait_brief`, `wait_script`, `error`, `dead`. Các row khác là `None`.
  - **Detail thêm `"progress"`:** nguyên kết quả `stages.view` (row nào cũng có, kể cả `done`, cho tab "Các bước"), và
    `"now": float` (giờ server, để giao diện tính giờ dự kiến).
  - Danh sách `done` lấy từ `state.json` bằng `queue._Folder(path).state` đọc an toàn (state hỏng → `set()`).
  - `typical` tính **một lần** mỗi lần gọi `rows()` hay `run_detail`.

- [ ] **Step 1: Write the failing tests:**
  - `tests/test_queue.py::test_running_row_has_progress`: run giả có `run.json` `{"auto": true}`, `state.json`
    `{"research": "done"}`, `times.json` `{"brief_check": {"start": <now − 5>}}`, `auto.json` running với pid còn sống (theo mẫu
    test row running có sẵn) → `row["progress"]["n"] == 2`, `row["progress"]["label"] == "Duyệt brief"`,
    `row["progress"]["status"] == "running"`, `0 <= row["progress"]["percent"] <= 99`.
  - `tests/test_web.py::test_detail_has_progress_for_a_finished_run`: run `s` (đã `done`) → `j["progress"]["percent"] == 100`,
    có 10 phần tử `stages`, có `"now"`.
  - `tests/test_web.py::test_state_survives_broken_times`: ghi `s/times.json = "{oops"` → `/api/state` trả 200, row `s` vẫn có mặt.
- [ ] **Step 2: Run** them. Expected: FAIL (`KeyError: 'progress'`).
- [ ] **Step 3: Implement.**
  - `rows()` tính `typ = stages.typical(stages.history(runs_dir()))` rồi truyền vào `status(run, queued, typ)`.
  - `status` gọi `stages.view` cho các state kể trên và rút gọn thành `progress`.
  - `run_detail` gọi `stages.view` với row hiện tại.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(web): stages and time left in /api/state and the video's page` and push.

### Task 4: Nhận ảnh bìa Gemini

**Files:**
- Modify: `vshort/cover.py` (thêm `save_gemini`, `GEMINI`; `package` ưu tiên ảnh Gemini), `vshort/web.py` (route
  `POST /api/runs/{slug}/cover`, `COVERS`, field mới), `vshort/queue.py` (row `"cover"`)
- Test: `tests/test_cover.py`, `tests/test_web.py`

**Interfaces:**
- Produces:
  - `cover.GEMINI = {"9x16": "gemini-9x16.jpg", "16x9": "gemini-16x9.jpg"}`; `RATIO_TOL = 0.05`; `MAX_SIDE = 2048`;
    `MAX_UPLOAD = 15_000_000`.
  - `cover.save_gemini(run_dir: Path, shape: str, data: bytes) -> Path`. Ghi `cover/gemini-<shape>.jpg`. Lỗi thì raise `ValueError`
    với câu tiếng Việt, và không ghi gì:
    - "Khổ ảnh phải là 9x16 hoặc 16x9"
    - "Ảnh lớn quá 15 MB"
    - "File này không phải ảnh"
    - "Ảnh <w>×<h> không đúng khổ <shape> (lệch quá 5 %)"
  - `cover.package` dùng `cover/gemini-9x16.jpg` cho `thumb-doc-9x16.jpg` và `cover/gemini-16x9.jpg` cho `thumb-ngang-16x9.jpg`
    nếu có.
  - **API:**
    - `POST /api/runs/{slug}/cover`, body `{"shape": "9x16"|"16x9", "data": "<base64>"}`.
      - 204 khi xong. Sau đó gọi `cover.package` nếu có `final.mp4` và `cover/cover.json`.
      - 400 kèm thông báo của `ValueError`, hoặc khi base64 hỏng.
      - 413 khi chuỗi base64 dài quá `MAX_UPLOAD * 4 // 3 + 4`.
    - `COVERS` thêm `cover/gemini-9x16.jpg` và `cover/gemini-16x9.jpg`.
    - Detail thêm `"gemini": {"9x16": mtime | None, "16x9": mtime | None}`.
    - Row thêm `"cover": {"name": "cover/gemini-9x16.jpg" | "cover/thumb-9x16.jpg", "v": mtime} | None`. Ưu tiên Gemini.

- [ ] **Step 1: Write the failing tests:**
  - `test_cover.py::test_save_gemini_converts_and_caps_size`: PNG 3000×5333 → file JPEG, cạnh dài 2048, tỉ lệ giữ nguyên.
  - `test_cover.py::test_save_gemini_refuses_wrong_ratio_bad_shape_non_image_and_huge`: bốn trường hợp, mỗi trường hợp
    `pytest.raises(ValueError, match=…)`, và thư mục `cover/` không có file `gemini-*` mới.
  - `test_cover.py::test_package_prefers_gemini`: có `cover/gemini-9x16.jpg` màu đỏ → `thumb-doc-9x16.jpg` trong `xuat/` là màu đỏ.
  - `test_web.py::test_cover_upload_errors`:
    - không mã → 403;
    - `content=b"x", headers={"content-type": "multipart/form-data"}` → 415;
    - `{"shape": "4x3", "data": ""}` → 400;
    - base64 hỏng → 400;
    - chuỗi quá dài → 413.
  - `test_web.py::test_cover_upload_saves_serves_and_repackages`: ảnh 1080×1920 hợp lệ → 204;
    - `GET /files/s/cover/gemini-9x16.jpg` → 200 `image/jpeg`;
    - detail có `gemini["9x16"]`; row `cover.name` là file Gemini;
    - có `cover.json` sẵn thì `xuat/*/thumb-doc-9x16.jpg` là ảnh mới.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** `save_gemini`.
  - Pillow `Image.open` trong `try`; `ImageOps.exif_transpose`; `convert("RGB")`; `thumbnail((MAX_SIDE, MAX_SIDE))`.
  - So tỉ lệ w/h với 9/16 hay 16/9 bằng `abs(r / want − 1) <= RATIO_TOL`.
  - Ghi file tmp rồi `replace`.
- [ ] **Step 4: Implement** the route as `_post(save_cover, run=True)`, then the new fields, then `package`.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q`. Expected: all pass.
- [ ] **Step 6: Commit** `feat(cover): Gemini covers uploaded from the panel replace the composed ones in the export` and push.

### Task 5: Giao diện nền: màu, font, khung trang

**Files:**
- Modify: `web/src/index.css` (thay token màu tối, `--radius`, `@font-face` Plus Jakarta Sans, `--font-sans`; thêm `web/src/fonts/*.woff2`), `web/src/App.tsx`
  (header như bản phác: ô logo tím, "vshort", "Bảng điều khiển video", viên "Đang chạy n/3"), `web/src/components/ui/button.tsx`
  (nút bo `rounded-xl` ≈ 12 px, nút nhỏ `rounded-lg` 8 px, nút chính màu nhấn), `web/src/api.ts` (kiểu mới từ Task 3–4)
- Test: build và lint

**Interfaces:**
- Consumes: Row `progress`, `cover`; Detail `progress`, `now`, `gemini` (Task 3, 4).
- Produces:
  - Kiểu TypeScript trong `api.ts`: `Progress` (Row), `StageView`, `Stage`, `Eta`. Field đúng tên như Task 2–4.
  - Hàm trong `status.tsx`:
    - `fmtLeft(seconds: number | null): string` → "khoảng 21 phút", "dưới 1 phút", "—";
    - `fmtClock(serverNow: number, seconds: number): string` → "~14:33" theo giờ máy người xem (cộng độ lệch `Date.now()/1000 − now`);
    - `fmtElapsed(seconds: number): string` → "24 phút 10 giây".

- [ ] **Step 1: Implement** the token change.
  - Trang chỉ có giao diện tối: đặt class `dark` cố định trên `<html>` trong `web/index.html` nếu chưa có.
  - Thay giá trị trong khối `.dark` bằng bảng màu Global Constraints (oklch hay hex đều được).
  - `--radius: 0.5rem`: `rounded-lg` = 8 px cho thẻ, `rounded-xl` = 11,2 px (gần với 12 px của Clipcup) cho nút và tab.
  - Bỏ `@import "@fontsource-variable/geist"` khỏi CSS. Gói vẫn để trong `package.json`, vì gỡ gói không thuộc việc này.
- [ ] **Step 2: Implement** the header, the button change, the API types and the three formatters.
- [ ] **Step 3: Run** `cd web && npm run build && npm run lint`. Expected: build OK, lint không có lỗi mới.
- [ ] **Step 4: Commit** `feat(web): Clipcup dark theme, Plus Jakarta Sans, new header` and push.

### Task 6: Trang chủ

**Files:**
- Modify: `web/src/RunList.tsx` (chia mục), `web/src/AddTopics.tsx` (thành thẻ "Tạo video ngắn từ một bài báo": tiêu đề trái, form
  phải, nút gạt "Bỏ duyệt brief", nút tím "Tạo video"; giữ nguyên hành vi gửi)
- Test: build, lint

**Interfaces:**
- Consumes: Row `progress`, `cover`, `title`; `fmtLeft`, `fmtElapsed` (Task 5).

- [ ] **Step 1: Implement** the sections, theo thứ tự của bản phác:
  1. **"Cần bạn":** row `wait_brief`, `wait_script`, `error`, `dead`, và row cần đăng nhập lại NotebookLM. Thẻ vàng (lỗi thì đỏ),
     một dòng lý do, nút đi thẳng tới trang video.
  2. **"Đang tạo":** thẻ có ô % lớn, `n/10 · label`, thanh 10 ô (xong xanh, đang chạy tím, còn lại xám), "Đã chạy …",
     "còn khoảng …" (`eta.until_stop`), chi phí. Cả thẻ là một link.
  3. **"Đang xếp hàng":** như hiện nay, nút gỡ giữ nguyên.
  4. **"Video đã xong":** lưới `repeat(auto-fill, minmax(min(100%, 260px), 1fr))`, gồm:
     - ảnh `row.cover`, khung 3:4 (`object-cover`);
     - nhãn "Soát: …" và thời lượng trên ảnh;
     - tiêu đề đăng (thiếu thì slug), "$x · xong … trước";
     - nút "Đăng bài" (link trang video) và nút tải video.

     Bộ lọc dạng tab Clipcup "Tất cả / Cần sửa". "Chưa đăng" để giai đoạn B.
  5. **"Chưa chạy tự động":** `<details>` thu gọn, liệt kê slug.
- [ ] **Step 2: Run** `cd web && npm run build && npm run lint`. Expected: OK.
- [ ] **Step 3: Commit** `feat(web): home page sections, running cards with time left, cover grid` and push.

### Task 7: Danh sách chặng và trang video đang chạy

**Files:**
- Create: `web/src/Stages.tsx`, chứa:
  - `ProgressHeader({ view, now, row })`: vòng %, "Bước n trên 10", tên chặng, "Đã chạy …", hai ô thời gian còn lại;
  - `StageList({ view, compact })`: 10 chặng dọc, có đường nối; chặng đang chạy mở ra các bước con; `compact` chỉ hiện chặng hiện
    tại và các chặng đã xong thu gọn trên một dòng.
- Modify: `web/src/RunDetail.tsx` (`Progress` dùng `ProgressHeader` + `StageList` + cột phải Thông tin/Nhật ký; tiêu đề trang như
  bản phác), `web/src/BriefReview.tsx`, `web/src/ScriptReview.tsx`, `web/src/Failed.tsx` (đặt `StageList compact` lên đầu; giữ
  nguyên mọi hành vi duyệt, sửa, chạy lại)
- Test: build, lint

**Interfaces:**
- Consumes: Detail `progress`, `now`; `fmtLeft`, `fmtClock`, `fmtElapsed`.
- Produces: `ProgressHeader`, `StageList` (Task 8 dùng `StageList` cho tab "Các bước").

- [ ] **Step 1: Implement `Stages.tsx`** theo màn 2 của bản phác.
  - **Chấm trạng thái:** xong = chấm xanh có dấu ✓; đang chạy = viền tím; chờ bạn = viền vàng; lỗi = đỏ; chưa tới = viền xám có số.
  - **Chữ thời gian bên phải mỗi chặng:**
    - "xong · 8 phút";
    - "đang chạy 11:20 · thường ~15 phút", hoặc "lâu hơn thường lệ" khi `overdue`;
    - "chờ bạn";
    - "~4 phút".
  - **Hai ô thời gian:**
    - ô 1: "Tới lúc cần bạn {stop viết thường}", "còn khoảng X · ~hh:mm";
    - ô 2: "Sau khi bạn duyệt, tới lúc xong", "khoảng Y".

    `stop` là `None` thì chỉ một ô "Tới lúc xong".
- [ ] **Step 2: Wire it** into `RunDetail`, the two review pages and `Failed`.
- [ ] **Step 3: Run** `cd web && npm run build && npm run lint`. Expected: OK.
- [ ] **Step 4: Commit** `feat(web): stage list with time left on running, waiting and failed videos` and push.

### Task 8: Trang video xong: các tab và ô tải ảnh Gemini

**Files:**
- Modify: `web/src/Finished.tsx`
- Test: build, lint

**Interfaces:**
- Consumes:
  - `StageList` (Task 7); `copyText`, `useKept` (`runKit.tsx`);
  - Detail `gemini`, `prompt`, `prompt_wide`, `cover_v`;
  - `POST /api/runs/{slug}/cover` (Task 4).

- [ ] **Step 1: Implement** the tabs.
  - Tab kiểu Clipcup (rãnh `#21232C`, tab chọn nền trắng): "Đăng bài / Báo cáo soát / Các bước / Chi phí". Tab đang chọn nhớ theo video bằng `useKept(slug, "tab", "post")`.
  - Nội dung cũ chuyển vào tab tương ứng: `review.md` → Báo cáo soát, `CostTable` → Chi phí, `StageList` → Các bước.
  - Khối "Ghi chú của lần chạy" chuyển xuống cuối tab Báo cáo soát.
- [ ] **Step 2: Implement** tab Đăng bài theo màn 3 của bản phác.
  1. Tiêu đề đăng, kèm Sao chép.
  2. Khối "Ảnh bìa": hai ô Gemini (9:16 và 16:9) và ảnh tự ghép dự phòng.
     - Mỗi ô Gemini: kéo thả, hoặc một `<label>` bọc `<input type="file" accept="image/*">`.
     - Đọc file bằng `FileReader.readAsDataURL`, bỏ tiền tố `data:…;base64,`, `post(runApi(c, "cover"), {shape, data})`.
     - Thành công: toast, rồi `c.reload()`. Lỗi: toast hiện thông báo của server.
     - Có ảnh rồi thì hiện ảnh (`/files/<slug>/cover/gemini-<shape>.jpg?v=<mtime>`) và nút "Thay ảnh".
     - Không có mã thì các ô bị tắt (`c.off`).
  3. Hướng dẫn 3 bước và hai nút sao chép prompt (dùng lại khối `Publish` có sẵn).
- [ ] **Step 3: Run** `cd web && npm run build && npm run lint`. Expected: OK.
- [ ] **Step 4: Commit** `feat(web): finished page tabs, Gemini cover upload` and push.

### Task 9: Thử thật và đưa lên server

**Files:**
- Modify: `/Users/Apple/.claude/projects/-Users-Apple-video-pipeline/memory/web-control-panel.md` (ghi giao diện mới, `times.json`,
  ảnh Gemini)

- [ ] **Step 1: Thử trên Mac với dữ liệu thật.**
  - Chép một run đã xong từ pve2 vào thư mục tạm, như đã làm hôm 05/11:
    `rsync -a --include='*/' --include='cover/***' --include='auto.json' --include='run.json' --include='state.json' --include='final.mp4' --include='review.md' --include='review.json' --include='cost.json' --include='script.vi.json' --include='timeline.json' --exclude='*' pve2:notebooklm-videos/<slug> <tmp>/runs/`.
  - Thêm một run giả "đang chạy": `auto.json` running với pid của một `sleep` đang chạy; `times.json` có `fetch` đang mở.
  - Chạy web với `queue.runs_dir` trỏ vào `<tmp>/runs` trên cổng 8771.
- [ ] **Step 2: Kiểm bằng Playwright** ở bề ngang 1440 và 390 px:
  - trang chủ có đủ các mục;
  - thẻ "Đang tạo" có % và "còn khoảng";
  - trang video đang chạy có 10 chặng và hai ô thời gian;
  - trang video xong có 4 tab;
  - tải một ảnh 9:16 lên thì ảnh hiện ra và `xuat/` đổi theo;
  - ở 390 px không có cuộn ngang (`document.documentElement.scrollWidth <= innerWidth`).
- [ ] **Step 3: Deploy:** `git push`, rồi chạy lệnh `systemd-run … update-server.sh` ở Global Constraints. Đợi journal báo
  "đã cập nhật … → <commit>".
- [ ] **Step 4: Kiểm trên server:** mở `http://192.168.1.214:8770`, xem trang chủ và một video đã xong. Không tải ảnh lên video thật.
  Việc đó để Tai làm.
- [ ] **Step 5: Ghi memory:**
  - giao diện mới, `times.json`, ảnh Gemini ở `cover/gemini-*.jpg`;
  - "giai đoạn B chờ, kế hoạch riêng".

  Commit nếu có file trong repo đổi.
