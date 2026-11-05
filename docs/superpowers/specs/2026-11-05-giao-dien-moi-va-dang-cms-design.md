# Bàn điều khiển: giao diện mới, theo dõi từng bước, gửi lên CMS — thiết kế (05/11/2026)

Hai giai đoạn, làm theo thứ tự:
- **A**: giao diện mới, theo dõi từng bước và thời gian còn lại, tải ảnh bìa Gemini lên.
- **B**: gửi bài lên CMS Tạp chí An ninh mạng và đề xuất bài mạng xã hội.

A dùng được ngay mà không cần B. B dựa trên màn "Đăng bài" của A.

## Vì sao

Ngày 05/11 Tai xem bàn điều khiển (`vshort-web`, spec `2026-11-03-giao-dien-web-design.md`) và nói "UI/UX của tool này vẫn chưa ổn".
Hai điểm Tai nêu đích danh:
1. "Trong quá trình gen video tôi không nhìn thấy trực quan quy trình". Trang hiện chỉ có một ô "Bước: …" và đoạn log.
2. Muốn tích hợp "tool để tôi đăng lên CMS của tạp chí an ninh mạng và tạo bài mạng xã hội trên đó", "hoặc có thể call api sang
   bên web".

Phần sửa nhanh đã làm và deploy cùng ngày (commit `5e5679f`, `64fbc44`): tiêu đề đăng thay tên thư mục, ô "Đăng bài" có prompt ảnh bìa
Gemini và nút sao chép, bỏ logo góc. Spec này là hai phần còn lại.

Tai làm khoảng 5 video mỗi ngày, mở trang trên **web** (Mac, Chrome, màn hình lớn), thỉnh thoảng trên điện thoại. Hỏi "máy tính hay
điện thoại", Tai trả lời: "improve lên UI/UX cho web".

## Mục tiêu

**Giai đoạn A**
- **Nhìn thấy quy trình:** với mỗi video đang chạy, thấy 10 bước, bước nào xong (mất bao lâu), bước nào đang chạy (đã bao lâu, thường
  bao lâu), bước nào chờ Tai, và **còn khoảng bao lâu**. Cũng thấy được trên danh sách, không cần mở từng video.
- **Giao diện theo phong cách bộ Figma "Clipcup"** mà Tai chọn
  (https://www.figma.com/design/QOnBzrx1gvfVn0GwRBaAP7/, node 65-400). Đây là bộ UI cho app điện thoại; ta mượn phong cách cho web:
  nền gần đen, thẻ xám đậm bo tròn lớn, điểm nhấn tím, nút và tab dạng viên thuốc (tab chọn có nền trắng, chữ đen), nút chính tím
  bo tròn hoàn toàn.
- **Bản phác Tai đã duyệt ("oke rồi"):** https://claude.ai/artifact/GuGnqtfibBsV8AWYkoWEh5, gồm 3 màn:
  1. Trang chủ.
  2. Video đang chạy.
  3. Video xong, mục Đăng bài.

  Làm theo bản phác về bố cục và nội dung. Màu và cỡ chữ trong bản phác là gợi ý.
- **Ảnh bìa Gemini:** Tai vẽ hai ảnh trong app Gemini từ prompt đã có (9:16 và 16:9), rồi kéo thả lên trang video. Ảnh nằm cùng
  video trên server và được kéo về Mac như ảnh bìa hiện nay.

**Giai đoạn B**
- Trên trang video đã xong, có nút **"Gửi lên CMS"**. Bấm nút này thì server tạo một **bài cá nhân chưa xuất bản** trên CMS, dựng
  theo đúng khuôn bài mẫu 22457.
- Server tiếp đó **đề xuất** bài Facebook, YouTube, TikTok cho bài đó. CMS tự viết lời bằng AI của tòa soạn, kèm video.
- Tai mở CMS, xem lại, **tự bấm xuất bản** (CMS hỏi OTP như thường lệ) và duyệt bài mạng xã hội trong CMS.

## Không làm

- Không tự xuất bản. Bài luôn vào luồng cá nhân (PRIVATE). Xuất bản cần OTP của Tai, và đó là chủ ý của CMS.
- Không gọi API trả phí để vẽ ảnh. Tai đã từ chối key Gemini trả phí; ảnh vẽ tay trong app Gemini.
- Không lưu, không dùng tài khoản hay mật khẩu CMS của Tai. Tai từng dán mật khẩu vào chat; không bao giờ dùng nó.
- Không sửa repo CMS (`~/Documents/Mediasoft/*`). Chỉ gọi API sẵn có. Nếu cần sửa CMS thì hỏi Tai; repo đó có luật riêng.
- *(Quyết định của tôi:)* không làm hai mục "Đã đăng" và "Cài đặt" ở thanh trên cùng của bản phác. Bộ lọc "Chưa đăng" trên danh sách
  đã đủ, còn trang cài đặt chưa có gì để chỉnh.
- *(Quyết định của tôi:)* không đổi pipeline ngoài việc ghi thời gian từng bước (giai đoạn A) và bước gửi CMS (giai đoạn B).
- Không bảng phân cảnh và không sửa từng câu. Đó vẫn là đợt 2 và 3 của spec 03/11.

## Thất bại dù vẫn chạy được

- Thời gian còn lại nhảy lung tung hoặc sai xa. Ví dụ "còn 2 phút" suốt 15 phút NotebookLM, hay gộp cả thời gian chờ Tai duyệt vào
  một con số.
- Bấm "Gửi lên CMS" hai lần ra hai bài trùng trên CMS.
- Bài lên CMS không giống bài mẫu: video không phát ở trang đọc, sai chuyên mục, thiếu ảnh đại diện.
- Token máy của CMS lộ ra trình duyệt, vào log, vào git, hay ra ai đó cùng mạng LAN.
- Ô tải ảnh lên mở ra lỗ CSRF. Hiện mọi lệnh ghi chỉ nhận `application/json` để chặn trang khác trên cùng host gửi form (xem
  `_not_json` trong `vshort/web.py`).
- Giao diện mới làm mất những gì đang chạy tốt:
  - đọc lại mỗi 5 giây nhưng giữ chỗ đang sửa dở;
  - mã truy cập;
  - duyệt brief và duyệt bản dịch;
  - video tua được trên iPhone;
  - xem được ở bề ngang điện thoại.

## Hiện trạng cần biết

- `vshort/web.py` (Starlette) và `vshort/queue.py` (Row của từng video, `STEPS` = 17 bước có nhãn). Giao diện ở `web/`: React 19,
  Tailwind 4, shadcn, Vite. Các file chính: `RunList.tsx`, `RunDetail.tsx`, `Finished.tsx`, `BriefReview.tsx`, `ScriptReview.tsx`,
  `status.tsx`.
- `state.json` chỉ ghi `{"bước": "done"}`, **không có giờ**. `cost.json` có `seconds` cho các bước do agent làm. Các bước `vshort`
  cố định (NotebookLM `fetch`, `tts`, `render`…) không có thời gian ở đâu cả.
- Ảnh bìa: `vshort/cover.py` ghi `cover/{anh-dai-dien,thumb}-{16x9,9x16}.jpg`, `cover/prompt.txt` và `xuat/<tiêu đề>/`. Mac kéo
  `*/xuat/` về `~/Movies/vshort` mỗi 5 phút.
- Cập nhật server: `ssh pve2 'systemd-run --user --unit vshort-update --collect -E PATH="$PATH"
  ~/video-pipeline/scripts/update-server.sh'`. Script này đợi lúc không có video chạy. Code commit thẳng lên `main` rồi push.

## Giai đoạn A

### Ghi thời gian từng bước

- Mỗi bước trong `STEPS` và mỗi bước agent (`brief_check`, `motion_design`, `visuals_agent`, `fix*`, `review*`, `cover`) được ghi
  giờ bắt đầu và giờ kết thúc vào `RUN/times.json`, dạng `{"bước": {"start": epoch, "end": epoch}}`. `state.json` giữ nguyên.
- Ghi ở chỗ mọi bước đều đi qua trong `vshort/auto.py` (`_vs`, `_agent`, `run_claude`, các bước chạy song song trong `_build` và
  `_flow`). Cách đặt là việc của người làm.
- Một bước chạy lại (vòng sửa, Chạy lại) thì ghi đè lần mới. Thời gian chờ Tai duyệt không tính vào bước nào.
- Hai bước song song (`tts` chạy cùng `plates`/`motion`/`stills`/`visuals`; `motion_design` chạy cùng NotebookLM) đều được ghi. Trang
  hiện bước "đang chạy" theo thứ tự trong danh sách.

### 10 chặng hiển thị

Gộp các bước thật thành 10 chặng, giống bản phác. Mỗi chặng hiện tên, một dòng mô tả, trạng thái và thời gian.

| # | Chặng | Bước thật |
|---|---|---|
| 1 | Tìm hiểu | research |
| 2 | Duyệt brief | approve_brief (chờ Tai) hoặc brief_check (khi bỏ duyệt) |
| 3 | NotebookLM làm video | source, fetch (song song: motion_design) |
| 4 | Lấy phụ đề | detect, transcribe, text |
| 5 | Dịch | translate |
| 6 | Duyệt bản dịch | approve_script (chờ Tai) |
| 7 | Giọng đọc và hình | plates, motion, motion_bind, stills, visuals, visuals_agent, tts |
| 8 | Dựng video | timeline, render |
| 9 | Soát và sửa | review0, fix*, review1… |
| 10 | Ảnh bìa và xuất | cover |

- **Trạng thái mỗi chặng:** xong, đang chạy, chờ Tai, chưa tới, hoặc bỏ qua. Chặng 2 khi bỏ duyệt brief vẫn là "xong" vì có
  brief_check.
- **Chặng đang chạy** mở ra danh sách các bước thật bên trong, mỗi bước có dấu xong, đang chạy hoặc chưa tới, như bản phác.
- **Video lỗi:** chặng hỏng hiện đỏ, kèm lý do từ `auto.json`.
- **Video đã xong:** cả 10 chặng hiện ở tab "Các bước", kèm thời gian thật.

### Thời gian còn lại

- **Thời gian thường của mỗi chặng** = trung vị thời gian chặng đó trong *(quyết định của tôi)* 5 video gần nhất có `times.json`.
  Chưa đủ dữ liệu thì dùng một bảng mặc định trong code, ước từ `cost.json` của các run cũ cộng với số đo tay. Ví dụ NotebookLM
  khoảng 15 phút; spec 03/11 ghi 5–40 phút.
- **Không gộp phần chờ Tai vào một con số.** Hiện hai số như bản phác:
  - "tới lúc cần bạn duyệt …": tổng thời gian còn lại tới chặng chờ Tai kế tiếp;
  - "sau khi bạn duyệt, tới lúc xong".

  Bỏ duyệt brief thì chỉ còn chặng duyệt bản dịch.
- **Chặng đang chạy:** còn lại = max(thời gian thường − đã chạy, một sàn nhỏ). Chạy quá thời gian thường thì ghi "lâu hơn thường lệ",
  không ghi số âm hay "còn 0 phút".
- **Phần trăm** = tổng thời gian thường của các chặng đã xong cộng phần đã chạy của chặng hiện tại, chia cho tổng cả 10 chặng.
  Không tính thời gian chờ Tai.
- **Giờ dự kiến** (≈14:33) lấy theo giờ máy của người xem.
- *(Quyết định của tôi:)* tính ở server, trả trong `/api/state` (cho thẻ trên danh sách) và `/api/runs/<slug>`. Trang không tự đặt
  logic song song.

### Màn hình

Theo bản phác. Những chỗ chính:

**Trang chủ**
- **Ô "Tạo video":** chủ đề hoặc link, nút gạt "Bỏ duyệt brief", nút tím. Giữ đúng hành vi của `AddTopics.tsx`.
- **"Cần bạn":** chờ duyệt brief, chờ duyệt bản dịch, lỗi, dừng giữa chừng. Mỗi mục có nút đi thẳng tới chỗ cần làm.
- **"Đang tạo":** thẻ có % lớn, chặng hiện tại, thanh 10 ô, đã chạy bao lâu, còn khoảng bao lâu, chi phí.
- **"Đang xếp hàng":** như hiện nay, gỡ được chủ đề chưa chạy.
- **"Video đã xong":** lưới thẻ ảnh bìa 9:16 (ảnh Gemini nếu có, không thì `thumb-9x16.jpg`), tiêu đề đăng, nhãn Soát, thời lượng,
  chi phí. Bộ lọc "Tất cả / Chưa đăng / Cần sửa"; "Chưa đăng" có nghĩa từ giai đoạn B.
- **"Chưa chạy tự động":** các thư mục cũ, gom thành một dòng thu gọn ở cuối.

**Video đang chạy**
- Đầu trang: vòng %, "Bước n trên 10", tên chặng, đã chạy bao lâu, hai ô thời gian còn lại.
- Danh sách 10 chặng dọc. Cột phải có Thông tin (chủ đề, duyệt brief, chi phí tới giờ, giọng) và Nhật ký (vài dòng cuối, có nút xem
  hết).

**Video chờ duyệt brief hoặc bản dịch**
- Giữ nguyên các thành phần và hành vi duyệt, chỉ đổi giao diện.
- Thêm đầu trang và danh sách chặng thu gọn, để biết video đang ở đâu.

**Video xong**
- Trái: video (`final.mp4`, tua được) và nút Tải video.
- Phải: các tab Đăng bài / Báo cáo soát / Các bước / Chi phí. Tab Đăng bài có:
  - tiêu đề đăng kèm nút sao chép;
  - ảnh bìa: ô ảnh Gemini và ảnh tự ghép dự phòng;
  - hướng dẫn 3 bước vẽ ảnh bằng Gemini, nút sao chép prompt và câu 16:9;
  - khung "Gửi lên CMS" (giai đoạn B; ở giai đoạn A thì ẩn).

**Phong cách**
- Nền tối, điểm nhấn tím. Chữ Be Vietnam Pro: repo đã có sẵn TTF ở `assets/fonts/`, dùng lại thay vì thêm gói mới.
- Tương phản chữ đạt 4.5:1, kể cả chữ phụ màu xám. Vùng bấm ≥ 44 px.
- Bề ngang điện thoại: các cột xếp chồng, tab tự xuống dòng.

### Tải ảnh Gemini lên

- Trên tab Đăng bài, mỗi khổ (9:16, 16:9) có một ô: kéo thả hoặc bấm để chọn ảnh, xem trước được, thay được.
- Server lưu thành `cover/gemini-9x16.jpg` và `cover/gemini-16x9.jpg`. Nhận JPEG, PNG hay WebP; *(quyết định của tôi)* đổi sang JPEG,
  giữ tỉ lệ, cạnh dài nhất ≤ 2048 px.
- Ảnh sai tỉ lệ: báo cho Tai, không tự cắt. Nhận ảnh lệch tỉ lệ tối đa khoảng 5 %.
- Có ảnh Gemini thì `xuat/<tiêu đề>/` dùng ảnh đó cho `thumb-doc-9x16.jpg` và `thumb-ngang-16x9.jpg`, và thẻ trên danh sách cũng
  dùng ảnh đó. Ảnh tự ghép vẫn giữ trong `cover/`.
- **An toàn:** lệnh ghi này cũng cần mã truy cập, và phải giữ được hàng rào CSRF hiện có. Cách làm là việc của người làm, miễn trang
  khác không gửi được. Ví dụ: gửi ảnh dạng base64 trong JSON, hoặc bắt một header riêng để trình duyệt phải hỏi preflight.
- Có giới hạn dung lượng.

## Giai đoạn B: gửi lên CMS

### Những gì đã biết từ mã nguồn CMS

Tai cho phép đọc `~/Documents/Mediasoft`. Các điểm then chốt đã kiểm lại bằng tay.

**Xác thực**
- CMS-Backend nhận một **token tĩnh cho máy**, `STATIC_BEARER_TOKEN` hoặc `MCP_STATIC_BEARER_TOKEN`
  (`CMS-Backend/src/modules/auth/jwt-auth.guard.ts:124`).
- Gửi kèm header `x-mcp-act-as` (tên hoặc id người dùng mà bài đứng tên) và `x-department-id` (bắt buộc với mọi request).
- Lưu vào luồng PRIVATE thì **không cần OTP**. OTP chỉ bị đòi khi chuyển sang luồng xuất bản có `require_otp`
  (`publish-step-up.util.ts:24`).

**Tạo bài**
- `articles_create(body: ArticleSaveInputDto!)` (`schema.gql` ~11407). Trường bắt buộc: `title`, `content`, `department_id`, `slug`
  (để trống thì server tự tạo).
- Bài điện tử: `article_type_id = 1`.
- `workflow_id`: chặng PRIVATE của phòng ban.
- `submit_type: "save"`.

**Tải file**
1. `POST {API}/files/presigned-upload` với `{file_name, mime_type, file_size, department_id}`.
2. `PUT` các byte lên địa chỉ MinIO nhận được.
3. `POST {API}/files/confirm-upload` với `{s3_key}`, trả về `{upload: {id, …}}`.

- Ảnh dùng id đó cho `avatar1_id` / `avatar2_id`.
- Danh sách cho phép có `video/mp4`. Giới hạn mặc định 2 GB.

**Video**
- Tai chọn **tải mp4 qua đường file thường rồi nhúng vào nội dung**.
- Không dùng đường ingest video: nó từ chối bài điện tử vì không có vai trò REPORT/SCRIPT.

**Mạng xã hội**
- `articles_transform_preview` là AI của CMS. Theo bộ mẫu `AI_SOCIAL_PRESETS`, nó viết lời cho Facebook (target 9002), YouTube (9003),
  TikTok (9004). Mutation này chỉ tạo chữ, không đăng.
- Sau đó `propose_zernio_post` đề xuất bài đăng. Tai duyệt trong CMS (`approve_zernio_post`), Zernio đăng thật.
- *(Quyết định của tôi, Tai không phản đối:)* dùng AI của CMS, để giọng văn khớp với tòa soạn.

### Khuôn bài: bài mẫu 22457

Tai: "1 bài tương tự như này là đủ thông tin". Các trường đọc từ bài mẫu:

| Trường | Bài mẫu | Bài máy soạn |
|---|---|---|
| Tiêu đề | "Sự cố bảo mật Binance: …" | tiêu đề đăng (`cover/cover.json` `title`) |
| Sapo (`desc`) | 1 câu, khoảng 50 chữ | 1–2 câu tóm tắt từ brief, cùng luật dữ kiện như tiêu đề |
| Ảnh đại diện (`avatar1_id`) | ảnh 16:9 có chữ (1074×604) | `cover/gemini-16x9.jpg`, không có thì `thumb-16x9.jpg` |
| Ảnh đại diện khác (`avatar2_id`) | ảnh dọc 9:16 (533×949) | `cover/gemini-9x16.jpg`, không có thì `thumb-9x16.jpg` |
| Nội dung | chỉ một khối video (dưới đây) | khối video của `final.mp4` |
| Thể loại | Đa phương tiện › Video ngắn | như mẫu |
| Chuyên mục | Chuyển động công nghệ (chính), Short video | như mẫu, cho mọi video |
| Loại bài viết | Short Video | như mẫu |
| Từ khóa | 6 (giới hạn), từ đầu là từ khóa chính | 6 từ khóa máy chọn từ nội dung video |
| SEO / thông báo đẩy | bật / tắt | như mẫu |
| Người đứng tên | tài khoản của Tai | `x-mcp-act-as` = Tai |

Khối video trong nội dung của bài mẫu (bỏ link):

```html
<figure class="mce-noneditable" data-align-image="center" contenteditable="false">
  <video style="max-width: 100%; height: auto; display: block; width: 100%;" controls preload="metadata" playsinline>
    <source src="https://cdn.tapchianninhmang.vn/original/videos/….m3u8" type="application/vnd.apple.mpegurl">
    <source src="https://cdn.tapchianninhmang.vn/original/videos/….mp4" type="video/mp4">
    Your browser does not support the video tag.
  </video>
  <figcaption><p class="mce-editable ms-caption-empty" contenteditable="true" data-placeholder="Chèn chú thích vào đây"></p></figcaption>
</figure>
```

- Bài mẫu có bản HLS `.m3u8` vì video đi qua thư viện media. Đường file thường có lẽ chỉ cho mp4; khi đó chỉ có thẻ `<source>` mp4,
  là đủ.
- Địa chỉ CDN của file vừa tải lên, và cách CMS-Site-Render đọc khối này, người làm tự tìm trong mã nguồn hoặc thử trên bản dev.

### Luồng "Gửi lên CMS"

1. Tai bấm "Gửi lên CMS" trên tab Đăng bài. Nút chỉ bật khi video đã xong và có cấu hình CMS. Nút cần mã truy cập.
2. Server làm lần lượt, mỗi việc xong thì ghi vào `RUN/cms.json`, để chạy lại thì làm tiếp chứ không làm lại:
   1. tải ảnh 16:9;
   2. tải ảnh 9:16;
   3. tải `final.mp4`;
   4. tạo bài (`articles_create`);
   5. viết lời mạng xã hội cho từng nền tảng (`articles_transform_preview`);
   6. đề xuất (`propose_zernio_post`, kèm video và `articleId`).
3. **Không bao giờ tạo bài trùng.** `cms.json` đã có `article_id` thì không bao giờ tự gọi `articles_create` lần hai.
   *(Quyết định của tôi, sau buổi soát:)* lần bấm sau phải an toàn với bài Tai đã động vào:
   1. Trước hết đọc trạng thái hiện tại của bài trên CMS.
   2. **Bài còn ở chặng PRIVATE:** chỉ thay **ảnh đại diện và khối video**, và chỉ khi file đã đổi (ảnh Gemini mới, video dựng lại).
      Gửi lại `workflow_id` hiện có của bài. **Không đụng** tiêu đề, sapo, từ khóa, chuyên mục, vì Tai có thể đã sửa trong CMS.
   3. **Bài đã sang chặng khác** (đã gửi duyệt, đã xuất bản…): không ghi gì. Chỉ hiện trạng thái và link mở bài, ghi "bài đã rời
      luồng cá nhân, sửa trong CMS".
      - Tuyệt đối không gửi `workflow_id` PRIVATE cho bài đã xuất bản: làm vậy là kéo bài đang đọc được về lại nháp.
      - Không gửi gì cần OTP.
   4. **Bài đã bị xóa** (CMS báo không tìm thấy): hiện rõ điều đó, kèm nút riêng "Tạo bài mới", có hỏi xác nhận. Nút này xóa
      `article_id` cũ trong `cms.json` rồi tạo lại. Đây là cách duy nhất để có `articles_create` lần hai.
   5. **Đề xuất mạng xã hội đã có:** không đề xuất lại. Nếu video đã dựng lại sau lúc đề xuất, hiện cảnh báo "đề xuất mạng xã hội
      đang dùng video cũ, sửa trong CMS".
4. Trang hiện từng việc kèm dấu xong hoặc lỗi. Khi xong, trang hiện mã bài, link mở bài trong CMS
   (`https://cms.tapchianninhmang.vn/article/edit/personal/1/<id>`) và trạng thái đề xuất mạng xã hội.
5. Lỗi thì hiện lý do bằng tiếng Việt, kèm nút thử lại. Nút thử lại làm tiếp từ việc hỏng.
6. *(Quyết định của tôi:)* việc gửi chạy ở nền, không giữ request HTTP. Video 30 MB cộng hai ảnh vẫn có thể mất cả phút.
7. Danh sách: video đã có `article_id` không còn trong bộ lọc "Chưa đăng", và thẻ ghi "Đã gửi CMS".

### Cấu hình và bí mật

- Một file trên pve2, ví dụ `~/.config/vshort/cms.env`, quyền 600. **Tai tự tạo**; mình không bao giờ thấy giá trị trong đó. File gồm:
  - địa chỉ API prod (mã nguồn không ghi, nó được gắn lúc deploy);
  - token máy;
  - `x-mcp-act-as`;
  - `department_id`;
  - id chặng PRIVATE;
  - id các chuyên mục, thể loại, loại bài;
  - id tài khoản Zernio cho từng nền tảng.
- Token chỉ server đọc. Không trả về trình duyệt, không ghi vào log hay `cms.json`, không commit.
- Các id phân loại lấy một lần từ bài mẫu 22457 qua API (truy vấn chi tiết bài) rồi ghi vào file cấu hình. Cách lấy là việc của người
  làm.
- Thiếu file cấu hình thì khung "Gửi lên CMS" ghi rõ thiếu gì, không hiện lỗi khó hiểu.

## Tai cần chuẩn bị (giai đoạn B)

- Token máy của CMS prod, đặt vào file cấu hình trên pve2. Không gửi qua chat.
- Địa chỉ API của CMS prod.
- Tài khoản Zernio đã nối với Facebook, YouTube, TikTok, kèm id tài khoản.
- Đổi mật khẩu CMS vì đã dán vào chat ngày 05/11.

## Để người làm quyết

- Cấu trúc component và cách chia file trong `web/src`, cách nạp font.
- Hình dạng JSON của chặng, thời gian dự kiến và trạng thái gửi CMS trong API.
- Cách ghi `times.json` trong `auto.py` và bảng thời gian mặc định.
- Chi tiết gọi GraphQL và REST của CMS (thư viện, thời gian chờ, thử lại), miễn tôn trọng luồng trên.
- Thứ tự commit và cách thử, miễn có test cho:
  - phần tính thời gian còn lại;
  - phần chống tạo bài trùng;
  - phần CSRF của ô tải ảnh.
