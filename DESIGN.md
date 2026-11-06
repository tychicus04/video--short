# Video Short – quy trình lồng tiếng khớp nhịp (thiết kế)

> Bổ sung: `docs/superpowers/specs/2026-10-31-hinh-theo-loi-design.md` (hình theo lời, vá chữ sai) và
> `docs/superpowers/specs/2026-11-06-hinh-goc-notebooklm-design.md` (từ 06/11/2026: hình là chính video NotebookLM co giãn theo
> lời Việt; hình động vẽ tay, ẩn dụ, nhịp hình, thẻ tư liệu và máy quay trên ảnh tĩnh đã bỏ).
> Chỗ nào khác tài liệu này thì theo tài liệu đó: bước 4 "Khớp giây" thành "Hình theo lời", không còn ép câu Việt vừa
> khung giây tiếng Anh, giọng giữ tốc độ gốc, hình minh họa có thể được vá chữ hoặc thay bằng tư liệu thật.

## Mục đích

Tai làm video ngắn dọc (TikTok/Reels) cho người xem Việt Nam, chủ đề công nghệ/bảo mật
(ví dụ dự án CyberZ chống lừa đảo, vụ Coruna & DarkSword). NotebookLM tạo được video ngắn
có hình minh họa tốt, nhưng bản gốc "chán và cùi":

- phụ đề in cứng vào hình, vụn 2–4 chữ, tách đôi từ ghép, vị trí nhảy giữa các cảnh;
- có watermark "Gemini Notebook" ở góc dưới phải và 3 giây logo Gemini ở cuối;
- không có tiêu đề;
- giọng đọc NotebookLM, không chọn được giọng;
- đôi khi hình chứa chi tiết sai so với kịch bản (ví dụ màn hình ghi "iOS 17.5.1").

Tai muốn mỗi lần làm video, các agent chạy đúng quy trình 6 bước (ảnh "Quy trình lồng tiếng
khớp nhịp"): **Video → Phụ đề thật → Dịch sát → Hình theo lời → TTS trung tính → Ghép hoàn chỉnh**.
Video gốc tạo bằng **tiếng Anh**, rồi dịch và lồng tiếng Việt.

## Mục tiêu

Một lệnh trong Claude Code: `/video-short <chủ đề | URL | đường dẫn tài liệu>`.

0. **Tìm hiểu & kịch bản**: tìm nguồn đáng tin (ưu tiên báo cáo gốc), tạo notebook
   NotebookLM, nạp nguồn, viết brief tiếng Việt theo mẫu của Tai (Thông điệp duy nhất /
   Người xem / Câu móc câu / Ví dụ mô phỏng / Ý chính / Lưu ý độ chính xác / Câu chốt /
   Lời kêu gọi) với mục **Tiêu đề (câu mở đầu)**: luận điểm cả video chứng minh, video mở đầu bằng đúng câu này.
   **ĐIỂM DỪNG DUY NHẤT: Tai duyệt brief và tiêu đề.** Sau đó chạy tự động đến file cuối.
1. **Tạo video**: nạp brief (bản tiếng Anh) làm nguồn, `generate video --format short
   --language en`, chờ xong, tải về.
2. **Phụ đề thật**: dò từng mảnh phụ đề in trong hình và mốc thời gian (như
   `prototype/detect.py`), agent đọc ảnh cắt để lấy đúng chữ tiếng Anh, ghép thành câu.
   Xóa phụ đề cũ khỏi hình (như `prototype/plates.py`).
3. **Dịch sát nghĩa** từng câu sang tiếng Việt. Không thêm, không đoán nội dung.
4. **Hình theo lời**: giọng Việt đọc liền mạch ở tốc độ tự nhiên (không rút câu, không tăng
   tốc); mỗi câu có một ảnh tĩnh chọn từ video NotebookLM và một đoạn hình dài đúng bằng câu
   đó. Agent `vs-visuals` vá chữ sai trong ảnh (mâu thuẫn với lời Việt hoặc brief) và thay tối đa 5 câu
   bằng tư liệu thật vẽ lại (SVG hoặc ảnh nét chì, ghi nguồn).
5. **Tạo giọng đọc** bằng Gemini TTS, một giọng tiếng Việt trung tính cho cả video.
6. **Ghép hoàn chỉnh**: giọng nối tiếp, ảnh zoom/trượt chậm nối nhau bằng mờ chồng, phụ đề tiếng
   Việt cố định một chỗ, xóa watermark, đóng logo Tạp chí An ninh mạng Việt Nam xám mờ ở góc trên phải, bỏ đoạn logo
   Gemini cuối và thay bằng 2,5 giây logo ANM chạy hình (`render.end_card`), xuất `.mp4`.
   Cuối cùng một agent soát lại: chữ phụ đề khớp lời đọc, không lộ phụ đề cũ, chuyển động mượt,
   hình tư liệu khớp nguồn, chỗ vá không lộ viền, và liệt kê chi tiết còn mâu thuẫn với brief
   để Tai tự quyết.

Kết quả ở `~/notebooklm-videos/<slug>/`: `final.mp4`, brief, bảng phụ đề EN/VI có mốc
thời gian, file giọng đọc, `visuals.json` (chỗ vá chữ và hình tư liệu kèm nguồn), báo cáo soát.

## Không làm (non-goals)

- Nhạc nền (bản quyền, Content ID). Hiệu ứng âm thanh thì có từ 05/11/2026 (Tai chọn), nhưng chỉ tối đa 3
  điểm nhấn tự đặt theo hình: vào khung vẽ tay, lúc khung vẽ đầu tiên chuyển đỏ, lúc tư liệu đầu tiên hiện
  (`vshort/sound.py`, file CC0 trong `assets/sfx/`).
- Vẽ lại hình bằng AI tạo ảnh (Gemini image) hoặc video AI.
- Giữ lại animation gốc của NotebookLM ở bất kỳ đoạn nào.
- Sửa nét vẽ sai (không phải chữ) trong hình NotebookLM: chỉ báo cáo. Chữ sai thì `vs-visuals` vá,
  tư liệu thật thì vẽ lại bằng SVG hoặc bộ lọc nét chì (xem spec "hình theo lời").
- Đăng lên TikTok/Reels.
- Xuất nhiều ngôn ngữ.

## Thất bại dù vẫn chạy được (anti-goals)

- Chữ phụ đề khác lời đọc.
- Bản dịch thêm ý, đoán ý, hoặc lệch dữ kiện so với nguồn.
- Phụ đề cũ ló ra hoặc lóe lên dù chỉ một khung hình.
- Giọng đọc bị ép nhanh nghe gấp, hoặc có khoảng lặng dài bất thường.
- Phụ đề tách đôi từ ghép ("hoàn | toàn").
- Lộ khóa API (in ra log, commit, gửi đi đâu khác ngoài Gemini API).

## Ràng buộc

- Chạy trên server `ubuntu-pve2` (Ubuntu 26.04, không màn hình, chỉ CPU), Tai điều khiển
  qua VSCode Remote SSH từ máy Mac.
- CLI NotebookLM: `uv run notebooklm …` trong `~/Document/notebooklm-py-main` (bản 0.8.6).
  Đăng nhập: không chạy được `notebooklm login` trên server (Playwright không hỗ trợ
  Ubuntu 26.04, không có màn hình); Tai đăng nhập trên Mac rồi `scp storage_state.json`.
  Khi lệnh báo hết phiên, dừng và nhắc Tai làm lại bước này.
- `GEMINI_API_KEY` nằm trong `~/Document/notebooklm-py-main/.env`.
- Server không có ffmpeg hệ thống; dùng ffmpeg từ gói `imageio-ffmpeg` (có libass, libx264).
- Gemini TTS hỗ trợ tiếng Việt (vi-VN, GA).
- Video ngắn NotebookLM: 720×1280, ~60 giây, 30 fps, phong cách cố định. Phụ đề cũ nằm ở
  một trong vài độ cao tùy cảnh (video hôm nay: y≈930 và y≈1147). Các cảnh gần như đứng yên.
- Watermark ở x≈530–697, y≈1240–1255; đoạn logo cuối ~3 giây, im lặng.

## Phần đã quyết (đề xuất của Claude, Tai có thể đổi)

- **Bố trí**: script ở `~/video-pipeline/`; lệnh `/video-short` là skill ở
  `~/.claude/skills/video-short/`; các subagent ở `~/.claude/agents/`.
- **Chỉ dùng agent cho bước cần phán đoán**: tìm hiểu & viết brief, đọc phụ đề từ ảnh,
  dịch sát, chọn/vá hình (`vs-visuals`), soát cuối. Các bước cố định (tạo/tải video, dò phụ đề, xóa chữ,
  TTS, ghép) là script được skill gọi.
- **Model của subagent** theo quy ước của Tai: viết/sửa file → Sonnet; soát cuối → Opus.
- **Kiểu chữ** (Tai đổi sau lần chạy thử 31/10): giữ kiểu phụ đề của NotebookLM — hộp xám nhạt
  vuông góc, chữ xám đậm kiểu viết tay (font Patrick Hand, đủ dấu tiếng Việt); không thanh tiêu đề,
  không tô màu từ khóa; mọi hộp đặt cố định, đáy ở y=1140 (từ 05/11/2026; trước đó tâm ở y=1150, dải phụ đề thấp của NotebookLM,
  nhưng nửa dưới bị tên kênh/mô tả của TikTok/Reels/Shorts che), chữ rộng tối đa 516 px để không lấn cột nút.
  Câu đầu là tiêu đề trong brief, hiện trọn câu; các câu tiếng Anh liền sau chỉ lặp ý mà nó đã nói
  thì để trống (khung giờ của chúng vẫn là nguồn ảnh cho tiêu đề). Các câu sau thành cụm
  một dòng ngắt ở chỗ tự nhiên.
- **Mốc phụ đề tiếng Việt** lấy theo giọng đọc mới (không theo giọng gốc); giọng nối tiếp, cách nhau một nhịp ngắn cố định.
- **Xóa phụ đề cũ**: mỗi cảnh một ảnh nền sạch. Ưu tiên khung sạch có sẵn, nếu không có
  thì dùng LaMa (big-lama.pt, ~200MB, CPU), như `prototype/plates.py`. Xóa ở mọi dải, vì hộp
  phụ đề mới nhỏ hơn hộp cũ nên không che được.

## Quyết định sau khi soát

- **Brief là chuẩn nội dung** (Tai đã đồng ý). Người dịch nhận cả lời đọc tiếng Anh lẫn brief
  đã duyệt và danh sách nguồn. Khi lời tiếng Anh sai dữ kiện, khẳng định điều brief cấm,
  hoặc đổi câu móc/câu chốt/lời kêu gọi đã duyệt, bản tiếng Việt theo brief. Mọi chỗ sửa so
  với tiếng Anh được ghi vào báo cáo soát. Chữ trong hình không còn khớp với lời đã sửa thì
  `vs-visuals` vá; báo cáo ghi mọi chỗ vá và các chỗ hình còn lệch (nét vẽ). Đường dẫn menu trong lời kêu gọi dùng đúng nhãn tiếng Việt của iOS.
- Video vẫn tạo từ brief (bản tiếng Anh) cộng với tất cả nguồn đã nạp, như video Coruna.
- **Hạn mức Gemini: gói miễn phí, 10 lần gọi TTS/ngày cho mỗi model** (đo được khi chạy thử 31/10).
  Tai chọn **đọc cả kịch bản trong một lần gọi** rồi tự cắt thành từng câu theo khoảng lặng
  (thay cho mỗi câu một lần gọi):
  - mỗi video chỉ tốn một lần gọi; âm thanh lưu theo nội dung nên chạy lại không tốn thêm; `timeline` không gọi TTS;
  - giới hạn theo phút thì tự đợi rồi gọi lại; hết hạn mức theo ngày thì **đọc bằng ZeroTTS** (Tai chọn 02/11/2026):
    TTS tiếng Việt chạy CPU trên máy, mỗi câu một lần gọi lệnh `zerotts` (không phải cắt theo khoảng lặng), giọng
    `zerotts_voice` trong `config.toml`. Đã đọc bằng ZeroTTS thì chạy lại vẫn giữ giọng đó. ZeroTTS không chạy được
    (chưa cài, thiếu weights) thì dừng (mã 75) như trước.
- Môi trường chạy (imageio-ffmpeg, numpy, pillow, opencv, torch CPU, font Be Vietnam Pro,
  `big-lama.pt`) được cài lại dưới `~/video-pipeline/`, không dùng thư mục tạm.

## Hình động một khung (02/11/2026)
- Đoạn cơ chế là **một khung hình**, vẽ theo nhịp (mỗi bước cơ chế của brief một nhịp, tối đa 6), cái đã vẽ giữ lại và nhạt đi khi
  lời sang bước khác, một chấm đỏ đi suốt đoạn; tối đa 7 thứ trên khung; khung cuối đọc được như sơ đồ A→Z.
- `vs-motion` vẽ khung từ brief (`motion.json`, `vshort motion RUN --design`) **trong lúc NotebookLM tạo video**; sau khi Tai duyệt
  bản dịch, nó gắn từng nhịp vào câu đọc (`motion.bind.json`, `vshort motion RUN`), bỏ nhịp mà lời bỏ hoặc đọc lệch thứ tự; còn
  dưới 2 nhịp thì đoạn đó dùng ảnh tĩnh. Không thêm điểm dừng.
- Hình kit chưa có là dữ liệu nét vẽ (`assets/shapes/<tên>.json`, ô 0–100, 1–12 nét), vẽ bằng đúng nét tay của kit. Thư viện chỉ
  thêm, không sửa; mỗi run giữ bản sao hình đã dùng trong `RUN/shapes/`. Cuối run `vshort auto` commit riêng `assets/shapes` và push;
  push lỗi chỉ báo trong lời nhắn cuối.
- Vùng vẽ `y 96–1050`: tránh logo góc trên phải.
- Thiết kế: `docs/superpowers/specs/2026-11-02-hinh-dong-mot-khung-design.md`.

## Điều phối bằng `vshort auto` (02/11/2026)
- Tai đặt ngân sách ~$5/video (trước đó ~$18,9 theo giá API). Không còn phiên Claude điều phối suốt: `vshort auto` chạy nền
  trên server, gọi các agent `vs-*` bằng `claude -p` (researcher, transcriber, translator, visuals: Haiku; motion: Sonnet;
  reviewer: Opus), dừng hai lần cho Tai duyệt (brief, bản dịch), tối đa 2 vòng sửa sau soát, ghi chi phí từng video
  (`cost.json`). `/video-short` chỉ khởi động, chờ, đưa Tai duyệt và báo kết quả.
- Thiết kế: `docs/superpowers/specs/2026-11-02-dieu-phoi-bang-script-design.md`.

## Để người dựng tự quyết

- Tên model Gemini TTS chính xác, giọng mặc định trung tính (để trong file cấu hình),
  cách viết prompt giọng.
- Cách tự tìm các độ cao phụ đề cũ và mốc chuyển cảnh cho từng video mới
  (prototype đang ghi cứng cho video Coruna).
- Phương án dự phòng khi một cảnh không đứng yên (không dùng được ảnh nền sạch).
- Cấu trúc file trung gian, tên thư mục `<slug>`.

## Tài liệu tham khảo

- `prototype/` – script đã dùng cho video Coruna & DarkSword (v4): `detect.py` (dò mảnh
  phụ đề + mốc), `plates.py` (ảnh nền sạch, LaMa), `render.py` (tiêu đề, phụ đề cụm, vá
  "iOS 26", xóa watermark, cắt cuối), `brief_c01.md` (mẫu brief).
- Video mẫu: `~/notebooklm-videos/coruna-darksword-short.mp4` (gốc) và `-v4.mp4` (đích).
- `docs/superpowers/specs/2026-10-31-hinh-theo-loi-design.md` – thiết kế "hình theo lời" (bỏ khoảng lặng,
  chuyển động mượt, tư liệu thật, vá chữ sai); `claude/agents/vs-visuals.md` – agent chọn và sửa hình.
