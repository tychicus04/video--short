# Hình động giải thích cơ chế (thiết kế)

Bổ sung cho `DESIGN.md` và `2026-10-31-hinh-theo-loi-design.md`. Chỗ nào khác hai tài liệu đó thì theo tài liệu này.

## Vì sao

Video Coruna & DarkSword bản v5 (1/11) đã sạch, mượt, có tư liệu thật, nhưng Tai thấy nó "toàn ảnh minh họa và nói,
không giải thích cách hacker làm như nào". Tai muốn có hiệu ứng, nét vẽ di chuyển, chẳng hạn luồng đi của một gói tin
từ máy tính A đến máy tính B được vẽ ra, để người xem dễ hiểu.

Hai bản thử (vứt đi) trên câu 7–13 của Coruna, có giọng đọc và phụ đề thật:
- **v1:** nhiều chi tiết, nhiều thứ cùng chuyển động. Tai thấy "rối rắm quá".
- **v2:** 3 cảnh, mỗi cảnh một ý, 2–4 hình to, chỉ chấm đỏ di chuyển. Tai đồng ý.

Ba cảnh của v2 nằm trong `2026-11-01-hinh-dong-v2.png`, mã nằm ở `prototype/hinh-dong/` (chỉ để xem cách vẽ). Đây là
chuẩn nhìn của tính năng: hình mới phải gọn bằng hoặc hơn v2.

## Ý tưởng chính

Đoạn lời giải thích cơ chế tấn công không dùng ảnh tĩnh nữa mà dùng **hình động vẽ tay**. Các khối tự vẽ ra bằng nét
bút chì trên nền giấy. "Kẻ tấn công" là một chấm đỏ đi theo đúng lời đang đọc. Cái gì bị chiếm thì chuyển đỏ.

Agent không vẽ và không viết mã. Nó viết **mô tả cảnh** bằng một bộ hình có sẵn; chương trình dựng thành khung hình.

## Mục tiêu

1. **Lời phải có cơ chế.** Hình chạy theo lời, lời Việt dịch sát lời Anh, và lời Anh do NotebookLM viết từ brief. Vì
   vậy cách duy nhất để video giải thích cơ chế là brief yêu cầu điều đó:
   - `vs-researcher` thêm mục **"Cơ chế từng bước"** vào `brief.vi.md` và `brief.en.md`: 3–5 bước ở mức khái niệm,
     mỗi bước một câu (cái gì đi đâu, vượt qua lớp nào, lấy được gì). Không có tên kỹ thuật, không có mã.
   - Prompt của `vshort fetch` thêm yêu cầu: giải thích các bước này theo đúng thứ tự.
   - Tai duyệt brief như cũ. Lần duyệt đó cũng là điểm kiểm an toàn cho cách diễn đạt cơ chế.
   - **Chế độ tự động** (không dừng duyệt brief): bước tự soát brief, vốn so dữ kiện với `sources.md`, kiểm thêm mục
     "Cơ chế từng bước" theo luật an toàn ở dưới và sửa nếu lệch. Như vậy là đủ *(Claude quyết)*. Lý do: hình động
     chỉ vẽ điều lời đọc đã nói, nên không đi xa hơn lời đọc, mà lời đọc vốn đã ra video ở chế độ này. Ngoài ra còn
     luật nhãn do code kiểm (mục An toàn) và `vs-reviewer` soát cuối.
   - Bản dịch vẫn dịch sát. Không bẻ câu để có chỗ cho hình động. Nếu lời không có câu nào giải thích cơ chế thì
     video không có hình động.
2. **Chọn đoạn.** Hình động dùng cho một đoạn câu liền nhau trong `script.vi.json` mà lời nói giải thích cơ chế
   (ví dụ Coruna: câu 7–13).
   - Mỗi video tối đa một đoạn, và đoạn không dài quá một nửa video *(Claude quyết; Coruna: 28 trên 66 giây)*.
   - Không có đoạn nào cũng là kết quả hợp lệ.
   - Các câu ngoài đoạn giữ nguyên ảnh tĩnh, chỗ vá chữ và tư liệu thật như bây giờ.
3. **Cảnh.** Đoạn chia thành 1–4 cảnh, mỗi cảnh một ý và gồm trọn một hay vài câu liền nhau (đổi cảnh ở ranh giới
   câu). Luật gọn được **code kiểm, không chỉ dặn agent** *(Claude quyết)*:
   - Mỗi lúc trong một cảnh có tối đa 4 thứ nhìn thấy. Một hình kèm nhãn của nó tính là một.
   - Nhãn ngắn (tối đa khoảng 20 ký tự) và to: chữ không nhỏ hơn cỡ nhãn nhỏ nhất của v2 (khoảng 32 px trên khung
     720×1280).
   - Mọi thứ nằm trong x 40–680, y 60–1050: trên dải phụ đề (y 1094–1206) và ngoài góc watermark.
   - Chỉ hai loại thứ được di chuyển: kẻ tấn công, và thứ được chuyển đi (dữ liệu bị lấy, gói tin). Mọi thứ khác chỉ
     tự vẽ ra, đổi màu hoặc nứt.
4. **Bộ hình.** Đủ cho Coruna và cho ví dụ của Tai (gói tin đi từ A đến B):
   - Thiết bị: điện thoại, máy tính, máy chủ.
   - Hộp hoặc tầng có nhãn.
   - Khung nét đứt cho một lớp bảo vệ (sandbox, tường lửa).
   - Đường đi giữa hai thứ, thẳng hoặc cong, có thể có mũi tên.
   - Chấm: đỏ là kẻ tấn công; màu khác là dữ liệu bình thường như gói tin.
   - Nhãn chữ, người ("hacker").
   - Biểu tượng: chìa khóa (mật khẩu), tin nhắn, ví, tệp, ổ khóa, thư.
   - Vết nứt.

   Hành động: vẽ ra, chạy theo đường, dội lại, xuyên qua, chuyển đỏ, bay từ chỗ này sang chỗ kia, biến mất.

   Màu như v2: mực xám, đỏ cho bị tấn công, xanh lá cho hợp pháp hoặc an toàn, xanh lơ cho lớp bảo vệ. Nhãn viết tay
   bằng Patrick Hand.
5. **Mốc theo câu, không theo giây.** Mỗi hành động gắn với một câu (id), có thể kèm cụm phụ đề thứ mấy trong câu đó
   hoặc một vị trí trong câu (0–1). Mốc giây thật được tính lúc dựng, từ `timeline.json` và `phrase_times`, nên chạy
   lại TTS không làm hình lệch lời.

   Kiểm khi đọc mô tả cảnh:
   - mọi id có trong script và nằm trong đoạn;
   - các cảnh phủ đúng và đủ các câu của đoạn;
   - mỗi hành động diễn ra trong khoảng của câu nó gắn.
6. **Ghép.**
   - Câu trong đoạn hình động không có ảnh tĩnh và không có camera zoom hay trượt: chuyển động là chính nét vẽ.
   - Giữa ảnh tĩnh và hình động, và giữa hai cảnh, nối bằng mờ chồng như hiện nay (XF).
   - Phụ đề không đổi.
7. **Không chồng lên tư liệu.** Bước hình động chạy **trước** `vs-visuals`, nên `vs-visuals` biết câu nào đã có hình
   động *(Claude quyết)*.
   - Câu thuộc đoạn hình động không được có `svg` hay `photo`: `vshort visuals` từ chối mục đó và báo lỗi rõ, không
     lặng lẽ bỏ qua.
   - `patch` thì vẫn được và vẫn làm như cũ, vì ảnh tĩnh của các câu đó là bản dự phòng (mục 8). Ví dụ Coruna: thanh
     địa chỉ "untrusted-site.com" ở câu 8–13 vẫn phải vá, kể cả khi các câu đó đang dùng hình động.
8. **Lỗi không chặn video.** Mô tả cảnh được kiểm ngay ở bước hình động. Nếu sau khi agent đã sửa mà vẫn không qua,
   bước đó bỏ đoạn hình động: các câu quay về ảnh tĩnh như hiện nay, video vẫn ra, và báo cáo cuối ghi lý do *(Claude
   quyết, giống cách dự phòng của `vs-visuals`)*.
9. **Soát cuối.** `vs-reviewer` kiểm thêm:
   - hình động khớp lời: chấm đỏ làm đúng điều câu đang nói, không đi trước, không đi sau;
   - mỗi cảnh gọn, nhãn đọc được;
   - không có gì mang tính hướng dẫn tấn công;
   - nét vẽ và chuyển cảnh mượt.

   Báo cáo cuối liệt kê đoạn hình động: các câu, các cảnh, ý của mỗi cảnh.

## Ví dụ

**Coruna, câu 7–13 (như bản thử v2):**

| Cảnh | Câu | Hình |
|---|---|---|
| 1 | 7 "Bạn mở một trang web hợp pháp đã bị nhiễm ngầm." · 8 "…mã độc chạy âm thầm trong Safari." · 9 "…zero-click, bạn không làm gì thêm." | Điện thoại to, thanh địa chỉ `tin-tuc.example`, nhãn xanh lá "trang web hợp pháp" (7). Chấm đỏ hiện trong trang, nhãn "mã độc" (8). Chấm đỏ nhấp nháy, không có gì khác (9). |
| 2 | 10 sandbox · 11 xâu chuỗi lỗ hổng để thoát sandbox · 12 leo thang tới kernel | Ba tầng "Safari", "Hệ thống", "Lõi (kernel)"; khung nét đứt xanh lơ "sandbox" quanh Safari. Chấm đỏ dội vào tường (10). Tường nứt, chấm xuống "Hệ thống", tầng đó chuyển đỏ (11). Chấm xuống "Lõi", chuyển đỏ, nhãn "đã bị chiếm" (12). |
| 3 | 13 đánh cắp mật khẩu, tin nhắn, ví | Điện thoại viền đỏ, hộp "hacker". Mật khẩu, tin nhắn, ví tiền lần lượt bay sang, mỗi thứ đúng lúc lời nhắc tới nó. |

**Gói tin đi từ máy A đến máy B (ví dụ của Tai, chủ đề giả định):**

| Cảnh | Hình |
|---|---|
| 1 | Máy tính "A" bên trái, máy tính "B" bên phải, một đường đi giữa hai máy. Một chấm xanh (gói tin) chạy từ A sang B. |
| 2 | Cùng hai máy. Một người "kẻ nghe lén" xuất hiện giữa đường. Gói tin đi qua thì một chấm đỏ tách ra bay về phía kẻ đó. |

Khi dựng xong, cả hai ví dụ được dựng từ mô tả cảnh và xem bằng mắt như phần nghiệm thu.

## An toàn

Luật "không hướng dẫn tấn công" của hai tài liệu trước áp dụng cho hình động:

- Chỉ ở mức khái niệm: tầng, ranh giới, dữ liệu, ai lấy được gì.
- Nhãn chỉ dùng từ có trong lời đọc của đoạn đó, danh từ thường nằm trong một danh sách cố định của bộ hình (điện
  thoại, máy chủ, dữ liệu, hệ thống, hacker…), hoặc tên `.example`. Code kiểm luật này từng chữ, nên tên kỹ thuật
  hay tên công cụ không lọt được vào nhãn *(Claude quyết; danh sách cụ thể do người dựng lập)*.
- Không có trong hình:
  - tên lỗ hổng hay mã CVE, tên exploit, tên hàm hay tiến trình;
  - lệnh, mã;
  - địa chỉ web thật (dùng tên `.example`);
  - các bước đủ chi tiết để làm lại.
- Hình động không nói điều lời không nói, và không thêm bước hay tầng mang nội dung mới.
  - Được phép một tầng trung gian chung chung khi lời nói có nhiều bước, ví dụ tầng "Hệ thống" giữa Safari và lõi
    khi lời nói "leo thang đặc quyền từng bước".
  - *(Claude quyết; Tai đã đồng ý bản v2 có tầng này.)*

## Không làm

- Vẽ hay làm video bằng AI (Gemini image, Veo).
- Nhạc nền, hiệu ứng âm thanh.
- Hình động cho câu không giải thích cơ chế: tiêu đề, tin tức, ai phát hiện, lời kêu gọi.
- Agent viết mã vẽ riêng cho từng video.
- Camera zoom hay trượt trên hình động.
- Giữ animation gốc của NotebookLM.

## Thất bại dù vẫn chạy được

- Rối như bản thử v1: nhiều thứ cùng lúc, chữ nhỏ, nhiều thứ cùng chuyển động.
- Hình lệch lời, ví dụ tường đã nứt khi lời còn đang nói sandbox bảo vệ thế nào.
- Hình nói điều lời không nói, hoặc sai so với brief.
- Hình mang tính hướng dẫn tấn công.
- Nét vẽ giật, nhảy bậc, hoặc lệch hẳn phong cách giấy và bút chì của phần còn lại.
- Hình chui vào dải phụ đề, hoặc phụ đề che mất chỗ đang diễn ra.

## Ràng buộc

- Server `ubuntu-pve2`: chỉ CPU, không màn hình. Bản thử v2 dựng 126 ms mỗi khung (khoảng 1 phút 40 giây cho 28 giây
  hình), chấp nhận được.
- Có sẵn pillow, numpy, imageio-ffmpeg (libass, libx264), cairosvg. Font: Patrick Hand, Be Vietnam Pro.
- Khung 720×1280, 30 fps. Phụ đề và mờ chồng giữ nguyên như hiện nay.
- Làm thẳng trên nhánh `main` của `~/video-pipeline`.

## Phần đã quyết

Tai quyết:
- Video cần hình động giải thích cách tấn công, ở mức khái niệm (ví dụ gói tin đi từ A đến B).
- Kiểu v2: gọn, mỗi cảnh một ý, ít hình to, chỉ chấm đỏ di chuyển; kiểu v1 thì rối.
- Chỉ dùng ở đoạn giải thích cơ chế; các câu khác giữ ảnh tĩnh và tư liệu (Tai xác nhận bản tóm tắt).
- Agent mô tả cảnh bằng bộ hình có sẵn, chương trình dựng (Tai xác nhận bản tóm tắt).

Claude đề xuất (Tai giao "bạn thấy hợp lí là được"):
- Mục "Cơ chế từng bước" trong brief; không có cơ chế thì không có hình động.
- Tối đa một đoạn mỗi video, không dài quá nửa video.
- Mốc theo câu và cụm phụ đề, không theo giây.
- Luật gọn do code kiểm: tối đa 4 thứ mỗi lúc, nhãn to và ngắn, vùng an toàn, chỉ kẻ tấn công và dữ liệu di chuyển.
- Bước hình động chạy trước `vs-visuals`. `vshort visuals` từ chối tư liệu trên câu có hình động, nhưng vẫn vá chữ
  cho ảnh tĩnh dự phòng.
- Không camera trên hình động.
- Lỗi thì quay về ảnh tĩnh, video vẫn ra.
- Chế độ tự động: phần tự soát brief kiểm thêm mục cơ chế. Nhãn bị code giới hạn trong từ của lời đọc và danh sách
  danh từ thường.
- Cho phép tầng trung gian chung chung khi lời nói "từng bước".

## Để người dựng tự quyết

- Định dạng file mô tả cảnh, tên lệnh và tên agent.
- Agent nào viết cảnh: agent mới, hay thêm việc cho `vs-visuals` miễn là phần chọn và kiểm hình động xong trước phần
  tư liệu.
- Agent cho tọa độ, hay chương trình tự xếp chỗ.
- Hình dạng cụ thể của từng món trong bộ hình, tốc độ vẽ và chạy.
- Cách vẽ nét tay. Bản thử dùng: vẽ ở 2× rồi thu nhỏ, nét lượn sóng nhẹ, nét hiện dần theo độ dài, chữ hiện từ trái
  sang phải như đang viết.
- Dựng khung hình động lúc `render`, hay dựng trước ra đĩa.
- Cách đếm "thứ nhìn thấy" cho các trường hợp lửng lơ: vết nứt, khung nét đứt, nhãn đứng riêng.
