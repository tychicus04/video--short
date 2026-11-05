# Nhịp hình cho phần ảnh tĩnh và thẻ tư liệu — thiết kế (05/11/2026)

## Vì sao

Ngày 05/11, trong lúc làm video `ai-an-ninh-mang-ba-mat-tran`, Tai nói: "phần phía sau motion chỉ là ảnh ko có chuyển động, vẫn có
thể tận dụng để làm nhiều motion hơn". Tai để mình đề xuất.

Hai lần làm thử, trên ảnh thật của video Synology (script và ảnh so sánh giữ ở `2026-11-05-nhip-hinh-thu/`):
1. **Một dấu chì mỗi ảnh và máy quay đẩy chậm.** Tai: "vẫn hơi nhàm chán".
2. **Cứ ~1 giây một thay đổi gắn với lời:** cắt cận, dấu chì, thẻ tự viết ra, hình vẽ tay ở lề, số bật ra. Bản này dựng trên 9 giây
   đầu và 24 giây cuối, có giọng đọc và phụ đề, đặt cạnh bản hiện tại (`2026-11-05-nhip-hinh-thu/so-sanh.jpg` là các khung chụp từ video so sánh; script `engine2.py`,
   `build2.py`). Tai: "oke hơn rồi".

Thiết kế này làm bản 2 thành tính năng thật.

Nguyên nhân nhàm chán:
- Mỗi câu ngoài đoạn hình động là một hình đứng 4–7 giây, máy quay chỉ zoom/lia tối đa 8 % (`render._camera`).
- Ở Synology, phần sau hình động là 4 thẻ trích dẫn (`svg`) toàn chữ, hiện nguyên một lần.
- Đo trên video NotebookLM, ngoài đoạn sơ đồ hình gần như đứng yên: câu 1, 2, 10, 11 chuyển động 0–4 % thời gian. Vì vậy lấy lại
  chuyển động từ `clean.mp4` không giúp được.

## Mục tiêu

- **Luật nhịp:** trên mọi câu có ảnh tĩnh hay tư liệu (không phải hình động), cứ tối đa ~2 giây phải có một thay đổi nhìn thấy được.
  Mỗi thay đổi gắn với chữ lời đang đọc lúc đó, không phải trang trí lặp lại.
- Giữ nét chì trên giấy, cùng nét với kit hình động (`kit._stroke`). Không neon, không AI tạo ảnh.
- Chi phí Claude thêm nhỏ: phần lớn do code; agent `vs-nhip` (Sonnet) chỉ chọn vật và giờ. Dựng mất thêm ~1,2 s cho mỗi giây video (đo ở bản thử),
  chưa đo trên pve2 (các bước chạy bằng máy ở pve2 chậm hơn Mac ~2,5 lần): đo khi làm, báo Tai con số thật.
- Video cũ và video không có kế hoạch nhịp vẫn dựng như nay.

## Không làm (để sau, nếu Tai muốn)

- Khung hình động vẽ tay thứ hai (cách C). Cách này cần gộp nhánh `hinh-dong-an-du` trước.
- Hiệu ứng âm thanh cho từng nhịp.
- Đo giờ từng chữ bằng nhận giọng. Giờ chữ ước theo tỉ lệ âm tiết như phụ đề, lệch vài phần mười giây là chấp nhận được.

## Thiết kế

### 1. Thẻ tư liệu tự viết ra (code, không cần agent)

Câu có `svg` không còn hiện cả thẻ một lần:
- Khung thẻ vẽ dần như một nét chì chạy quanh.
- Các phần tử còn lại (chữ, đường kẻ, chấm mốc thời gian) hiện lần lượt theo thứ tự trong file SVG, mỗi phần tử quét trái → phải
  ~0,3–0,5 s.
- Khung thẻ đã vẽ xong ngay ở khung hình đầu tiên sau chỗ cắt, để không bao giờ có khung giấy trắng (bản thử mở câu 9
  bằng 0,25 s giấy trống; vs-reviewer coi đó là lỗi).
- Rải đều trong khoảng 60 % đầu của câu. Mỗi phần tử hiện ra là một "thay đổi" trong luật nhịp.

Cách dựng: dùng `cairosvg` vẽ các trạng thái cộng dồn (k phần tử đầu) một lần ở cỡ 2x, cache lại, rồi quét giữa hai trạng thái liền
nhau. Code ghi giờ hiện ra và box của từng phần tử vào `shots/reveal.json`, để agent và bước kiểm biết dòng nào có lúc nào.
Ảnh `photo` vẽ nét chì không tự viết ra: chỉ dùng nhịp ở mục 2.

### 2. Kế hoạch nhịp `RUN/shots.json` (agent viết, code kiểm và dựng)

Mỗi câu không có hình động có một danh sách nhịp. Mỗi nhịp gắn vào một cụm phụ đề (đếm từ 1, như `motion.bind.json`) và một vị trí
`at` 0–1 trong cụm (mặc định 0):

```json
{"10": [
  {"phrase": 1, "focus": [120, 300, 600, 520], "mark": {"shape": "underline", "box": [150, 470, 560, 500]}},
  {"phrase": 3, "focus": null, "mark": {"shape": "circle", "box": [170, 590, 550, 700]}},
  {"phrase": 3, "at": 0.6, "pop": "2024"}
 ]}
```

Mỗi nhịp có thể có:
- **`focus`:** box mà máy quay bật tới trong 0,25 s (ease), rồi trôi nhẹ. `null` là kéo ra toàn cảnh; bỏ trường là giữ khung cũ.
  Mức zoom do code tính để box vừa khung, có giới hạn:
  - ảnh NotebookLM tối đa 1,5x, vì ảnh chỉ 720×1280 nên zoom hơn sẽ mờ;
  - thẻ `svg` tối đa mức mà cả bề ngang chữ của thẻ còn nằm trong khung, để không cắt mép chữ như bản thử.
- **`mark`:** dấu chì vẽ dần trong ~0,5 s, bắt đầu 0,2 s trước chữ. `shape` là một trong `circle`, `arrow`, `underline`, `cross`,
  `tick`; `box` ôm vật được chỉ. Dấu mờ dần khi nhịp có dấu kế tiếp bắt đầu, để không chồng chất. Mũi tên tự chọn hướng từ phía có
  nhiều giấy trống hơn.
- **`doodle`:** `{"shape": "<tên trong assets/shapes>", "box": [...]}`, một hình vẽ tay nhỏ bật ra ở chỗ giấy trống, vẽ bằng
  `shapes.strokes_in_box`. Ví dụ quả địa cầu (`internet`) cho "Internet", ổ NAS cho "NAS ở nhà".
- **`pop`:** một chữ hoặc số ngắn (≤ 12 ký tự) viết tay to, nảy vào. Phải có nguyên văn trong lời Việt của câu đó, để không bịa dữ
  kiện. Tối đa 3 lần mỗi video.

### 3. Kiểm (`vshort shots RUN`; mã 2 kèm một dòng mỗi lỗi, mã 0 thì ghi `shots/sheet.png` để agent xem)

- **Dạng:** đúng dạng ở trên. Id phải là câu có lời, không thuộc hình động. `phrase` và `at` trong khoảng hợp lệ. Nhịp tăng dần theo giờ.
- **Luật nhịp:** khoảng cách giữa đầu câu, các thay đổi (nhịp và phần tử thẻ hiện ra) và cuối câu không quá 2,0 s. Câu ngắn hơn 2 s
  không cần nhịp.
- **Vùng an toàn trên màn hình:** dấu, hình vẽ tay và số bật ra, tính sau camera của nhịp đó, phải nằm trong vùng mà
  TikTok/Reels/Shorts không che (cùng giới hạn với tư liệu: `visuals.REF_*`) và không chạm vùng phụ đề.
- **Box của `mark` có mực:** ≥ ~3 % điểm ảnh khác màu giấy. Box của `doodle` là giấy trống: ≤ ~3 %.
- **`pop`:** có trong lời câu đó, đếm tổng số lần mỗi video.
- **Thẻ chưa viết tới:** trên thẻ `svg`, `mark` hay `focus` không được bắt đầu trước khi các phần tử nằm dưới box của nó hiện ra
  (theo `shots/reveal.json`).
- **Dải vá phụ đề:** trên ảnh NotebookLM, `focus` không cận vào dải dưới nơi phụ đề cũ đã bị xóa (dải giấy vá lộ rõ khi phóng to).
- **`shots.json` cũ hơn kịch bản hay khung hình:** `vshort render` báo lỗi như với `motion/lines.json`. Không có `shots.json` thì
  dựng như cũ. Một câu có nhịp sai thì riêng câu đó dựng như cũ, các câu khác vẫn theo nhịp; lời nhắn cuối liệt kê các câu rơi về
  kiểu cũ.

### 4. Dựng (`render.py`)

- Câu có nhịp: camera theo nhịp thay cho `_kinds`/`_camera` xoay vòng. Câu không có nhịp giữ như cũ.
- Dấu và hình vẽ tay vẽ lên ảnh **trước** camera, nên chúng dính vào hình khi máy quay bật.
- Chuyển câu: giữ crossfade 0,4 s như nay (`XF` dùng chung cho camera cũ, chỗ vào/ra hình động, outro và test; đổi toàn cục
  không đáng). Đây là lựa chọn của mình; bản thử dùng 0,2 s.
- Ảnh gốc vẫn cache. Khung chỉ vẽ lại khi có dấu, hình vẽ tay hay phần tử thẻ đang chuyển động.

### 5. Agent mới `vs-nhip` (Sonnet) và quy trình

**Tai chọn Sonnet, agent riêng (05/11/2026)** sau khi xem hai bản chạy thử trên 6 câu Synology, cùng một lời giao:
- Haiku qua hết luật đo được nhưng chọn sai nghĩa: ngọn lửa cho "không vào được máy", cụm máy ảo cho "nhóm người", và thẻ câu 11
  toàn hình vẽ ở lề.
- Sonnet khoanh và gạch đúng chữ trên thẻ ("Internet", "update DSM", "2024"), tránh được hình vẽ sai nghĩa.

Ước thêm khoảng $0,2–0,5 và 5–7 phút mỗi video, chưa đo thật. `vs-visuals` giữ Haiku và giữ nguyên việc cũ.

`vs-nhip` chạy sau khi `vshort visuals` qua (cần `frames/`), trước `timeline`/`render`:
- Xem `frames/<id>.png` và lưới tọa độ của nó (code ghi thêm `frames/grid/<id>.png`), `shots/reveal.json` (giờ từng dòng thẻ hiện
  ra), giờ từng cụm (code in ra), và tờ hình `shots/shapes.png` (`shapes.sheet`) để chọn `doodle` theo đúng hình vẽ, không đoán
  theo tên. `doodle` chỉ dùng khi hình vẽ đúng là thứ lời nói tới.
- Với mỗi câu được phép, đọc lời Việt theo từng cụm và chọn vật được nhắc trong cụm đó: cận vào nó, đánh dấu nó, hoặc vẽ hình tay ở lề.
- Viết `shots.json`, chạy `vshort shots` tới khi mã 0, rồi xem `shots/sheet.png` (khung cuối mỗi nhịp) để kiểm dấu đúng vật.

Ưu tiên khi chọn: nhắc vật cụ thể thì cận vào hoặc đánh dấu nó; nhắc thứ không có trong hình thì vẽ hình tay; con số hay năm then
chốt thì `pop`.

`auto` có thêm bước `shots`:
- gọi `vs-nhip` như các agent khác (`run_claude`, ghi chi phí, có `TIMEOUT`), rồi tự chạy `vshort shots` để kiểm lại;
- vòng sửa sau soát (`fix<r>_*`) có thể giao việc cho `vs-nhip` như với `motion`/`visuals`;
- `vs-nhip` lỗi, hết giờ hay không qua kiểm thì video vẫn dựng theo kiểu cũ, và lời nhắn cuối ghi rõ điều đó;
- `stages.py` và bàn điều khiển web gộp bước mới vào chặng hình (để người làm chọn chặng cụ thể).

Agent đặt ở `claude/agents/vs-nhip.md` trong repo, symlink vào `~/.claude/agents/` trên Mac và server như các agent `vs-*` khác.

### 6. Soát (`vs-reviewer`)

Thêm vào danh sách soát:
- dấu chỉ đúng vật được nói;
- không có hình mờ vì zoom quá;
- chữ thẻ không bị cắt mép;
- nhịp không rối.

## Lựa chọn của mình (Tai chưa duyệt riêng từng điểm)

Tai duyệt hướng đi qua video so sánh, chưa duyệt các con số này: ngưỡng cứng 2,0 s, tối đa 3 `pop` mỗi video, zoom ảnh tối đa
1,5x, giữ `XF` 0,4 s, rơi về kiểu cũ theo từng câu, Agent Sonnet riêng là Tai chọn (mục 5).

## Kiểm thử

- Test `vshort shots`: từng luật ở mục 3, gồm cả câu thiếu nhịp vượt 2 s.
- Test dựng:
  - khung trước giờ dấu không có dấu;
  - khung sau khi vẽ xong khác ảnh ở quanh box;
  - camera tại giờ giữa nhịp đúng là zoom của `focus`.
- Test thẻ tự viết ra: khung đầu câu có ít mực hơn khung ở 60 % câu; khung cuối giống `svg_frame`.
- Thử thật: chạy `vs-nhip` + `vshort render` cho `ai-an-ninh-mang-ba-mat-tran` và Synology, Tai xem.

## Để lại cho người làm

- Hình chính xác của từng dấu, độ dày nét, cỡ chữ `pop`.
- Cách tìm thứ tự phần tử SVG để viết ra (thẻ do agent viết tay, cấu trúc đơn giản).
- Nhánh `hinh-dong-an-du` (chưa gộp) đổi `kit._stroke` nhưng chỉ thêm tham số có mặc định (`view=FULL`), và thêm `camera.py` cho
  khung hình động. Tính năng này chỉ gọi `kit._stroke`/`ease` theo chữ ký cũ và để camera nhịp trong `render.py`, nên không cần
  gộp nhánh trước.
- Gom hình học dùng chung giữa kiểm và dựng: một hàm trả về các điểm của dấu và một hàm trả về camera tại giờ t.
- Lấy gì từ `2026-11-05-nhip-hinh-thu/engine2.py`: đó là bản nháp, không có test.
