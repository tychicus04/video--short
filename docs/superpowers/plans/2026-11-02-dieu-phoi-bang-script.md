# Điều phối /video-short bằng script — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `vshort auto` chạy trọn một video trên server, gọi các agent `vs-*` bằng `claude -p`, dừng hai lần cho Tai duyệt, ghi chi phí từng video — thay cho phiên Claude điều phối.

**Architecture:** Module mới `vshort/auto.py` giữ toàn bộ luồng: mỗi bước là một hàm, bỏ qua khi `state.json` đã ghi xong. Bước cố định gọi thẳng `cli.main([...])` trong cùng tiến trình (qua một hàm `run_vshort()` thay được trong test); agent gọi qua `run_claude()` (subprocess `claude -p --agent … --output-format json`). Trạng thái cho người ngoài nằm ở `$RUN/auto.json`; chi phí ở `$RUN/cost.json`. Lệnh `vshort auto` mặc định tự tách thành tiến trình nền, ghi `$RUN/auto.log`.

**Tech Stack:** Python 3.12 stdlib (subprocess, threading/concurrent.futures, json, os), pytest. Không thêm thư viện.

**Spec:** `docs/superpowers/specs/2026-11-02-dieu-phoi-bang-script-design.md`

## Global Constraints

- Hai điểm dừng: sau brief, sau bản dịch. Chế độ tự động (`--auto`) chỉ bỏ điểm dừng brief (thay bằng một lần gọi agent soát brief với `sources.md`); vẫn dừng duyệt bản dịch.
- `vshort approve RUN brief` từ chối khi `brief.vi.md` mới hơn `brief.en.md` (mtime).
- Vòng sửa sau soát: tối đa **2** vòng; soát lại luôn gọi **reviewer mới** (lần `claude -p` mới) với lời giao bắt đầu bằng "Soát lại".
- Lỗi reviewer gán cho bản dịch: không đè `script.vi.json`; translator ghi `script.proposed.json`, script dừng ở trạng thái chờ duyệt bản dịch.
- Mỗi lần gọi agent ghi một dòng vào `$RUN/cost.json`; tổng > **$5** thì in cảnh báo (không chặn).
- Không đổi hành vi các lệnh `vshort` hiện có (trừ `status` in thêm trạng thái auto, và `Run.unmark` mới).
- Agent chạy trong `~/video-pipeline` (thư mục đã cấu hình Sonnet + tắt advisor); không truyền `--model` — agent dùng `model:` trong frontmatter.
- Thông báo cho Tai bằng tiếng Việt; không in/ghi `GEMINI_API_KEY`.
- Test không gọi `claude` hay NotebookLM thật.

## Review Focus

- Script chết giữa chừng (máy tắt, bị kill) rồi chạy lại: phải tiếp từ bước dở, không làm lại bước đã xong, không chạy agent hai lần cho cùng bước đã ghi xong → test ở Task 3.
- Agent trả lỗi (`is_error`, mã ≠ 0, đầu ra không phải JSON, quá giờ): dừng với trạng thái `error` và lý do tiếng Việt, không traceback, vẫn ghi dòng chi phí nếu có → test ở Task 1.
- Hai `vshort auto` cùng một RUN (Tai gọi lại `/video-short` khi script cũ còn chạy): cái sau từ chối, không phá cái trước; khóa của tiến trình đã chết thì được lấy lại → test ở Task 2.
- `review.json` thiếu hoặc sai dạng: không lặp sửa; dừng `error` "review.json không đọc được" để người xem → test ở Task 5.
- Tai duyệt bản dịch khi `vshort check` trượt (sửa tay sai): `approve script` từ chối và in lỗi của check → test ở Task 2.

---

### Task 1: Gọi agent và sổ chi phí

**Files:**
- Create: `vshort/auto.py`
- Modify: `vshort/run.py` (thêm `unmark`)
- Test: `tests/test_auto.py`

**Interfaces:**
- Produces:
  - `Run.unmark(self, *steps: str) -> None` — xóa các bước khỏi `state.json` (đọc lại file trước, như `mark`).
  - `CLAUDE: list[str] = ["claude"]` (module-level, test thay bằng script giả).
  - `class AgentError(Exception)` — `str(e)` là lý do tiếng Việt.
  - `run_claude(run: Run, step: str, agent: str, prompt: str, timeout: int) -> str` — chạy `[*CLAUDE, "-p", "--agent", agent, "--output-format", "json", prompt]` với `cwd=ROOT`, `timeout`; ghi một dòng `cost.json`; trả `result`; ném `AgentError` khi quá giờ / mã ≠ 0 / không phải JSON / `is_error`.
  - Dòng `cost.json`: `{"step", "agent", "seconds", "cost_usd", "models": [..], "ok": bool}` (`models` = khóa của `modelUsage`).
  - `total_cost(run: Run) -> float`.
  - Hằng `TIMEOUT = {"vs-researcher": 1800, "vs-transcriber": 900, "vs-translator": 1200, "vs-motion": 2400, "vs-visuals": 2400, "vs-reviewer": 3600}` (giây).

- [ ] **Step 1: Viết test (thất bại)** trong `tests/test_auto.py`, với một script giả `fake_claude` viết vào `tmp_path` (đọc biến môi trường `FAKE_CLAUDE` = JSON in ra / mã thoát / số giây ngủ) và `monkeypatch.setattr(auto, "CLAUDE", [sys.executable, str(fake)])`:
  - `test_run_claude_returns_result_and_logs_cost`: fake in `{"result": "xong", "total_cost_usd": 0.12, "is_error": false, "modelUsage": {"claude-haiku-5-5": {}}}` → trả `"xong"`; `cost.json` có 1 dòng với `step="translate"`, `agent="vs-translator"`, `cost_usd=0.12`, `models=["claude-haiku-5-5"]`, `ok=True`; `total_cost(run) == 0.12`.
  - `test_run_claude_error_cases_raise_with_reason`: (a) `is_error: true` → `AgentError`, dòng chi phí `ok=False` vẫn được ghi với cost của nó; (b) mã thoát 1 → `AgentError` có chữ "vs-translator"; (c) in `"không phải json"` → `AgentError`; (d) ngủ 2 s với `timeout=1` → `AgentError` có chữ "quá" và `cost.json` có dòng `ok=False, cost_usd=0`.
  - `test_unmark_removes_steps`: mark `tts`, `timeline` rồi `unmark("tts")` → `done("tts")` False, `done("timeline")` True.
- [ ] **Step 2: Chạy, thấy thất bại** — `uv run pytest tests/test_auto.py -q` → lỗi import `vshort.auto`.
- [ ] **Step 3: Viết `Run.unmark`, `run_claude`, `total_cost`, `AgentError`, `CLAUDE`, `TIMEOUT`.** Ghi `cost.json` bằng đọc–nối–ghi (list JSON).
- [ ] **Step 4: Chạy lại** — `uv run pytest tests/test_auto.py -q` → PASS; `uv run pytest -q` → không hỏng test cũ.
- [ ] **Step 5: Commit** — `git commit -m "feat: vshort.auto runs a vs-* agent with claude -p and logs its cost per run"`

### Task 2: Trạng thái, khóa, duyệt, chờ

**Files:**
- Modify: `vshort/auto.py`, `vshort/cli.py` (lệnh con `approve`, `wait`; `status` in thêm)
- Test: `tests/test_auto.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - Trạng thái `$RUN/auto.json`: `{"state": "running"|"wait_brief"|"wait_script"|"error"|"done", "message": str, "round": int, "pid": int}`.
  - `set_state(run: Run, state: str, message: str = "") -> None`; `get_state(run: Run) -> dict` (không có file → `{"state": "none", ...}`).
  - Mã thoát mới trong `cli.py`: `WAIT_BRIEF, WAIT_SCRIPT = 20, 21` (giữ `OK, FAILED, BAD_INPUT, AUTH, QUOTA`). `STATE_CODE = {"done": OK, "wait_brief": WAIT_BRIEF, "wait_script": WAIT_SCRIPT, "error": FAILED}`.
  - `acquire_lock(run: Run) -> bool` / `release_lock(run: Run)`: file `$RUN/auto.lock` chứa pid; khóa của pid không còn sống (`os.kill(pid, 0)` lỗi) thì lấy lại.
  - `vshort approve RUN brief|script`: brief → từ chối (mã 2, thông báo "brief.vi.md mới hơn brief.en.md — cập nhật bản tiếng Anh trước") khi mtime vi > en; ngược lại `mark("approve_brief")`. script → nếu có `script.proposed.json` thì từ chối (mã 2, "chép bản đề xuất vào script.vi.json hoặc xóa nó trước"); chạy `cmd_check`, khác 0 thì trả mã đó; 0 thì `mark("approve_script")`.
  - `vshort wait RUN [--poll 15]`: chờ tới khi `state` khác `running`, in `state` + `message`, thoát `STATE_CODE[state]`.
  - `vshort status RUN` in thêm một dòng `auto: <state> — <message>` khi có `auto.json`.

- [ ] **Step 1: Viết test (thất bại):**
  - `test_approve_brief_refuses_stale_english`: ghi `brief.en.md` rồi `brief.vi.md` (mtime vi lớn hơn, đặt bằng `os.utime`) → `main(["approve", run, "brief"]) == 2`, stderr có "brief.en.md"; đặt en mới hơn → `0` và `Run(run).done("approve_brief")`.
  - `test_approve_script_runs_check`: `script.vi.json` có câu rỗng (như test `check` hiện có) → mã 2, chưa `approve_script`; có `script.proposed.json` → mã 2 và stderr có "script.proposed.json".
  - `test_lock_refuses_second_and_takes_dead_lock`: `acquire_lock` True, lần hai False; ghi pid không tồn tại (vd. 999999) vào `auto.lock` → `acquire_lock` True.
  - `test_wait_returns_state_code`: `set_state(run, "wait_script", "xem bản dịch")` → `main(["wait", run, "--poll", "0"]) == 21`, stdout có "xem bản dịch".
- [ ] **Step 2: Chạy, thấy thất bại.**
- [ ] **Step 3: Viết** các hàm trên và nối lệnh con trong `cli.main` (giữ kiểu `sub.add_parser` hiện có).
- [ ] **Step 4: Chạy** `uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** — `feat: vshort approve/wait and an auto.json state the skill can read; one auto run per folder`

### Task 3: Luồng tới điểm dừng bản dịch

**Files:**
- Modify: `vshort/auto.py`, `vshort/cli.py` (lệnh `auto`, chạy `--foreground`), `claude/agents/vs-researcher.md`
- Test: `tests/test_auto.py`

**Interfaces:**
- Consumes: Task 1–2; `cli.main`, `cli._notebooklm`, `cli._speech`.
- Produces:
  - `run_vshort(args: list[str]) -> int` — gọi `cli.main(args)`; test thay hàm này.
  - `notebooklm(args: list[str]) -> int` — bọc `cli._notebooklm`, trả mã; test thay.
  - `run_auto(run: Run) -> int` — chạy từ bước dở tới điểm dừng/xong/lỗi; luôn `set_state` trước khi trả; bắt `AgentError` → `error`.
  - `vshort auto <slug> --topic T [--auto] [--foreground]` (lần đầu: `cmd_new`, lưu `topic`, `auto` vào `run.json`) và `vshort auto RUN [--foreground]` (lần sau). Task 3 chỉ cần `--foreground`; Task 6 làm phần tách nền.
  - Bước (khóa trong `state.json`): `research` → [`brief_check` nếu `--auto`] → dừng `wait_brief` nếu chưa `approve_brief` và không `--auto` → `source` → `fetch` → `detect` → `transcribe` → `text` → `translate` → dừng `wait_script` nếu chưa `approve_script`.
  - Researcher ghi notebook id vào `$RUN/notebook.txt` (một dòng); script đọc và ghi vào `run.json` `notebook_id`. Thiếu file → `error` "researcher không ghi notebook.txt".
  - `translation.md`: bảng `| id | tiếng Anh | tiếng Việt | note |` (lời Việt bỏ `|`), ghi trước khi dừng `wait_script`.
  - Lời giao agent (mẫu cố định, chỉ trỏ tới file): researcher (chủ đề, slug, RUN, "ghi notebook id vào RUN/notebook.txt"); brief_check dùng `vs-researcher` với "Soát brief.vi.md và brief.en.md với sources.md … sửa cả hai bản, không tạo notebook mới" (luật an toàn mục "Cơ chế từng bước" chép từ SKILL.md cũ); transcriber (RUN, danh sách `sheets/sheet*.png`, số mảnh, "ghi fragments_text.json"); translator (RUN + bảng `id\tstart–end\ten` dựng từ `sentences.en.json`, giống đầu ra `vshort text`).
  - Lệnh `fetch` dùng đúng `--prompt` đang có trong SKILL.md bước 3 (chép nguyên văn vào hằng `FETCH_PROMPT`); `source add` dùng tiêu đề `# BRIEF (EN) – <slug>`.
- [ ] **Step 1: Viết test (thất bại)** với `fake_agent` (thay `run_claude`: ghi file mà agent thật sẽ ghi — brief, notebook.txt, fragments_text.json, script.vi.json hợp lệ — và đếm số lần gọi theo agent) và `fake_vshort`/`fake_notebooklm` ghi lại lệnh, trả 0 và `mark` bước:
  - `test_stops_for_brief_then_for_translation`: lần 1 `run_auto` → `WAIT_BRIEF`, `auto.json.state == "wait_brief"`, chỉ researcher được gọi; `approve brief`; lần 2 → `WAIT_SCRIPT`, `translation.md` có đủ id; `notebooklm` được gọi `source add` đúng 1 lần.
  - `test_rerun_does_not_repeat_finished_steps`: chạy tới `WAIT_SCRIPT`, rồi gọi lại `run_auto` → vẫn `WAIT_SCRIPT`, số lần gọi mỗi agent không tăng.
  - `test_auto_mode_checks_brief_instead_of_stopping`: `run.json.auto = true` → không dừng `wait_brief`; `vs-researcher` được gọi 2 lần (lần 2 có chữ "Soát brief"); vẫn dừng `WAIT_SCRIPT`.
  - `test_notebooklm_login_stops_with_auth`: `fake_vshort` trả `AUTH` cho `fetch` → `run_auto == AUTH`, `state == "error"`, `message` có "đăng nhập".
  - `test_missing_notebook_id_is_an_error`: fake researcher không ghi `notebook.txt` → `FAILED`, message có "notebook.txt".
- [ ] **Step 2: Chạy, thấy thất bại.**
- [ ] **Step 3: Viết** `vshort`, `notebooklm`, các bước, `run_auto`, lệnh `auto --foreground`; sửa `vs-researcher.md` (thêm dòng ghi `RUN/notebook.txt`).
- [ ] **Step 4: Chạy** `uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** — `feat: vshort auto runs research → brief stop → video → transcription → translation stop`

### Task 4: Dựng video

**Files:**
- Modify: `vshort/auto.py`
- Test: `tests/test_auto.py`

**Interfaces:**
- Consumes: Task 3.
- Produces: các bước sau `approve_script`: `tts` (luồng nền qua `concurrent.futures.ThreadPoolExecutor`, gọi `run_vshort(["tts", RUN])`) song song `plates` → `motion` → `stills` → `visuals` → chờ `tts` → `timeline` → `render`. Luật dự phòng chép từ SKILL.md bước 6–11 thành code:
  - motion: gọi `vs-motion`, rồi tự `vshort(["motion", RUN])`; khác 0 → đổi tên `motion.json` thành `motion.loi.json`, chạy lại `vshort motion` (không hình động), ghi lý do vào `auto.json.message` để báo.
  - visuals: gọi `vs-visuals`, rồi `vshort visuals`; khác 0 → `visuals.json` → `visuals.loi.json`, ghi `[]`, chạy lại; vẫn khác 0 → `vshort stills`, đặt bản agent về chỗ, `vshort visuals` một lần; vẫn khác 0 → quay về `[]`.
  - tts: `QUOTA` → `error` "hết hạn mức Gemini và ZeroTTS không chạy được"; mã 1 → `error` kèm stderr đầu tiên.
  - timeline mã 2 → `unmark("tts")`, chạy `tts` lại một lần rồi `timeline`.
  - render mã 2 → dự phòng motion như trên rồi `render` lại một lần.
  - Lời giao: motion (RUN; "đọc brief.vi.md mục Cơ chế từng bước và Lưu ý độ chính xác, script.vi.json"); visuals (RUN; "đọc motion.json để biết câu đã có hình động, sources.md, brief.vi.md").
- [ ] **Step 1: Viết test (thất bại):**
  - `test_build_runs_steps_in_order_with_tts_alongside`: `fake_vshort` ghi thứ tự; `tts` có mặt; `timeline` sau cả `tts` và `visuals`; `render` cuối.
  - `test_motion_failure_falls_back_to_no_motion`: `vshort motion` lần 1 trả 2 → có `motion.loi.json`, không còn `motion.json`, `motion` chạy lại lần 2, luồng đi tiếp tới `render`.
  - `test_visuals_failure_falls_back_to_empty`: `vshort visuals` trả 2 hai lần rồi 0 → chuỗi lệnh đúng như luật trên, `visuals.json` cuối là `[]`.
  - `test_tts_quota_stops_with_reason`: `tts` trả 75 → `run_auto == QUOTA`, `state == "error"`.
  - `test_timeline_stale_voice_reruns_tts_once`: `timeline` trả 2 lần đầu → `tts` chạy 2 lần, `timeline` 2 lần, đi tiếp.
- [ ] **Step 2–4:** chạy thấy thất bại → viết → `uv run pytest -q` PASS.
- [ ] **Step 5: Commit** — `feat: vshort auto builds the video with the skill's fallbacks (motion, visuals, stale voice)`

### Task 5: Soát, vòng sửa, kết quả

**Files:**
- Modify: `vshort/auto.py`, `claude/agents/vs-reviewer.md`
- Test: `tests/test_auto.py`

**Interfaces:**
- Consumes: Task 4.
- Produces:
  - Reviewer ghi thêm `$RUN/review.json`: `{"verdict": "Đạt"|"Cần sửa", "findings": [{"agent": "motion"|"visuals"|"translator"|"none", "ids": [int], "at": str, "what": str}]}` — thêm vào `vs-reviewer.md` (mỗi lỗi gán agent phụ trách; "none" = chỉ người sửa được).
  - `read_review(run: Run) -> dict` — ném `AgentError("review.json không đọc được …")` khi thiếu/sai dạng.
  - Vòng sửa (`auto.json.round` 1..2): nhóm `findings` theo `agent`; motion → `vs-motion` (lời giao: "Sửa theo review.json, các lỗi agent=motion: …") rồi kiểm/dự phòng như Task 4 và `stills` không chạy lại; visuals → `vs-visuals` tương tự; translator → `vs-translator` với "ghi bản sửa vào script.proposed.json, không sửa script.vi.json", rồi `set_state("wait_script", <so sánh cũ/mới>)`, `unmark("approve_script", "tts", "timeline", "render")` và trả `WAIT_SCRIPT` (lần chạy sau sau khi duyệt: tts → timeline → render → soát lại). Sau sửa: `timeline` (nếu cần) → `render` → reviewer **mới** với lời giao "Soát lại: chỉ các phần đã sửa" + danh sách đã sửa.
  - Hết 2 vòng mà vẫn "Cần sửa", hoặc chỉ còn lỗi `none` → `done` kèm message "còn lỗi, xem review.md".
  - Xong: `set_state("done", summary)`; `summary` gồm `final.mp4`, lệnh `scp tai@pve2:~/notebooklm-videos/<slug>/final.mp4 ~/Downloads/<slug>.mp4`, giọng (Gemini/ZeroTTS — đọc từ tên clip trong `tts.json`: tên có tag ZeroTTS hay không, dùng `cli.clip_paths` với `_zerotts_tag`), đoạn hình động (các câu trong `motion.json` `lines`, hoặc "không có hình động" + lý do nếu có `motion.loi.json`), mỗi mục `visuals.json` một dòng (vá: câu, chữ cũ → mới; tư liệu: câu, loại, `source`), kết luận review, `total_cost` và chi phí từng agent; `> 5.0` thì thêm dòng "Vượt ngân sách $5".
- [ ] **Step 1: Viết test (thất bại):**
  - `test_pass_review_finishes_with_cost_summary`: fake reviewer ghi `verdict: "Đạt"` → `run_auto == OK`, `state == "done"`, message có "final.mp4", "scp", các câu hình động và tổng chi phí.
  - `test_motion_finding_runs_one_fix_round_with_fresh_reviewer`: reviewer lần 1 "Cần sửa" (1 lỗi motion), lần 2 "Đạt" → `vs-motion` gọi 2 lần (lần 2 có "review.json"), `vs-reviewer` 2 lần (lần 2 bắt đầu "Soát lại"), `render` 2 lần, `round == 1`.
  - `test_fix_rounds_stop_after_two`: reviewer luôn "Cần sửa" → reviewer gọi đúng 3 lần, `state == "done"`, message có "còn lỗi".
  - `test_translator_finding_waits_for_tai`: lỗi `translator` → `run_auto == WAIT_SCRIPT`, `script.vi.json` không đổi, có `script.proposed.json`, `done("tts")` False.
  - `test_bad_review_json_stops_without_looping`: reviewer không ghi `review.json` → `FAILED`, message có "review.json", reviewer gọi 1 lần.
  - `test_over_budget_warns`: `cost.json` tổng 5,4 → message có "Vượt ngân sách".
- [ ] **Step 2–4:** thất bại → viết → `uv run pytest -q` PASS.
- [ ] **Step 5: Commit** — `feat: vshort auto reviews, runs up to two fix rounds with a fresh reviewer, and reports the cost`

### Task 6: Chạy nền và skill mới

**Files:**
- Modify: `vshort/cli.py` (lệnh `auto` không `--foreground`), `claude/skills/video-short/SKILL.md`, `DESIGN.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2 (`acquire_lock`, `get_state`), Task 3 (`run_auto`).
- Produces:
  - `vshort auto …` (không `--foreground`): kiểm khóa (đang chạy → mã 2 "đang chạy (pid …)"), `set_state("running")`, khởi chạy chính nó với `--foreground` bằng `subprocess.Popen(..., start_new_session=True, stdout/stderr → $RUN/auto.log, stdin=DEVNULL)`, in RUN và pid, trả 0 ngay. Tiến trình `--foreground` giữ khóa trong suốt lúc chạy, nhả khi thoát.
  - SKILL.md mới (ngắn): (1) `vshort auto <slug> --topic "<chủ đề>"` [`--auto` khi Tai nói chạy tự động]; (2) chạy nền `vshort wait $RUN` và chờ thông báo, không hỏi dồn; (3) theo mã: 20 → dán `brief.vi.md` (tiêu đề lên đầu) cho Tai, Tai sửa thì sửa **cả hai** bản brief, duyệt → `vshort approve $RUN brief` rồi `vshort auto $RUN`; 21 → dán `translation.md` (và so sánh đề xuất nếu có `script.proposed.json`), Tai sửa/đồng ý → cập nhật `script.vi.json` (chép bản đề xuất nếu Tai chọn, xóa file đề xuất), `vshort approve $RUN script`, `vshort auto $RUN`; 0 → dán message (đường dẫn, scp, tóm tắt, chi phí); 1/4/75 → dán message nguyên văn. Giữ các luật ngữ cảnh gọn đã có; bỏ phần điều phối từng bước cũ (đã nằm trong `vshort/auto.py`).
  - DESIGN.md: một đoạn "Điều phối bằng `vshort auto`" trỏ tới spec.
- [ ] **Step 1: Viết test (thất bại):** `test_auto_launch_detaches_and_refuses_while_running` — `monkeypatch` `subprocess.Popen` trong `cli` bằng fake ghi lại args và trả object có `pid=4242`; `main(["auto", run])` → 0, args có `--foreground` và `start_new_session=True`; ghi `auto.lock` với pid của tiến trình test (còn sống) → lần gọi sau trả 2, stderr có "đang chạy".
- [ ] **Step 2–4:** thất bại → viết → `uv run pytest -q` PASS.
- [ ] **Step 5: Commit** — `feat: vshort auto detaches and logs; /video-short only starts it, relays the two approvals and the result`

### Task 7: Thử trên server

**Files:** không đổi code (trừ khi phát hiện lỗi — sửa kèm test rồi commit riêng).

- [ ] **Step 1:** push; trên server `cd ~/video-pipeline && git pull --ff-only && uv run pytest -q` → PASS.
- [ ] **Step 2: Quyền khi chạy không người.** Trên server, thư mục `~/video-pipeline`: `claude -p --agent vs-transcriber --output-format json "Ghi chữ ok vào /tmp/auto-smoke/ok.txt bằng Write, rồi chạy: cd ~/video-pipeline && uv run vshort status /tmp/auto-smoke"` (tạo `/tmp/auto-smoke` trước) → `ok.txt` có, `is_error` false, `modelUsage` chỉ có `claude-haiku-5-5` (xác nhận `--agent` dùng `model:` của agent khi không truyền `--model`). Nếu bị chặn quyền: chọn và ghi vào `CLAUDE` cờ quyền phù hợp (ưu tiên `--allowedTools` liệt kê `Bash(uv run vshort:*)`, `Read`, `Write`, `WebSearch`, `Bash(curl:*)` hơn là bỏ hết kiểm), thêm test cho args, chạy lại bước này.
- [ ] **Step 3: Chạy thật tới điểm dừng đầu** (tốn ít: chỉ researcher Haiku) với một chủ đề Tai đưa: `uv run vshort auto <slug> --topic "<chủ đề>"` → `vshort wait` trả 20, `brief.vi.md`, `notebook.txt`, `cost.json` có dòng `vs-researcher`. Báo Tai chi phí dòng đó; **dừng ở đây** — chạy tiếp cả video là việc Tai quyết.
