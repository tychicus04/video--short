from vshort.captions import Fragment
from vshort.script import (Sentence, check_brief, check_numbers, check_script, check_style, group_sentences, merge_text,
                           merged, syllables)


def test_merge_drops_ui_label_and_scene_cut_duplicate():
    fr = [Fragment(0, 0, 1, 900, 960), Fragment(1, 1, 1.1, 900, 960), Fragment(2, 1.1, 2, 900, 960),
          Fragment(3, 2, 2.2, 900, 960)]
    out = merge_text(fr, {0: "It starts", 1: "on a page.", 2: "on a page.", 3: ""})
    assert [(f.start, f.end, f.text) for f in out] == [(0, 1, "It starts"), (1, 2, "on a page.")]


def test_group_sentences_windows():
    fr = [Fragment(0, 0, 1, 0, 0, "Imagine"), Fragment(1, 1, 2, 0, 0, "this."), Fragment(2, 2, 3.5, 0, 0, "Update now!")]
    s = group_sentences(fr)
    assert [(x.start, x.end, x.en) for x in s] == [(0, 2, "Imagine this."), (2, 3.5, "Update now!")]


def test_sentence_ends_inside_closing_quote():
    fr = [Fragment(0, 0, 1, 0, 0, '"Quantum-safe,'), Fragment(1, 1, 2, 0, 0, 'no rebuild."'), Fragment(2, 2, 3, 0, 0, "We use it.")]
    assert [x.en for x in group_sentences(fr)] == ['"Quantum-safe, no rebuild."', "We use it."]


def test_number_cut_across_captions_is_not_a_sentence_end():
    fr = [Fragment(0, 0, 1, 0, 0, "draining 2."), Fragment(1, 1, 2, 0, 0, "7 million dollars."),
          Fragment(2, 2, 3, 0, 0, "Since 2026."), Fragment(3, 3, 4, 0, 0, "3 firms left.")]
    assert [x.en for x in group_sentences(fr)] == ["draining 2.7 million dollars.", "Since 2026.", "3 firms left."]


def test_syllables():
    assert syllables("Đó là tấn công | *Zero-click.*") == 7
    assert syllables("Anthropic: AI viết exploit root Linux") == 11
    assert syllables("CVE-2026-98432, người dùng") == 3 + 7 + 9 + 2


def test_syllables_reads_numbers_aloud():
    # bảy trăm | hai nghìn không trăm hai mươi sáu | hai mươi chín | mười | một trăm linh năm | một nghìn
    assert [syllables(n) for n in ["700", "2026", "29", "10", "105", "1000", "0"]] == [2, 7, 3, 1, 4, 2, 1]
    assert syllables("từ hơn 700 ví") == 5
    assert syllables("2,7 triệu") == 4  # hai phẩy bảy triệu
    assert syllables("5.500 ví") == 5  # năm nghìn năm trăm ví


def test_check_script_reports_problems():
    s = [Sentence(1, 0, 3, "a"), Sentence(2, 3, 4, "b")]
    probs = check_script(s, [{"id": 1, "phrases": "Câu đầu | bị chia", "note": ""}])
    assert any("câu đầu" in p.lower() for p in probs) and any("Thiếu câu 2" in p for p in probs)


def test_long_sentence_is_fine_but_wide_phrase_is_not():
    s = [Sentence(1, 0, 3, "a"), Sentence(2, 3, 3.5, "b")]
    long_ok = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "một hai ba bốn năm sáu | bảy tám chín mười mười một"}]
    assert check_script(s, long_ok) == []
    wide = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "chữ " * 40}]
    assert any("vượt" in p for p in check_script(s, wide))


def test_title_takes_the_time_of_the_sentences_left_empty_after_it():
    s = [Sentence(1, 0, 1.3, "No link tapped."), Sentence(2, 1.3, 2.7, "No app installed."), Sentence(3, 2.7, 8, "A chain.")]
    script = [{"id": 1, "phrases": "iPhone bị hack chỉ vì mở một trang web"}, {"id": 2, "phrases": ""},
              {"id": 3, "phrases": "Một chuỗi khai thác."}]
    assert [(x.id, x.start, x.end) for x in merged(s, script)] == [(1, 0, 2.7), (3, 2.7, 8)]
    assert check_script(s, script) == []
    script[0]["phrases"] = " "
    assert any("tiêu đề" in p for p in check_script(s, script))

BRIEF = "Câu chốt\nPhá cả hai phần.\nLời kêu gọi\nHãy hỏi đội IT, và chia sẻ video này.\n"
CTA = {"id": 3, "phrases": "Hãy hỏi đội IT, | và chia sẻ video này."}


def test_absolute_words_need_a_note_about_that_word():
    script = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "vẫn hoàn toàn | không đọc được", "note": ""}, CTA]
    assert check_brief(script, BRIEF) == [("Câu 2: có 'hoàn toàn' — brief thường cấm khẳng định tuyệt đối; "
                                           "bỏ, viết lại theo mục Lưu ý của brief, hoặc ghi note nhắc 'hoàn toàn' và vì sao giữ")]
    script[1]["note"] = "Dùng nhãn Apple tiếng Việt 'Chế độ phong tỏa'."
    assert len(check_brief(script, BRIEF)) == 1
    script[1]["note"] = "Giữ 'hoàn toàn': nguồn nói đúng như vậy."
    assert check_brief(script, BRIEF) == []


def test_last_line_ends_with_the_approved_call_to_action():
    script = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "Không mở được cửa đó."}]
    assert check_brief(script, BRIEF) == [("Câu 2 là câu cuối nhưng không kết bằng nguyên văn lời kêu gọi trong brief "
                                           "('Hãy hỏi đội IT, và chia sẻ video này.'); nếu câu tiếng Anh là câu chốt "
                                           "thì giữ nó và nối lời kêu gọi sau, hoặc ghi note vì sao khác")]
    script[1]["phrases"] = "Không mở được cửa đó. | Hãy hỏi đội IT, |  và chia sẻ video này."
    assert check_brief(script, BRIEF) == []
    script[1] = {"id": 2, "phrases": "Hãy hỏi đội IT.", "note": "Font không có dấu →, đổi thành ›."}
    assert check_brief(script, BRIEF) == []
    assert check_brief([{"id": 1, "phrases": "Tiêu đề"}], "Câu chốt\nPhá cả hai phần.\n") == []


def test_call_to_action_heading_may_be_marked_up():
    script = [{"id": 1, "phrases": "Tiêu đề"}, {"id": 2, "phrases": "Không mở được cửa đó."}]
    for head in ("## Lời kêu gọi", "**Lời kêu gọi**", "Lời kêu gọi:", "Lời kêu gọi\n"):
        brief = f'Câu chốt\nPhá cả hai phần.\n{head}\n"Hãy hỏi đội IT, và chia sẻ video này."\n'
        assert len(check_brief(script, brief)) == 1, head


def test_translationese_needs_rewording_or_a_note():
    script = [{"id": 2, "phrases": "phải chấp nhận một cách mù quáng | các yêu cầu TCP", "note": ""},
              {"id": 3, "phrases": "bị nhắm tới bởi các gói tin | được thiết kế đặc biệt"},
              {"id": 4, "phrases": "Lấy “chỉ Kinh Thánh” | làm ví dụ."},
              {"id": 5, "phrases": "Có một cách khác, | bởi vì máy chủ | được vá bởi vì lỗi đã lộ."}]
    assert [p.split(" là văn dịch")[0] for p in check_style(script)] == [
        "Câu 2: 'một cách'", "Câu 3: 'bị nhắm tới bởi'", "Câu 4: 'lấy “chỉ kinh thánh” làm ví dụ'"]
    script[0]["note"] = "Giữ 'một cách' vì brief dùng đúng chữ này."
    assert len(check_style(script)) == 2



def test_numbers_said_in_english_are_said_in_vietnamese():
    # polymarket: "2.7" written "2,7", one English sentence spread over two lines, the second left empty
    sents = [Sentence(1, 0, 2, "CVE-2026-98432 explained."), Sentence(2, 2, 6, "On October 29th, it drained 2.7 million"),
             Sentence(3, 6, 8, "from over 700 wallets.")]
    script = [{"id": 1, "phrases": "AI viết exploit"}, {"id": 2, "phrases": "Ngày 29 tháng 10, rút 2,7 triệu đô | từ hơn 700 ví."},
              {"id": 3, "phrases": ""}]
    assert check_numbers(sents, script) == []  # the title is the brief's; "tháng 10" for "October" is fine
    script[1]["phrases"] = "Ngày 29 tháng 10, rút 27 triệu đô | từ hàng trăm ví."
    assert check_numbers(sents, script) == [
        "Câu 2: câu tiếng Anh có số 700 mà lời Việt không có; giữ đúng số, hoặc ghi note nhắc số đó và vì sao bỏ"]
    script[1]["note"] = "Bỏ 700 cho gọn."
    assert check_numbers(sents, script) == []
    script[1]["phrases"] = "Ngày 29 tháng 10, rút 7,2 triệu đô | từ hơn 700 ví."
    assert check_numbers(sents, script)[0].startswith("Câu 2: câu tiếng Anh có số 27 ")  # a changed figure


RAILS_16_VI = ("Một ảnh độc | là đủ để ghi file lạ; | một lần cập nhật | là đủ để chặn. | Nếu app Rails của bạn | "
               "xử lý ảnh bằng ImageMagick: | nâng lên 8.1.4.1 | hoặc 8.0.5.2 ngay, | đổi bí mật nếu dùng Disk, | "
               "và chia sẻ cho | người làm backend. | Bản 8.0 không còn | được vá bảo mật | sau 07/11/2026.")


def _two(vi: str, start: float = 75.63, end: float = 81.07) -> list[str]:
    sents = [Sentence(1, 0.1, 2.67, "Rails writes any file."),
             Sentence(16, start, end, "One bad image was enough to write files; one update is enough to stop it.")]
    return check_script(sents, [{"id": 1, "phrases": "Ảnh độc upload, Rails ghi file tùy ý", "note": ""},
                                {"id": 16, "phrases": vi, "note": ""}])


def test_rails_closing_line_with_repeated_call_to_action_fails():
    probs = [p for p in _two(RAILS_16_VI) if p.startswith("Câu 16: lời Việt")]
    assert len(probs) == 1 and "đừng nối ý mà video tiếng Anh đã nói ở câu khác" in probs[0]


def test_ordinary_line_passes():
    assert not [p for p in _two("Một ảnh độc | là đủ để ghi file lạ; | một lần cập nhật | là đủ để chặn.")
                if "lời Việt" in p]


def test_title_line_is_exempt():
    sents = [Sentence(1, 0.1, 0.9, "Rails.")]
    assert not [p for p in check_script(sents, [{"id": 1, "phrases": RAILS_16_VI.replace(" |", ","), "note": ""}])
                if "lời Việt" in p]
