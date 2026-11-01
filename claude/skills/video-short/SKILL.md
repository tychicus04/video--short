---
name: video-short
description: Dùng khi Tai muốn làm một video ngắn (video short, TikTok/Reels) về một chủ đề bằng NotebookLM. Chạy quy trình lồng tiếng, hình theo lời - tìm hiểu, Tai duyệt brief, NotebookLM tạo video tiếng Anh, lấy phụ đề thật, dịch sát, Gemini TTS tiếng Việt, hình động vẽ tay cho đoạn giải thích cơ chế, ảnh tĩnh từng câu kèm vá chữ sai và tư liệu thật vẽ lại, ghép hoàn chỉnh.
---

# /video-short <chủ đề | URL | tài liệu>

Quy trình 6 bước "Video → Phụ đề thật → Dịch sát → Hình theo lời → TTS trung tính → Ghép hoàn chỉnh": giọng Việt đọc liền
mạch ở tốc độ tự nhiên, mỗi câu có đoạn hình dài đúng bằng câu đó; đoạn lời giải thích cơ chế tấn công được vẽ thành hình động.
Thiết kế: `~/video-pipeline/DESIGN.md`, `~/video-pipeline/docs/superpowers/specs/2026-10-31-hinh-theo-loi-design.md` và
`~/video-pipeline/docs/superpowers/specs/2026-11-01-hinh-dong-co-che-design.md` (chỗ khác nhau thì theo tài liệu sau hơn).
Mọi bước cố định là lệnh `vshort`; sáu bước cần suy xét giao cho subagent.

- `vshort` = `cd ~/video-pipeline && uv run vshort …`
- `notebooklm` = `cd ~/Document/notebooklm-py-main && uv run notebooklm …`
- Thư mục chạy: `RUN=~/notebooklm-videos/<slug>` (slug ngắn, không dấu, gạch nối).
- Mã thoát `vshort`: 0 xong · 1 lỗi · 2 dữ liệu sai (in danh sách lỗi) · 4 hết phiên NotebookLM · 75 hết hạn mức Gemini.
- Mỗi lệnh ghi trạng thái vào `$RUN/state.json`; `vshort status $RUN` cho biết đang ở đâu. Khi chạy tiếp một video dở, bắt đầu từ bước chưa xong.
- Không bao giờ in, ghi hay gửi đi `GEMINI_API_KEY`.

## Các bước

1. **Tìm hiểu & kịch bản** — giao `vs-researcher` (chủ đề, slug, `$RUN`). Nó tạo notebook `"<Chủ đề> – Video Short"`, nạp nguồn,
   viết `$RUN/brief.vi.md` (có mục "Tiêu đề (câu mở đầu)"), `$RUN/brief.en.md`, `$RUN/sources.md`. Nó trả về notebook id.
2. **ĐIỂM DỪNG DUY NHẤT** — đưa Tai brief tiếng Việt, tiêu đề lên đầu (dán nội dung, không chỉ đường dẫn). Chờ Tai duyệt hoặc sửa;
   sửa thì cập nhật cả `brief.vi.md` lẫn `brief.en.md`. Sau khi Tai duyệt, chạy liền một mạch đến cuối, không hỏi thêm.
   **Chế độ tự động** (Tai nói "chạy tự động" / "không cần duyệt"): không dừng ở đây. Tự soát brief với `sources.md`
   (dữ kiện, ngày, điểm tranh cãi), sửa nếu lệch, rồi đi tiếp; đưa brief (có tiêu đề) vào câu trả lời cuối. Soát cả mục
   "Cơ chế từng bước" theo luật an toàn: chỉ mức khái niệm, không tên lỗ hổng/kỹ thuật/công cụ, không mã hay lệnh; lệch thì sửa
   ở cả hai bản brief.
3. **Tạo video tiếng Anh** — chạy tiếp một video dở (đã có `$RUN/run.json` với `artifact_id`) thì bỏ qua `new` và
   `source add`, chỉ chạy lại `vshort fetch $RUN` (nó tiếp tục đúng video đã yêu cầu, không tạo video mới).
   - `vshort new <slug> --notebook <id>`
   - `notebooklm source add -n <id> --type text --title "# BRIEF (EN) – <slug>" "$(cat $RUN/brief.en.md)"`
   - `vshort fetch $RUN --prompt "Vertical short. Follow the source '# BRIEF (EN) – <slug>' closely: open with its title line, word for word, cover its key points in order, end with its call to action. Walk through its 'How it works, step by step' section in order, unless it says None. Explain at concept level only; do not assert claims the brief marks as disputed."`
     Chạy nền (mất 5–40 phút) và chờ thông báo, đừng hỏi dồn. Mã 4 → đưa Tai đúng thông báo đăng nhập lại mà lệnh in ra rồi dừng.
4. **Phụ đề thật**
   - `vshort detect $RUN` → giao `vs-transcriber` các ảnh `$RUN/sheets/*.png`, nó ghi `$RUN/fragments_text.json`.
   - `vshort text $RUN` → in từng câu tiếng Anh: `id  start–end  en`.
5. **Dịch sát** — giao `vs-translator` đường dẫn `$RUN` và nguyên văn đầu ra của `vshort text`.
   Nó ghi `$RUN/script.vi.json` và tự chạy `vshort check $RUN` tới khi mã 0. Không có giới hạn độ dài câu.
6. **Giọng đọc** (nền, song song với bước 7–10) — `vshort tts $RUN` (một lần gọi Gemini cho cả kịch bản, tự cắt thành từng câu).
   Mã 75 → hết hạn mức Gemini trong ngày (gói miễn phí 10 lần/ngày mỗi model). Mã 1 với thông báo bắt đầu bằng "Không tách"
   ("Không tách được giọng đọc…" hoặc "Không tách chắc chắn…") → báo nguyên văn.
   Với cả hai mã: đợi bước 7–10 chạy xong rồi mới báo Tai và dừng. Khi Tai gọi lại `/video-short`, xem `vshort status $RUN`:
   các bước đã ✓ (`plates`, `motion`, `stills`, `visuals`) được bỏ qua, chạy tiếp từ `tts`.
7. **Nền sạch** — `vshort plates $RUN` (cần `captions.json` từ bước 4). Chạy nền và chờ mã 0 rồi mới sang bước 9 (làm bước 8 trong lúc chờ):
   chưa có `plates/plates.json` thì `vshort stills` từ chối (mã 2), vì ảnh tĩnh sẽ còn nguyên phụ đề tiếng Anh cũ.
8. **Hình động** — giao `vs-motion` đường dẫn `$RUN`. Nó chọn đoạn câu liền nhau mà lời giải thích cơ chế, chia 1–4 cảnh vẽ tay,
   ghi `$RUN/motion.json` (hoặc `null` khi lời không có cơ chế) và tự chạy `vshort motion $RUN` tới khi mã 0. Giữ đầu ra của nó cho câu
   trả lời cuối. Đừng tin lời nó: tự chạy `vshort motion $RUN` một lần. Mã khác 0 → `mv $RUN/motion.json $RUN/motion.loi.json`, chạy lại
   `vshort motion $RUN` (không có file = không có hình động, mã 0; các câu dùng ảnh tĩnh như thường) và báo lý do cho Tai.
   Phải xong bước này trước bước 10.
9. **Ảnh tĩnh** — `vshort stills $RUN`. Ghi `$RUN/clean.mp4` (video đã xóa phụ đề cũ và watermark), `$RUN/stills.json`,
   `$RUN/stills/<id>.png` (một ảnh vẽ xong cho mỗi câu), `stills/grid/<id>.png` (phủ lưới), `stills/sheet.png` (tất cả trên một tờ).
10. **Hình theo lời** — giao `vs-visuals` đường dẫn `$RUN`. Nó vá chữ sai trong hình, chọn tối đa 5 câu (ít hơn 3, kể cả 0, nếu không có
   tư liệu thật phù hợp) thay bằng tư liệu thật vẽ lại, ghi `$RUN/visuals.json` và tự chạy `vshort visuals $RUN` tới khi mã 0 (ra `$RUN/frames/<id>.png`, `frames.json`).
   Giữ nguyên đầu ra của nó (mỗi mục một dòng) cho câu trả lời cuối. Đừng tin lời nó: tự chạy `vshort visuals $RUN` một lần và
   lấy mã thoát đó. Mã khác 0 → giữ bản của nó (`mv $RUN/visuals.json $RUN/visuals.loi.json`), ghi `[]` vào `$RUN/visuals.json`,
   chạy lại `vshort visuals $RUN` để có khung hình gốc, và báo lý do cho Tai. Nếu lần chạy với `[]` cũng khác 0 (ảnh tĩnh hỏng hoặc thiếu):
   chạy lại `vshort stills $RUN`, đặt bản của nó về chỗ cũ (`mv $RUN/visuals.loi.json $RUN/visuals.json`) rồi chạy lại
   `vshort visuals $RUN` đúng một lần. Chỉ khi lần đó vẫn khác 0 mới quay về `[]` (giữ bản của nó thành `visuals.loi.json`, ghi `[]`,
   chạy `vshort visuals $RUN`).
11. **Ghép & soát** — chờ bước 6 và bước 10 xong (có `tts.json` và `frames.json`). `vshort timeline $RUN` (xếp giọng đọc nối tiếp,
   ra `timeline.json` và `narration.wav`; không gọi TTS; mã 2 "giọng đọc cũ không khớp kịch bản" → chạy lại `vshort tts $RUN`),
   rồi `vshort render $RUN` (ra `final.mp4`; lỗi thì giữ bản cũ; mã 2 nhắc "chạy lại `vshort motion`" → chạy `vshort motion $RUN`,
   khác 0 thì làm như dự phòng ở bước 8 (`mv` sang `motion.loi.json`, chạy lại `vshort motion $RUN`), rồi render lại; mất khoảng bằng độ dài video, nên chạy nền hoặc đặt timeout dài và
   chờ nó xong) → giao `vs-reviewer` đường dẫn `$RUN`; nó ghi `$RUN/review.md`.
12. **Trả lời Tai** (tiếng Việt):
   - đường dẫn `$RUN/final.mp4`;
   - lệnh chép về Mac, ghi rõ "gõ trong terminal Mac, không có dấu `!`":
     `scp tai@pve2:~/notebooklm-videos/<slug>/final.mp4 ~/Downloads/<slug>.mp4`
   - đoạn hình động: các câu, từng cảnh (câu nào, ý gì) theo đầu ra của `vs-motion`; hoặc "không có hình động" và lý do
     (lời không có cơ chế, hoặc `motion.json` không qua kiểm: lỗi cuối);
   - danh sách `visuals.json`: mỗi chỗ vá chữ (câu, chữ cũ → chữ mới, vì sao) và mỗi hình tư liệu (câu, loại, URL nguồn,
     ngày truy cập, những gì đã bỏ trong `note`);
   - tóm tắt `review.md`: chỗ lời Việt khác lời Anh (note), chỗ hình còn không khớp lời, lỗi reviewer tìm thấy.
