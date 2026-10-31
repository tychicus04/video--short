# Prompt chạy tự động /video-short

Mở Claude Code trên server (thư mục nào cũng được), dán nguyên khối dưới đây, thay dòng CHỦ ĐỀ:

```
/video-short CHỦ ĐỀ: <viết chủ đề, hoặc dán URL / đường dẫn tài liệu>

Chạy tự động từ đầu đến cuối, không dừng hỏi tôi duyệt brief.
- Người xem: mặc định của skill (sửa dòng này nếu muốn khác).
- Tự tìm nguồn đáng tin, tự soát brief với nguồn rồi đi tiếp.
- Gặp lỗi tự xử lý được thì tự xử lý và chạy tiếp. Chỉ dừng khi:
  hết phiên NotebookLM (mã 4), hết hạn mức Gemini trong ngày (mã 75), hoặc không tách được giọng đọc.
  Khi dừng: nói rõ tôi cần làm gì và gõ lại câu nào để chạy tiếp.
- Cuối cùng trả lời bằng tiếng Việt: brief + tiêu đề đã dùng, đường dẫn final.mp4,
  lệnh scp về Mac, và danh sách chỗ vá chữ và hình tư liệu kèm nguồn, tóm tắt review.md (chỗ lời Việt khác lời Anh, chỗ hình không khớp lời, đoạn cần xem kỹ).
```

Chạy tiếp một video bị dừng giữa chừng: dán lại đúng prompt cũ; skill đọc `~/notebooklm-videos/<slug>/state.json`
và làm tiếp từ bước chưa xong (video NotebookLM đã yêu cầu sẽ không bị tạo lại).
