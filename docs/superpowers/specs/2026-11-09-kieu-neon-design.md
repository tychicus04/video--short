# Kiểu neon: hình động vẽ bằng code, lời Việt viết thẳng từ brief (thiết kế)

Ngày 09/11/2026. Tài liệu này thay `2026-11-06-hinh-goc-notebooklm-design.md` ở phần **hình** và **lời**. Phần tìm hiểu, duyệt
brief, giọng đọc, âm thanh, ảnh bìa và đăng CMS vẫn như `DESIGN.md` và các spec trước, trừ chỗ ghi khác dưới đây.

## Vì sao

Ngày 09/11/2026, Tai nhắn: "Tôi không muốn sử dụng kiểu style gemini notebook nữa, tôi muốn thực sự có 1 kiểu video unique 1 chút
như những loại video mẫu tôi gửi". Sau đó Tai nói thêm: video "cơ bản sẽ là để giới thiệu công nghệ, giải thích cơ chế cho người đọc
và xem dễ hiểu", và nâng giới hạn lên "khoảng 30$/video".

Tai chọn giữa hai bản thử dài 34 giây, dựng trên giọng đọc có sẵn của video OpenMatter:
- **kiểu A, neon**, theo video mẫu HTTP/3;
- **kiểu B, phóng sự**, theo video Binance của tạp chí.

Tai trả lời "A hợp hơn". Về nguồn của lời kể, Tai chọn **cách 2**: Claude viết thẳng lời Việt từ brief đã duyệt. Không tạo video
NotebookLM nữa.

Bản thử để đối chiếu nằm ở `docs/superpowers/specs/2026-11-09-kieu-neon-thu/`:
- `template.html`: hai composition và trình phát;
- `inject.py`: ghép giọng, mốc phụ đề và logo vào trang.

Đầu vào là run `openmatter-network-giai-phap-dien-toan-phi-tap-trung-thay` trên pve2. Bản dựng xong nằm ở
`.superpowers/brainstorm/86371-1794199382/content/kieu-hinh.html`, đã gitignore. **Bản thật phải trông như kiểu A của bản thử.**

**Lịch sử, để không lặp lại:**
- Ngày 06/11, Tai bỏ hình tự vẽ (`vs-motion`, `vs-nhip`, ẩn dụ) vì ba lý do:
  - "khoanh tròn rồi zoom ra zoom vào, nhàm chán";
  - "màu sắc, kiểu dáng không thống nhất";
  - kém chính video NotebookLM.
- Hình tự vẽ lúc đó hỏng vì mỗi video một agent vẽ tự do, có máy quay khoanh và zoom, và trộn bốn kiểu hình.
- Kiểu neon khác ở ba điểm:
  - **một bộ mẫu cố định** cho mọi video;
  - **không có máy quay**;
  - **vị trí do code xếp và kiểm**, không do agent tự đặt tọa độ.

**Lấy từ OpenMontage** (repo đã đọc ngày 09/11, xem memory `openmontage-review-2026-11-09`):
- HyperFrames, công cụ biến HTML có hình động thành video, giấy phép Apache-2.0;
- ý "một bộ quy định hình ảnh cho mọi video";
- kiểm máy móc bằng code trước khi nhờ người soát (LLM).

Không chép code của OpenMontage: phần đó theo AGPL.

## Mục tiêu

1. **Video dọc 9:16, 720×1280, 30 khung/giây, dài khoảng 75 giây (60–90 giây).** Ở nhịp 4,3 âm tiết/giây, kể cả câu tiêu đề và lời
   kêu gọi, là khoảng 260–390 âm tiết. Đây là lựa chọn của mình, Tai chưa nói độ dài.
2. **Trông như kiểu A của bản thử:**
   - Nền: gần đen (#04060c) với lưới chấm mờ.
   - Hình: một sơ đồ liền mạch, không cắt cảnh, không máy quay. Mỗi thứ bật sáng (nhấp nháy kiểu đèn neon khoảng 0,2 s) hoặc được
     vẽ nét ngay lúc lời nhắc tới.
   - Chữ gõ dần tại chỗ, không xô chữ bên cạnh.
   - Màu mang nghĩa: xanh dương #2BE3FF là bình thường, đỏ #FF4D61 là rủi ro hay hỏng, vàng #FFC53D là lời tuyên bố hay con số,
     xanh lá #3DFF9E là an toàn hay đã kiểm chứng. Trắng và xám không tính là màu.
   - **Mỗi khung tối đa 2 màu neon.**
   - Chữ: Be Vietnam Pro, và IBM Plex Mono cho nhãn mục.
3. **Giữ:**
   - thanh tiêu đề tạp chí (vạch vàng, khung xanh #206B88, y 680–842) gõ chữ trong lúc đọc câu tiêu đề, rồi cuộn đi;
   - logo góc trên phải (x 470–700, y 24–82) màu gốc, đặt trên một miếng nền trắng bo góc, vì chữ xanh đậm không đọc được trên nền tối;
   - phụ đề từng cụm: chữ trắng đậm có quầng xanh, không hộp, đáy ở y 1140, rộng tối đa 516 px (`MAX_TEXT_W`);
   - outro ANM 2,5 s;
   - −14 LUFS;
   - tối đa 3 tiếng hiệu ứng;
   - không nhạc nền.
4. **Mỗi bước trong mục "Cơ chế từng bước" của brief thành một thay đổi của sơ đồ**, đúng lúc lời nói tới.
5. **Mọi video dùng chung một bộ mẫu**, nên nhìn thống nhất trong một video và giữa các video.
6. **Tiền Claude mỗi video tối đa $30**, theo `cost.json`. Hiểu như vậy là lựa chọn của mình; Tai chưa nói $30 là tiền gì. Kiểu neon
   không cần dịch vụ tạo ảnh hay clip trả phí.
7. **Hai điểm dừng như cũ:** duyệt brief và duyệt lời Việt. Kịch bản hình không có thêm bước duyệt.

## Không làm

- AI tạo ảnh hay video, và mọi API tạo hình trả phí.
- Nhạc nền.
- Logo của các hãng được nhắc tới (chưa ai yêu cầu).
- Ảnh chụp màn hình thật.
- Video tiếng Anh, `brief.en.md` và video NotebookLM. NotebookLM chỉ còn dùng để `vs-researcher` gom nguồn, nếu nó vẫn cần.
- **Mẫu hình cho mã, lệnh, terminal hay payload.**
  - Luật an toàn của brief cũng ràng buộc kịch bản hình: chỉ ở mức khái niệm, không tên lỗ hổng, kỹ thuật hay công cụ, không mã hay
    lệnh. Luật này hiện nằm trong `BRIEF_CHECK` và `vs-researcher.md`.
  - Icon chỉ là hình chung chung: máy chủ, tệp, ổ khóa…

## Thất bại dù vẫn chạy

- Chữ đè lên đường nối, lên icon hay lên chữ khác. Bản thử mắc lỗi này 4 lần trước khi sạch.
- Hơn 2 màu neon trong một khung, hoặc trộn kiểu hình.
- Sơ đồ nói quá hay trái brief, ví dụ một con số không có trong brief.
- Hình hiện trễ so với lời đến mức thấy rõ.
- Khoanh tròn, zoom, máy quay trên ảnh tĩnh.

## Luồng mới

| # | Chặng | Ai làm | Ra |
|---|---|---|---|
| 1 | Tìm hiểu | `vs-researcher` (như cũ, bỏ bản tiếng Anh) | `brief.vi.md`, `sources.md` |
| 2 | Duyệt brief (dừng) | Tai; chế độ tự động thì `brief_check` | — |
| 3 | Viết lời | `vs-writer` (mới, Sonnet) | `script.vi.json` |
| 4 | Duyệt lời (dừng) | Tai | — |
| 5 | Giọng đọc | `vshort tts` + `timeline` (như cũ) | `narration.wav`, `timeline.json` |
| 6 | Kịch bản hình | `vs-scene` (mới, Sonnet) + `vshort scene` kiểm | `scene.json` |
| 7 | Dựng video | `vshort render` (HyperFrames rồi ffmpeg) | `final.mp4` |
| 8 | Soát và sửa | `vs-reviewer` (Opus, danh mục mới), tối đa 2 vòng | `review.md`, `review.json` |
| 9 | Ảnh bìa và xuất | như cũ | `xuat/…` |

### 3 · Viết lời (`vs-writer`)

- `script.vi.json` giữ đúng dạng hiện nay: mỗi câu một mục `id`, `phrases` (các cụm phụ đề ngăn bằng `|`) và `note`.
  - Câu 1 là tiêu đề trong brief, nguyên văn.
  - Câu 2 là "Chi tiết mở màn".
  - Rồi đến "Cơ chế từng bước", bắt đầu bằng bước 0 "Bình thường".
  - Rồi "Ý chính", gồm ý về cái giá hay giới hạn; mỗi con số mở bằng nguồn của nó, và điều chưa xác nhận được nói thành lời.
  - Rồi "Câu chốt" và "Lời kêu gọi".
- Thứ tự và giọng văn theo các luật brief đã có (`aff35c8`, `ebb1e7b`). Không thêm ý ngoài brief.
- `vshort check` không còn so với câu tiếng Anh. Nó kiểm:
  - câu 1 đúng tiêu đề brief;
  - mọi con số và tên riêng trong lời đều có trong brief (`check_numbers`, `check_brief` sửa lại);
  - mỗi cụm vừa `MAX_TEXT_W`;
  - tổng số âm tiết trong khoảng 260–390;
  - các luật hiện có của `check_style`.
- Bước "Duyệt lời" thay "Duyệt bản dịch". Trang duyệt cho thấy lời từng câu, số âm tiết, thời lượng ước tính, cùng các ghi chú.

### 5 · Giọng đọc

Như hiện nay: Gemini đọc cả bài một lần, hết lượt thì ZeroTTS; `fit.sequence` nối các câu. Mốc của từng cụm phụ đề lấy từ
`fit.phrase_times`. Đó cũng là đồng hồ của kịch bản hình.

### 6 · Kịch bản hình (`vs-scene` + `vshort scene`)

- **Lệnh in bảng cho agent.** `vshort scene RUN --table` in số thứ tự toàn cục của từng cụm, giờ bắt đầu và chữ của cụm. Câu tiêu
  đề là cụm 0, mỗi cụm sau đó một số. Mục "Cơ chế từng bước" của brief cũng được in.
- **Agent viết `scene.json`.** Agent chỉ dùng **từ vựng của bộ mẫu**: tên phần tử, tên bố cục, số thứ tự cụm. Không có tọa độ,
  không có màu tự chọn ngoài bốn nghĩa.
- **Code xếp chỗ và kiểm.** `vshort scene RUN` dàn vị trí rồi kiểm (mục "Kiểm bằng code"). Lỗi in ra để agent sửa. Agent chạy lại
  tới khi mã 0, giống `vshort visuals` hiện nay.

### 7 · Dựng video

1. `vshort render` sinh composition HyperFrames từ `scene.json` cộng bộ mẫu, gồm:
   - sơ đồ;
   - phụ đề từng cụm;
   - thanh tiêu đề;
   - logo.
2. HyperFrames render ra `visuals.mp4` không tiếng, đúng dài `total`.
3. Một lần ffmpeg như hiện nay:
   - ghép `narration.wav` với tiếng hiệu ứng (`sound.master`);
   - nối outro;
   - chuyển màu BT.709, ra `final.mp4`.
4. Bỏ ASS, `title.mov` và lớp logo ffmpeg. Các hằng số hình học của thanh tiêu đề (`render.STRIPE`, `render.BAR`) giữ lại cho
   `cover.py`.

### 8 · Soát và sửa

- `vs-reviewer` có danh mục mới, xem từng khung lúc mỗi nhịp hình bắt đầu và kết thúc:
  - hình đúng điều lời đang nói;
  - chữ đọc được;
  - không gì trái brief;
  - kiểu thống nhất;
  - phụ đề khớp `script.vi.json`;
  - thanh tiêu đề và logo đúng;
  - outro đúng.
- Lỗi máy đo được thì đã chặn ở bước 6 (xem dưới). Reviewer không đo lại.
- Theo luật của OpenMontage, mỗi lỗi nặng phải kèm **cách sửa cụ thể**: thêm trường `fix` vào `review.json`.
- Mỗi lỗi ghi `agent` là một trong ba:
  - `"scene"`: sửa `scene.json`, rồi `vshort scene`, rồi render lại;
  - `"writer"`: ghi `script.proposed.json` để Tai duyệt, như `translator` hiện nay;
  - `"none"`.
- Tối đa 2 vòng.

## Bộ mẫu neon

### Từ vựng

Danh sách từ bản thử, cộng phần cần để diễn tả ba brief cũ (bảng dưới):

| Phần tử | Làm gì |
|---|---|
| `section` | nhãn mục gõ dần ở góc trên trái, ví dụ "THÔNG THƯỜNG", "OPENMATTER ĐỀ XUẤT", "KIỂM CHỨNG" |
| `node` | một icon có nhãn (máy chủ, người dùng, tệp, ổ khóa…), bật sáng hoặc vẽ nét |
| bố cục | `center`, `pair` (trái và phải), `chain` (hàng hay cột N có mũi tên), `ring` (N quanh một nút), `grid` |
| `link` | đường nối hai nút: liền, đứt, hoặc `tunnel` (đường đôi) |
| `flow` | hạt sáng chạy dọc đường nối, lặp hữu hạn; có thể rẽ một bản sao tới nút thứ ba |
| `state` | đổi nghĩa màu của nút hay đường nối: bình thường, rủi ro, tuyên bố, an toàn, mờ |
| `badge` | icon nhỏ ở ô dành sẵn cạnh nút (ổ khóa, chìa, mắt gạch, dấu kiểm, cảnh báo, cửa) |
| `swap` | đổi icon của nút, ví dụ tệp thành tệp bị khóa, chìa A thành chìa B |
| `split` / `merge` | một khối chia thành N mảnh bay tới các nút, hoặc ngược lại |
| `chip` | viên chữ: ngày, con số có trong brief, lời tuyên bố; màu theo nghĩa |
| `quote` | bong bóng lời tuyên bố kèm người nói ("công ty tự nhận …") |
| `statement` | câu lớn gõ dần, trong dải chữ dành sẵn |
| `hero` | icon lớn vẽ nét ở giữa cho cao trào (khiên, dấu kiểm, ổ khóa) |
| `clear` | tắt dần một nhóm hay tất cả (0,35 s) trước khi dựng phần sau; không cắt cứng |

**Thử từ vựng với ba brief cũ.** Chỉ ở mức khái niệm.

**SharePoint (storm-2603):**
1. `node` máy chủ ở `center`, `badge` dấu kiểm: bình thường.
2. `node` kẻ tấn công ở `pair`, `flow` một yêu cầu tới máy chủ.
3. Máy chủ chuyển `state` rủi ro, `chip` "chạy mã lạ".
4. `badge` chìa bay về kẻ tấn công, `badge` cửa trên máy chủ.
5. `ring` các máy nội bộ, đỏ lan dọc `link`.
6. `swap` tệp thành tệp khóa trên từng máy.

**Synology:**
1. `node` NAS kèm `chip` "DSM cũ".
2. `badge` khiên chuyển `state` rủi ro.
3. NAS chuyển đỏ.
4. `grid` các tệp, `swap` sang tệp khóa.
5. `node` thư đòi tiền.

**VPN hậu lượng tử:**
1. `pair` chi nhánh và trụ sở, nối bằng `link tunnel`; `flow` gói dữ liệu.
2. `node` kẻ nghe lén; `flow` rẽ một bản sao vào kho lưu.
3. Hai `node` chìa (cổ điển, hậu lượng tử) `merge` thành một chìa.
4. `swap` chìa hậu lượng tử thành chìa khác, chìa cổ điển vẫn sáng.

**Bộ icon.** Khoảng 40 icon nét 24 px, lấy một phần của Lucide (giấy phép ISC), đóng gói trong repo:
- người dùng, kẻ xấu;
- máy chủ, NAS, PC, điện thoại, GPU, đám mây, Internet, tòa nhà;
- tệp, tệp khóa, thư;
- ổ khóa, chìa, khiên, khiên vỡ, mắt, mắt gạch, dấu kiểm, dấu nhân, cảnh báo, cửa;
- bộ định tuyến, kho dữ liệu…

Không icon nào là mã hay giao diện công cụ cụ thể.

### Vị trí do code tính

- **Hình học tính trong Python**, không trong trình duyệt và không do agent đặt.
  - Bố cục cho ra tọa độ nút và chừa chỗ cho nhãn và badge.
  - Bề rộng chữ đo bằng PIL với chính font sẽ dùng, như `textfit.py`, cộng biên an toàn khoảng 6 %.
  - Composition nhận tọa độ tuyệt đối; JS chỉ làm chuyển động.
- **Bài học từ bản thử:** vòng 6 nút đặt ở góc 0°, 50°, 130°, 180°, 230° và 310°, bán kính 228, quanh tâm (330, 560). Nhờ vậy:
  - phía trên và dưới tâm trống cho chip và nhãn;
  - cạnh phải dừng ở x ≤ 614.
- **Các dải dành sẵn:**
  - nhãn mục ở y 190–230;
  - sơ đồ trong y 250–900;
  - phụ đề ở y 1000–1140;
  - logo ở góc trên phải.
  - Dải câu lớn (`statement`) để builder chọn, miễn qua được phép kiểm.

### Chuyển động (theo bản thử)

| Chuyển động | Cách làm |
|---|---|
| Bật | độ mờ 0 → 1 → 0,25 → 1 → 0,6 → 1 trong 0,2 s |
| Tắt | 0,35 s |
| Vẽ nét | `stroke-dashoffset`, 0,3–0,8 s |
| Gõ chữ | từng ký tự hiện tại chỗ |
| Hạt sáng | chạy thẳng, lặp hữu hạn |
| Mảnh | bay 0,6 s, `power2.inOut` |

- Hình vào sớm hơn đầu cụm khoảng 0,1–0,2 s.
- Không bounce, không pop to nhỏ.
- Mọi chuyển động nằm trên một GSAP timeline dừng sẵn, có thể tua tới bất kỳ giây nào. Không dùng `Math.random`, không lặp vô hạn
  (luật của HyperFrames).

## Kiểm bằng code

`vshort scene` kiểm tại mọi mốc có thay đổi. Phải qua trước khi render:

1. Mọi nhịp chỉ tới một cụm có thật, và mọi nút được nhắc tới đều đã khai báo.
2. **Không chồng lấn**, với biên vài px:
   - hộp chữ với hộp chữ;
   - hộp chữ với icon;
   - hộp chữ với đoạn thẳng của đường nối;
   - icon với icon.
3. **Vùng an toàn:**
   - từ y 535 xuống, không gì vượt x 618;
   - y < 141 chỉ có logo;
   - y ≥ 1151 trống;
   - dải phụ đề chỉ có phụ đề.
4. **Tối đa 2 màu neon** cùng lúc.
5. **Chữ vừa chỗ:** nhãn, chip và statement không quá bề rộng cho phép; font có đủ dấu tiếng Việt.
6. **Mọi con số và tên riêng** trong chip, quote và statement đều có trong brief, cùng cách so như `check_numbers`.

Sau khi render:
- `ffprobe` cho độ dài bằng `total`;
- `npx hyperframes validate` không có lỗi console.

## Âm thanh

`sound.master` giữ nguyên các mức: `UNDER` 3 dB, cách nhau `SPACE` 1,5 s, −14 LUFS. Có tối đa 3 tiếng, lấy mốc từ kịch bản hình vì
không còn cắt cảnh:

| Tiếng | Đặt ở |
|---|---|
| `whoosh` | nhịp hình đầu tiên sau câu tiêu đề |
| `glitch` | lần đầu một thứ chuyển `state` rủi ro |
| `pop` | `hero` |

## HyperFrames

- **Phiên bản:** ghim `hyperframes@0.8.206` (ra ngày 26/10/2026; gói cần Node ≥ 22). Cài cục bộ trong repo bằng `package.json` riêng
  cho bộ mẫu, không dùng `npx` bản mới nhất. Gói này ra bản mới nhiều lần mỗi ngày.
- **Máy:**
  - pve2: Node 24.19.0, có `/usr/bin/google-chrome`;
  - Mac: Node 24.19.0, có Google Chrome.
- **Wrapper:** mình tự viết trong Python, gọi CLI qua `subprocess`. Không chép `hyperframes_compose.py` hay style bridge của
  OpenMontage (AGPL).
- **Task 1 của kế hoạch là cổng.** Render một composition neon dài 3 giây ra MP4 bằng bản đã ghim, trên pve2 và trên Mac.
  - Nếu không được, dùng đường lùi: Chrome headless (puppeteer-core hoặc Playwright) tua timeline tới từng khung, chụp PNG, rồi
    ffmpeg ghép lại.
  - Phải báo Tai nếu cổng không qua.

## Chi phí

- Hạn `BUDGET` trong `auto.py` từ 5 lên 30.
- Dự đoán mỗi video:
  - `vs-writer` khoảng $0,5–1;
  - `vs-scene` khoảng $2–6, kể cả vòng sửa;
  - `vs-reviewer` khoảng $2–5.
- Tổng khoảng $5–12, dưới hạn.

## Chuyển đổi và chấp nhận

- **Luồng cũ vẫn chạy được** cho tới khi Tai chấp nhận luồng mới.
  - Run mới mang cờ kiểu trong `run.json`. `vshort auto` chọn luồng theo cờ đó.
  - Lý do: Tai làm video mỗi ngày.
- **Chấp nhận:**
  - Chạy 2 chủ đề thật qua luồng mới: một sự cố bảo mật, một giới thiệu công nghệ.
  - Tai xem và so với bản thử.
  - Tai đồng ý thì luồng mới thành mặc định.
- **Sau khi Tai chấp nhận mới xóa code cũ:**
  - lấy video NotebookLM (`source`, `fetch`);
  - `captions.py` và `detect`;
  - `vs-transcriber` và `text`;
  - `vs-translator`;
  - `plates.py` / `clean` (LaMa);
  - `stills.py`;
  - `retime.py`;
  - `visuals.py` và `vs-visuals`;
  - phần ASS và `title.mov` của `render.py`.
- **Trước khi đưa lên pve2:** xem `queue.json` có run đang chạy không.
- **Cập nhật theo:**
  - `stages.py`: `STAGES`, `STEPS_OF`, `DEFAULT_SECONDS`, 9 chặng như bảng trên;
  - `web.py` nếu cần;
  - skill `video-short`;
  - `vs-reviewer.md`;
  - `DESIGN.md`;
  - các test trích hằng số giới hạn (`8c92a70`);
  - memory.
- **Ảnh bìa 9:16** vẫn lấy khung của `final.mp4` lúc tiêu đề gõ xong: giữ cách tính giờ của `render.title_times`.
- **Lỗi mất lời tiếng Anh** (4/13 run, ghi trong memory `openmontage-review-2026-11-09`) tự hết khi bỏ dò phụ đề.

## Ai quyết điều gì

**Tai đã quyết:**
- bỏ hình NotebookLM;
- mục đích: giới thiệu công nghệ, giải thích cơ chế dễ hiểu;
- kiểu A (neon);
- lời viết thẳng từ brief (cách 2);
- giới hạn khoảng $30/video.

**Mình tự quyết (Tai chưa nói, có thể đổi):**
- dài 60–90 giây;
- $30 là tiền Claude theo `cost.json`;
- hai điểm dừng, kịch bản hình không có bước duyệt;
- `vs-writer` và `vs-scene` chạy Sonnet, reviewer chạy Opus;
- HyperFrames 0.8.206;
- hình học tính trong Python;
- từ vựng và bộ icon ở trên;
- phụ đề và logo vẽ trong composition;
- logo trên miếng nền trắng;
- mốc của 3 tiếng hiệu ứng;
- luồng cũ chạy song song tới khi chấp nhận.

**Để builder tự quyết:**
- dạng JSON chính xác của `scene.json`;
- danh sách icon cụ thể;
- thời lượng chuyển động chi tiết;
- cách chia module;
- cách reviewer chọn khung;
- tên chính xác của lệnh và tệp.
