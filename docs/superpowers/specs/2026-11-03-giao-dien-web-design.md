# Giao diện web cho /video-short, đợt 1: bàn điều khiển — thiết kế (03/11/2026)

## Vì sao

Hiện mỗi video được khởi động và duyệt qua terminal hoặc phiên chat `/video-short`. `vshort auto` đã chạy trọn một video không cần
phiên Claude điều phối (spec `2026-11-02-dieu-phoi-bang-script-design.md`): nó tự gọi agent bằng `claude -p`, dừng ở hai chỗ duyệt,
ghi trạng thái vào `auto.json` và chi phí vào `cost.json`. Còn thiếu một chỗ để **bấm** thay vì gõ lệnh.

Tai muốn một trang web đẹp hẳn hoi để thao tác trực tiếp, làm **khoảng 5 video mỗi ngày**, không cần mở cửa sổ chat. Về lâu dài, Tai
muốn chỉnh video theo từng khung và **dựng khung hình chính trước** thay vì "gen ra mới biết". Hai việc đó là đợt 2 và 3 (cuối file).
Tai đồng ý thứ tự: đợt 1 bàn điều khiển → đợt 2 bảng phân cảnh sau khi có hình → đợt 3 bảng phân cảnh lúc duyệt brief.

## Mục tiêu

- Một trang web chạy trên server `pve2`. Máy nào cùng mạng (Mac, điện thoại, máy người khác) cũng mở được, ai mở cũng dùng được
  (Tai chọn: "không chỉ tôi dùng, ai cũng vào được, nhưng chỉ cùng mạng").
- **Thêm video hàng loạt:** dán nhiều chủ đề (hoặc link), mỗi dòng một video, vào một hàng đợi. Có ô "Bỏ duyệt brief" cho cả đợt
  (tương đương `--auto`).
- **Thấy ngay việc nào cần mình:** danh sách mọi video kèm trạng thái, việc cần Tai (chờ duyệt, lỗi) nổi lên đầu.
- **Duyệt ngay trên trang:** đọc, sửa rồi duyệt brief; đọc, sửa rồi duyệt bản dịch.
- **Khi xong:** xem `final.mp4` trên trình duyệt (tua được), tải về (thay cho `scp`), đọc kết quả soát (`review.md`), chi phí Claude.
- **Khi lỗi:** lý do bằng tiếng Việt (lấy từ `auto.json`) và nút "Chạy lại".
- Không cần mở cửa sổ chat hay terminal cho một ngày làm video bình thường.

## Không làm (đợt này)

- Không sửa pipeline: các bước `vshort`, agent, `vshort auto` giữ nguyên. Giao diện chỉ gọi lệnh và đọc trạng thái có sẵn.
  *(Quyết định của tôi:)* trừ đúng hai chỗ nhỏ trong `vshort`, để trang có tín hiệu tin được thay vì đoán từ chữ trong `message`
  (xem "Lỗi chung cho mọi video" và "Đọc trạng thái"):
  1. kiểm phiên NotebookLM trước bước research;
  2. phát hiện khóa hoặc pid cũ sau khi khởi động lại máy.
- Không bảng phân cảnh, không chỉnh từng câu/khung (đợt 2, 3).
- Không tài khoản riêng từng người, không phân quyền, không tính tiền. Chỉ một mã chung cho việc tốn tiền (mục "An toàn").
  Thương mại hoá để sau (xem "Ràng buộc").
- Không nút "nhờ AI sửa" brief/bản dịch theo lời mô tả (Tai biết, để sau).
- Không đăng nhập lại NotebookLM từ trang (phải làm tay trên Mac như hiện nay).
- *(Quyết định của tôi:)* không xóa video và không dừng video đang chạy từ trang. Gỡ một chủ đề **chưa chạy** khỏi hàng đợi thì có.
- *(Quyết định của tôi:)* không thông báo đẩy (push, email); trạng thái chỉ hiện khi mở trang.

## Thất bại dù vẫn chạy được (anti-goal)

- Trang báo "đang chạy" trong khi tiến trình đã chết (máy khởi động lại, bị kill). `vshort wait` đã có cách phát hiện; trang phải
  dùng đúng cách đó.
- Một video chờ duyệt làm kẹt cả hàng đợi qua đêm.
- Ai đó trong mạng đọc được file ngoài thư mục video, hay chèn lệnh qua ô chủ đề vào agent có quyền chạy Bash.
- Bấm Duyệt brief mà NotebookLM lại làm video từ bản tiếng Anh cũ.
- Video không phát hoặc không tua được trên iPhone.
- Trang có nhánh logic riêng song song với `vshort` rồi lệch dần (đọc JSON theo cách khác, tự đặt trạng thái).

## Ràng buộc

- **Hạn mức:**
  - Gemini TTS miễn phí 10 lượt/ngày, mỗi video tốn 1 lượt, nên 5 video/ngày vẫn vừa; hết lượt thì `vshort tts` tự đọc bằng ZeroTTS.
  - NotebookLM tạo video mất 5–40 phút.
  - Agent chạy bằng gói Max 20x của Tai.
- **Thời gian thật cho 5 video** (ước theo 3 run gần đây, chạy 3 video cùng lúc):
  - Kể cả khi bỏ duyệt brief, mỗi video vẫn dừng ở bước duyệt bản dịch. Dán 5 chủ đề thì khoảng 1–1,5 giờ sau cả 5 đứng chờ duyệt
    bản dịch.
  - Tai duyệt xong thì máy dựng, soát và sửa thêm khoảng 1–2 giờ, lâu hơn nếu có vòng sửa. Ví dụ `linux-tcp-cve` có 2 vòng sửa nên
    mất nhiều giờ.
- **Server `pve2`:**
  - Linux, `python3` (không có lệnh `python`), `uv`, `claude` ở `~/.local/bin`, `node` v24 qua nvm.
  - `notebooklm` không nằm trên PATH: `vshort` gọi nó qua `uv run` trong `notebooklm_dir`.
  - Server đang chạy cả CMS-Admin: 9/14 GB RAM đã dùng.
  - Các cổng đang dùng: 22, 4318, 6379, 8001–8004, 8006, 8009, 8011, 8080, 8265, 8266 và vài cổng ngẫu nhiên trên 127.0.0.1.
  - Server có IP LAN 192.168.1.214 và Tailscale 100.104.111.64.
- **Máy chạy web phải đủ điều kiện để `vshort auto` chạy được:** tiến trình web chạy dưới user `tai`, PATH có `~/.local/bin` và `uv`,
  `claude` đã đăng nhập, và có `~/Document/notebooklm-py-main/.env`. Một systemd unit với môi trường trống sẽ hỏng mà không báo gì.
- **Thương mại hoá:** chạy agent bằng gói Max cho người ngoài dùng để kiếm tiền gần như chắc phải chuyển sang API trả tiền
  (~$3–5/video theo giá API, xem `docs/research-2026-11-02.md` mục 10). Điều khoản cụ thể chưa kiểm. Thiết kế đợt này không chặn
  việc đó, nhưng cũng không chuẩn bị gì cho nó.
- **Code đang thay đổi:** `vshort/` đang được sửa song song ở phiên khác (`main` có thay đổi chưa commit ở `cli.py`, `script.py`,
  `captions.py`). Dựa vào tên hàm, không dựa vào số dòng. Commit phần web riêng, không gộp với các thay đổi đó.

## Công nghệ (quyết định của tôi, Tai chưa chọn trừ chỗ ghi)

- **Giao diện:** React + **shadcn/ui** (Tai chọn) + Tailwind. *(Quyết định của tôi:)* nền tối mặc định, vì đây là công cụ làm video.
  Chữ trên giao diện bằng tiếng Việt.
- **Phía server:** Python, nằm trong repo `video-pipeline` (thư mục mới, ví dụ `web/`), dùng chung code `vshort`, không có pipeline thứ hai.
- **Framework web:** để builder chọn. Ràng buộc là phải phát video có hỗ trợ **HTTP Range**, vì Safari/iOS không phát `<video>` nếu
  thiếu. `http.server` của thư viện chuẩn không có Range. Thêm một thư viện vì lý do này là chấp nhận được.
- **Build giao diện:** build trên server (đã có node) hoặc trên Mac rồi chép bản tĩnh, builder chọn. Lúc chạy, server Python phục vụ
  luôn file tĩnh: một tiến trình, một cổng.
- **Cổng:** chọn một cổng chưa dùng ở trên, ví dụ 8770, nghe trên mọi địa chỉ để vào được qua LAN và Tailscale.
- **Chạy lâu dài:** systemd user unit (hoặc cách tương đương) tự khởi động lại, môi trường như mục "Ràng buộc".
- **Stageshow:** Tai muốn dùng. Skill này vẽ giao diện giả cho trang quảng cáo, không dựng app thật, nên để dành cho trang giới thiệu
  khi thương mại hoá. Không dùng trong đợt này.

## Màn hình

### Màn hình chính: danh sách

Kiểu "A" trong bản phác *(quyết định của tôi, Tai chưa chọn)*.

- **Trên cùng:** ô dán chủ đề nhiều dòng, ô "Bỏ duyệt brief", nút "Thêm vào hàng đợi".
- **Bên dưới:** mỗi video một dòng, sắp theo thứ tự: cần Tai (chờ duyệt, lỗi) → đang chạy → đang xếp hàng (theo thứ tự hàng đợi) → xong
  (mới nhất trước).
- Mỗi dòng có slug, chủ đề, trạng thái bằng lời, và:
  - **đang chạy:** bước đang làm, thời gian đã chạy;
  - **lỗi:** lý do;
  - **xong:** kết luận soát, chi phí, độ dài.
- Dùng được trên điện thoại.

### Thêm video

- Mỗi dòng không trống là một video. Slug tự sinh từ chủ đề (bỏ dấu, chữ thường, nối bằng `-`, cắt ngắn) và Tai sửa được trước khi
  thêm.
- Slug phải khớp `^[a-z0-9][a-z0-9-]{0,59}$` và chưa có trong `runs_dir`, sai thì báo ngay trên dòng đó.
- Chủ đề giới hạn độ dài (ví dụ 500 ký tự).

### Duyệt brief (trạng thái `wait_brief`)

- Hiện `brief.vi.md` để đọc và sửa. `brief.en.md` hiện bên cạnh, có thể thu gọn.
- **Vấn đề:**
  - `vshort approve RUN brief` từ chối khi `brief.vi.md` mới hơn `brief.en.md`, vì NotebookLM làm video từ bản tiếng Anh.
  - Hiện phiên chat `/video-short` giữ hai bản khớp nhau. Bỏ chat thì phải có cách khác.
- *(Quyết định của tôi:)* khi Tai lưu bản Việt đã sửa, trang gọi **một agent rẻ** (Haiku, ví dụ `claude -p` với `vs-researcher`
  hoặc một prompt riêng) cập nhật `brief.en.md` theo đúng chỗ sửa, rồi hiện bản Anh mới. Chi phí chỉ vài cent. Tai cũng được tự sửa
  bản Anh. Nút Duyệt chỉ bật khi bản Anh mới hơn bản Việt, đúng luật của `approve`.
- Duyệt = `vshort approve RUN brief`, rồi đưa video vào lại hàng đợi.

### Duyệt bản dịch (trạng thái `wait_script`)

- Bảng: id, câu tiếng Anh (`sentences.en.json`), lời Việt (`script.vi.json`), `note`. Giống `translation.md` mà `vshort auto` đã
  viết, nhưng sửa được lời Việt.
- Dấu `|` trong `phrases` là chỗ ngắt cụm phụ đề. Giữ nó khi sửa; *(quyết định của tôi:)* hiện mỗi cụm như một ô nhỏ hoặc hiện
  luôn dấu `|`, builder chọn cách dễ đọc hơn.
- Lưu thì chạy `vshort check RUN` và hiện lỗi cạnh câu bị lỗi.
- Nếu có `script.proposed.json` (bản đề xuất từ vòng sửa): hiện cạnh bản hiện tại, cho "Dùng bản đề xuất" (chép vào
  `script.vi.json` rồi xóa nó) hoặc "Bỏ". `approve` từ chối khi file này còn.
- Duyệt = `vshort approve RUN script` (nó tự chạy `check`), rồi vào lại hàng đợi.

### Video xong (trạng thái `done`)

- Trình phát `final.mp4` tua được, nút tải về.
- Nội dung `auto.json` → `message`: giọng, hình động, nguồn hình, kết luận soát, chi phí. Bỏ dòng `scp` vì đã có nút tải.
- `review.md` hiển thị dạng markdown.
- Bảng chi phí theo từng bước từ `cost.json`.

### Lỗi (`error` hoặc trạng thái riêng mà `vshort auto` ghi)

- Hiện `message` nguyên văn (ví dụ hướng dẫn đăng nhập lại NotebookLM) và 50 dòng cuối của `auto.log`.
- Nút "Chạy lại" đưa video vào lại hàng đợi.

## Hàng đợi

- **Chạy song song, tối đa 3 video** đang "chạy" cùng lúc (Tai muốn song song; con số 3 là *quyết định của tôi*, một hằng số trong
  `config.toml`). Lý do được làm song song: phần lớn thời gian là chờ NotebookLM và agent trên cloud. Ví dụ five-solas: brief →
  NotebookLM xong mất 31 phút, duyệt bản dịch → `final.mp4` mất 25 phút; phần máy tự tính chỉ khoảng 5 phút. Lý do giới hạn 3: lúc
  nặng nhất mỗi video cần khoảng 1,3 GB RAM, server còn khoảng 5 GB trống, 3 × 1,3 GB thì vẫn chừa chỗ cho CMS-Admin.
- **Chưa biết:** NotebookLM cho tạo mấy video cùng lúc hay mỗi ngày trên tài khoản của Tai. Builder thử với 3 video; NotebookLM từ
  chối thì đó là lỗi của video ấy (hiện `message`, "Chạy lại" sau), không làm hỏng các video khác.
- **Tranh chấp giữa các video chạy cùng lúc:** mỗi run đã có khóa riêng (`auto.lock`). Chỗ dùng chung duy nhất đã thấy là
  `publish_shapes` (git commit/push thư viện hình). Lỗi git ở đó không làm hỏng video (đã có sẵn); tệ nhất là hình mới của một video
  chưa được đưa vào thư viện. Builder kiểm còn chỗ dùng chung nào khác không.
- **Video chờ duyệt hoặc lỗi nhường chỗ:** máy chạy tiếp video kế trong hàng, không đứng chờ Tai.
- **Thứ tự:** video vừa được duyệt hoặc bấm "Chạy lại" đứng **trước** video chưa bắt đầu (*quyết định của tôi:* nó gần xong hơn).
  Trong cùng nhóm thì ai vào trước chạy trước.
- **Hàng đợi lưu trên đĩa** (ví dụ `runs_dir/queue.json`, ghi kiểu nguyên tử như `auto.set_state`), để khởi động lại tiến trình web
  không mất thứ tự. Video đã vào hàng nhưng chưa chạy thì chưa có thư mục run; builder có thể tạo sẵn run (`vshort new` + `topic`
  trong `run.json`) nếu tiện hơn.
- **Bắt đầu một video:** gọi `vshort auto <slug> --topic … [--auto]` (lần đầu) hoặc `vshort auto RUN` (chạy tiếp). Lệnh này tự chạy
  nền, tự khóa (`auto.lock`), tự ghi log. Trang không tự chạy các bước.
- **Video đã có thư mục từ trước** (chạy bằng terminal hoặc `/video-short`) vẫn hiện trong danh sách theo trạng thái của nó, không
  cần đi qua hàng đợi.

### Lỗi chung cho mọi video: tạm dừng hàng đợi

Cả mục này là quyết định của tôi.

- **Vấn đề:** có những lỗi video nào chạy cũng gặp, ví dụ NotebookLM hết phiên. Nếu cứ "nhường chỗ" thì 5 chủ đề dán buổi tối sẽ thành
  5 lỗi lúc sáng, mỗi cái phải bấm "Chạy lại", có cái còn làm research lại từ đầu.
- **Cách xử lý:**
  - Khi `vshort auto` dừng với mã `AUTH` (NotebookLM hết phiên), hàng đợi **tạm dừng**: không bắt đầu video mới.
  - Trên cùng trang hiện một băng báo lý do, hướng dẫn đăng nhập lại (`RELOGIN`) và nút "Chạy tiếp hàng đợi".
  - Video đang chạy dở thì cứ chạy tiếp.
- **Lỗi khác** (agent lỗi, quá giờ, Gemini hết lượt mà ZeroTTS cũng hỏng…) vẫn là lỗi của riêng video đó. Chỉ tạm dừng theo mã mà
  `vshort` đã gắn nhãn, không đoán theo chữ.
- **Sửa nhỏ trong `vshort`:**
  - Hiện chỉ `fetch` và `source` nhận ra NotebookLM hết phiên. Nếu phiên chết từ trước, `vs-researcher` gặp lỗi trước, bằng lệnh
    `notebooklm` của chính nó, và video dừng với lỗi chung chung.
  - Nên `vshort auto` kiểm phiên NotebookLM bằng một lệnh nhẹ qua `cli._notebooklm` **trước bước research**, hết phiên thì dừng với
    mã `AUTH` như `fetch`.
  - Chọn lệnh nào để kiểm là việc của builder.
- **Giới hạn Claude** (hết lượt dùng gói Max, mất đăng nhập) hiện chưa có mã riêng, nên vẫn là lỗi từng video. Ghi `ponytail:`: gắn
  mã riêng rồi cho tạm dừng nếu thấy xảy ra thật.

## Đọc trạng thái: dùng lại, không viết lại

- Trạng thái: `auto.get_state(run)`.
- "Đang chạy" mà tiến trình đã chết: `auto.alive_run(run)`. Đây là cách `vshort wait` đang dùng; chết thì hiện như lỗi kèm "Chạy lại".
- **Sửa nhỏ trong `vshort`** *(quyết định của tôi)*:
  - **Vấn đề:** `alive_run` và `locked_by` chỉ thử pid còn sống (`os.kill(pid, 0)`), còn `_alive` coi cả `PermissionError` là còn
    sống. Sau khi khởi động lại máy, pid cũ có thể trùng một tiến trình khác. Lúc đó trang báo "đang chạy" mãi, chiếm một chỗ chạy, và
    `vshort auto` từ chối "Chạy lại".
  - **Cách sửa:** sửa ngay trong `auto.py`, để `vshort wait` cũng được lợi. Cách cụ thể do builder chọn, miễn chạy được cả trên Mac
    lẫn Linux, ví dụ ghi kèm thời điểm tiến trình bắt đầu, hoặc kiểm pid đó đúng là `vshort`.
- Có đang khóa không: `auto.locked_by(run)`. Chi phí: `auto.total_cost(run)`. Các bước đã xong: `run.done(step)`, như `vshort status`.
- **Khi video đang chạy (đang khóa), mọi nút sửa và duyệt bị tắt.** Sửa file trong lúc agent đang ghi là hỏng dữ liệu.
- Trang tự làm mới trạng thái định kỳ (ví dụ 5–10 giây). Chưa cần WebSocket.
- *(Quyết định của tôi:)* hai người cùng sửa một video thì ai lưu sau thắng. Không khóa sửa giữa người dùng.

## An toàn (không bỏ, dù chỉ trong mạng)

- Ô chủ đề đi thẳng vào `vs-researcher`, agent có quyền chạy Bash, bằng gói Max của Tai. Trang nghe trên LAN nhà và Tailscale.
  Tailscale chỉ có máy của Tai (Tai xác nhận).
- **Mã truy cập chung cho việc tốn tiền** (Tai chọn):
  - **Không cần mã:** xem danh sách, trạng thái, video, `review.md`, chi phí.
  - **Cần mã:** mọi thao tác ghi hoặc tốn tài nguyên. Gồm thêm chủ đề, gỡ khỏi hàng đợi, lưu brief (gọi agent), lưu bản dịch,
    dùng/bỏ bản đề xuất, Duyệt, Chạy lại, Chạy tiếp hàng đợi.
  - **Cách dùng:**
    - Mã nằm trong file cấu hình trên server, ngoài git (ví dụ cạnh `.env`).
    - Nhập một lần, trình duyệt nhớ bằng cookie; Tai đưa mã cho ai thì người đó dùng được.
    - Kiểm mã **ở phía server** cho mọi lệnh ghi, không chỉ ẩn nút.
    - Lệnh ghi chỉ nhận POST, có chống CSRF; cookie `SameSite=Strict` là đủ.
  - Video và file tải về không cần mã, nên `<video>` và nút tải không phải mang cookie đặc biệt.
- Slug kiểm bằng regex ở trên, **ở phía server**, trước mọi thao tác file.
- Mọi đường dẫn file (video, ảnh, log, brief) được giải thành đường dẫn thật, và phải nằm trong `runs_dir/<slug>/`. Ngoài đó thì 404.
  Không nhận đường dẫn tùy ý từ trình duyệt.
- Mọi lệnh gọi bằng danh sách tham số (`subprocess` không qua shell). Không ghép chuỗi lệnh.

## Kiểm tra trước khi coi là xong

- `pytest` thêm vài test nhỏ cho phần logic: chọn video kế trong hàng (nhường chỗ, ưu tiên video đã duyệt), kiểm slug, chặn đường
  dẫn ra ngoài run (`../`, symlink). `tests/conftest.py` đã chặn gọi agent thật; giữ nguyên.
- Thử tay trên server:
  1. Dán 2 chủ đề với "Bỏ duyệt brief" → cả hai lần lượt tới chỗ chờ duyệt bản dịch mà không đụng terminal.
  2. Duyệt brief một video không bỏ duyệt: sửa một câu bản Việt → bản Anh được cập nhật → Duyệt chạy được → video chạy tiếp.
  3. Duyệt bản dịch có sửa một câu → video chạy tới xong.
  4. `final.mp4` **phát và tua được trên iPhone (Safari)** và trên Mac; nút tải về cho đúng file.
  5. Tắt tiến trình web giữa chừng rồi bật lại → trạng thái đúng, hàng đợi chạy tiếp. Kill tiến trình `vshort auto` → trang báo dừng
     giữa chừng, "Chạy lại" làm tiếp.
  6. NotebookLM hết phiên → trang hiện hướng dẫn đăng nhập lại; làm xong, "Chạy lại" chạy tiếp.
  7. Gọi `/files/../../etc/passwd` hoặc slug lạ → 404 hoặc báo lỗi, không đọc được gì.
  8. Trình duyệt chưa nhập mã: xem được danh sách và video. Gửi thẳng lệnh thêm chủ đề hoặc Duyệt (bằng `curl`, không qua nút) → bị
     từ chối.

## Để builder quyết

- Framework web Python (thỏa điều kiện Range), cách phục vụ file tĩnh, cấu trúc thư mục `web/`.
- Cách hiển thị markdown và cụm phụ đề, bố cục chi tiết trong khuôn shadcn/ui.
- Cách sinh slug từ chủ đề tiếng Việt hoặc link.
- Prompt cập nhật `brief.en.md`, miễn là chạy model rẻ và chỉ đổi phần tương ứng.

## Về sau (chưa thiết kế, chỉ ghi để đợt 1 không chặn)

- **Đợt 2: bảng phân cảnh sau khi có hình.**
  - Mỗi câu một khung 9:16: hình (`frames/N.png`), phụ đề (`script.vi.json`), giọng (`tts.json`), thời điểm (`timeline.json`).
  - Đổi hình: chọn khung khác của NotebookLM (`stills.json` → `t`), tư liệu thật hoặc ảnh tải lên (`visuals.json`).
  - Sửa chữ, nghe giọng, rồi dựng lại riêng các bước cuối trong vài phút.
  - Duyệt bản dịch sẽ gộp vào đây. Cần một đường "dựng lại từ chỗ đã sửa", thứ `vshort auto` chưa có.
- **Đợt 3: bảng phân cảnh lúc duyệt brief.** Lập phân cảnh từ brief. Khung do mình dựng (tiêu đề, tư liệu, hình động) xem được
  ngay, khung của NotebookLM là ô chờ kèm gợi ý cảnh. Tai chọn: NotebookLM vẫn vẽ phần lớn hình. Phải sửa pipeline (chọn tư liệu
  trước khi gen, gửi gợi ý cảnh cho NotebookLM). Chưa brainstorm chi tiết.
- **Thương mại hoá:** trang giới thiệu (stageshow), tài khoản, chuyển agent sang API.
