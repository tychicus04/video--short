# Điều phối /video-short bằng script — thiết kế (02/11/2026)

## Vì sao

Một video tốn khoảng $18,9 theo giá API (đo trên run `hybrid-pqc-vpn`, xem `docs/research-2026-11-02.md` mục 10–12). Tai đặt
ngân sách **khoảng $5/video**. Phần lớn chi phí là ngữ cảnh dài bị đọc lại mỗi lượt: phiên chính điều phối (89 lượt, ngữ cảnh tới
375 nghìn token) và reviewer. Đổi model các agent đã làm (Haiku cho researcher, transcriber, translator, visuals; motion giữ
Sonnet vì Tai coi hình động giải thích cơ chế là phần quan trọng nhất; reviewer giữ Opus). Phần còn lại là bỏ phiên chính:
các bước cố định đã là lệnh `vshort`, chỉ cần một script nối chúng và gọi agent không qua một phiên Claude dài.

## Mục tiêu

- Chạy trọn một video trên server `pve2` mà không có phiên Claude nào điều phối suốt quá trình.
- Dừng **hai lần** cho Tai duyệt (Tai chọn):
  1. sau khi có brief (`brief.vi.md`, tiêu đề lên đầu);
  2. sau khi có bản dịch: từng câu tiếng Anh (phụ đề thật đã chép) cạnh lời Việt và `note`, trước khi đọc giọng và vẽ.
- Ghi chi phí thật từng lần gọi agent và tổng mỗi video (`$RUN/cost.json`), in tổng khi xong.
- Chạy lại sau khi dừng (duyệt, lỗi, hết phiên NotebookLM) thì tiếp từ bước dở, như `state.json` hiện nay.
- Giữ nguyên chất lượng soát: reviewer Opus vẫn soát video cuối; có vòng sửa tối đa 2 lần.

## Không làm

- Không đổi các bước `vshort` hiện có (detect, text, check, tts, plates, motion, stills, visuals, timeline, render) ngoài chỗ cần
  cho script gọi.
- Không đổi phong cách hình, không thêm AI tạo ảnh/video (DESIGN.md).
- Chưa xử lý ý "quá nhiều ảnh chuyển động" Tai nêu — chưa rõ là đoạn nào; để một đợt sau.

## Thất bại dù vẫn chạy được (anti-goal)

- Video ra mà lỗi brief cấm (nói quá, mất điều kiện, lời kêu gọi sai) lọt qua vì không còn ai "đọc lại" như phiên chính cũ.
- Script kẹt im lặng (agent treo, NotebookLM chờ mãi) mà Tai không biết.
- Chi phí vượt xa $5 mà không ai thấy.

## Cách dùng (Tai quyết: vẫn gõ `/video-short`)

`/video-short <chủ đề>` vẫn là lối vào. Skill rút gọn còn: khởi động script, chờ nó dừng, đưa Tai thứ cần duyệt (dán nội dung brief /
bảng dịch), nhận ý Tai, gọi script chạy tiếp, cuối cùng báo kết quả. Phiên đó chạy Sonnet, không advisor (đã cấu hình ở
`~/Document/notebooklm-py-main` và `~/video-pipeline`), không đọc file lớn, không tự soát gì. *(Gọi script trực tiếp từ terminal
cũng phải chạy được.)*

## Luồng của script

Lệnh: `vshort auto <slug> --topic "<chủ đề>"` lần đầu; `vshort auto $RUN` các lần sau. Mỗi lần chạy đọc `state.json`, làm tiếp bước
chưa xong, dừng ở điểm duyệt hoặc khi xong/lỗi, thoát với mã cho biết lý do.

1. **research** — `claude -p --agent vs-researcher` (chủ đề, slug, `$RUN`). Researcher phải ghi notebook id vào một file trong `$RUN`
   (hiện nó chỉ "trả về" bằng lời — cần sửa prompt) để script đọc được.
2. **Dừng duyệt brief** (mã riêng). Tai sửa thì sửa thẳng `brief.vi.md` / `brief.en.md` hoặc nói với phiên `/video-short` để nó sửa
   cả hai. Duyệt bằng `vshort approve $RUN brief`. *(Quyết định của tôi:)* `approve brief` từ chối khi `brief.vi.md` mới hơn
   `brief.en.md`, vì NotebookLM làm video từ bản tiếng Anh — bản cũ là mất 5–40 phút ra video sai.
   *Chế độ tự động* (Tai nói "chạy tự động"; Tai chọn): **chỉ bỏ điểm dừng brief**, vẫn dừng duyệt bản dịch. Thay cho Tai đọc brief:
   một lần gọi agent rẻ soát brief với `sources.md` (dữ kiện, ngày, điểm tranh cãi, luật an toàn mục "Cơ chế từng bước" như SKILL.md
   cũ), sửa cả hai bản nếu lệch; cách làm cụ thể là việc của builder.
3. **video** — `vshort new`, `notebooklm source add` (brief EN), `vshort fetch` với prompt như skill hiện nay. Mã 4 (hết phiên NotebookLM)
   → dừng, in thông báo đăng nhập lại.
4. **transcribe** — `vshort detect` → `claude -p --agent vs-transcriber` → `vshort text`.
5. **translate** — `claude -p --agent vs-translator` với đầu ra `vshort text`; translator tự chạy `vshort check` tới mã 0; script chạy
   lại `vshort check` để chắc.
6. **Dừng duyệt bản dịch** (mã riêng). Script in (và ghi ra file để skill dán) bảng: id, câu Anh, lời Việt (bỏ `|`), `note`. Tai sửa
   thì sửa `script.vi.json` (hoặc nhờ phiên `/video-short`), duyệt bằng `vshort approve $RUN script`; script chạy `vshort check` lại khi duyệt.
7. **build** — như skill bước 6–11: `tts` (nền) song song với `plates` → `motion` (agent) → `stills` → `visuals` (agent) → chờ `tts`
   → `timeline` → `render`. Mọi luật dự phòng hiện ghi trong SKILL.md (motion lỗi → `motion.loi.json` rồi chạy không hình động;
   visuals lỗi → `visuals.loi.json`, `[]`, chạy lại stills…; `render` mã 2 nhắc motion…) chuyển thành code trong script.
   Script tự chạy lại `vshort motion` / `vshort visuals` sau agent, không tin lời agent (như skill hiện nay).
8. **review** — `claude -p --agent vs-reviewer`. Để script biết sửa gì, reviewer ghi thêm `$RUN/review.json`: kết luận và danh sách lỗi,
   mỗi lỗi có loại/agent phụ trách (motion, visuals, translator…), câu hoặc thời điểm. Cần sửa prompt reviewer.
9. **fix** (tối đa 2 vòng) — lỗi thuộc agent nào thì gọi agent đó (`claude -p`, phiên mới) với `review.json` + phần việc; chạy lại
   các bước `vshort` phía sau; render; gọi **reviewer mới** ở chế độ "Soát lại" chỉ phần đã sửa. Sau 2 vòng còn lỗi thì dừng và
   báo, không lặp tiếp. Lỗi chỉ người sửa được (vd. hình NotebookLM sai sự thật mà không vá được) → ghi để báo Tai.
   **Lỗi ở bản dịch** (lời Tai đã duyệt; Tai chọn): không tự sửa. Translator (phiên mới) ghi bản sửa đề xuất ra file riêng (không đè
   `script.vi.json`), script **dừng** với mã duyệt bản dịch và in so sánh cũ/mới; Tai duyệt (`vshort approve $RUN script` sau khi
   chép bản đề xuất vào, hoặc nhờ phiên `/video-short`) thì chạy tiếp: `tts` lại, rồi các bước sau, rồi soát lại. `state.json` phải
   ghi đang ở vòng sửa nào để chạy tiếp đúng chỗ. Vòng sửa có lỗi bản dịch vẫn tính vào giới hạn 2 vòng.
10. **Xong** — in: đường dẫn `final.mp4`, lệnh `scp` về Mac, đoạn hình động, danh sách `visuals.json`, tóm tắt review, giọng đã dùng
    (Gemini hay ZeroTTS), **tổng chi phí** và chi phí từng agent.

## Gọi agent

- `claude -p --agent <vs-*> --output-format json "<prompt>"`, chạy trong `~/video-pipeline` (thư mục đã cấu hình Sonnet + tắt advisor;
  agent tự dùng `model:` trong frontmatter). Đã thử: `--agent vs-transcriber --model haiku` chạy đúng Haiku và trả `total_cost_usd`,
  `modelUsage`. Chưa thử: `--agent` không có `--model` có dùng đúng `model:` của agent không — builder phải kiểm.
- Không được có hỏi quyền tương tác; builder chọn chế độ quyền (thư mục này đang `auto`) sao cho agent ghi được file trong `$RUN`
  và chạy `vshort`.
- Prompt mỗi agent dựng từ file, theo mẫu cố định trong code (không còn "ghi chú của người điều phối" do Opus viết). Những gì phiên chính
  cũ hay thêm (lưu ý độ chính xác của brief, câu nào đã có hình động, nguồn trong `sources.md`) thì agent tự đọc từ file — prompt chỉ
  trỏ tới file.
- Mỗi lần gọi ghi một dòng vào `$RUN/cost.json`: bước, agent, model, giây, `total_cost_usd`, mã thoát.
- Giới hạn thời gian mỗi lần gọi; quá thì dừng và báo (chống "kẹt im lặng").

## Chạy tách khỏi phiên (quyết định của tôi)

- Một video mất ~1,5 giờ, phần lớn là chờ. Script chạy **tách khỏi** phiên Claude/ssh đã khởi động nó (sống tiếp khi phiên tắt),
  ghi log vào `$RUN/auto.log` và ghi trạng thái hiện tại (đang chạy / dừng chờ duyệt brief / dừng chờ duyệt bản dịch / lỗi / xong,
  kèm lý do) vào một file `vshort status $RUN` đọc được.
- Không chạy hai script cùng lúc trên một `$RUN` (khóa).
- "Báo Tai" = trạng thái + log + thông báo in ra; phiên `/video-short` đang mở thì đọc và đưa cho Tai, gọi lại `/video-short` thì
  đọc trạng thái mà tiếp. **Không** thêm kênh báo qua điện thoại/chat — ngoài phạm vi.

## Chi phí

Ước tính (chưa đo, trừ chỗ ghi "đo"): researcher Haiku ~$0,1; transcriber/translator/visuals Haiku ~$0,06 (đo ở phép thử); motion
Sonnet ~$1,2–1,9 (đo $1,86 gồm một lượt sửa); reviewer Opus đã làm gọn ~$2–4; phiên `/video-short` rút gọn ~$0,2–0,5. Tổng
~$3,5–6. Tổng thật in ra mỗi video; vượt $5 thì in cảnh báo (không chặn).

## Builder tự quyết

- Script viết bằng Python trong gói `vshort` (lệnh con `auto`, `approve`) hay file riêng; mã thoát cụ thể cho từng lý do dừng.
- Định dạng `review.json`, cách reviewer gán lỗi cho agent.
- Chế độ quyền cho `claude -p`, giới hạn thời gian, cách chạy nền `tts`/`plates`.
- Cách soát brief ở chế độ tự động.
- Test: dùng agent giả (thay lệnh `claude`) để kiểm luồng, điểm dừng, chạy tiếp, vòng sửa, ghi chi phí; không gọi Claude thật trong test.
