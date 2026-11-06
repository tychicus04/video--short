# Hình gốc NotebookLM: một kiểu hình cho cả video (thiết kế)

Bổ sung cho `DESIGN.md` và `2026-10-31-hinh-theo-loi-design.md`. Chỗ nào khác hai tài liệu đó thì theo tài liệu này. Tài liệu
này **thay** các thiết kế hình động (`2026-11-01-hinh-dong-co-che`, `2026-11-02-hinh-dong-mot-khung`, `2026-11-03-hinh-dong-an-du`)
và nhịp hình (`2026-11-05-nhip-hinh`): những phần đó bị bỏ.

## Vì sao

Ngày 06/11, Tai xem các video gần đây (BOSSAI, ClawHub, Rails) và nhận xét:
- cứ khoanh tròn rồi zoom ra zoom vào, nhàm chán;
- hình không thống nhất về màu sắc và kiểu dáng;
- kém hơn chính video NotebookLM tiếng Anh mà nó được làm ra từ đó.

Đo trên Rails và BOSSAI (`2026-11-06-hinh-goc-thu/rails-cu.jpg` đặt cạnh `rails-notebooklm.jpg`) thấy ba nguyên nhân:

1. **Một video trộn 4 kiểu hình, mỗi kiểu một màu và một font:**
   - hình động tự vẽ: người que, chữ viết tay, nhãn xanh lá/xanh dương/đỏ;
   - thẻ tư liệu tự vẽ: thẻ trắng, chữ kiểu giao diện web, tô xanh ngọc;
   - sơ đồ của NotebookLM;
   - tranh chì của NotebookLM.

   Video gốc chỉ có hai kiểu sau, cùng nền kem và điểm nhấn đỏ.
2. **Mất animation của NotebookLM.** Mỗi câu chỉ lấy một khung tĩnh (`vshort stills`). Sơ đồ vốn dựng dần theo lời thì đứng yên,
   nên phải bù bằng máy quay và khoanh bút chì. Đó là chỗ "khoanh rồi zoom".
3. **Đoạn cơ chế bị kể hai lần bằng hai bộ hình:** hình động ẩn dụ của mình, rồi sơ đồ NotebookLM.

**Bản thử ngày 06/11.** Video Rails được dựng lại từ chính video NotebookLM đang chạy (`clean.mp4`). Mỗi câu co giãn cho vừa lời
Việt, giọng và phụ đề giữ nguyên. Script nằm ở `2026-11-06-hinh-goc-thu/spike_retime.py`, khung hình ở `rails-hinh-goc.jpg`.
Tai xem và nói: "oke tốt đấy".

**Lịch sử cần nhớ.** Ngày 31/10, Tai bỏ animation gốc vì hai lý do:
- **lặng dài:** câu Việt phải bắt đầu đúng mốc câu Anh. Lỗi này không quay lại, vì dòng thời gian theo lời vẫn giữ;
- **"giật và xấu, có lúc gần như trắng trơn":** hình hiện dần từng phần. Lỗi này phải chặn, xem mục 1 và 7.

## Ý chính

Giữ dòng thời gian theo lời như hiện nay: giọng Việt đọc liền mạch, mỗi câu một đoạn, `timeline.json` không đổi. Hình của mỗi đoạn
là **chính đoạn video NotebookLM** của câu tiếng Anh tương ứng, co giãn cho vừa câu Việt.

Không còn ảnh tĩnh có máy quay, và không còn hình nào mình tự vẽ. Ngoại lệ duy nhất là câu có chữ sai phải vá (mục 3).

## Mục tiêu

### 1. Hình là đoạn video gốc, co giãn theo lời

- **Đoạn nguồn của câu i:** `[en_i.start, en_{i+1}.start)`, lấy theo các câu có lời Việt (`script.merged`). Câu tiếng Anh để
  trống nhường thời gian cho câu trước nó, như hiện nay.
  - Câu đầu bắt đầu từ 0.
  - Câu cuối kéo tới hết câu tiếng Anh cuối, nhưng không lấn vào đoạn logo NotebookLM (`stills.NLM_OUTRO`).
- **Đoạn đích:** `[vi_i.start, vi_{i+1}.start)` theo `timeline.json`. Câu cuối kéo tới `total`. Khoảng nghỉ giữa hai câu nằm
  sẵn trong đó, nên không có lỗ đen.
- **Lời Việt ngắn hơn:** tua nhanh tối đa 1,5 lần. Nhanh hơn nữa thì bỏ phần đuôi của đoạn nguồn.
- **Lời Việt dài hơn:** phát tốc độ thường rồi giữ khung cuối. Không làm chậm cả đoạn, vì NotebookLM dựng hình ở đầu câu rồi đứng yên,
  nên phát chậm chỉ làm hình lề mề và giật.
- **Không giữ khung gần trắng.** Nếu đoạn nguồn mở bằng giấy trắng hay hình đang hiện dần (logic `BLANK` trong `stills.py`), không
  được kéo dài khúc đó. Nếu phải giữ khung, giữ khung đã vẽ xong.

Bản thử cho thấy với câu bình thường thì 8/16 câu phải tua 1,1–1,3 lần, và lâu nhất chỉ giữ khung 0,5 s.

### 2. Xóa phụ đề tiếng Anh theo từng khung

Đây là phần việc chính. Hiện `vshort plates` dán **một miếng vá đứng yên** cho mỗi cặp (cảnh, dải phụ đề). Có hai chỗ hỏng:
- `plates.scene_cuts` không nhận ra kiểu chuyển cảnh mờ dần của NotebookLM. Ví dụ, 62 giây đầu của Rails bị coi là một cảnh.
- Trên ảnh tĩnh thì miếng vá tạm ổn. Trên video chạy thì lộ thành ô nhạt trống, và còn cắt mất đáy hình vẽ
  (`2026-11-06-hinh-goc-thu/vet-o-trong.jpg`): bên trái là cảnh tranh chì, bên phải là cảnh sơ đồ có hai lớp ô chồng nhau.

**Đạt khi:** xem `final.mp4` (khung mỗi 0,5 s, và mỗi 0,1 s quanh chỗ chuyển cảnh) không còn thấy:
- chữ phụ đề Anh sót;
- ô nhạt;
- vết cắt ngang hình;
- vùng vá nhấp nháy giữa các khung liền nhau.

Phải đạt trên cả hai kiểu nền: tranh chì có đèn chiếu đang trôi, và sơ đồ nền kem. Phải đạt cả ở video nền tối (NetamLoader, xem
`captions._frames`).

Watermark góc dưới phải vẫn xóa bằng `render.WATERMARK` như cũ.

### 3. Chữ sai trong hình NotebookLM

`vs-visuals` chỉ còn một việc: vá chữ mâu thuẫn với lời Việt hay brief (`kind: "patch"`). Hai loại `svg` và `photo` bị bỏ.

Câu nào có chỗ vá thì cả đoạn của câu đó dùng **ảnh tĩnh đã vá**, đứng yên, không máy quay, không khoanh. Không vá trên video đang
chạy, vì miếng vá đứng yên sẽ lộ y như mục 2.

Chữ tiếng Anh không sai (như "Untrusted User", "Update Rails") thì giữ nguyên. Tai đã thấy chuyện này trong bản thử.

### 4. Hiệu ứng âm thanh

Vẫn tối đa 3 tiếng, cùng file và cùng mức như hiện nay (`sound.py`: `UNDER`, `SPACE`). Trước đây chúng gắn vào hình động và thẻ tư
liệu, giờ đặt vào **những chỗ chuyển cảnh lớn nhất** của video gốc. Không đặt trong câu đầu. *(Claude quyết)*

### 5. Lời kêu gọi không lặp

Ở Rails, câu chốt tiếng Việt dài 17 s trong khi tiếng Anh chỉ 5 s. `vs-translator` theo luật "brief thắng" (luật 2 trong
`claude/agents/vs-translator.md`) đã nối lời kêu gọi của brief vào câu cuối, dù câu 13–15 tiếng Anh đã nói đủ các ý đó.

Sửa thế này:
- Chỉ nối khi video tiếng Anh **không** nói ý đó ở bất kỳ câu nào.
- Thêm một lưới chặn máy móc trong `vshort check`: báo những câu mà lời Việt dài gấp nhiều lần câu Anh (đếm âm tiết so với số từ).
  Ngưỡng do builder chọn theo các video đã làm. *(Claude quyết)*

Lỗi này có từ trước, nhưng giờ nặng hơn vì sẽ thành một khung đứng yên rất lâu.

### 6. Bỏ hẳn

Xóa code, agent và test của các phần dưới đây. Lịch sử git vẫn giữ. *(Claude quyết, Tai đồng ý bỏ)*
- **Ẩn dụ:** `vs-an-du`, `RUN/an-du.md`, bước `an_du`. Ở điểm duyệt brief, Tai chỉ còn duyệt brief.
- **Hình động:** `vs-motion`, `motion.py`, `kit.py`, `shapes.py`, thư viện hình, `publish_shapes`, `examples/` của hình động, các
  bước `motion_design`/`motion_bind`/`motion`.
- **Nhịp hình:** `vs-nhip`, `shots.py`, `cards.py`, bước `shots`/`shots_agent`.
- **Thẻ tư liệu và ảnh nét chì:** phần `svg`/`photo` trong `visuals.py` và `vs-visuals.md`.
- **Máy quay trên ảnh tĩnh:** `camera.py` và phần máy quay, crossfade ảnh trong `render.py`, nếu không còn chỗ nào dùng.

**Giữ lại:**
- `vshort stills`, một khung mỗi câu, vì `vs-visuals` đọc chữ trên đó, ảnh bìa dùng `stills/1.png`, và `vs-reviewer` đối chiếu.
- Bước "Bình thường: …" trong brief. Đó là nội dung lời nói, không phải hình.

Trước khi xóa phải kiểm `kallaway-style`, `web.py`, `cover.py` và `publish.py` có còn dùng gì trong số đó không.

### 7. Soát cuối (`vs-reviewer`)

Danh sách kiểm mới:
- **Phụ đề, watermark, logo:** không còn chữ phụ đề Anh, ô vá hay vết cắt (mục 2). Không còn watermark. Không có đoạn logo Gemini.
- **Không giật, không gần trắng:**
  - không khung gần trắng (giữ kiểm 3 cũ);
  - ở chỗ nối hai câu và ở câu tua nhanh nhất thì không giật;
  - không giữ khung đứng yên quá 2 s.
- **Khớp lời:** hình của mỗi câu nói về đúng thứ lời đang nói. Chữ Anh trong hình mà trái với lời Việt thì giao `visuals` vá.
- **Âm thanh và phụ đề:** giữ các kiểm cũ về lặng dài, phụ đề khớp lời, âm lượng.

Bỏ các kiểm về hình động, nhịp hình và tư liệu vẽ lại. Vòng sửa chỉ còn hai agent sửa được: `translator` và `visuals`.

### 8. Những chỗ phải đổi theo

- `queue.STEPS`, `stages.STAGES`/`STEPS_OF`/`LABELS`/`WHAT_FIX`/`DEFAULT_SECONDS` và bàn điều khiển web
  (`web/src/Stages.tsx`…): danh sách chặng khớp quy trình mới, không còn chữ "hình động", "nhịp hình", "tư liệu thật".
- `cmd_status`, lời nhắn cuối (`auto._finish`): không còn dòng hình động, nhịp hình, hình mới. Thêm dòng các câu phải giữ khung
  lâu hay phải bỏ đuôi.
- `claude/skills/video-short/SKILL.md`: bỏ phần ẩn dụ ở bước duyệt brief, sửa mô tả skill.
- `TIMEOUT`, các prompt (`AN_DU`, `MOTION_*`, `NHIP`, phần `motion`/`shots` của `FIX_HOW`), `cli.py`: bỏ những gì không còn dùng.
- Ghi chú đầu `DESIGN.md`: trỏ sang tài liệu này.

### 9. Video cũ

Không tự dựng lại. Khi quy trình mới chạy ổn, Tai chọn video nào làm lại.

## Ràng buộc

- **Giữ nguyên các lựa chọn cũ của Tai:**
  - phụ đề kiểu NotebookLM (hộp xám, Patrick Hand, đứng trên `SUB_BOTTOM`), câu đầu là tiêu đề hiện trọn;
  - không logo góc, chỉ có outro ANM;
  - −14 LUFS, BT.709;
  - tốc độ giọng ~4,3 âm tiết/s, nghỉ 0,5 s;
  - không neon, không nhạc nền, tối đa 3 tiếng hiệu ứng.
- **Chuẩn chất lượng:** "ít nhất bằng `source.mp4`, bằng tiếng Việt". Mọi đoạn lời Anh đều có lời Việt.
- **Bước hình không làm dừng video vì lỗi agent.** Agent `vs-visuals` lỗi thì không vá, video vẫn đi tiếp, như hiện nay. Lỗi trong
  code dựng video thì dừng và báo như `render` bây giờ.
- **Thời gian trên pve2** (24 nhân, không GPU): bước xóa phụ đề và dựng video cộng lại không chậm hơn hiện nay quá ~10 phút một video.
  *(Claude quyết)*
- **Video đang dở trên pve2 lúc deploy:**
  - video đã qua duyệt bản dịch thì chạy tiếp theo quy trình mới, bỏ qua file hình động/nhịp hình còn sót;
  - `update-server.sh` vẫn đợi lúc không có video chạy.
- **Code thẳng trên `main`,** không nhánh, không worktree. Add file theo tên vì một phiên khác cũng commit lên `main`. Chạy
  `git pull --rebase` trước khi push.

## Không làm

- Dời phụ đề Việt tới chỗ phụ đề Anh cũ để che (đổi vị trí phụ đề là lựa chọn kiểu dáng của Tai).
- Vá chữ trên video đang chạy, dịch chữ tiếng Anh trong hình.
- Thêm máy quay, khoanh hay zoom dưới bất kỳ dạng nào.
- API ảnh Gemini trả phí, video AI.

## Để builder quyết

- Cách xóa phụ đề theo từng khung: vá theo cảnh thật (nhận ra mờ dần), LaMa trên khung mốc kèm bù chuyển động, hay cách khác. Miễn
  đạt mục 2 và ràng buộc thời gian. Nên đo trên 2–3 video trước khi chọn. Có sẵn model `models/big-lama.pt`.
- Dựng bằng đồ thị ffmpeg như bản thử, hay giữ đường ống PIL → ffmpeg của `render_video`.
- Nối hai câu bằng cắt thẳng hay mờ chồng ngắn. Bản thử cắt thẳng; video gốc vốn liền nên thường không thấy nhảy.
- Cách tìm chỗ chuyển cảnh lớn cho hiệu ứng âm thanh, và các ngưỡng.

## Kiểm cuối

Dựng lại Rails, BOSSAI và ClawHub trên pve2 từ dữ liệu đã có, không gọi NotebookLM lại. Ghi ra file riêng, **không** đè `final.mp4`
hay `xuat/`. Đặt cạnh `source.mp4` để Tai xem. Báo thêm:
- kết luận của `vs-reviewer`;
- thời gian dựng;
- chi phí Claude ước cho một video mới (hiện ~$10, riêng hình động, ẩn dụ và nhịp hình đã ~$5,3).
