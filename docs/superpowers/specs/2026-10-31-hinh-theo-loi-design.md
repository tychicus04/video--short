# Hình theo lời – bỏ khoảng lặng, chuyển động mượt, thêm tư liệu thật (thiết kế)

Bổ sung cho `DESIGN.md`. Chỗ nào khác `DESIGN.md` thì theo tài liệu này.

## Vì sao

Lần chạy thử video Coruna & DarkSword (31/10) cho ra video đúng quy trình, nhưng Tai thấy ba điều chưa được:

1. **Nhiều đoạn nghỉ nói quá lâu.** 20 trên 85 giây là im lặng. Lý do: câu tiếng Việt đọc ngắn hơn câu tiếng
   Anh khoảng 30%, mà mỗi câu Việt lại phải bắt đầu đúng mốc câu Anh, nên phần dư thành lặng (dài nhất 2,6 giây).
2. **Animation của NotebookLM giật và xấu.** Hình hiện dần từng phần, có lúc gần như trắng trơn (giây 22 chỉ
   còn viền mờ một chiếc điện thoại).
3. **Chỉ có hình minh họa chung chung.** Tai muốn tìm thêm tư liệu thật (hình cần thiết, có thật) rồi vẽ lại,
   thay vì chỉ dùng hình NotebookLM tự vẽ.

## Ý tưởng chính

**Đảo chiều: hình chạy theo lời, thay vì lời chạy theo hình.** Giọng Việt đọc liền mạch với nhịp tự nhiên; mỗi
câu có một đoạn hình dài đúng bằng câu đó. Hình mỗi đoạn là một khung tĩnh (từ NotebookLM, hoặc tư liệu thật đã vẽ
lại) với chuyển động chậm, mượt do mình tạo, chứ không dùng animation gốc.

## Mục tiêu

1. **Dòng thời gian mới.** Mỗi dòng có chữ trong `script.vi.json` là một đoạn. Đoạn dài bằng giọng đọc của câu đó
   cộng một nhịp nghỉ ngắn cố định. Giọng giữ tốc độ gốc, không tăng tốc. Độ dài video bằng tổng các đoạn
   (với Coruna khoảng 65 giây thay vì 85).
2. **Hình mặc định của mỗi đoạn** là một khung tĩnh lấy từ video NotebookLM, trong khung giờ tiếng Anh của câu đó
   (gồm cả khung giờ của các câu tiếng Anh để trống nhường cho nó, như câu tiêu đề). Chọn khung lúc hình đã vẽ
   xong: không lấy khung gần trắng, khung đang hiện dần hay khung đang chuyển cảnh. Khung đã xóa sạch phụ đề tiếng
   Anh cũ và watermark.
3. **Chuyển động.** Mỗi đoạn zoom hoặc trượt chậm trên khung tĩnh, mượt tới từng khung hình (không nhảy bậc từng
   pixel). Hướng chuyển động đổi giữa các đoạn liền nhau cho đỡ đều đều. Hai đoạn nối nhau bằng mờ chồng ngắn. Khi
   nhiều câu liền nhau cùng một cảnh NotebookLM, các khung tĩnh nối tiếp nhau cho thấy hình được "dựng dần", thay
   cho animation gốc.
4. **Tư liệu thật.** Một bước mới sau khi dịch: agent `vs-visuals` chọn 3–5 câu mà hình thật giúp người xem tin
   hơn hoặc hiểu hơn (ví dụ: màn hình Cài đặt iOS tiếng Việt khi lời kêu gọi cập nhật; trang báo cáo của Google/iVerify
   khi nói ai phát hiện; trang GitHub khi nói mã bị đăng công khai; ảnh trong bài báo gốc). Agent tìm tư liệu từ
   `sources.md` hoặc nguồn chính thức khác, vẽ lại theo phong cách video, và hình đó thay khung tĩnh của câu đó.
   Hai cách vẽ lại, đều miễn phí:
   - **Giao diện và trang chữ** (màn hình điện thoại, tiêu đề báo cáo, trang GitHub, mốc thời gian): agent vẽ lại
     bằng SVG theo kiểu NotebookLM (nét xám như bút chì trên nền giấy kem, khung mảnh, điểm màu nhạt), chép đúng
     từng chữ và con số từ nguồn; giao diện iOS dùng nhãn tiếng Việt thật.
   - **Ảnh chụp thật** (ảnh minh họa của bài báo/báo cáo, ảnh sản phẩm): tải về, chuyển thành nét chì bằng bộ lọc
     ảnh thông thường (không dùng AI), đặt trên nền giấy cùng kiểu khung.

   Mỗi hình ghi lại: câu id, loại, URL nguồn, ngày truy cập, đã vẽ lại những gì. Danh sách này có trong báo cáo cuối.
   Trong chính hình vẽ lại có một dòng nguồn nhỏ (ví dụ "Nguồn: Google Threat Intelligence") vẽ như một phần của
   hình, nằm ngoài vùng phụ đề và góc watermark *(Claude quyết)*.
   Tư liệu có thể chỉ đường tới mã tấn công (tên/chủ repo, URL tải mã) thì bỏ đi hoặc che, không chép; ghi việc đã
   bỏ vào danh sách *(Claude quyết, vì luật "không hướng dẫn tấn công" thắng luật "chép đúng từng chữ")*.
5. **Sửa chữ sai trong hình NotebookLM.** Khi chữ trên khung tĩnh mâu thuẫn với lời Việt hoặc brief (Coruna:
   thanh địa chỉ ghi "untrusted-site.com" suốt giây 22–79 trong khi lời nói trang web hợp pháp bị nhiễm ngầm; nút
   "iOS 18.7.6+" trong khi brief khuyên 26.3.1), bước tư liệu vá lại chữ đó: phủ nền cùng màu rồi viết chữ đúng,
   cùng cỡ và kiểu chữ gần nhất, giống hệt nhau trên mọi khung tĩnh của cảnh đó. Vì vậy bước tư liệu chạy sau khi
   đã chọn xong và làm sạch khung tĩnh. Chữ thay thế không được trỏ tới một trang web có thật (dùng tên chung như
   "tin-tuc.example") *(Claude quyết)*. Sai về nét vẽ (không phải chữ) vẫn chỉ báo cáo. Mọi chỗ vá ghi vào danh
   sách trong báo cáo cuối. Chữ tiếng Anh không sai (nhãn "OS Kernel"…) giữ nguyên.
6. **Phụ đề** giữ kiểu vừa làm xong (hộp xám, chữ viết tay, tâm ở y=1150, câu đầu là tiêu đề hiện trọn), mốc thời
   gian theo dòng thời gian mới.
7. **Soát cuối** kiểm thêm: chuyển động mượt, không có khung gần trắng, không khoảng lặng dài, chữ/số trong mỗi
   hình vẽ lại khớp nguồn của nó, và chỗ vá chữ không lộ viền.

## Hệ quả lên quy trình cũ

- **Bỏ ép câu Việt vừa khung giây tiếng Anh.** Không còn số âm tiết tối đa cho từng câu, không còn vòng "câu quá dài
  → rút gọn" (mã 3), không còn tăng tốc giọng (`max_tempo`). Dịch sát nghĩa vẫn là luật số một; câu Việt dài hay
  ngắn hơn câu Anh đều được, đoạn hình co giãn theo. Vì thế `syllables_per_sec` cũng không cần nữa, và lỗi cũ
  "`tts` tự sửa `config.toml`" biến mất theo.
- Quy tắc "các câu tiếng Anh liền sau tiêu đề có thể để trống" vẫn giữ. Nó không còn để lấy giây cho tiêu đề, mà
  để tiêu đề không bị lặp ý với các câu đó; khung giờ của chúng vẫn là nguồn khung tĩnh cho đoạn tiêu đề.
- Dò phụ đề cũ, đọc chữ, ảnh nền sạch, xóa watermark vẫn cần (để có khung tĩnh sạch). Đoạn logo cuối tự biến mất vì
  không lấy khung nào sau câu cuối.

## Không làm

- Vẽ lại bằng AI tạo ảnh (Gemini image). Tai sẽ cân nhắc trả phí sau; khi đó chỉ thay cách "vẽ lại" của bước
  tư liệu, còn đầu vào (tư liệu thật + câu) và đầu ra (một hình 720×1280 cho một câu) giữ nguyên. Không dựng sẵn
  gì cho việc đó bây giờ.
- Video AI (Veo, NotebookLM cinematic – cần gói Ultra).
- Nhạc nền, hiệu ứng âm thanh.
- Giữ lại animation gốc của NotebookLM ở bất kỳ đoạn nào.

## Thất bại dù vẫn chạy được

- Chuyển động giật, nhảy bậc, hoặc zoom tới mức hình vỡ nét.
- Phụ đề tiếng Anh cũ hoặc watermark lộ ra ở bất kỳ khung nào.
- Hình vẽ lại sai chữ/số so với nguồn, hoặc vẽ thứ nguồn không có rồi trình bày như thật (bịa giao diện, bịa tiêu
  đề báo, bịa ngày).
- Khoảng lặng dài giữa các câu, hoặc giọng bị ngắt cụt.
- Hình tư liệu lệch hẳn phong cách, nhìn như ảnh lạ dán vào.
- Dùng nguyên ảnh có bản quyền mà không vẽ lại / không ghi nguồn.
- Tư liệu mang tính hướng dẫn tấn công.

## Ràng buộc

- Server `ubuntu-pve2`: Ubuntu 26.04, không màn hình, chỉ CPU. Playwright/Chromium không chạy được, nên không chụp
  màn hình trang web; tư liệu lấy bằng tải HTTP (trang HTML, ảnh).
- Có sẵn `librsvg`/`libcairo` của hệ thống. Python hiện có numpy, pillow, imageio-ffmpeg (có libass, libx264),
  torch, google-genai; không có OpenCV. Thêm thư viện thì cài vào `~/video-pipeline` như các thứ khác.
- Gemini gói miễn phí: không vẽ được ảnh (hạn mức 0); TTS 10 lần/ngày mỗi model, mỗi video vẫn 1 lần gọi.
- Video NotebookLM 720×1280, 30 fps. Font phụ đề Patrick Hand.
- Làm thẳng trên nhánh `main` của `~/video-pipeline` (Tai không muốn nhánh riêng).

## Phần đã quyết

Tai quyết:
- Giữ miễn phí trước; có thể chuyển sang Gemini vẽ ảnh (trả phí) sau.
- Tìm tư liệu thật rồi vẽ lại, không chỉ dùng hình NotebookLM; bỏ animation giật của NotebookLM.
- Phụ đề kiểu NotebookLM, cố định một chỗ, câu đầu là tiêu đề (đã làm, commit `63cee33`).
- Tự vá chữ sai trong hình NotebookLM; sai về nét vẽ chỉ báo cáo.

Claude đề xuất (Tai giao "bạn thấy hợp lí là được"):
- Hình theo lời; mọi đoạn là khung tĩnh có chuyển động mượt; nối bằng mờ chồng.
- Bỏ ép câu Việt vừa khung giây tiếng Anh.
- 3–5 hình tư liệu mỗi video; giao diện/trang chữ vẽ bằng SVG, ảnh chụp dùng bộ lọc nét chì.

## Để người dựng tự quyết

- Cách chọn thời điểm khung tĩnh trong khung giờ của câu.
- Độ dài nhịp nghỉ giữa câu (khoảng 0,2–0,4 giây) và độ dài mờ chồng.
- Mức zoom/trượt (gợi ý không quá ~10%), kiểu đổi hướng, cách vẽ để mượt tới từng khung.
- Xóa phụ đề cũ trên khung tĩnh bằng ảnh nền sạch sẵn có hay LaMa trực tiếp trên khung đó. Lưu ý: ở Coruna, miếng
  vá LaMa p02 (giây 15,7–21,8) làm nhòe mấy dòng chữ bài báo nằm sát phụ đề cũ; khung tĩnh phóng to sẽ lộ rõ hơn.
- Cách tìm vị trí chữ cần vá (agent ước lượng trên ảnh, script dò chính xác viền chữ…).
- Cách render SVG (librsvg, cairosvg…), cách làm nét SVG trông như vẽ tay, thông số bộ lọc nét chì.
- Cách `vs-visuals` tìm và chọn tư liệu, cấu trúc file trung gian, tên lệnh mới.
