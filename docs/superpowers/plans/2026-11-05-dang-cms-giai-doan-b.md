# Gửi video lên CMS, giai đoạn B — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trên tab Đăng bài của video đã xong có nút "Gửi lên CMS". Bấm nút thì:
- server tạo một bài cá nhân chưa xuất bản theo khuôn bài 22457;
- server đề xuất bài Facebook, YouTube, TikTok;
- bấm lại thì an toàn: không bài trùng, không đè sửa của Tai, không kéo bài đã xuất bản về nháp.

**Architecture:**
- `vshort/cms.py`: đọc cấu hình, gọi GraphQL và REST của CMS bằng `urllib`. Mọi lệnh gọi mạng đi qua một hàm `_http` để test thay bằng CMS giả.
- `vshort/publish.py`: luồng gửi.
  - Làm từng việc, ghi kết quả vào `RUN/cms.json` (tách theo `dev`/`prod`). Chạy lại thì làm tiếp từ việc dở.
  - Đọc trạng thái bài trên CMS trước mỗi lần ghi.
- `vshort cms <run>`: chạy nền như `vshort auto`, có khóa riêng. Web gọi lệnh này rồi trả 202 ngay.
- Trang đọc `cms.json` qua `/api/runs/<slug>` mỗi 5 giây.

**Tech Stack:**
- Python 3.12 stdlib (`urllib.request`, `tomllib`, `hashlib`), Starlette, pytest.
- React 19, Tailwind 4. Không thêm gói nào.

**Spec:** `docs/superpowers/specs/2026-11-05-giao-dien-moi-va-dang-cms-design.md`, phần "Giai đoạn B". Dò mã nguồn CMS ngày 05/11 (CMS-Backend, CMS-Admin), các điểm dùng ở dưới đều có dòng code dẫn chứng trong memory `cms-publish-integration.md`.

## Global Constraints

- **Repo:** làm thẳng trên `main`, add file theo tên (không `commit -a`), `git pull --rebase` trước mỗi `git push`. Dòng cuối commit:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Không sửa `~/Documents/Mediasoft/*`.** Chỉ gọi API có sẵn.
- **Không bao giờ:**
  - gọi `approve_zernio_post`;
  - gửi `publishNow` hay `scheduledFor`;
  - gửi `workflow_id` khác chặng hiện tại của bài khi cập nhật;
  - gửi `step_up_token`.
  Test kiểm bằng cách soi mọi body gửi đi.
- **Token:**
  - Token CMS chỉ nằm trong file `token_file` quyền 600 trên pve2.
  - Không in ra màn hình hay chat, không ghi vào `cms.json`, `auto.log`, `web.log`, không trả về trình duyệt, không nằm trong câu báo lỗi.
  - Chép token từ file sang file bằng pipe.
- **Bài luôn là bài cá nhân (PRIVATE),** `submit_type: "save"`. Thử trên **dev** trước. Lần gửi **prod** đầu tiên làm cùng Tai.
- **Chữ trên trang:** tiếng Việt, gọi Tai là "bạn".
- **Lệnh ghi:** mọi lệnh ghi qua `_post` của `vshort/web.py` (mã truy cập, chỉ JSON).
- **Test:**
  - Không gọi CMS thật: `tests/conftest.py` thêm fixture autouse thay `cms._http` bằng hàm raise.
  - Test Python: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest -q`.
  - Giao diện: `cd web && npm run build && npm run lint`.
- **Deploy:** `ssh pve2 'systemd-run --user --unit vshort-update --collect -E PATH="$PATH" ~/video-pipeline/scripts/update-server.sh'`.

## Review Focus

- **Tiến trình chết sau khi `articles_create` trả về nhưng trước khi ghi `article_id`.** Lần chạy sau không được tạo bài thứ hai.
  → `test_crash_after_create_never_creates_twice` (Task 3).
- **Tai đã sửa tiêu đề, sapo, từ khóa trong CMS, rồi tải ảnh Gemini mới và bấm gửi lại.**
  - Lần cập nhật chỉ đổi ảnh đại diện và khối video.
  - Tiêu đề, slug, nội dung lấy từ bản đang có trên CMS.
  - Body không có `desc`, `article_tags`, `article_categories`, `article_genres`, `article_kind_ids`.
  → `test_resend_keeps_tais_edits` (Task 3).
- **Bài đã rời luồng cá nhân (gửi duyệt, đã xuất bản).** Bấm gửi lại không tải file, không ghi gì, chỉ hiện trạng thái và link.
  → `test_left_private_writes_nothing` (Task 3).
- **Token lộ ra ngoài** qua `cms.json`, câu lỗi, JSON trang video, hay `repr` của cấu hình.
  → `test_token_never_leaves` (Task 1), `test_detail_never_carries_the_token` (Task 4).
- **Đổi `use` từ dev sang prod sau khi đã gửi lên dev.** Prod có hồ sơ riêng trong `cms.json`, id bài dev không bao giờ được dùng trên prod.
  → `test_env_records_are_separate` (Task 3).

---

### Task 1: Cấu hình và client CMS

**Files:**
- Create: `vshort/cms.py`
- Modify: `config.toml` (thêm `cms_file = "~/.config/vshort/cms.toml"`), `tests/conftest.py` (fixture `no_real_cms`)
- Test: `tests/test_cms.py`

**Interfaces:**
- Produces:
  - **File cấu hình** `cms.toml`. Bản thân file không chứa bí mật; token nằm ở `token_file`. Dạng:

    ```toml
    use = "dev"                                   # bộ đang dùng: "dev" | "prod"
    [dev]
    api = "https://api.dev.mediasoft.com.vn"
    admin = "https://cms.dev.mediasoft.com.vn"
    token_file = "~/.config/vshort/cms-dev.token" # quyền 600, một dòng
    act_as = "phongvien01"
    department_id = 1
    private_workflow_id = 0                        # chặng PRIVATE của loại bài article_type_id trong phòng ban
    article_type_id = 1                            # bài điện tử
    categories = [0, 0]                            # cái đầu là chuyên mục chính
    genres = [0]                                   # cái đầu is_major
    kinds = [0]
    zernio = { facebook = "", youtube = "", tiktok = "" }   # trống = bỏ nền tảng đó
    [prod]
    # như [dev], api = "https://api.tapchianninhmang.vn", admin = "https://cms.tapchianninhmang.vn"
    ```
  - `class Settings` (dataclass, `repr=False` cho `token`): `env`, `api`, `admin`, `token`, `act_as`, `department_id`,
    `private_workflow_id`, `article_type_id`, `categories: list[int]`, `genres: list[int]`, `kinds: list[int]`,
    `zernio: dict[str, str]`.
  - `cms.load() -> tuple[Settings | None, list[str]]` → `(settings, [])` hoặc `(None, ["các mục thiếu, tiếng Việt"])`.
    Báo thiếu khi:
    - không có file;
    - `use` không phải dev/prod;
    - thiếu khóa, hoặc id bằng 0;
    - `token_file` không có, rỗng, hoặc nhóm/người khác đọc được (`st_mode & 0o077`): "token_file phải để quyền 600".
  - `class CmsError(Exception)`: `.message` (tiếng Việt), `.code: int | None`, `.not_found: bool`, `.answered: bool`.
    `answered` là True khi CMS đã trả lời (có `errors` hoặc mã HTTP), False khi lỗi mạng hay hết giờ.
  - `cms._http(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: int) -> tuple[int, bytes]`.
    Chỉ hàm này chạm mạng. Lỗi mạng → `CmsError("Không kết nối được CMS: …")`.
  - `cms.gql(s: Settings, query: str, variables: dict) -> dict`:
    - POST `{api}/graphql`, các header:
      - `Authorization: Bearer <token>`;
      - `x-mcp-act-as: <act_as>` (nếu có ký tự ngoài ASCII thì `urllib.parse.quote`);
      - `x-department-id: <department_id>`;
      - `Content-Type: application/json`.
    - Trả `data`. Có `errors` thì raise `CmsError` với message của lỗi đầu và `code = errors[0].extensions.code`.
      `not_found = code == 404`.
    - HTTP khác 200 cũng raise.
    - Câu lỗi không bao giờ chứa token.
  - `cms.upload(s: Settings, path: Path, mime: str) -> dict` → `{"id": int, "url": str}`, gồm ba bước:
    1. POST `{api}/files/presigned-upload`, JSON `{file_name, mime_type, file_size, department_id}`, cùng header như `gql`
       → `{uploadUrl, s3Key, expiresIn}`.
    2. PUT `uploadUrl`, body là nguyên byte file, **chỉ** header `Content-Type: <mime>` (không gửi Authorization sang MinIO).
       Timeout 600 s.
    3. POST `{api}/files/confirm-upload`, JSON `{s3_key}` → `{"upload": {"id", "url", …}}`. Trả `id`, `url`.
  - **Truy vấn** (hằng chuỗi trong `cms.py`; mọi field đều có trong `schema.gql`, đã dò 05/11):
    - `ARTICLE`: `query($id: Int!) { articles_detail(id: $id) { id title slug content department_id article_type_id workflow_id avatar1_id avatar2_id workflow { workflow_type_id name } } }`
    - `CREATE`: `mutation($b: ArticleSaveInputDto!) { articles_create(body: $b) { id } }`
    - `UPDATE`: `mutation($id: Int!, $b: ArticleSaveInputDto!) { articles_update(id: $id, body: $b) { id } }`
    - `TRANSFORM`: `mutation($b: ArticleTransformPreviewInput!) { articles_transform_preview(body: $b) { title caption hashtags } }`
    - `PROPOSE`: `mutation($i: ProposeZernioPostInput!) { propose_zernio_post(input: $i) { publishId status } }`
    - `WORKFLOWS`: `query($b: BaseInput!) { workflows_all(body: $b) { id name type_id workflow_type_id sub_type_id } }`
    - `ZERNIO`: `query { zernio_accounts { id platform username displayName needsReauth } }`
    - `SAMPLE`: như `ARTICLE`, thêm:
      - `desc`;
      - `articleCategories { category_id is_major category { name } }`;
      - `articleGenres { article_genre_id is_major articleGenre { name } }`;
      - `articleKinds { article_kind_id }`;
      - `articleTags { tag { name } }`.

- [ ] **Step 1: Write the failing tests** in `tests/test_cms.py`.
  - Dùng một `FakeHttp` ghi lại mọi lệnh gọi `(method, url, headers, body)` và trả lời theo kịch bản. Fixture autouse của conftest
    raise khi chưa thay.
  - Các test:
    - `test_load_reports_what_is_missing`: không file → `(None, [...])`. `use = "x"` → có mục báo `use`. Id bằng 0 → mục đó
      được nêu tên.
    - `test_load_refuses_a_token_others_can_read`: `token_file` quyền 644 → `(None, ["token_file phải để quyền 600"])`.
      Quyền 600 → `Settings`, có `token` đúng.
    - `test_gql_sends_the_machine_headers`: các header đúng như Interfaces. Body là `{"query", "variables"}`.
    - `test_gql_errors`:
      - `{"errors":[{"message":"Not Found","extensions":{"code":404}}]}` → `CmsError`, `not_found is True`,
        `answered is True`;
      - `_http` raise lỗi mạng → `answered is False`;
      - lỗi 403 → `not_found is False`, message là câu của CMS.
    - `test_upload_three_calls`:
      - đúng thứ tự presign → PUT → confirm;
      - PUT chỉ có `Content-Type` bằng mime;
      - presign gửi `file_size` đúng cỡ file;
      - trả `{"id", "url"}` từ `upload`.
    - `test_token_never_leaves`:
      - token `"BI-MAT-123"` không có trong `repr(settings)`;
      - không có trong `str(CmsError)` khi CMS trả lỗi có lặp lại header (giả lập body lỗi chứa token);
      - không có trong thông báo lỗi mạng.
- [ ] **Step 2: Run** `… pytest -q tests/test_cms.py`. Expected: FAIL (`No module named 'vshort.cms'`).
- [ ] **Step 3: Implement** `vshort/cms.py` theo Interfaces.
  - Câu lỗi lấy từ CMS thì thay mọi lần xuất hiện của token bằng `***` trước khi đưa vào `CmsError`.
- [ ] **Step 4: Run** cả bộ test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(cms): settings with the token kept in its own 600 file, a GraphQL and upload client` and push.

### Task 2: Nội dung bài và sapo, từ khóa

**Files:**
- Create: `vshort/publish.py` (phần dựng bài)
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `Settings` (Task 1); `auto.run_claude`, `auto.AgentError`; `cover/cover.json` (`title`).
- Produces:
  - `publish.video_block(url: str) -> str`: đúng khuôn `buildFigureVideoHtml` của CMS-Admin (`TextEditorTinyMce/utils.ts:249-272`)
    với `src = url`, `poster` để trống. Trong đó:
    - nguồn HLS đặt trước: `<source src="{url}/master.m3u8" type="application/vnd.apple.mpegurl">`;
    - figcaption rỗng `<p class="mce-editable" style="text-align: center; font-style: italic;"></p>`;
    - `url` được escape HTML.
  - `publish.swap_video(content: str, old_url: str, new_url: str) -> str`: thay mọi lần xuất hiện của `old_url` (nguồn mp4 và nguồn
    m3u8 đều bắt đầu bằng nó). Không có thì trả nguyên `content`.
  - `publish.META = "cover/cms-meta.json"`; `publish.ensure_meta(run: Run) -> dict`:
    - Trả `{"sapo": str, "keywords": [str, …]}`.
    - Thiếu file thì chạy một lần `run_claude(run, "cms_meta", "vs-researcher", CMS_META.format(run=run.path), 600)`.
    - Kiểm:
      - `sapo` 1–2 câu, 40–300 ký tự;
      - `keywords` 1–6 chuỗi không trùng (không phân biệt hoa thường), mỗi chuỗi ≤ 60 ký tự.
    - Sai → `CmsError("sapo/từ khóa agent viết chưa đúng: …")`, không ghi gì lên CMS.
  - `CMS_META` (prompt). Ghi `{run}/cover/cms-meta.json`:
    - `sapo`: 1 câu khoảng 40–50 chữ, tóm điều video nói. Chỉ dữ kiện có trong `script.vi.json` và `brief.vi.md`. Cùng luật như
      tiêu đề trong prompt `COVER` của `auto.py`: không bịa số, không tên tệp/công cụ mà "Lưu ý độ chính xác" cấm.
    - `keywords`: 6 cụm từ khóa tiếng Việt, cụm đầu là từ khóa chính.
    - Không làm gì khác.
  - `publish.create_body(s: Settings, title: str, meta: dict, video_url: str, cover16_id: int, cover9_id: int) -> dict`:
    - `title`; `slug: ""` (CMS tự tạo); `desc: meta["sapo"]`; `content: video_block(video_url)`;
    - `avatar1_id: cover16_id`; `avatar2_id: cover9_id`;
    - `workflow_id: s.private_workflow_id`; `article_type_id: s.article_type_id`; `department_id: s.department_id`;
    - `article_categories`: `[{category_id, display_order: i, is_major: i == 0}]`;
    - `article_genres`: `[{article_genre_id, display_order: i, is_major: i == 0}]`;
    - `article_kind_ids: s.kinds`;
    - `article_tags`: `[{name, for_seo: True, for_article: True}]`;
    - `is_seo: True`; `is_push_notify: False`; `submit_type: "save"`.
  - `publish.update_body(current: dict, avatar1_id: int, avatar2_id: int, content: str) -> dict`.
    - Chỉ gồm:
      - `title`, `slug`, `department_id`, `article_type_id`, `workflow_id` lấy từ `current` (kết quả `ARTICLE`);
      - `content`;
      - `avatar1_id`, `avatar2_id`;
      - `submit_type: "save"`.
    - Lý do: CMS bỏ qua mọi trường không gửi (TypeORM bỏ key `undefined`). `article_type_id` bắt buộc gửi lại, thiếu là CMS báo
      `articleTypeIdMismatch`.

- [ ] **Step 1: Write the failing tests:**
  - `test_video_block_matches_the_admin_editor`:
    - chuỗi có `class="mce-noneditable"`, `data-align-image="center"`, `playsinline`, `preload="metadata"`;
    - nguồn m3u8 đứng trước nguồn mp4;
    - URL có `"` thì bị escape.
  - `test_swap_video_replaces_both_sources_and_keeps_the_rest`: nội dung có thêm một đoạn `<p>Tai viết</p>` → đoạn đó còn nguyên.
  - `test_create_body_follows_the_sample`: đúng các khóa và giá trị ở Interfaces; không có `publishNow`, `step_up_token`.
  - `test_update_body_touches_only_pictures_and_video`: tập khóa đúng bằng 9 khóa ở Interfaces.
  - `test_ensure_meta_checks_what_the_agent_wrote`:
    - giả `auto.run_claude` ghi file hợp lệ → trả dict;
    - giả ghi 7 từ khóa → `CmsError`;
    - đã có file → không gọi agent.
- [ ] **Step 2: Run** them. Expected: FAIL (`No module named 'vshort.publish'`).
- [ ] **Step 3: Implement** theo Interfaces.
- [ ] **Step 4: Run** cả bộ test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(publish): the article as the sample 22457 has it, sapo and keywords from the agent` and push.

### Task 3: Luồng gửi, chạy lại an toàn

**Files:**
- Modify: `vshort/publish.py` (thêm `send`)
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: Task 1 (`load`, `gql`, `upload`, các truy vấn, `CmsError`), Task 2 (mọi hàm).
- Produces:
  - **`RUN/cms.json`:** `{"dev": Record, "prod": Record}`. Mỗi `Record` gồm:

    ```python
    {"state": "running" | "done" | "error" | "left" | "deleted" | "unsure",
     "message": str,                                  # tiếng Việt, cho trang
     "steps": [{"key", "label", "status"}],           # status: "done" | "running" | "error" | "next" | "skip"
     "files": {"cover16" | "cover9" | "video": {"sha": str, "id": int, "url": str}},
     "creating": bool,                                # đặt TRƯỚC khi gọi articles_create, xóa khi đã ghi article_id
     "article_id": int | None,
     "article_files": {"cover16": sha, "cover9": sha, "video": sha},  # bản file bài trên CMS đang dùng
     "workflow": str,                                 # tên chặng CMS báo lần cuối
     "social": {"9002" | "9003" | "9004": {"caption": str, "hashtags": [str]}},
     "proposal": {"publishId": str, "video_sha": str} | None,
     "warning": str | None,
     "link": str | None}                              # f"{admin}/article/edit/personal/1/{article_id}"
    ```
  - `publish.STEPS`, theo thứ tự:

    | key | label |
    |---|---|
    | `meta` | Viết sapo và từ khóa |
    | `cover16` | Tải ảnh ngang 16:9 |
    | `cover9` | Tải ảnh dọc 9:16 |
    | `video` | Tải video |
    | `article` | Tạo bài cá nhân (nhãn khi cập nhật: Cập nhật ảnh và video) |
    | `social` | Viết lời mạng xã hội |
    | `propose` | Đề xuất Facebook, YouTube, TikTok |
  - `publish.read(run_dir: Path, env: str) -> dict`: Record, hoặc `{}`. File hỏng → `{}`.
  - `publish.send(run_dir: Path, recreate: bool = False) -> dict`: Record cuối. Lưu `cms.json` sau mỗi việc (file tạm rồi `replace`).
    Bắt `CmsError` và `auto.AgentError`: `state "error"`, việc đang làm `status "error"`, `message` là lý do. Không raise.
- **Thuật toán `send`:**
  1. `load()` thiếu → Record `{"state": "error", "message": "Thiếu cấu hình CMS: …"}`.
  2. `recreate`:
     - chỉ nhận khi `state` là `"deleted"` hoặc `"unsure"`, không thì `error`;
     - xóa `article_id`, `article_files`, `creating`, `proposal`, `social`, `warning`. Giữ `files`.
  3. `creating` còn đặt mà không có `article_id` → `state "unsure"`, message "Không chắc bài đã được tạo: mở CMS xem trong bài
     cá nhân; chưa có thì bấm Tạo bài mới". Dừng, không ghi gì.
  4. Có `article_id` → gọi `ARTICLE`:
     - `not_found` → `state "deleted"`, dừng;
     - `workflow.workflow_type_id != 1` → `state "left"`, message "Bài đã rời luồng cá nhân (chặng {name}), sửa trong CMS", dừng.
       Không tải file, không ghi gì.
  5. `ensure_meta`. Lấy file:
     - `cover/gemini-16x9.jpg`, không có thì `cover/thumb-16x9.jpg`;
     - tương tự cho 9:16;
     - `final.mp4`.
     Tính sha256. File nào sha khác `files[k].sha` thì `upload`; còn lại `status "skip"`.
  6. Chưa có bài: đặt `creating`, lưu, gọi `CREATE(create_body(…))`, ghi `article_id`, `article_files`, bỏ `creating`, lưu.
     - `CREATE` lỗi với `answered` True: CMS đã từ chối, bỏ `creating`.
     - `answered` False (mất mạng, hết giờ): giữ `creating`, lần sau là `unsure`.
  7. Có bài và `article_files` khác sha hiện tại → `UPDATE(id, update_body(current, …, swap_video(current.content, cũ, mới)))`.
     Cập nhật `article_files`.
  8. `social`: mỗi `target` trong `[9002, 9003, 9004]` mà nền tảng có `zernio` id và chưa có trong `social` → `TRANSFORM` với
     `{"target_type": t, "sources": [{"article_id": id, "role": "primary"}]}`.
  9. `propose`:
     - Chưa có `proposal` và có ít nhất một nền tảng → **một** lệnh `PROPOSE` với:
       - `articleId`;
       - `content` = lời Facebook (hoặc lời nền tảng đầu tiên);
       - `mediaItems`: `[{"type": "video", "fileId": files.video.id}]`;
       - `platforms`: mỗi nền tảng một mục `{platform: "FACEBOOK"|"YOUTUBE"|"TIKTOK", accountId, customContent: caption + "\n\n" + " ".join(hashtags)}`.
       Ghi `proposal`.
     - Có `proposal` mà `video_sha` khác sha video hiện tại → `warning` "Đề xuất mạng xã hội đang dùng video cũ, sửa trong CMS".
       Không đề xuất lại.
  10. `state "done"`, `link`.

- [ ] **Step 1: Write the failing tests** với một `FakeCms` giữ bài và file trong bộ nhớ, trả lời `gql`/`upload` như CMS, và ghi
  lại mọi lệnh. Run giả có `final.mp4`, `cover/thumb-*.jpg`, `cover/cover.json`, `cover/cms-meta.json`.
  - `test_first_send_creates_once_and_proposes_once`:
    - đúng 3 upload, 1 `articles_create`, 3 `articles_transform_preview`, 1 `propose_zernio_post`;
    - `state "done"`, có `link`;
    - không lệnh nào chứa `approve_zernio_post`, `publishNow`, `scheduledFor`, `step_up_token`.
  - `test_second_send_with_nothing_new_writes_nothing`: lần 2 không upload, không create/update/propose.
  - `test_resend_keeps_tais_edits`:
    - FakeCms đổi tiêu đề bài thành "Tai sửa";
    - thêm `cover/gemini-16x9.jpg` rồi gửi lại;
    - đúng 1 upload, 1 `articles_update`;
    - body có `title == "Tai sửa"`, không có khóa nào ngoài 9 khóa của `update_body`;
    - `avatar1_id` là id mới.
  - `test_rebuilt_video_swaps_the_block_and_warns`: đổi byte `final.mp4` → `content` mới chứa URL mới, không còn URL cũ; `warning`
    về đề xuất; không có `propose` thứ hai.
  - `test_left_private_writes_nothing`: bài sang `workflow_type_id = 3` → `state "left"`, 0 upload, 0 update.
  - `test_deleted_article_needs_recreate`:
    - `articles_detail` báo 404 → `state "deleted"`, không create;
    - `send(…, recreate=True)` → create mới.
  - `test_crash_after_create_never_creates_twice`:
    - FakeCms tạo bài rồi raise `KeyboardInterrupt` (tiến trình chết) → lần chạy sau `state "unsure"`, 0 create;
    - FakeCms tạo bài rồi raise `CmsError(answered=False)` (hết giờ) → cũng `unsure`;
    - `recreate=True` → create.
  - `test_create_refused_by_the_cms_can_retry`: `CREATE` trả `errors` (answered) → `state "error"`, `creating` đã bỏ; lần sau
    create bình thường.
  - `test_error_midway_resumes`: upload video lỗi → `state "error"`, bước `video` là `error`. Chạy lại → không tải lại 2 ảnh.
  - `test_env_records_are_separate`: gửi với `use = "dev"`, đổi sang `"prod"` → bài prod được tạo mới, `cms.json["dev"]` giữ nguyên.
  - `test_platform_without_account_is_skipped`: `zernio.tiktok = ""` → 2 transform, `platforms` có 2 mục.
- [ ] **Step 2: Run** them. Expected: FAIL (`AttributeError: … 'send'`).
- [ ] **Step 3: Implement** `send` theo thuật toán.
- [ ] **Step 4: Run** cả bộ test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(publish): send to the CMS step by step, never twice, never over Tai's edits` and push.

### Task 4: Lệnh `vshort cms`, API của trang

**Files:**
- Modify: `vshort/cli.py` (lệnh `cms`, `cms-probe`), `vshort/web.py` (route, field `cms` của detail), `vshort/queue.py` (row `posted`)
- Test: `tests/test_web.py`, `tests/test_publish.py`

**Interfaces:**
- Consumes: `publish.send`, `publish.read`, `cms.load`, `cms.gql`, `cms.SAMPLE`, `cms.WORKFLOWS`, `cms.ZERNIO`.
- Produces:
  - **`vshort cms <run> [--recreate] [--foreground]`:**
    - Không `--foreground`: chạy nền như `cmd_auto`:
      - `Popen` với `start_new_session=True`;
      - log vào `RUN/auto.log`;
      - khóa `RUN/cms.lock` chứa pid, kiểm bằng `auto._alive`;
      - đang có thì mã `BAD_INPUT`.
    - Có `--foreground`: lấy khóa, chạy `publish.send`. Mã 0 khi `state` thuộc done/left/deleted/unsure, 1 khi error.
  - **`vshort cms-probe <article_id> [--env dev|prod]`:** in để điền `cms.toml`, **không in token**:
    - chặng, phòng ban, loại bài của bài đó;
    - chuyên mục, thể loại, loại bài viết, từ khóa (id kèm tên);
    - các chặng `workflows_all` với `filters: ["department_id:=(D)", "type_id:=(T)", "workflow_type_id:=(1)"]`;
    - các tài khoản `zernio_accounts`.
  - **`POST /api/runs/{slug}/cms`**, body `{"recreate": bool}` (mặc định false), qua `_post(…, run=True)`:
    - row không `done` → 400 "Chỉ gửi được video đã xong";
    - `cms.lock` còn sống → 409 "Đang gửi, đợi xong";
    - `cms.load()` thiếu → 400 kèm danh sách thiếu;
    - còn lại → gọi `vshort(["cms", path, *(["--recreate"] if recreate else [])])`, trả 202.
  - **Detail thêm `"cms"`:**

    ```python
    {"configured": bool, "missing": [str], "env": "dev" | "prod" | None, "running": bool,
     "record": Record (của env đang dùng, nguyên dạng cms.json) | {}}
    ```
  - **Row thêm `"posted": bool`:** Record của env đang dùng có `article_id`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cms_route_starts_the_send`:
    - giả `web.vshort` ghi args → 202, args là `["cms", path]`;
    - `{"recreate": true}` → có `--recreate`;
    - video chưa xong → 400;
    - không mã → 403;
    - multipart → 415.
  - `test_cms_route_without_settings_says_what_is_missing`: `cms.load` trả `(None, ["thiếu token_file"])` → 400, message chứa
    "token_file".
  - `test_detail_never_carries_the_token`: `cms.load` trả `Settings` có token `"BI-MAT-123"` → JSON detail và JSON `/api/state` không
    chứa chuỗi đó; `cms.env == "dev"`.
  - `test_row_posted_follows_the_current_env`: `cms.json` có `dev.article_id` → `posted` True khi `use = "dev"`, False khi `"prod"`.
  - `test_cli_cms_foreground_locks`: `cms.lock` với pid của chính test (còn sống) → `main(["cms", run, "--foreground"])` trả
    `BAD_INPUT`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** cả bộ test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(cms): vshort cms runs the send in the background; the page can start it and read how it went` and push.

### Task 5: Khung "Gửi lên CMS" trên trang

**Files:**
- Create: `web/src/Cms.tsx`
- Modify: `web/src/api.ts` (kiểu `CmsRecord`, `CmsInfo`, `Row.posted`, `Detail.cms`), `web/src/Finished.tsx` (đặt `<CmsBox c={c} />`
  cuối tab Đăng bài), `web/src/RunList.tsx` (bộ lọc "Chưa đăng", nhãn "Đã gửi CMS")
- Test: build, lint

**Interfaces:**
- Consumes: Detail `cms`, Row `posted`, `POST /api/runs/{slug}/cms` (Task 4); `runApi`, `post`, `toast`, `Tabs` có sẵn.

- [ ] **Step 1: Implement `CmsBox`** theo bản phác (khung "Đăng lên" ở màn 3), không có ô chọn nền tảng.
  - **Đầu khung:** tiêu đề "Gửi lên CMS", nhãn bản đang dùng: "Bản thử (dev)" màu vàng, hoặc "Bản thật" màu đỏ.
  - **Thiếu cấu hình:** "Chưa cấu hình CMS trên máy chủ:" và danh sách `missing`. Nút tắt.
  - **Nút chính:**
    - "Gửi lên CMS" khi chưa có bài, "Gửi lại" khi đã có;
    - tắt khi `c.off` hoặc `running`.
    - Bấm → `post(runApi(c, "cms"), {})`, toast "Đã bắt đầu gửi", `c.reload()`.
  - **Danh sách việc:** dùng lại dấu của `StageList` (✓ xanh, chấm tím đang chạy, ✗ đỏ, vòng xám chưa tới, "bỏ qua" xám).
  - **Theo `record.state`:**
    - `done`: "Bài số {id}", link "Mở bài trong CMS" (`target="_blank"`), "Đề xuất mạng xã hội: đã gửi, duyệt trong CMS";
    - `left` / `deleted` / `unsure` / `error`: hiện `message`;
    - `warning`: khung vàng.
  - **`deleted` hoặc `unsure`:** thêm nút "Tạo bài mới".
    - Bấm lần đầu đổi chữ thành "Bấm lần nữa để tạo bài mới" trong 5 giây. Không dùng `window.confirm`.
    - Bấm lần hai → `post(…, {recreate: true})`.
  - **`running`** mà khóa đã chết (`record.state == "running"` và `!running`): "Dừng giữa chừng", nút "Gửi lại".
- [ ] **Step 2: Danh sách:**
  - tab lọc thành "Tất cả / Chưa đăng (n) / Cần sửa (n)";
  - thẻ video đã gửi có nhãn "Đã gửi CMS" cạnh chi phí.
- [ ] **Step 3: Run** `cd web && npm run build && npm run lint`. Expected: OK, không lỗi lint mới.
- [ ] **Step 4: Commit** `feat(web): send to the CMS from the finished page, unposted filter` and push.

### Task 6: Cài trên pve2, thử trên dev, deploy

**Files:**
- Modify: memory `cms-publish-integration.md`, `web-control-panel.md`, `handoff-2026-11-05.md` (không thuộc repo)

- [ ] **Step 1: Deploy code** bằng lệnh ở Global Constraints. Đợi journal báo "đã cập nhật … → <commit>".
- [ ] **Step 2: Token dev,** chép từ file sang file, không in ra:
  `grep '^STATIC_BEARER_TOKEN=' ~/Documents/Mediasoft/CMS-Backend/.env | cut -d= -f2- | tr -d '"\r\n' | ssh pve2 'umask 077; mkdir -p ~/.config/vshort; cat > ~/.config/vshort/cms-dev.token'`.
  Kiểm: `ssh pve2 'stat -c "%a %s" ~/.config/vshort/cms-dev.token'` → `600` và cỡ > 0.
- [ ] **Step 3: Viết `~/.config/vshort/cms.toml` trên pve2** với `use = "dev"`, bộ `[dev]` như Task 1, id để 0. Rồi chạy
  `vshort cms-probe <id một bài video ngắn trên dev>` trên pve2.
  - **Token bị từ chối** (401/403 do token): thử `MCP_STATIC_BEARER_TOKEN` theo cách ở Step 2. Vẫn không được thì **dừng, hỏi Tai**.
  - **Lỗi phòng ban hoặc act-as:** báo Tai id phòng ban của `phongvien01` trên dev, hoặc hỏi Tai.
  - **Dev không có bài mẫu tương tự:** hỏi Tai một id bài video ngắn trên dev.
  - Điền id chuyên mục "Chuyển động công nghệ" (chính) + "Short video", thể loại "Video ngắn", loại bài "Short Video", chặng
    PRIVATE, id Zernio.
- [ ] **Step 4: Gửi thử một video** (Synology) trên dev bằng nút trên trang. Kiểm:
  - trang hiện đủ 7 việc xong, có link;
  - mở link trong Chrome (hỏi Tai chọn trình duyệt đã đăng nhập dev): bài ở luồng cá nhân, có tiêu đề, sapo, 2 ảnh đại diện,
    chuyên mục, thể loại, từ khóa;
  - xem trước bài: video phát được;
  - CMS có đề xuất mạng xã hội cho 3 nền tảng (hoặc số nền tảng có tài khoản) ở trạng thái chờ duyệt. **Không duyệt.**
  - Bấm "Gửi lại" ngay → không có gì mới trên CMS.
  - Nếu `link` không mở đúng bài: sửa mẫu link trong `publish.py`, ghi rulings.
- [ ] **Step 5: Ghi memory:**
  - `cms.toml` và token ở đâu;
  - id dev đã điền;
  - "prod chưa cấu hình: lần gửi prod đầu tiên làm cùng Tai";
  - "không bao giờ duyệt đề xuất".
- [ ] **Step 6: Dừng.** Báo Tai kết quả dev. **Không tự chuyển `use = "prod"`.** Lần prod đầu tiên làm cùng Tai: một bài, một đề xuất.
