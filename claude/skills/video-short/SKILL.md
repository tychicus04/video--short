---
name: video-short
description: Dùng khi Tai muốn làm một video ngắn (video short, TikTok/Reels) về một chủ đề bằng NotebookLM. Chạy quy trình lồng tiếng, hình theo lời - tìm hiểu, Tai duyệt brief, NotebookLM tạo video tiếng Anh, lấy phụ đề thật, dịch sát, Tai duyệt bản dịch, Gemini TTS tiếng Việt (hết lượt thì ZeroTTS), hình là chính video NotebookLM co giãn theo lời Việt (xóa phụ đề Anh từng khung, vá chữ sai), ghép hoàn chỉnh.
---

# /video-short <chủ đề | URL | tài liệu>

Mọi bước do `vshort auto` làm (script trên server, gọi các agent `vs-*` bằng `claude -p`, ghi chi phí từng video).
Phiên này **chỉ** khởi động nó, chờ, đưa Tai thứ cần duyệt, rồi báo kết quả — không tự làm bước nào, không tự soát.
Thiết kế: `~/video-pipeline/docs/superpowers/specs/2026-11-02-dieu-phoi-bang-script-design.md`.

- `vshort` = `cd ~/video-pipeline && uv run vshort …`
- Thư mục chạy: `RUN=~/notebooklm-videos/<slug>` (slug ngắn, không dấu, gạch nối).
- Không bao giờ in, ghi hay gửi đi `GEMINI_API_KEY`.
- Giữ ngữ cảnh gọn: mọi lượt đọc lại toàn bộ ngữ cảnh. Không đọc `auto.log`, `cost.json` hay file lớn trừ khi cần để báo lỗi
  (lúc đó `tail -20`). Không mở ảnh hay video.

## Các bước

1. **Bắt đầu** — `vshort auto <slug> --topic "<chủ đề / URL / mô tả tài liệu>"`. Thêm `--auto` khi Tai nói "chạy tự động" /
   "không cần duyệt" (chỉ bỏ điểm dừng brief; bản dịch vẫn dừng cho Tai duyệt). Lệnh in `$RUN` rồi chạy nền.
2. **Chờ** — chạy nền `vshort wait $RUN` và chờ thông báo (một video mất tới ~1,5 giờ); đừng hỏi dồn, đừng đọc file trong lúc chờ.
3. **Theo mã thoát của `vshort wait`** (nó in trạng thái và lời nhắn của script):
   - **20 — duyệt brief**: dán nội dung `$RUN/brief.vi.md` cho Tai (tiêu đề lên đầu). Tai sửa brief → sửa **cả** `brief.vi.md` lẫn
     `brief.en.md`. Tai duyệt → `vshort approve $RUN brief` (mã 2 = `brief.en.md` cũ hơn bản tiếng Việt: cập nhật rồi duyệt lại) →
     `vshort auto $RUN` → bước 2.
   - **21 — duyệt bản dịch**: dán `$RUN/translation.md` (câu Anh, lời Việt, note). Nếu lời nhắn nói có bản sửa đề xuất từ reviewer,
     dán cả lời nhắn đó (so sánh cũ → mới). Tai sửa → sửa `$RUN/script.vi.json` (giữ dấu `|` chia cụm phụ đề). Tai đồng ý bản đề
     xuất → chép `script.proposed.json` đè lên `script.vi.json` rồi xóa `script.proposed.json`; không đồng ý → xóa nó. Rồi
     `vshort approve $RUN script` (mã 2 = `vshort check` trượt: đưa Tai lỗi, sửa, duyệt lại) → `vshort auto $RUN` → bước 2.
   - **0 — xong**: dán nguyên lời nhắn (đường dẫn, tiêu đề, ảnh bìa, thư mục Mac tự kéo về kèm lệnh `rsync` lấy ngay — ghi rõ
     "gõ trong terminal Mac, không có dấu `!`" —, giọng, co giãn
     (câu nào đứng hình hay bỏ đuôi), vá chữ, kết luận soát, chi phí).
   - **1, 2, 4, 75 — dừng vì lỗi**: dán nguyên lời nhắn. Mã 4 = hết phiên NotebookLM (lời nhắn có cách đăng nhập lại); mã 75 = hết
     hạn mức Gemini và ZeroTTS không chạy được. Khi nguyên nhân đã xử lý xong, `vshort auto $RUN` chạy tiếp từ bước dở → bước 2.
4. **Video dở** (Tai gọi lại `/video-short` cho một slug đã có): `vshort status $RUN`. Dòng `auto:` là `running` → bước 2; `wait_brief`
   / `wait_script` → bước 3 với mã 20 / 21; `error` → đưa Tai lời nhắn, xử lý xong thì `vshort auto $RUN`.

## Kiểu neon (thử nghiệm)

Kiểu riêng, không dùng NotebookLM: Claude viết lời Việt thẳng từ brief, hình là sơ đồ neon vẽ bằng code (HyperFrames) theo lời.
Chỉ chạy khi Tai nói "kiểu neon". Thiết kế: `~/video-pipeline/docs/superpowers/specs/2026-11-09-kieu-neon-design.md`.

- **Bắt đầu**: `vshort auto <slug> --topic "…" --style neon` (thêm `--auto` như bước 1). Lệnh ghi `"style": "neon"` vào `run.json`;
  video không có cờ này chạy luồng NotebookLM như trên. Brief neon không có bản tiếng Anh (`brief.en.md`) nên `vshort approve $RUN brief`
  không đòi nó, và không có câu tiếng Anh để đối chiếu.
- **Hai điểm dừng**, vẫn theo mã thoát của `vshort wait` ở bước 3:
  - **20 — duyệt brief**: như trên, chỉ sửa `brief.vi.md`. Brief phải có mục "Cơ chế từng bước" (bước 0 "Bình thường" và ít nhất 2 bước có nguồn),
    thiếu thì script dừng ở đây báo lỗi.
  - **21 — duyệt lời**: dán `$RUN/loi.md` (mỗi câu một hàng: lời, số âm tiết, giây ước tính, note; cuối bảng là tổng và độ dài video, kể cả nghỉ giữa câu và outro; cần 60–70 giây).
    Tai sửa → sửa `$RUN/script.vi.json` (giữ dấu `|` chia cụm phụ đề). Rồi `vshort approve $RUN script` (mã 2 = `vshort check` trượt:
    đưa Tai lỗi, sửa, duyệt lại) → `vshort auto $RUN` → bước 2.
- **Các agent**: `vs-writer` (viết lời từ brief, chia cụm phụ đề, tự kiểm bằng `vshort check`), `vs-scene` (dựng `scene.json`: sơ đồ neon theo lời,
  code xếp chỗ và kiểm bằng `vshort scene`), `vs-reviewer-neon` (xem khung `final.mp4`, ghi `review.md` / `review.json`; lỗi thì vòng sửa
  chạy lại `vs-scene` hoặc `vs-writer`, tối đa 2 vòng). `vs-researcher` vẫn lo bước tìm hiểu.
- Bảng điều khiển hiện 9 chặng thay vì 10 (Viết lời, Duyệt lời, Giọng đọc, Kịch bản hình thay cho chặng NotebookLM → Giọng đọc và hình);
  cột tiếng Anh ở màn duyệt lời để trống.
