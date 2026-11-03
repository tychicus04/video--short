# Hình động kể bằng ẩn dụ đời thường — thiết kế (03/11/2026)

Nối tiếp `2026-11-02-hinh-dong-mot-khung-design.md` (một khung A→Z, dựng từ brief, thư viện hình). Phần nào tài liệu này không
nhắc tới thì giữ như tài liệu đó.

## Vì sao

Sau hai video gần nhất (`linux-tcp-cve-2026-98432`, `lxd-microcloud-cvss10`), Tai thấy hình động **còn nghèo**: ít chuyển động,
nét vẽ nhiều khi chưa chuẩn, và đoạn giải thích cơ chế **chưa tường minh, chưa dễ hiểu**. Cái Tai muốn là kiểu video giải thích
"hacker xâm nhập hệ thống như thế nào" bằng **ngôn ngữ đa số đại chúng hiểu được**.

Nhìn khung cuối của video LXD (`2026-11-03-hinh-dong-lxd-cu.png`, chép từ `motion/sheet.png` của run): khung thưa, đồ vật nhỏ, nhãn toàn
chữ kỹ thuật ("chuỗi chứng chỉ", "danh sách tin cậy"), đường đi của chấm đỏ là một đường dài men mép phải. Ý cốt lõi ("gắn chứng
chỉ người khác vào sau chứng chỉ mình, máy chủ không bắt chứng minh khóa") không hiện ra trên hình. Chỉ chấm đỏ và icon di
chuyển; mọi thứ khác chỉ tự vẽ ra.

Tai xem bản phác web cho vụ LXD (`2026-11-03-hinh-dong-an-du-phac.html`, mở thẳng trong trình duyệt; bốn khung chụp ở
`2026-11-03-hinh-dong-an-du-phac.png`) và chọn hướng này: "có
vẻ là tường tận hơn". Trong bản phác: thẻ nhân viên = chứng chỉ công khai, chìa = khóa riêng, máy quét + bảo vệ + bảng tên =
máy chủ và danh sách tin cậy, tòa nhà / phòng / tầng nền = cụm / máy ảo / máy chủ host. Kỹ sư cắm chìa của mình thì máy quét báo
"đúng chủ thẻ"; kẻ gian photo thẻ kỹ sư, kẹp sau thẻ mình, cắm chìa của chính hắn; máy quét chỉ xác nhận thẻ đầu nhưng bảo vệ dò
cả hai thẻ với bảng, thấy thẻ kỹ sư thì mở barie; các phòng lần lượt chuyển đỏ. Máy quay phóng vào từng bước rồi lùi ra cuối.

Đoạn ảnh tĩnh phía sau ("slide qua lại", tức camera phóng/lia luân phiên trong `render.py`) Tai cũng thấy nhàm, nhưng đó là **việc
riêng, làm sau** (xem "Không làm").

## Tai đã quyết

- **Kể bằng ẩn dụ đời thường** thay cho sơ đồ kỹ thuật: mỗi video chọn một cảnh ai cũng biết; mỗi khái niệm kỹ thuật thành một
  đồ vật trong cảnh. Chữ kỹ thuật chỉ là phụ.
- **Vẫn một khung A→Z, không cắt cảnh** (quyết định ngày 02/11 giữ nguyên). Cái mới là **máy quay**: phóng vào chỗ lời đang nói,
  theo nhân vật, cuối đoạn lùi ra cho thấy cả chuỗi.
- **Nhiều chuyển động hơn**: nhân vật đi lại; đồ vật được đưa, kẹp, cắm, mở; thứ bị chiếm chuyển đỏ; ✓/✗ và mũi tên cho thấy máy
  "so" cái gì với cái gì.
- **Phủ cả câu "bình thường thì…"**: đoạn hình động bắt đầu từ câu kể cách làm đúng (câu 3 ở vụ LXD), không chỉ từ câu kẻ gian ra
  tay. Có "trước" thì mới thấy chỗ hỏng.
- **Giữ luật chính xác và an toàn**: hình chạy theo lời, không thêm điều lời không nói; ẩn dụ không được làm sai điều brief cảnh
  báo (ví dụ không thành "ai cũng vào được").
- **Không cài nguyên hai bộ skill Tai gửi** (`Barty-Bart/motion-graphics`, `iart-ai/motion-skills`): chúng dựng bằng web/Remotion
  cho video sản phẩm, không khớp pipeline. Chỉ lấy mẹo nghề (mục "Mẹo nghề lấy từ hai bộ skill").
- **Giữ bộ vẽ Python (`vshort/kit.py`) và mở rộng**, không chuyển sang dựng bằng web/Chromium.
- **Sửa nét vẽ bằng một bộ "đạo cụ đời thường" vẽ sẵn, Tai duyệt một lần**; agent chủ yếu chọn và xếp, không tự vẽ mỗi video.
- **Video thử là vụ LXD**: dựng lại đoạn hình động của `lxd-microcloud-cvss10` theo cách mới để Tai so với bản cũ.
- **Ẩn dụ không gửi cho NotebookLM**: nó chỉ nằm ở phía tiếng Việt cho Tai duyệt và cho hình động; `brief.en.md` không có nó, lời đọc
  vẫn là chữ kỹ thuật như hiện nay.
- **Brief có bước 0 "Bình thường: …"** ở đầu mục "Cơ chế từng bước" (cả bản Việt lẫn bản Anh), để NotebookLM luôn nói cảnh "trước".
- **Ẩn dụ do một lượt Sonnet ngắn viết**, sau `vs-researcher` (vẫn Haiku) và trước điểm duyệt brief, chỉ đọc brief; thêm khoảng vài
  chục cent mỗi video.
- **Lấy luật của skill `kallaway-style`** (Tai cài 03/11/2026, chọn "lấy luật cho hình động", giữ nét chì trên giấy, không đổi sang
  neon): máy quay **trôi chậm** khi giữ một nhịp (phóng thêm khoảng 3 %, kiểu Ken Burns 3–6 %); **hình đi trước lời 0,2 s** (mỗi nhịp
  sau nhịp mở đoạn bắt đầu sớm 0,2 s so với chữ của nó); luôn có gì đó đổi trên hình (luật quãng chết ở mục 3); bảng "động từ →
  chuyển động" và màu mang nghĩa (đỏ = tấn công/sai, xanh lá = đúng/an toàn, xám = đã qua) trong lời dặn `vs-motion`. Trôi chậm không
  tính là "chuyển động" trong luật quãng chết. *(Claude quyết: nếu tính, luật quãng chết thành vô nghĩa.)* "Hành động đi trước lời"
  trong mục anti-goal là làm một **bước** trước khi lời nói tới bước đó, không phải 0,2 s này.

## Mục tiêu

- Người không làm IT xem trên điện thoại hiểu được kẻ tấn công vào bằng cách nào, và **chỗ hỏng nằm ở đâu** (bước "đáng lẽ phải
  làm X, nhưng lại làm Y" phải hiện ra thành một hành động nhìn thấy được, như bảo vệ dò cả xấp thẻ thay vì chỉ thẻ đã được xác
  nhận chủ).
- Người trong nghề vẫn nối được ẩn dụ với sự thật: lần đầu một đồ vật ẩn dụ xuất hiện, nhãn của nó nói nó là gì ("thẻ = chứng chỉ
  công khai").
- Đoạn cơ chế lúc nào cũng có gì đó đang chuyển động; không có quãng đứng im.
- Đồ vật nhìn ra là gì mà không cần đọc nhãn, cùng một phong cách nét chì qua mọi video.
- Chi phí Claude vẫn trong ngân sách ~$5/video. `vs-motion` lượt vừa rồi tốn $2,79; chọn-và-xếp từ bộ đạo cụ không được đắt hơn
  thế, nên rẻ hơn.

## Không làm

- Đoạn ảnh tĩnh nhàm (camera luân phiên trong `render.py`): việc riêng, thiết kế sau khi việc này xong.
- Không dùng AI tạo ảnh hay video (DESIGN.md). Không dựng bằng HTML/Chromium/Remotion.
- Không cho agent viết mã chạy trong pipeline: cảnh vẫn là **mô tả JSON**, đạo cụ là **dữ liệu nét**.
- Không đổi giọng đọc, phụ đề, bản dịch, tư liệu, vá chữ; không đổi màu, font (Patrick Hand), nền giấy, logo.
- Không thêm điểm dừng duyệt nào ngoài hai điểm hiện có (brief, bản dịch).

## Thất bại dù vẫn chạy được (anti-goal)

- **Trông trẻ con** so với một kênh tin bảo mật: nhân vật hoạt hình nhí nhảnh, mặt cười, màu mè. Nét vẫn là nét chì gọn của kit.
- **Ẩn dụ làm hiểu sai lỗ hổng**: ví dụ vẽ như "ai đi ngang cũng vào được" khi brief nói phải có truy cập mạng và thẻ của một
  client đã được tin; hay ẩn dụ gợi ra một bước lời không nói.
- Khung rối (bản v1 ngày 01/11): đông người, đông đồ, nhãn chen nhau; khung cuối lùi ra không đọc nổi ở cỡ điện thoại.
- Máy quay làm chóng mặt: phóng/lia liên tục không theo lời, hay phóng sâu tới mức nhòe nét.
- Hành động đi trước lời: barie mở khi lời còn đang nói bảo vệ kiểm thẻ.
- Lộ chi tiết đủ để làm lại tấn công (luật an toàn hiện có giữ nguyên).

## Thiết kế

### 1. Ẩn dụ chọn từ brief

- **Bước 0 trong brief (Tai quyết)**: `vs-researcher` mở mục "Cơ chế từng bước" bằng một câu "Bình thường: …" (cách hệ thống làm
  đúng, ví dụ "bình thường client phải chứng minh mình giữ khóa riêng"), ở cả `brief.vi.md` và `brief.en.md`. Bước 0 không tính vào
  luật "3–5 bước" hiện có. `BRIEF_CHECK` trong `vshort/auto.py` kiểm có bước 0 khi mục cơ chế không ghi "Không có".
- **Ẩn dụ do một lượt Sonnet ngắn viết (Tai quyết)**, chạy ngay sau `vs-researcher`, trước điểm dừng duyệt brief. Lượt này chỉ đọc
  brief tiếng Việt và danh sách đạo cụ trong thư viện, rồi viết: một câu kể cảnh ("tòa nhà có bảo vệ kiểm thẻ…") và bảng đổi
  `khái niệm kỹ thuật → đồ vật`, mỗi bước cơ chế (kể cả bước 0) ứng với một hành động trong cảnh. Ẩn dụ phải khớp mục "Lưu ý độ
  chính xác" (ví dụ giữ điều kiện "phải có thẻ của người đã được tin") và vẽ được bằng bộ đạo cụ. *(Claude quyết: một agent nhỏ
  riêng, ví dụ `vs-an-du` ghim Sonnet, lời dặn ngắn; không gộp vào `vs-motion`, vì lời dặn của `vs-motion` dài và sẽ dài thêm, mà mỗi
  lượt `vs-motion` đã tốn khoảng $2. Chi phí mục tiêu dưới $0,5; đo ở lần thử.)*
- **Không gửi NotebookLM (Tai quyết)**: ẩn dụ không vào `brief.en.md`. *(Claude quyết: ghi ra file riêng trong thư mục run, ví dụ
  `RUN/an-du.md`, không ghi vào `brief.vi.md`: sửa `brief.vi.md` sau bản Anh sẽ làm `vshort approve … brief` từ chối vì bản Anh "cũ
  hơn", như đã xảy ra ở run LXD.)* Ở điểm dừng duyệt brief (mã 20), lời nhắn của `vshort wait` và skill `/video-short` đưa Tai cả brief
  lẫn ẩn dụ; Tai sửa ẩn dụ thì sửa file đó; `vshort approve … brief` duyệt cả hai.
- Chế độ `--auto` bỏ điểm dừng brief, nên không ai duyệt ẩn dụ trước: `vs-reviewer` soát nó ở video cuối (mục 6).
- `vs-motion` dựng cảnh theo đúng bảng đổi đã duyệt; không tự đổi ẩn dụ.
- Brief ghi "Không có" ở mục cơ chế thì không có bước 0, không có ẩn dụ, như hiện nay.

### 2. Bộ đạo cụ đời thường

- Một bộ hình vẽ sẵn, chất lượng cao, cùng phong cách nét chì của kit, nằm trong thư viện `assets/shapes/` (định dạng nét hiện có
  hoặc mở rộng của nó). Làm một lần trong lúc dựng việc này; Tai duyệt trên một tờ xem trước (giống `shapes/sheet.png`).
- Bộ đầu tiên đủ cho vụ LXD và các ẩn dụ hay gặp trong tin bảo mật: **người** (đứng, bước đi, đưa tay; vai được nhận ra bằng phụ
  kiện: bảo vệ đội mũ, kẻ gian mũ trùm, nhân viên đeo thẻ), thẻ nhân viên, chìa, ổ khóa, cửa (đóng/mở), barie (đóng/mở), máy quét,
  bảng danh sách, tòa nhà, phòng, tầng/cầu thang (leo thang quyền), két sắt, phong bì/thư, hòm thư, kiện hàng, xe giao hàng,
  camera an ninh, hàng rào. Máy tính, điện thoại, máy chủ, tường, icon hiện có giữ nguyên. *(Claude chọn danh sách; builder thêm
  bớt theo vài chủ đề bảo mật điển hình: chiếm quyền đăng nhập, lừa đảo qua thư, chuỗi cung ứng, nghe lén, thoát sandbox, leo thang
  quyền.)*
- Đồ vật nào có trạng thái (cửa, barie, két) thì có phần chuyển động được (cánh cửa, tay barie, cửa két) để cảnh "mở" bằng chuyển
  động thật, không phải đổi hình.
- Nhân vật: người là một thứ **di chuyển được** (đi có nhún nhẹ theo bước), có thể **cầm/đeo** một đồ vật (đồ vật đi theo người).
- Không mặt cười, không biểu cảm hoạt hình; nét gọn như hình kit hiện có.

### 3. Cảnh chuyển động hơn

Mở rộng `motion.json` và kit (tên trường và cú pháp để builder chọn):

- **Thứ di chuyển được**: ngoài `dot` và `icon`, người và các đạo cụ nhỏ (thẻ, chìa, thư, kiện hàng…) cũng di chuyển.
- **Hành động mới**: đưa/gắn một đồ vật vào người hay vào đồ vật khác (từ đó nó đi theo); cắm/đặt một đồ vào chỗ (chìa vào máy
  quét); mở/đóng phần chuyển động của đạo cụ; dấu ✓ (xanh) và ✗ (đỏ) hiện ở một chỗ; mũi tên so sánh vẽ ra từ thứ này tới thứ kia
  (máy "so" thẻ với bảng). `red`, `pulse`, `bounce`, `hide`, `move` theo `path` giữ nguyên.
- **"Actor" là kẻ tấn công**, không nhất thiết là chấm: có thể là người mũ trùm đỏ đi suốt đoạn, hoặc chấm đỏ như cũ khi ẩn dụ không
  có người (gói tin, mã độc). Luật cũ "actor không biến mất, không lùi" giữ nguyên.
- **Nhãn ẩn dụ**: lần đầu một đạo cụ ẩn dụ hiện ra, nhãn của nó ghi cả hai vế ("thẻ = chứng chỉ công khai"); sau nhịp đó nhãn rút
  về chữ đời thường ("thẻ"), để khung cuối gọn. *(Claude quyết.)* Danh sách chữ được phép (`COMMON` trong `vshort/motion.py`) thêm từ
  đời thường của bộ đạo cụ (thẻ, chìa, bảo vệ, cửa, barie, tòa nhà, phòng, két, thư, kiện hàng…) và vài động từ/cụm ngắn cảnh cần
  (bản sao, kẹp, cho vào, đúng chủ…); vế kỹ thuật vẫn phải là chữ có trong brief/lời như luật hiện nay. Chữ trong `an-du.md` đã
  duyệt cũng được dùng trên nhãn, để mỗi ẩn dụ mới (bưu điện, xe giao hàng, két) không phải nới `COMMON`. *(Claude quyết.)*
- **Đầu bút**: khi một thứ đang vẽ ra, một đầu bút chì nhỏ chạy theo đầu nét (kiểu video bảng trắng). *(Claude quyết: rẻ, làm khung
  sống hơn.)*
- **Không có quãng chết** (code kiểm trong `vshort motion`): trong đoạn cơ chế, không có quãng nào dài quá khoảng 1,5 s mà không có
  gì đang vẽ ra, di chuyển, đổi màu hay máy quay đang đi. `pulse` không tính. Con số là Claude đặt; builder chỉnh theo video thử.

### 4. Máy quay

- Cảnh vẫn vẽ trên khung 720×1280. Máy quay là một phép **phóng + dời** áp lên toàn cảnh khi dựng từng khung hình (kit đã vẽ lại từ tọa
  độ mỗi khung, nên phóng là đổi tọa độ và độ dày nét, không phải phóng ảnh bitmap: nét không nhòe).
- **Code tự tính máy quay** từ cảnh, agent không phải viết: mỗi nhịp, máy quay khung lấy vùng chứa các thứ nhịp đó vẽ ra, di chuyển
  hay có hành động, cộng lề; chuyển giữa hai nhịp bằng gia tốc mềm; nhịp cuối kết thúc bằng cú lùi ra toàn khung (phóng 1×) để thấy
  A→Z. Agent được ghi đè vùng khung cho một nhịp khi cần. *(Claude quyết.)*
- Giới hạn chống chóng mặt và nhòe: phóng trong khoảng 1×–2×; không đổi khung giữa chừng một nhịp trừ khi đi theo thứ đang di chuyển.
  Vùng được khung phải nằm trong vùng an toàn của màn hình (tránh logo trên phải và dải phụ đề dưới).
- Cỡ chữ nhỏ nhất hiện có (`MIN_LABEL_EM`) áp cho **khung cuối ở phóng 1×**, để sơ đồ lùi ra vẫn đọc được.

### 5. Gắn vào lời

- Bước 0 là nhịp đầu của cảnh. Bước gắn nhịp (`motion.bind.json`) cho đoạn câu bắt đầu từ **câu "bình thường thì…"** mà lời đọc nói
  bước 0. Lời không nói bước 0 thì nhịp đó `null` như mọi nhịp khác.
- Giới hạn độ dài đoạn cơ chế nới từ "không quá nửa video" lên **khoảng 55 % số âm tiết lời đọc** (ở LXD, câu 3–8 là 47,5 %; câu 4–8 là
  41,9 %). Con số là Claude đặt theo đo ở LXD; builder chỉnh nếu thử thấy chặt.
- Các luật khác của bước gắn nhịp giữ nguyên.
- Mỗi hành động rơi đúng vào chữ đang đọc (đã có: mốc theo câu và cụm phụ đề); không hành động nào đi trước lời.

### 6. Soát

- `vs-reviewer` thêm mục soát: ẩn dụ đúng với brief và "Lưu ý độ chính xác" (không nói quá, không thiếu điều kiện; ở `--auto` đây là
  lần soát duy nhất), chỗ hỏng hiện thành hành động nhìn
  thấy được, không trông trẻ con, máy quay không gây chóng mặt, khung cuối lùi ra đọc được.
- Vòng sửa (`FIX_HOW["motion"]`) sửa cảnh như hiện nay; không sửa đạo cụ đã có trong thư viện.

## Mẹo nghề lấy từ hai bộ skill

Từ `motion-broll` (Barty-Bart) và `whiteboard-animation`, `diagram-animation`, `short-form-video` (iart-ai), những điều áp được
cho pipeline này: mỗi thay đổi rơi đúng một chữ đang đọc; máy quay phóng cho trạng thái đang nói lấp đầy khung; không có thời gian
chết; chuyển động lò xo/gia tốc mềm, không nảy tưng; nét hiện dần có đầu bút chạy theo; dữ liệu chạy dọc đường nối; không bịa số
liệu; vòng tự kiểm "dựng khung → xem tờ ảnh → sửa" (pipeline đã có). Không lấy: con trỏ chuột điều khiển, giao diện sản phẩm,
nhạc/hiệu ứng âm thanh, hiệu ứng phát sáng/hạt.

## Ví dụ nghiệm thu

Dựng lại đoạn hình động của `~/notebooklm-videos/lxd-microcloud-cvss10` theo cách mới (câu 3–8, lời Việt đã duyệt giữ nguyên),
render lại video, đặt cạnh bản hiện tại cho Tai xem. Run này có trước bước 0 và ẩn dụ: dùng ẩn dụ của bản phác Tai đã xem làm
`an-du.md`, coi câu 3 là bước 0, không chạy lại NotebookLM. Agent viết ẩn dụ (`vs-an-du`) thử riêng trên brief LXD và brief
`linux-tcp-cve-2026-98432`, Tai xem kết quả. Đạt khi:

- người xem thấy được: thẻ ai cũng photo được; chìa chỉ chủ thẻ có; máy quét chỉ xác nhận thẻ đầu; bảo vệ dò cả xấp với bảng tên và
  cho vào vì thấy thẻ kỹ sư; vào trong thì chiếm phòng, có quyền cao thì chiếm cả tòa;
- không có cắt cảnh; khung cuối lùi ra thấy đủ chuỗi và đọc được ở cỡ điện thoại;
- không có quãng chết quá ngưỡng; máy quay theo lời;
- `vs-reviewer` không còn lỗi hình động; chi phí `vs-motion` không vượt lượt cũ ($2,79).

Hai ví dụ chuẩn trong `examples/motion/` (coruna, goi-tin) và các video cũ vẫn dựng được (cảnh không dùng tính năng mới phải ra như
trước, trừ máy quay).

## Để builder quyết

- Cú pháp mới của `motion.json`, cách lưu phần chuyển động của đạo cụ, cách người cầm/đeo đồ vật.
- Cách vẽ bộ đạo cụ (tay vẽ dữ liệu nét, hay chuyển từ một bộ icon nét mã nguồn mở như Lucide/Tabler rồi cho rung nét chì), miễn là
  giấy phép cho dùng và phong cách khớp kit.
- Con số: ngưỡng quãng chết, lề và tốc độ máy quay, giới hạn phóng.
- Cảnh cũ không có máy quay nên giữ khung tĩnh hay cũng được tính máy quay.
