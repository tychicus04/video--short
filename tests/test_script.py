from vshort.captions import Fragment
from vshort.script import Sentence, check_brief, check_script, group_sentences, merge_text, merged, syllables


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

def test_syllables():
    assert syllables("Đó là tấn công | *Zero-click.*") == 7
    assert syllables("Anthropic: AI viết exploit root Linux") == 11
    assert syllables("CVE-2026-98432, người dùng") == 3 + 8 + 10 + 2


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
