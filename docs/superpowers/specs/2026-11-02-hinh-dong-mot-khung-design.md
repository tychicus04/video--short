# Hình động một khung, dựng từ brief — thiết kế (02/11/2026)

## Vì sao

Video `linux-tcp-cve-2026-98432` (02/11) có đoạn hình động câu 4–8 chia thành 3 cảnh. Mỗi lần sang cảnh mới là một tờ giấy
trắng: máy chủ nhận gói tin → bộ nhớ và hai luồng → bước chạy lệnh root. Tai nhận xét: hình động **cần mượt và đi từ A tới Z
để giải thích trong một khung hình**. Tai cũng muốn **mỗi video, trước khi gen, phải code trước phần hình động và bộ nhận
diện hình ảnh**.

Hiện nay hình động chỉ được nghĩ ra sau khi bản dịch đã được duyệt (`vs-motion` trong `_build`). Lúc đó agent phải chọn đoạn,
chia cảnh và vẽ cùng một lượt, và chỉ được dùng các hình có sẵn trong kit (`phone`, `computer`, `server`, `box`, `wall`,
`person`, `icon`, `dot`, `text`, `crack`, `path`). Một chủ đề như lỗi nhân Linux (nhân, bộ nhớ, luồng, đường điều khiển,
root) phải ghép tạm từ `box` và `dot`.

## Tai đã quyết

- Đoạn giải thích cơ chế là **một khung hình duy nhất**. Hình vẽ dần theo lời đọc, những gì đã vẽ thì **giữ lại**, nên tới câu cuối
  của đoạn người xem thấy cả chuỗi A→Z. Không cắt sang tờ giấy mới giữa đoạn. (Tai đồng ý bản mô tả: gói tin đỏ đi từ kẻ tấn
  công vào máy chủ, trong máy chủ lộ ra bộ nhớ, hai luồng chạm vào nó và nứt, kẻ tấn công dò tới đường điều khiển và ghi đè,
  "root" bật lên.)
- "Mượt": chuyển động có gia tốc mềm, nét hiện dần, không bật ra hay cắt cảnh.
- **Bộ hình riêng cho từng video được làm ngay sau khi duyệt brief, trước khi NotebookLM gen.** Từ mục "Cơ chế từng bước" của
  brief, agent liệt kê các nhân vật và đồ vật cần vẽ. Hình nào kit chưa có thì vẽ thêm theo đúng phong cách chung.
- **Kịch bản hình động cũng viết từ brief**, theo các bước cơ chế. Bước này chạy song song trong lúc NotebookLM đang gen.
  Sau khi duyệt bản dịch, hình động chỉ còn việc khớp thời gian vào câu.
- **Không thêm điểm dừng.** Vẫn chỉ hai lần duyệt (brief, bản dịch). Bản xem trước hình động tự chạy; reviewer soát ở video cuối.

## Mục tiêu

- Đoạn cơ chế là một cảnh liền mạch: không còn mờ chồng giữa các cảnh trong đoạn, cuối đoạn là một sơ đồ đọc được.
- Chủ đề mới có hình đúng chủ đề (ví dụ "nhân", "bộ nhớ", "root") mà vẫn cùng một phong cách với các video trước.
- Hình mỗi chủ đề được làm một lần rồi dùng lại: thư viện hình lớn dần qua các video.
- Thời gian chạy một video không tăng, vì phần hình chạy trong lúc chờ NotebookLM.
- Chi phí Claude không vượt ngân sách $5/video vì việc này. Hiện `vs-motion` tốn khoảng $1,50/video; tổng của hai lượt mới
  không nên vượt mức đó quá nhiều.

## Không làm

- Không dùng AI tạo ảnh hay video (DESIGN.md). Hình vẫn là nét vẽ tay do chương trình dựng.
- Không cho agent viết mã Python chạy trong pipeline. Hình mới là **dữ liệu nét vẽ**, không phải mã.
- Không đổi phần ảnh tĩnh, tư liệu, vá chữ, phụ đề, giọng đọc.
- Không đổi màu, font, nền giấy hay logo đang có. "Bộ nhận diện" là các thứ này cộng với thư viện hình.

## Thất bại dù vẫn chạy được (anti-goal)

- **Khung rối như bản v1** (spec 01/11): quá nhiều hình nhỏ, nhãn chen nhau. Giữ hết A→Z không được biến thành một sơ đồ dày đặc.
- Hình nói điều lời không nói, hoặc vẽ bước mà NotebookLM đã bỏ khỏi lời đọc.
- Hình mới lệch phong cách (nét thẳng máy móc, màu lạ), nhìn như dán từ chỗ khác.
- Chấm đỏ đi trước lời: phá tường khi lời còn đang nói tường bảo vệ thế nào.
- Hình lộ chi tiết kỹ thuật đủ để làm lại tấn công (luật an toàn hiện có vẫn giữ nguyên).

## Thiết kế

### 1. Thư viện hình (bộ nhận diện)

- Hình trong kit hiện có giữ nguyên. Thêm một thư viện hình dạng dữ liệu, ví dụ `assets/shapes/<tên>.json`: mỗi hình là một
  danh sách nét (đường gấp khúc hoặc đường cong) trong một ô chuẩn, kèm tên tiếng Việt và cỡ gợi ý.
- Kit vẽ các nét đó bằng chính cách vẽ tay hiện có (`_wobble`, `_stroke`, cùng độ dày, cùng màu `ink/green/blue/red`, cùng cách
  hiện dần trong `DRAW`). Nhờ vậy hình mới tự khớp phong cách, agent không phải tự giữ.
- Hình mới làm cho một video được lưu vào thư viện chung, video sau dùng lại. *(Claude quyết: lưu chung chứ không để riêng trong
  thư mục run, vì Tai muốn hình nhất quán qua các video.)*
- **Đồng bộ (Tai quyết):** run xong, pipeline tự commit các file hình mới (chỉ thư mục thư viện hình, không đụng file khác) vào git
  rồi push, nên Mac chỉ cần `git pull`. Hai run cùng thêm hình một lúc thì commit sau phải tự rebase. Push lỗi không làm hỏng
  video: báo trong lời nhắn cuối.
- **Chỉ thêm, không sửa** *(Claude quyết)*: hình đã có trong thư viện thì không được tự động sửa, kể cả trong vòng sửa lỗi. Hình bị
  chê lệch phong cách thì vẽ bản mới với tên mới. Mỗi run giữ một bản sao các hình nó đã dùng (trong thư mục run), để dựng lại
  video sau này vẫn ra đúng như cũ.
- Code kiểm hình mới: nét nằm trong ô, số nét có giới hạn (đơn giản, nhìn rõ ở cỡ nhỏ), không có chữ trong hình (chữ chỉ ở nhãn).
- Agent xem hình mới trên một tờ xem trước (giống `motion/sheet.png`) trước khi dùng.

### 2. Kịch bản một khung, viết từ brief

- Sau khi Tai duyệt brief, một lượt agent (`vs-motion`, giữ Sonnet) đọc mục "Cơ chế từng bước" và "Lưu ý độ chính xác" và viết
  kịch bản theo **nhịp**: mỗi bước cơ chế là một nhịp, gồm những gì vẽ thêm và những gì di chuyển. Chưa có câu Việt nào, nên
  kịch bản chỉ nói tới nhịp, không nói tới câu.
- Cả đoạn là **một cảnh**: không còn `scenes` nhiều cảnh trong đoạn cơ chế.
- Chống rối (các con số là Claude đặt, builder chỉnh theo thử nghiệm): tổng cộng tối đa khoảng 7 thứ có nhãn trên khung. Khi
  nhịp sau bắt đầu, các thứ của nhịp trước **lùi lại** (nét nhạt về mực xám, nhãn nhỏ đi) để mắt theo chỗ đang được nói, nhưng
  vẫn còn trên khung. Cuối đoạn là một sơ đồ: đường đi của chấm đỏ nối các bước lại với nhau.
- "Mượt": chấm đỏ là một vật **đi xuyên suốt** đoạn từ nhịp đầu tới nhịp cuối, không biến đi rồi hiện lại ở chỗ khác khi không
  có lý do. Mọi di chuyển dùng gia tốc mềm (`ease` hiện có).
- Bố cục theo một hướng đọc (trên → dưới hoặc trái → phải) trong vùng an toàn. Vùng an toàn phải tránh logo mới ở góc trên phải
  (x 481–704, y 24–80); hiện `kit.SAFE` bắt đầu từ y 60 nên chồng lên logo.
- Luật an toàn và luật nhãn giữ nguyên. Nhãn lấy từ chữ trong brief cộng danh sách `COMMON`, rồi kiểm lại theo lời Việt ở bước
  khớp thời gian (mục 3).
- Agent chạy `vshort motion` ở chế độ thời gian ước lượng và xem tờ xem trước. Bước này chạy song song với `fetch`, giống cách
  `tts` đang chạy song song trong `_build`.

### 3. Khớp thời gian sau khi duyệt bản dịch

- Khi đã có `script.vi.json`, mỗi nhịp được gắn vào một mốc lời đọc (câu và cụm phụ đề, theo cách viết `when` hiện có), theo đúng
  thứ tự nhịp.
- Có nhịp nào lời không nói tới (NotebookLM gộp hay bỏ bước) thì bỏ nhịp đó. Thứ nào nhịp sau cần thì hiện cùng nhịp sau.
- Lời đọc các bước theo thứ tự khác brief thì bỏ các nhịp lệch thứ tự để phần còn lại vẫn đúng thứ tự brief (bố cục khung đã
  xếp theo brief). Còn dưới 2 nhịp thì dùng hướng dự phòng ảnh tĩnh. *(Claude quyết.)*
- Có nhãn nào không qua kiểm chữ theo lời Việt thì đổi sang chữ có trong lời.
- Việc này là một lượt agent ngắn và rẻ, chỉ ghi phần gắn mốc. *(Claude quyết: giao cho agent vì việc ghép nghĩa "nhịp này ứng
  với cụm nào" code khó làm chắc. Builder chọn model; nếu dùng Haiku thì ghi lý do vào CLAUDE.md, theo bảng chọn model của Tai.)*
- Không ghép được (lời không có đoạn cơ chế, hoặc vẫn trượt kiểm sau khi sửa) → hướng dự phòng hiện có `_no_motion`: video dùng
  ảnh tĩnh cho đoạn đó.

### 4. Ghép và soát

- Render vẽ đoạn cơ chế như một cảnh. Mờ chồng chỉ còn ở hai đầu đoạn, chỗ chuyển giữa ảnh tĩnh và hình động.
- Reviewer (`vs-reviewer.md`) soát thêm: đoạn cơ chế là một khung liền mạch, cuối đoạn đọc được như một sơ đồ, không rối, hình mới
  đúng phong cách.
- Vòng sửa (`FIX_HOW["motion"]`) sửa kịch bản hoặc phần gắn mốc như hiện nay, hoặc thêm hình mới, nhưng không sửa hình đã có
  trong thư viện.

## Ví dụ nghiệm thu

Dựng lại đoạn câu 4–8 của `~/notebooklm-videos/linux-tcp-cve-2026-98432` theo cách mới, rồi đặt cạnh bản 3 cảnh hiện tại cho Tai
xem. Đoạn đạt khi:

- không có cắt cảnh trong đoạn;
- khung cuối thấy đủ năm bước: gói tin vào máy chủ → bộ nhớ nứt khi hai luồng chạm → dò và ghi đè đường điều khiển → mã chạy →
  root;
- ít nhất một hình mới trong thư viện (ví dụ "nhân" hoặc "bộ nhớ") cùng phong cách với hình cũ.

Hai ví dụ chuẩn trong `examples/motion/` (coruna, goi-tin) phải được chuyển sang dạng mới và vẫn dựng được.

## Để builder quyết

- Định dạng file kịch bản theo nhịp, cách viết dữ liệu nét vẽ, tên file và tên lệnh.
- Giữ `motion.json` cũ chạy song song, hay chuyển hẳn sang dạng mới và chuyển luôn các ví dụ.
- Con số cụ thể: số thứ tối đa, mức "lùi lại", số nét tối đa mỗi hình.
- Có tách hai lượt agent (dựng hình, gắn mốc) thành hai agent hay dùng một agent với hai lời dặn.
