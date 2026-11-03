# Giao diện web /video-short, đợt 1: bàn điều khiển — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một trang web trên `pve2` để thêm video hàng loạt vào hàng đợi (tối đa 3 chạy cùng lúc), duyệt brief và bản dịch, xem và
tải `final.mp4`, thấy lỗi và chạy lại. Không cần terminal hay cửa sổ chat.

**Architecture:**
- Phía server: một tiến trình Python (Starlette + uvicorn) nằm trong package `vshort`. Nó đọc trạng thái bằng các hàm có sẵn của
  `vshort.auto`, và gọi lệnh `vshort` (`auto`, `approve`, `check`) bằng subprocess.
- Một vòng lặp nền mỗi 5 giây chọn video kế trong hàng đợi để chạy.
- Giao diện là React + shadcn/ui, build thành file tĩnh và được chính tiến trình Python phục vụ: một tiến trình, một cổng.
- Hai sửa nhỏ trong `vshort/auto.py`: phát hiện pid cũ sau khi khởi động lại máy, và kiểm phiên NotebookLM trước bước research.

**Tech Stack:** Python 3.12, Starlette ≥ 0.39 (FileResponse có HTTP Range), uvicorn, httpx (chỉ để test), pytest; React + TypeScript +
Vite + Tailwind + shadcn/ui; systemd user unit trên Linux.

**Spec:** `docs/superpowers/specs/2026-11-03-giao-dien-web-design.md`

## Global Constraints

- Chữ trên giao diện và mọi thông báo lỗi trả về trình duyệt bằng **tiếng Việt**.
- Slug khớp `^[a-z0-9][a-z0-9-]{0,59}$`, kiểm **ở phía server** trước mọi thao tác file. Chủ đề tối đa 500 ký tự.
- Mọi file đọc hoặc gửi cho trình duyệt phải nằm trong `runs_dir/<slug>/` sau khi giải symlink, ngoài đó thì 404.
- Mọi subprocess gọi bằng list tham số, không bao giờ `shell=True`.
- Cấu hình mới trong `config.toml`: `web_port = 8770`, `web_max_running = 3`, `web_token_file = "~/.config/vshort/web_token"`.
- Ghi (POST) cần cookie mã truy cập. Đọc thì không cần. Video và nút tải không cần mã.
- Nền tối mặc định (`class="dark"` trên `<html>`), dùng component shadcn/ui.
- **Không test nào được gọi agent thật.** `tests/conftest.py` đã đặt `auto.CLAUDE = ["false"]`; test cần agent thì monkeypatch
  `auto.run_claude`. Test không được gọi `notebooklm` thật.
- **Có phiên khác đang sửa `vshort/` trên `main`** (chưa commit ở `cli.py`, `script.py`, `captions.py`…):
  - Làm trong worktree riêng (superpowers:using-git-worktrees). `assets/fonts/` và `models/` nằm trong `.gitignore`, nên
    worktree mới không có. Tạo xong thì symlink hai thư mục đó từ bản checkout chính; `uv sync` sẽ dựng `.venv` mới. Thiếu font thì
    test của `conftest.py` hỏng vì môi trường, không phải vì code.
  - Mỗi commit chỉ `git add` đúng file của task; không `git add -A`, không `commit -a`.
  - Dựa vào tên hàm, không dựa vào số dòng.
- Chạy test bằng `uv run pytest …` ở gốc repo.

## Review Focus

1. **Bấm "Duyệt" hai lần** (hai tab, hai người, mạng chậm): video không được vào hàng đợi hai lần. `add_resume` không thêm trùng.
   Test ở Task 3.
2. **Dán chủ đề có dòng trống, dòng trùng nhau, hoặc chủ đề chỉ có ký hiệu/emoji** (slug sinh ra rỗng): dòng trống bị bỏ qua, còn
   slug rỗng hay trùng trong cùng lần dán thì báo lỗi đúng dòng, không làm sập server. Test ở Task 3.
3. **Thư mục lạ trong `runs_dir`** (đang có thật: `haiku-test`, `zerotts-test`), thư mục thiếu `run.json`, hay `auto.json` hỏng:
   danh sách vẫn hiện, không lỗi 500. Test ở Task 3.
4. **Xem hoặc tải `final.mp4` khi video đang được dựng lại** (vòng sửa đang chạy): trả 409, không gửi file đang ghi dở. Test ở Task 4.
5. **Mã truy cập trên server bị đổi hoặc xóa** trong khi trình duyệt còn cookie cũ: lệnh ghi bị từ chối 403, và trang quay về ô
   nhập mã thay vì lỗi im lặng. Test phía server ở Task 4, phía giao diện kiểm tay ở Task 6.

---

### Task 1: Pid cũ sau khi khởi động lại máy không còn được coi là "đang chạy"

**Files:**
- Modify: `vshort/auto.py` (`_alive`, `alive_run`, `locked_by`)
- Test: `tests/test_auto.py`

**Interfaces:**
- Produces: `auto._started(pid: int) -> float | None` (giờ tiến trình bắt đầu, epoch giây; `None` khi không có tiến trình đó) và
  `auto._alive(pid: int, since: float) -> bool`. `alive_run(run)` và `locked_by(run)` giữ nguyên chữ ký.

- [ ] **Step 1: Viết test hỏng**

```python
def test_a_pid_that_started_after_its_file_is_not_our_run(tmp_path):
    import os, time
    run = _run(tmp_path)
    run.file("auto.lock").write_text(str(os.getpid()))
    assert auto.locked_by(run) == os.getpid()            # this process was running when the lock was written
    old = time.time() - 10 * 365 * 86400
    os.utime(run.file("auto.lock"), (old, old))          # lock written long before this process started: pid reused
    assert auto.locked_by(run) is None
    auto.set_state(run, "running", pid=os.getpid())
    os.utime(run.file("auto.json"), (old, old))
    run.file("auto.lock").unlink()
    assert not auto.alive_run(run)


def test_started_is_none_for_no_such_process():
    assert auto._started(999999) is None and auto._started(0) is None
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `uv run pytest tests/test_auto.py -k "started" -v`
Expected: FAIL (`locked_by` vẫn trả pid; `_started` chưa có).

- [ ] **Step 3: Viết `_started` và `_alive(pid, since)` trong `vshort/auto.py`**

Gọi `["ps", "-o", "lstart=", "-p", str(pid)]` với `env=os.environ | {"LC_ALL": "C"}`, rồi đọc bằng
`time.mktime(time.strptime(s, "%a %b %d %H:%M:%S %Y"))`. Cách này chạy được cả trên macOS lẫn Linux. Với `pid <= 0` thì trả
`None`. `_alive(pid, since)` trả `start is not None and start <= since + 1`. `lstart` chỉ chính xác tới giây; file luôn được ghi
**sau** khi tiến trình đã chạy, bởi chính nó hoặc bởi `cmd_auto` sau `Popen`. Truyền `since` như sau:
- `locked_by`: `lock.stat().st_mtime`;
- `alive_run`: mtime của `auto.json` (không có file thì `False`).

Viết docstring nói rõ vì sao: sau khi khởi động lại máy, pid cũ có thể thuộc một tiến trình khác.

- [ ] **Step 4: Chạy lại toàn bộ test liên quan**

Run: `uv run pytest tests/test_auto.py tests/test_cli.py -v`
Expected: PASS hết, kể cả `test_lock_refuses_second_and_takes_dead_lock`, `test_wait_reports_a_run_that_died` và
`test_auto_launch_detaches_and_refuses_while_running`.

- [ ] **Step 5: Commit**

```bash
git add vshort/auto.py tests/test_auto.py
git commit -m "fix: a pid reused after a reboot no longer looks like a live vshort auto (start time vs the file that names it)"
```

---

### Task 2: Kiểm phiên NotebookLM trước bước research

**Files:**
- Modify: `vshort/auto.py` (`_flow`, nhánh `if not run.done("research")`)
- Test: `tests/test_auto.py`

**Interfaces:**
- Consumes: `auto.notebooklm(args) -> int` (đã có), `cli.AUTH`, `cli.RELOGIN`.
- Produces: khi phiên hết hạn, `run_auto` trả `AUTH` (4), `auto.json` có `state == "error"` và `message == cli.RELOGIN` **đúng
  nguyên văn**. Task 3 dựa vào phép so sánh bằng này để tạm dừng hàng đợi.

- [ ] **Step 1: Viết test hỏng**

```python
def test_expired_notebooklm_stops_before_research(flow, monkeypatch):
    from vshort.cli import RELOGIN
    run, fk = flow
    monkeypatch.setattr(auto, "notebooklm", lambda args: fk.nb.append(args[:2]) or (4 if args[:2] == ["auth", "check"] else 0))
    assert auto.run_auto(run) == 4
    st = auto.get_state(run)
    assert st["state"] == "error" and st["message"] == RELOGIN and not fk.agents
```

Sửa luôn test cũ `test_stops_for_brief_then_for_translation`: `assert fk.nb == [["auth", "check"], ["source", "add"]]`.
`test_rerun_does_not_repeat_finished_steps` phải vẫn qua: research đã xong thì không kiểm lại.

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `uv run pytest tests/test_auto.py -k "notebooklm or brief_then" -v`
Expected: FAIL.

- [ ] **Step 3: Thêm phần kiểm trong `_flow`**

Đặt ngay đầu khối `if not run.done("research"):`, gọi `notebooklm(["auth", "check", "--test"])`. Mã khác 0 thì
`raise Stop(code, RELOGIN if code == AUTH else "Không kiểm được phiên NotebookLM; xem auto.log")`, đúng như `_vs`. Không dùng
`--passive`, để lần kiểm cũng tự làm mới cookie giống các lệnh thật. Đã đo trên `pve2` ngày 03/11: chạy 1,3 giây; phiên hết hạn thì
thoát 1 và in "Run 'notebooklm login'", nên `cli._notebooklm` tự trả `AUTH`. Cùng lúc đó `notebooklm list` thật cũng hỏng với cùng
lý do, tức lần kiểm này khớp với lúc dùng thật, không khắt khe hơn. Thêm ghi chú `# ponytail:`: lệnh này có lần treo hơn 2 phút
trên Mac; nếu thấy treo trên server thì thêm timeout cho `run_notebooklm`.

- [ ] **Step 4: Chạy lại**

Run: `uv run pytest tests/test_auto.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vshort/auto.py tests/test_auto.py
git commit -m "feat: vshort auto checks the NotebookLM session before research and stops with the relogin message"
```

---

### Task 3: Hàng đợi, slug, đường dẫn an toàn, trạng thái từng video (`vshort/queue.py`)

**Files:**
- Create: `vshort/queue.py`
- Modify: `config.toml` (thêm ba khóa ở Global Constraints)
- Test: `tests/test_queue.py`

**Interfaces:**
- Consumes: `vshort.run.Run`, `vshort.run.config`, `auto.get_state`, `auto.alive_run`, `auto.total_cost`, `cli.RELOGIN`.
- Produces:
  - `SLUG_RE`, `MAX_TOPIC = 500`.
  - `slugify(topic: str) -> str`: bỏ dấu (NFKD, `đ`→`d`), chữ thường, ký tự ngoài `[a-z0-9]` thành `-`, gộp các `-` liền nhau,
    bỏ `-` hai đầu, cắt ≤ 60 ký tự tại một dấu `-`. Topic là URL thì lấy đoạn cuối của path. Có thể trả `""`.
  - `runs_dir() -> Path`.
  - `run_path(slug: str) -> Path`: `ValueError` khi slug sai regex.
  - `safe_file(slug: str, name: str) -> Path | None`: `resolve()` rồi phải `is_relative_to(run_path(slug).resolve())` và là file
    thường; không thì `None`.
  - `@dataclass Queue: new: list[dict]` (mỗi phần tử `{"slug", "topic", "auto", "added"}`) và `resume: list[str]`.
  - `load_queue() -> Queue`, `save_queue(q: Queue) -> None`: file `runs_dir()/queue.json`, ghi tmp rồi `replace` như `Run._save`.
  - `add_topics(q: Queue, items: list[dict], auto: bool) -> list[str]`: `items` là `{"slug", "topic"}`. Trả một chuỗi lỗi cho mỗi
    item, `""` là hợp lệ. **Chỉ thêm khi không item nào lỗi.**
  - `add_resume(q: Queue, slug: str) -> None`: không thêm trùng.
  - `STEPS: list[tuple[str, str]]`: thứ tự và nhãn tiếng Việt: `research` "Tìm hiểu", `approve_brief` "Chờ duyệt brief",
    `source` "Nạp brief", `fetch` "NotebookLM làm video", `detect` "Tách phụ đề", `transcribe` "Chép phụ đề", `text` "Ghép câu",
    `translate` "Dịch", `approve_script` "Chờ duyệt bản dịch", `plates` "Xóa chữ cũ", `motion` "Hình động", `stills` "Ảnh tĩnh",
    `tts` "Đọc giọng", `visuals` "Tư liệu", `timeline` "Dòng thời gian", `render` "Dựng video", `review0` "Soát".
  - `status(run: Run, queued: bool) -> dict`, gọi là **Row**: `{"slug", "topic", "auto", "state", "message", "step", "since",
    "cost", "verdict", "seconds", "relogin"}`.
    - `state` là một trong `queued | running | dead | wait_brief | wait_script | error | done | idle`:
      - `queued` khi `queued=True`;
      - `dead` khi `auto.json` nói `running` nhưng `not alive_run`;
      - `idle` khi chưa có `auto.json`.
      - Trạng thái lạ (ngoài `running | wait_brief | wait_script | error | done`, là những trạng thái `auto.py` ghi hiện nay) thì
        coi như `error` để nó hiện ở nhóm cần Tai, không biến mất khỏi danh sách.
    - `step`: nhãn của bước đầu tiên trong `STEPS` chưa `done`.
    - `since`: mtime của `auto.json`, không có thì của `run.json`.
    - `verdict` lấy từ `review.json`, `seconds` từ `timeline.json["total"]`; thiếu file thì `None`.
    - `relogin`: `state == "error" and message == cli.RELOGIN`.
    - `message` bỏ các dòng bắt đầu bằng `"Chép về Mac"`.
    - Đọc JSON hỏng hay thiếu `run.json` không được ném lỗi. `auto.json` đọc không được thì coi như không có (`idle`).
      `run.json` thiếu hoặc hỏng thì `topic` rỗng.
  - `rows(q: Queue) -> list[Row]`:
    - gồm mọi thư mục con của `runs_dir()` có slug hợp lệ, và các item `q.new` (Row `queued`, `since = added`);
    - slug trong `q.resume` thì `queued=True`;
    - sắp xếp: `wait_brief`, `wait_script`, `error`, `dead` → `running` → `queued` (theo thứ tự `resume` rồi `new`) → `done`
      (mới nhất trước) → `idle`.
  - `relogin_waiting(rs: list[Row]) -> list[str]`: slug có `relogin` và không `queued`. Khác rỗng nghĩa là hàng đợi đang tạm dừng.
  - `next_to_start(q: Queue, rs: list[Row], max_running: int) -> list[tuple[str, str]]`: trả `[("resume", slug) | ("new", slug)]`,
    `resume` trước `new`, theo FIFO. Số lượng = `max_running` trừ số Row `running`. Trả `[]` khi `relogin_waiting(rs)` khác rỗng.

- [ ] **Step 1: Viết test hỏng** (`tests/test_queue.py`)

Dùng `monkeypatch` cho `queue.runs_dir` trỏ tới `tmp_path`.

```python
def test_slugify_and_validation():
    assert queue.slugify("Five Solas: năm chữ “chỉ” của Cải cách") == "five-solas-nam-chu-chi-cua-cai-cach"
    assert queue.slugify("https://www.reformationbiblecollege.org/blog/the-five-solas") == "the-five-solas"
    assert queue.slugify("🙂 !!!") == ""
    assert len(queue.slugify("a-" * 80)) <= 60
    with pytest.raises(ValueError):
        queue.run_path("../etc")

def test_add_topics_all_or_nothing(tmp_runs):          # tmp_runs: runs_dir() -> tmp_path; tmp_path/"five-solas" exists
    q = queue.Queue([], [])
    errs = queue.add_topics(q, [{"slug": "a", "topic": "A"}, {"slug": "a", "topic": "A2"},
                                {"slug": "", "topic": "🙂"}, {"slug": "five-solas", "topic": "x"},
                                {"slug": "b", "topic": "x" * 501}], auto=True)
    assert errs[0] == "" and all(errs[1:]) and q.new == []
    assert queue.add_topics(q, [{"slug": "a", "topic": "A"}], auto=True) == [""] and q.new[0]["auto"] is True

def test_add_resume_is_idempotent():
    q = queue.Queue([], [])
    queue.add_resume(q, "s"); queue.add_resume(q, "s")
    assert q.resume == ["s"]

def test_safe_file_stays_inside_the_run(tmp_runs, tmp_path):
    (tmp_path / "s").mkdir(); (tmp_path / "s" / "final.mp4").write_bytes(b"x")
    (tmp_path / "secret").write_text("x"); (tmp_path / "s" / "link.mp4").symlink_to(tmp_path / "secret")
    assert queue.safe_file("s", "final.mp4") == (tmp_path / "s" / "final.mp4").resolve()
    assert queue.safe_file("s", "../secret") is None and queue.safe_file("s", "link.mp4") is None
    assert queue.safe_file("s", "nothing.mp4") is None

def test_rows_survive_odd_folders_and_sort(tmp_runs, tmp_path):
    # odd: no run.json; broken: auto.json is not JSON; w: wait_script; d: done; r: running with a dead pid
    ...
    rs = queue.rows(queue.Queue([{"slug": "n", "topic": "N", "auto": False, "added": 1.0}], []))
    assert [r["slug"] for r in rs][:2] == ["w", "r"] and {r["state"] for r in rs} >= {"dead", "done", "queued", "idle"}
    assert next(r for r in rs if r["slug"] == "r")["state"] == "dead"

def test_queued_resume_hides_the_old_wait_state(tmp_runs, tmp_path):
    # a run whose auto.json still says wait_brief but is in q.resume shows as queued, not as needing Tai
    ...

def test_next_to_start_respects_limit_order_and_pause():
    q = queue.Queue([{"slug": "n1"}, {"slug": "n2"}], ["r1"])
    running = [{"state": "running", "relogin": False, "slug": "x"}]
    assert queue.next_to_start(q, running, 3) == [("resume", "r1"), ("new", "n1")]
    assert queue.next_to_start(q, running * 3, 3) == []
    paused = running + [{"state": "error", "relogin": True, "slug": "e"}]
    assert queue.next_to_start(q, paused, 3) == [] and queue.relogin_waiting(paused) == ["e"]
```

Các test có `...` thì người làm tự dựng thư mục cho đúng chú thích. Assert giữ nguyên như trên. Run `r` có `auto.json` đặt
`running` với `pid=999999`.

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `uv run pytest tests/test_queue.py -v`
Expected: FAIL (`ModuleNotFoundError: vshort.queue`).

- [ ] **Step 3: Viết `vshort/queue.py` và thêm ba khóa vào `config.toml`**

Theo đúng Interfaces ở trên. `rows()` chỉ gọi `alive_run` cho Row có `auto.json` là `running`, vì mỗi lần gọi chạy một lệnh `ps`.

- [ ] **Step 4: Chạy lại**

Run: `uv run pytest tests/test_queue.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vshort/queue.py tests/test_queue.py config.toml
git commit -m "feat: web queue — slugs, safe run files, per-video status rows, what to start next"
```

---

### Task 4: Server web, phần đọc: trạng thái, chi tiết, video có Range, mã truy cập, file tĩnh

**Files:**
- Create: `vshort/web.py`
- Modify: `pyproject.toml` (`dependencies` thêm `"starlette>=0.39"` và `"uvicorn"`; nhóm `dev` thêm `"httpx"`), `uv.lock`
  (`uv lock`), `.gitignore` (thêm `web/node_modules/`, `web/dist/`)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: mọi thứ Task 3 đưa ra; `auto.locked_by`.
- Produces:
  - `app: Starlette`; `main()` chạy `uvicorn.run(app, host="0.0.0.0", port=config()["web_port"])`. Có thêm
    `if __name__ == "__main__": main()` để chạy bằng `python -m vshort.web`.
  - `token() -> str`: đọc `web_token_file`, bỏ khoảng trắng; thiếu file thì `""`.
  - `can_write(request) -> bool`: `token()` khác rỗng và `hmac.compare_digest` với cookie `vshort_token`.
  - Các route đọc:
    - `GET /api/state` → `{"rows": [Row], "relogin": [slug], "can_write": bool, "token_set": bool, "max_running": int}`.
    - `GET /api/runs/{slug}` → `{"row": Row, "locked": bool, "brief_vi": str|None, "brief_en": str|None,
      "brief_en_stale": bool, "translation": [{"id", "en", "phrases", "note"}]|None, "proposed": [{"id", "phrases", "note"}]|None,
      "review_md": str|None, "cost": [dòng cost.json], "log_tail": str, "video": bool}`.
      - `translation` ghép `sentences.en.json` với `script.vi.json` theo `id`.
      - `brief_en_stale` đúng khi mtime của `brief.vi.md` lớn hơn của `brief.en.md` (cùng luật với `cmd_approve`).
      - `log_tail` là 50 dòng cuối `auto.log`.
      - `video` đúng khi có `final.mp4` và không `locked`.
    - `GET /files/{slug}/final.mp4[?download=1]` → `FileResponse` qua `safe_file`. Có `download` thì `filename=f"{slug}.mp4"`.
      Đang khóa thì 409. Chỉ phục vụ đúng tên `final.mp4`.
    - `POST /api/login {"token"}` → đúng mã thì đặt cookie `vshort_token` (`httponly`, `samesite="strict"`, `max_age` 1 năm),
      trả 204; sai thì 403.
  - Mọi lỗi trả `JSONResponse({"error": "<tiếng Việt>"}, status)`. Slug sai thì 404.
  - Route video khai báo là `/files/{slug}/{name}`; `name` khác `final.mp4` thì 404.
  - `Mount("/", StaticFiles(directory=ROOT / "web" / "dist", html=True))` đặt **cuối** danh sách route, và **chỉ khi thư mục đó
    tồn tại**. Khi chưa build, StaticFiles với thư mục thiếu sẽ trả 500, nên lúc đó đường dẫn lạ phải trả 404.

- [ ] **Step 1: Viết test hỏng** (`tests/test_web.py`, dùng `starlette.testclient.TestClient`)

Fixture `client` đặt `queue.runs_dir` vào `tmp_path`, `web.token` → `"bi-mat"`, rồi dựng run `s` có `final.mp4` 1000 byte,
`brief.vi.md`, `brief.en.md`, `sentences.en.json`, `script.vi.json`, `auto.json` (`done`).

```python
def test_state_lists_runs_and_reports_no_write(client):
    j = client.get("/api/state").json()
    assert [r["slug"] for r in j["rows"]] == ["s"] and j["can_write"] is False and j["token_set"] is True

def test_video_supports_range_and_download(client):
    r = client.get("/files/s/final.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100 and r.headers["accept-ranges"] == "bytes"
    assert 's.mp4' in client.get("/files/s/final.mp4?download=1").headers["content-disposition"]

def test_files_refuse_other_names_and_escapes(client):
    for url in ("/files/s/brief.vi.md", "/files/s/..%2F..%2Fetc%2Fpasswd", "/files/..%2Fs/final.mp4", "/files/NOPE/final.mp4"):
        assert client.get(url).status_code == 404

def test_video_is_409_while_the_run_is_locked(client, run_s):
    run_s.file("auto.lock").write_text(str(os.getpid()))
    assert client.get("/files/s/final.mp4").status_code == 409

def test_login_sets_cookie_only_with_the_right_token(client, monkeypatch):
    assert client.post("/api/login", json={"token": "sai"}).status_code == 403
    assert client.post("/api/login", json={"token": "bi-mat"}).status_code == 204
    assert client.get("/api/state").json()["can_write"] is True
    monkeypatch.setattr(web, "token", lambda: "doi-ma")           # token changed on the server
    assert client.get("/api/state").json()["can_write"] is False

def test_detail_joins_translation_and_flags_stale_english_brief(client, run_s):
    ...  # touch brief.vi.md newer than brief.en.md
    j = client.get("/api/runs/s").json()
    assert j["brief_en_stale"] is True and j["translation"][0] == {"id": 1, "en": "Hello there.", "phrases": "Xin | chào", "note": ""}
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `uv sync && uv run pytest tests/test_web.py -v`
Expected: FAIL (`vshort.web` chưa có).

- [ ] **Step 3: Viết `vshort/web.py` (phần đọc), sửa `pyproject.toml`, `uv lock`, `.gitignore`**

Endpoint viết sync (`def`); Starlette tự chạy chúng trong threadpool.

- [ ] **Step 4: Chạy lại**

Run: `uv run pytest tests/test_web.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vshort/web.py tests/test_web.py pyproject.toml uv.lock .gitignore
git commit -m "feat: vshort web — read API, final.mp4 with HTTP Range, shared access code, static UI"
```

---

### Task 5: Server web, phần ghi và vòng lặp hàng đợi

**Files:**
- Modify: `vshort/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 3, Task 4; `auto.run_claude(run, step, agent, prompt, timeout) -> str`; `auto.locked_by`.
- Produces:
  - `LOCK = threading.Lock()`: bọc **mọi** chuỗi load → sửa → save `queue.json`, cả trong `tick()` lẫn trong route.
  - `vshort(args: list[str]) -> subprocess.CompletedProcess`: chạy `[sys.executable, "-m", "vshort.cli", *args]`, `cwd=ROOT`,
    `capture_output=True`, `text=True`, `timeout=120`.
  - `start(kind: str, slug: str, item: dict | None) -> None`:
    - `new` → `vshort(["auto", slug, "--topic", item["topic"], *(["--auto"] if item["auto"] else [])])`;
    - `resume` → `vshort(["auto", str(run_path(slug))])`;
    - mã khác 0 thì ghi một dòng vào `runs_dir()/web.log` rồi bỏ item. Thêm ghi chú
      `# ponytail: item hỏng bị bỏ, chỉ ghi log; hiện lên trang nếu thấy xảy ra`.
  - `tick() -> None`: dưới `LOCK`: `load_queue` → `rows` → `next_to_start(q, rs, config()["web_max_running"])` → `start` từng cái →
    gỡ khỏi `q` → `save_queue`.
  - Lifespan của Starlette chạy một task asyncio, cứ 5 giây gọi `await anyio.to_thread.run_sync(tick)`; lỗi trong `tick` chỉ ghi log,
    không làm chết vòng lặp.
  - `BRIEF_SYNC` (prompt tiếng Việt):
    `"RUN={run}. Tai vừa sửa {run}/brief.vi.md (diff bên dưới). Sửa {run}/brief.en.md cho khớp đúng những chỗ đó, giữ nguyên phần
    còn lại. Không tạo notebook, không nạp nguồn, không tìm web.\n\n```diff\n{diff}\n```"`.
  - Các route ghi: tất cả là POST, nhận JSON. Chưa có mã thì 403 `{"error": "Cần mã truy cập"}`. Route của một run mà run đang khóa
    thì 409 `{"error": "Video đang chạy, đợi nó dừng rồi sửa"}`.
    - `/api/queue {"items": [{"slug", "topic"}], "auto": bool}` → `{"errors": [str]}`; 400 khi có lỗi.
    - `/api/queue/remove {"slug"}`: chỉ gỡ khỏi `q.new`.
    - `/api/runs/{slug}/brief {"vi"}`:
      - ghi `brief.vi.md`;
      - nếu khác bản cũ: `difflib.unified_diff`, rồi `auto.run_claude(run, "brief_sync", "vs-researcher", BRIEF_SYNC…, 600)`;
      - trả `{"brief_en": <đọc lại>, "brief_en_stale": bool}`;
      - agent lỗi thì 502 kèm lý do, bản Việt vẫn đã lưu.
    - `/api/runs/{slug}/brief_en {"en"}` → ghi `brief.en.md`.
    - `/api/runs/{slug}/script {"rows": [{"id", "phrases", "note"}]}`:
      - tập `id` phải đúng bằng tập hiện có, không thì 400;
      - ghi `script.vi.json`, chạy `vshort(["check", path])`;
      - trả `{"ok": returncode == 0, "problems": [dòng stderr không rỗng]}`.
    - `/api/runs/{slug}/proposal {"use": bool}`: `use` thì chép `script.proposed.json` sang `script.vi.json`; trường hợp nào cũng
      xóa `script.proposed.json`.
    - `/api/runs/{slug}/approve {"what": "brief"|"script"}` → `vshort(["approve", path, what])`. Mã 0 thì `add_resume`, trả 204;
      khác 0 thì 400 với stderr.
    - `/api/runs/{slug}/retry`: chỉ khi Row là `error` hoặc `dead`, rồi `add_resume`.
    - `/api/resume`: `add_resume` cho mọi slug trong `relogin_waiting(rows(q))`.

- [ ] **Step 1: Viết test hỏng**

Đặt `web.vshort` thành hàm giả ghi lại `args` và trả `CompletedProcess` theo kịch bản. Monkeypatch `auto.run_claude` cho test brief.
Đăng nhập trước bằng `client.post("/api/login", …)`.

```python
def test_writes_need_the_code(client_anon):
    assert client_anon.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False}).status_code == 403

def test_queue_add_then_tick_starts_up_to_the_limit(client, calls, monkeypatch):
    cfg = web.config()
    monkeypatch.setattr(web, "config", lambda: cfg | {"web_max_running": 2})  # web.py: `from vshort.run import config`
    items = [{"slug": s, "topic": s.upper()} for s in ("a", "b", "c")]
    assert client.post("/api/queue", json={"items": items, "auto": True}).json() == {"errors": ["", "", ""]}
    web.tick()
    assert calls == [["auto", "a", "--topic", "A", "--auto"], ["auto", "b", "--topic", "B", "--auto"]]
    assert [i["slug"] for i in queue.load_queue().new] == ["c"]

def test_approve_requeues_once_and_tick_resumes_it(client, calls, run_wait_script):
    assert client.post("/api/runs/w/approve", json={"what": "script"}).status_code == 204
    client.post("/api/runs/w/approve", json={"what": "script"})
    assert queue.load_queue().resume == ["w"]
    web.tick()
    assert calls[-1] == ["auto", str(queue.run_path("w"))]

def test_locked_run_refuses_edits(client, run_s):
    run_s.file("auto.lock").write_text(str(os.getpid()))
    assert client.post("/api/runs/s/script", json={"rows": []}).status_code == 409

def test_script_save_runs_check_and_reports_problems(client, calls_with_check_failing, run_wait_script): ...
    # rows with a missing id → 400; good rows → script.vi.json written, {"ok": False, "problems": ["câu 2: …"]}

def test_brief_save_syncs_english_with_a_cheap_agent(client, run_wait_brief, monkeypatch):
    seen = []
    monkeypatch.setattr(auto, "run_claude", lambda run, step, agent, prompt, t: seen.append((step, agent, prompt))
                        or run.file("brief.en.md").write_text("EN mới") or "xong")
    j = client.post("/api/runs/b/brief", json={"vi": "VI mới"}).json()
    assert j == {"brief_en": "EN mới", "brief_en_stale": False}
    assert seen[0][:2] == ("brief_sync", "vs-researcher") and "+VI mới" in seen[0][2]

def test_relogin_pauses_the_queue_until_resume(client, calls, run_relogin):
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False})
    web.tick(); assert calls == []
    assert client.post("/api/resume").status_code == 204
    web.tick(); assert calls[0] == ["auto", str(queue.run_path("e"))]
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `uv run pytest tests/test_web.py -v`
Expected: các test mới FAIL, test của Task 4 vẫn PASS.

- [ ] **Step 3: Viết phần ghi và vòng lặp vào `vshort/web.py`**

- [ ] **Step 4: Chạy cả bộ test**

Run: `uv run pytest -q`
Expected: PASS hết. Test cũ nào hỏng vì thay đổi của phiên khác thì ghi lại, không sửa.

- [ ] **Step 5: Commit**

```bash
git add vshort/web.py tests/test_web.py
git commit -m "feat: vshort web — queue of up to 3 runs, approve and edit brief/translation, retry, pause on NotebookLM relogin"
```

---

### Task 6: Giao diện, khung app và màn hình danh sách

**Files:**
- Create: `web/` (Vite + React + TypeScript), gồm `web/package.json`, `web/vite.config.ts`, `web/index.html`, `web/src/main.tsx`,
  `web/src/api.ts`, `web/src/App.tsx`, `web/src/RunList.tsx`, `web/src/AddTopics.tsx`, `web/src/AccessCode.tsx`, và
  `web/src/components/ui/*` do `npx shadcn@latest add` sinh ra
- Modify: không

**Interfaces:**
- Consumes: các route ở Task 4–5, đúng tên trường JSON đã ghi ở đó.
- Produces:
  - `web/src/api.ts`:
    - các type `Row`, `State`, `Detail` khớp JSON;
    - `getState(): Promise<State>`, `getRun(slug): Promise<Detail>`;
    - `post(path, body): Promise<any>`: ném `ApiError {status, error}` khi mã khác 2xx.
  - Định tuyến bằng hash: `#/` là danh sách, `#/r/<slug>` là chi tiết (Task 7 viết màn hình chi tiết; ở task này để một chỗ trống).

Chi tiết từng phần:

- **Khởi tạo:** `npm create vite@latest web -- --template react-ts`, cài Tailwind theo hướng dẫn Vite hiện tại của shadcn, rồi
  `npx shadcn@latest init`. Component dùng: `button card badge input textarea checkbox table alert separator skeleton sonner`.
- **`vite.config.ts`:** proxy `/api` và `/files` tới `http://127.0.0.1:8770` để chạy thử trên Mac. `index.html` có
  `<html lang="vi" class="dark">`.
- **Băng trên cùng:** khi `state.relogin` khác rỗng, hiện `Alert` "Hàng đợi tạm dừng: NotebookLM hết phiên đăng nhập". Kèm các
  slug, nội dung hướng dẫn (lấy `message` của Row `relogin`, giữ xuống dòng), và nút "Chạy tiếp hàng đợi" (`POST /api/resume`).
- **`AddTopics`:**
  - một `Textarea`, mỗi dòng một chủ đề;
  - xem trước bảng `slug | chủ đề`, slug sinh bằng một bản `slugify` phía client chỉ để gợi ý, và sửa được;
  - `Checkbox` "Bỏ duyệt brief", nút "Thêm vào hàng đợi";
  - lỗi trả về hiện dưới đúng dòng.
- **`RunList`:**
  - mỗi Row một dòng (hoặc một thẻ trên màn hẹp), gồm slug, chủ đề, `Badge` trạng thái tiếng Việt;
  - nhãn trạng thái: `queued` "Đang xếp hàng", `running` "Đang chạy", `dead` "Dừng giữa chừng", `wait_brief` "Chờ duyệt brief",
    `wait_script` "Chờ duyệt bản dịch", `error` "Lỗi", `done` "Xong", `idle` "Chưa chạy tự động";
  - `running` hiện `step` và thời gian kể từ `since`; `error`/`dead` hiện dòng đầu `message`; `done` hiện `verdict`, chi phí `$x.xx`,
    độ dài `seconds`;
  - bấm một dòng thì vào `#/r/<slug>`; Row `queued` chưa có thư mục thì có nút "Gỡ" (`POST /api/queue/remove`).
- **Làm mới:** gọi lại `getState` mỗi 5 giây.
- **`AccessCode`:** khi `can_write` là false, hiện ô nhập mã và nút "Nhập mã" (`POST /api/login`). Nút ghi bị tắt và có ghi chú
  "Cần mã truy cập". Lệnh ghi nào trả 403 thì làm mới `State` để ô nhập mã hiện lại.

- [ ] **Step 1: Khởi tạo dự án, cài shadcn và các component trên**

Run: `cd web && npm install && npm run build`
Expected: build xong, có `web/dist/index.html`.

- [ ] **Step 2: Viết `api.ts`, `App.tsx`, `RunList`, `AddTopics`, `AccessCode`**

- [ ] **Step 3: Kiểm kiểu và build**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: không lỗi.

- [ ] **Step 4: Kiểm tay trên Mac**

Chạy `uv run python -m vshort.web`, rồi `cd web && npm run dev`. Mở trang bằng skill `run` hoặc trình duyệt.

Danh sách phải hiện các run thật trong `~/notebooklm-videos`, trong đó `haiku-test` và `zerotts-test` không làm sập trang. Thu hẹp
cửa sổ còn 390px, không cuộn ngang. **Không** nhập mã và **không** thêm chủ đề thật trên Mac, vì việc đó sẽ chạy agent thật.

Thử cookie cũ:
1. Tạo file mã tạm.
2. Nhập mã trên trang.
3. Đổi nội dung file mã.
4. Bấm một nút ghi bất kỳ. Ô nhập mã phải hiện lại.
5. Xóa file mã tạm.

- [ ] **Step 5: Commit**

```bash
git add web/ ':!web/node_modules' ':!web/dist'
git commit -m "feat: web UI — shadcn list of videos, paste topics into the queue, access code, relogin banner"
```

---

### Task 7: Giao diện, màn hình chi tiết một video

**Files:**
- Create: `web/src/RunDetail.tsx`, `web/src/BriefReview.tsx`, `web/src/ScriptReview.tsx`, `web/src/Finished.tsx`, `web/src/Failed.tsx`
- Modify: `web/src/App.tsx` (gắn `#/r/<slug>`)

**Interfaces:**
- Consumes: `getRun`, `post`, các type trong `api.ts` (Task 6).

Chi tiết từng phần:

- **`RunDetail`:** đầu trang có slug, chủ đề, trạng thái. Khi `locked`, mọi nút sửa/duyệt bị tắt và có dòng "Video đang chạy".
  Làm mới mỗi 5 giây, **trừ khi** đang có chỉnh sửa chưa lưu.
- **`BriefReview` (`wait_brief`):**
  - `Textarea` lớn cho `brief_vi`, nút "Lưu và cập nhật bản tiếng Anh"; trong lúc chờ (có thể 1–2 phút) hiện "Đang cập nhật bản
    tiếng Anh…";
  - `brief_en` ở khung thu gọn được, sửa tay được (nút "Lưu bản tiếng Anh");
  - nút "Duyệt brief" tắt khi `brief_en_stale`, kèm dòng giải thích "Bản tiếng Anh cũ hơn bản tiếng Việt — NotebookLM làm video từ
    bản tiếng Anh".
- **`ScriptReview` (`wait_script`):**
  - bảng `id | tiếng Anh | tiếng Việt | ghi chú`;
  - lời Việt sửa trong ô nhập, dấu `|` giữ nguyên và hiện mờ như chỗ ngắt cụm phụ đề;
  - nút "Lưu và kiểm" hiện `problems` dưới bảng;
  - có `proposed` thì hiện cột "Đề xuất" cạnh lời Việt, với nút "Dùng bản đề xuất" và "Bỏ";
  - nút "Duyệt bản dịch" (lỗi 400 thì hiện stderr).
- **`Finished` (`done`):** `<video controls playsInline src="/files/<slug>/final.mp4">` và nút "Tải về" (`?download=1`). Hiện
  `message` (giữ xuống dòng), `review_md` qua một trình hiển thị markdown nhẹ, ví dụ `react-markdown`, và bảng `cost`
  (bước, agent, giây, $).
- **`Failed` (`error`, `dead`):** hiện `message` nguyên văn và `log_tail` trong khung chữ đơn cách, cùng nút "Chạy lại"
  (`POST /api/runs/<slug>/retry`).
- Các trạng thái khác hiện thông tin của Row và `log_tail`.

- [ ] **Step 1: Viết các component trên**

- [ ] **Step 2: Kiểm kiểu và build**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: không lỗi.

- [ ] **Step 3: Kiểm tay trên Mac** (chỉ xem, không ghi)

- Mở `five-solas`: video phát và tua được trong Safari trên Mac, nút tải về tải đúng file `five-solas.mp4`, `review.md` hiển thị
  đúng.
- Mở `linux-tcp-cve-2026-98432`: bảng chi phí có nhiều dòng.
- Muốn xem màn hình duyệt: chép `five-solas` sang `~/notebooklm-videos/ui-test`, sửa `auto.json` thành `wait_script`, mở trang,
  rồi xóa `ui-test`.

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat: web UI — per-video page: review brief/translation, watch and download, errors and retry"
```

---

### Task 8: Đưa lên `pve2` và chạy kiểm tra của spec

**Files:**
- Create: `web/vshort-web.service`
- Modify: `docs/research-2026-11-02.md` (thêm một mục ngắn: cổng, cách khởi động lại, chỗ đặt file mã)

**Interfaces:**
- Consumes: toàn bộ các task trước.

Nội dung `web/vshort-web.service` (systemd user unit):
- `WorkingDirectory=%h/video-pipeline`.
- `Environment=PATH=%h/.local/bin:%h/.nvm/versions/node/v24.19.0/bin:/usr/local/bin:/usr/bin:/bin`.
- `ExecStart=%h/.local/bin/uv run python -m vshort.web`.
- `Restart=on-failure`, `WantedBy=default.target`.

Việc nào đụng tới server mà cần quyền (`loginctl enable-linger`, hay cần `sudo`) thì **hỏi Tai trước**.

- [ ] **Step 1: Đưa code lên server.** Merge vào `main` và push (hỏi Tai trước khi push). Rồi trên server: `cd ~/video-pipeline &&
  git pull && uv sync && cd web && npm ci && npm run build`.
- [ ] **Step 2: Tạo mã truy cập.** Trên server, chạy
  `python3 -c "import secrets; print(secrets.token_urlsafe(12))" > ~/.config/vshort/web_token && chmod 600 ~/.config/vshort/web_token`.
  Tạo thư mục trước nếu chưa có. Báo mã cho Tai qua terminal, không ghi vào git.
- [ ] **Step 3: Cài dịch vụ.** Chép unit vào `~/.config/systemd/user/`, rồi `systemctl --user daemon-reload && systemctl --user
  enable --now vshort-web`. Kiểm bằng `curl -s http://192.168.1.214:8770/api/state | head -c 200`: phải ra JSON có `"rows"`.
- [ ] **Step 4: Đăng nhập lại NotebookLM.** Lúc lập kế hoạch (03/11), cả `notebooklm auth check --test` lẫn `notebooklm list` trên
  server đều hỏng vì thiếu cookie `__Secure-1PSIDTS`. Nhờ Tai đăng nhập lại (trên Mac, `notebooklm login` rồi `scp` như `cli.RELOGIN`) trước khi chạy kiểm tra 1.
- [ ] **Step 5: Cùng Tai chạy 8 kiểm tra trong mục "Kiểm tra trước khi coi là xong" của spec,** đúng thứ tự, ghi kết quả từng cái.
  Kiểm tra 4 (video phát và tua được trên iPhone Safari) phải do Tai làm trên điện thoại.
- [ ] **Step 6: Commit unit và ghi chú**

```bash
git add web/vshort-web.service docs/research-2026-11-02.md
git commit -m "docs: run vshort web on pve2 as a systemd user service"
```
