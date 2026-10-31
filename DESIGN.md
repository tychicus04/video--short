# Video Short – quy trình lồng tiếng khớp nhịp (thiết kế)

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
khớp nhịp"): **Video → Phụ đề thật → Dịch sát → Khớp giây → TTS trung tính → Ghép hoàn chỉnh**.
Video gốc tạo bằng **tiếng Anh**, rồi dịch và lồng tiếng Việt.

## Mục tiêu

Một lệnh trong Claude Code: `/video-short <chủ đề | URL | đường dẫn tài liệu>`.

0. **Tìm hiểu & kịch bản**: tìm nguồn đáng tin (ưu tiên báo cáo gốc), tạo notebook
   NotebookLM, nạp nguồn, viết brief tiếng Việt theo mẫu của Tai (Thông điệp duy nhất /
   Người xem / Câu móc câu / Ví dụ mô phỏng / Ý chính / Lưu ý độ chính xác / Câu chốt /
   Lời kêu gọi) kèm tiêu đề video (dòng nhỏ + dòng lớn).
   **ĐIỂM DỪNG DUY NHẤT: Tai duyệt brief và tiêu đề.** Sau đó chạy tự động đến file cuối.
1. **Tạo video**: nạp brief (bản tiếng Anh) làm nguồn, `generate video --format short
   --language en`, chờ xong, tải về.
2. **Phụ đề thật**: dò từng mảnh phụ đề in trong hình và mốc thời gian (như
   `prototype/detect.py`), agent đọc ảnh cắt để lấy đúng chữ tiếng Anh, ghép thành câu.
   Xóa phụ đề cũ khỏi hình (như `prototype/plates.py`).
3. **Dịch sát nghĩa** từng câu sang tiếng Việt. Không thêm, không đoán nội dung.
4. **Canh thời lượng**: mỗi câu tiếng Việt phải đọc vừa trong khoảng thời gian của câu tiếng
   Anh tương ứng, ở tốc độ tự nhiên. Quá dài thì agent rút gọn câu (giữ nghĩa), không ép
   giọng đọc nhanh bất thường; ngắn hơn thì chèn lặng.
5. **Tạo giọng đọc** bằng Gemini TTS, một giọng tiếng Việt trung tính cho cả video.
6. **Ghép hoàn chỉnh**: thay tiếng gốc bằng giọng mới, thêm thanh tiêu đề, phụ đề tiếng
   Việt cố định sát đáy, xóa watermark, cắt đoạn logo cuối, xuất `.mp4`.
   Cuối cùng một agent soát lại: chữ phụ đề khớp lời đọc, không lộ phụ đề cũ, và liệt kê
   chi tiết trong hình mâu thuẫn với brief để Tai tự quyết.

Kết quả ở `~/notebooklm-videos/<slug>/`: `final.mp4`, brief, bảng phụ đề EN/VI có mốc
thời gian, file giọng đọc, báo cáo soát.

## Không làm (non-goals)

- Nhạc nền, hiệu ứng âm thanh.
- Sửa hình minh họa ngoài việc xóa phụ đề cũ, watermark, đoạn cuối. Chi tiết sai trong
  hình chỉ được báo cáo (vá như "iOS 26" hôm nay là việc làm tay, không tự động).
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
  dịch & canh thời lượng, soát cuối. Các bước cố định (tạo/tải video, dò phụ đề, xóa chữ,
  TTS, ghép) là script được skill gọi.
- **Model của subagent** theo quy ước của Tai: viết/sửa file → Sonnet; soát cuối → Opus.
- **Kiểu chữ** giống bản v4 hôm nay: font Be Vietnam Pro; thanh tiêu đề đen ở trên (dòng
  nhỏ vàng + dòng lớn trắng); hộp phụ đề đen, chữ trắng, từ khóa vàng; đáy hộp ở y=1204;
  câu đầu hiện trọn câu (giới thiệu chủ đề), các câu sau thành cụm một dòng ngắt ở chỗ tự
  nhiên.
- **Mốc phụ đề tiếng Việt** lấy theo giọng đọc mới (không theo giọng gốc).
- **Xóa phụ đề cũ**: mỗi cảnh một ảnh nền sạch. Ưu tiên khung sạch có sẵn, nếu không có
  thì dùng LaMa (big-lama.pt, ~200MB, CPU), như `prototype/plates.py`. Phụ đề cũ nằm ở
  dải mà hộp phụ đề mới đã che thì không cần xóa.

## Quyết định sau khi soát

- **Brief là chuẩn nội dung** (Tai đã đồng ý). Người dịch nhận cả lời đọc tiếng Anh lẫn brief
  đã duyệt và danh sách nguồn. Khi lời tiếng Anh sai dữ kiện, khẳng định điều brief cấm,
  hoặc đổi câu móc/câu chốt/lời kêu gọi đã duyệt, bản tiếng Việt theo brief. Mọi chỗ sửa so
  với tiếng Anh được ghi vào báo cáo soát. Báo cáo cũng ghi các chỗ hình minh họa không còn
  khớp với lời đã sửa. Đường dẫn menu trong lời kêu gọi dùng đúng nhãn tiếng Việt của iOS.
- Video vẫn tạo từ brief (bản tiếng Anh) cộng với tất cả nguồn đã nạp, như video Coruna.
- **Hạn mức Gemini: gói miễn phí, 10 lần gọi TTS/ngày cho mỗi model** (đo được khi chạy thử 31/10).
  Tai chọn **đọc cả kịch bản trong một lần gọi** rồi tự cắt thành từng câu theo khoảng lặng
  (thay cho mỗi câu một lần gọi):
  - ước lượng độ dài câu tiếng Việt trước khi gọi TTS (tốc độ đọc đo được lưu trong config.toml);
  - mỗi vòng đọc (kể cả vòng rút gọn câu) chỉ tốn một lần gọi; âm thanh lưu theo nội dung nên chạy lại không tốn thêm;
  - giới hạn theo phút thì tự đợi rồi gọi lại; hết hạn mức theo ngày thì dừng (mã 75) và chạy lại sau.
- Môi trường chạy (imageio-ffmpeg, numpy, pillow, opencv, torch CPU, font Be Vietnam Pro,
  `big-lama.pt`) được cài lại dưới `~/video-pipeline/`, không dùng thư mục tạm.

## Để người dựng tự quyết

- Tên model Gemini TTS chính xác, giọng mặc định trung tính (để trong file cấu hình),
  cách viết prompt giọng.
- Thuật toán canh thời lượng (giới hạn chỉnh tốc độ, xử lý câu quá dài/ngắn).
- Cách tự tìm các độ cao phụ đề cũ và mốc chuyển cảnh cho từng video mới
  (prototype đang ghi cứng cho video Coruna).
- Phương án dự phòng khi một cảnh không đứng yên (không dùng được ảnh nền sạch).
- Cấu trúc file trung gian, tên thư mục `<slug>`.

## Tài liệu tham khảo

- `prototype/` – script đã dùng cho video Coruna & DarkSword (v4): `detect.py` (dò mảnh
  phụ đề + mốc), `plates.py` (ảnh nền sạch, LaMa), `render.py` (tiêu đề, phụ đề cụm, vá
  "iOS 26", xóa watermark, cắt cuối), `brief_c01.md` (mẫu brief).
- Video mẫu: `~/notebooklm-videos/coruna-darksword-short.mp4` (gốc) và `-v4.mp4` (đích).
