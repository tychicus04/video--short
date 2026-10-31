---
name: video-short
description: Dùng khi Tai muốn làm một video ngắn (video short, TikTok/Reels) về một chủ đề bằng NotebookLM. Chạy quy trình lồng tiếng khớp nhịp - tìm hiểu, Tai duyệt brief, NotebookLM tạo video tiếng Anh, lấy phụ đề thật, dịch sát, canh thời lượng, Gemini TTS tiếng Việt, ghép hoàn chỉnh.
---

# /video-short <chủ đề | URL | tài liệu>

Quy trình 6 bước "Video → Phụ đề thật → Dịch sát → Khớp giây → TTS trung tính → Ghép hoàn chỉnh".
Thiết kế: `~/video-pipeline/DESIGN.md`. Mọi bước cố định là lệnh `vshort`; bốn bước cần suy xét giao cho subagent.

- `vshort` = `cd ~/video-pipeline && uv run vshort …`
- `notebooklm` = `cd ~/Document/notebooklm-py-main && uv run notebooklm …`
- Thư mục chạy: `RUN=~/notebooklm-videos/<slug>` (slug ngắn, không dấu, gạch nối).
- Mã thoát `vshort`: 0 xong · 1 lỗi · 2 dữ liệu sai (in danh sách lỗi) · 3 câu quá dài (in id) · 4 hết phiên NotebookLM · 75 hết hạn mức Gemini.
- Mỗi lệnh ghi trạng thái vào `$RUN/state.json`; `vshort status $RUN` cho biết đang ở đâu. Khi chạy tiếp một video dở, bắt đầu từ bước chưa xong.
- Không bao giờ in, ghi hay gửi đi `GEMINI_API_KEY`.

## Các bước

1. **Tìm hiểu & kịch bản** — giao `vs-researcher` (chủ đề, slug, `$RUN`). Nó tạo notebook `"<Chủ đề> – Video Short"`, nạp nguồn,
   viết `$RUN/brief.vi.md`, `$RUN/brief.en.md`, `$RUN/sources.md`, và đề xuất dòng nhỏ (kicker, chữ HOA) + tiêu đề. Nó trả về notebook id.
2. **ĐIỂM DỪNG DUY NHẤT** — đưa Tai brief tiếng Việt + kicker + tiêu đề (dán nội dung, không chỉ đường dẫn). Chờ Tai duyệt hoặc sửa;
   sửa thì cập nhật cả `brief.vi.md` lẫn `brief.en.md`. Sau khi Tai duyệt, chạy liền một mạch đến cuối, không hỏi thêm.
3. **Tạo video tiếng Anh**
   - `vshort new <slug> --kicker "<KICKER>" --title "<Tiêu đề>" --notebook <id>`
   - `notebooklm source add -n <id> --type text --title "# BRIEF (EN) – <slug>" "$(cat $RUN/brief.en.md)"`
   - `vshort fetch $RUN --prompt "Vertical short. Follow the source '# BRIEF (EN) – <slug>' closely: open with its hook, cover its key points in order, end with its call to action. Explain at concept level only; do not assert claims the brief marks as disputed."`
     Chạy nền (mất 5–40 phút) và chờ thông báo, đừng hỏi dồn. Mã 4 → đưa Tai đúng thông báo đăng nhập lại mà lệnh in ra rồi dừng.
4. **Phụ đề thật**
   - `vshort detect $RUN` → giao `vs-transcriber` các ảnh `$RUN/sheets/*.png`, nó ghi `$RUN/fragments_text.json`.
   - `vshort text $RUN` → in từng câu tiếng Anh với khung giây và số âm tiết tối đa.
5. **Dịch sát + canh thời lượng** — giao `vs-translator` đường dẫn `$RUN` và nguyên văn đầu ra của `vshort text`.
   Nó ghi `$RUN/script.vi.json` và tự chạy `vshort check $RUN` tới khi mã 0.
   Song song (chạy nền): `vshort plates $RUN` (cần `captions.json` từ bước 4).
6. **Giọng đọc** — `vshort tts $RUN`. Mã 75 → báo Tai: hết hạn mức Gemini, các câu đã đọc được giữ, đợi hạn mức hồi rồi gọi lại
   `/video-short` để chạy tiếp; dừng.
   `vshort fit $RUN`. Mã 3 → giao lại `vs-translator` chỉ các id bị báo, kèm khung giây; rồi `vshort check`, `vshort tts`, `vshort fit`.
   Tối đa 2 vòng; sau đó vẫn đi tiếp và ghi các id còn dài vào báo cáo.
7. **Ghép & soát** — `vshort render $RUN` → giao `vs-reviewer` đường dẫn `$RUN`; nó ghi `$RUN/review.md`.
8. **Trả lời Tai** (tiếng Việt):
   - đường dẫn `$RUN/final.mp4`;
   - lệnh chép về Mac, ghi rõ "gõ trong terminal Mac, không có dấu `!`":
     `scp tai@pve2:~/notebooklm-videos/<slug>/final.mp4 ~/Downloads/<slug>.mp4`
   - tóm tắt `review.md`: chỗ lời Việt khác lời Anh (note), chỗ hình không khớp lời, cảnh có chuyển động cần xem, câu còn dài.
