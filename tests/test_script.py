from vshort.captions import Fragment
from vshort.script import Sentence, budget, check_script, group_sentences, merge_text, merged, syllables


def test_merge_drops_ui_label_and_scene_cut_duplicate():
    fr = [Fragment(0, 0, 1, 900, 960), Fragment(1, 1, 1.1, 900, 960), Fragment(2, 1.1, 2, 900, 960),
          Fragment(3, 2, 2.2, 900, 960)]
    out = merge_text(fr, {0: "It starts", 1: "on a page.", 2: "on a page.", 3: ""})
    assert [(f.start, f.end, f.text) for f in out] == [(0, 1, "It starts"), (1, 2, "on a page.")]


def test_group_sentences_windows():
    fr = [Fragment(0, 0, 1, 0, 0, "Imagine"), Fragment(1, 1, 2, 0, 0, "this."), Fragment(2, 2, 3.5, 0, 0, "Update now!")]
    s = group_sentences(fr)
    assert [(x.start, x.end, x.en) for x in s] == [(0, 2, "Imagine this."), (2, 3.5, "Update now!")]


def test_budget_and_syllables():
    assert syllables("Đó là tấn công | *Zero-click.*") == 5
    assert budget(Sentence(1, 0.0, 2.0, "x"), rate=5.0) == 9


def test_check_script_reports_problems():
    s = [Sentence(1, 0, 3, "a"), Sentence(2, 3, 4, "b")]
    probs = check_script(s, [{"id": 1, "phrases": "Câu đầu | bị chia", "note": ""},
                             {"id": 2, "phrases": "một hai ba bốn năm sáu bảy tám chín mười", "note": ""}], rate=5.0)
    assert any("câu đầu" in p.lower() for p in probs) and any("quá dài" in p for p in probs)


def test_title_takes_the_time_of_the_sentences_left_empty_after_it():
    s = [Sentence(1, 0, 1.3, "No link tapped."), Sentence(2, 1.3, 2.7, "No app installed."), Sentence(3, 2.7, 8, "A chain.")]
    script = [{"id": 1, "phrases": "iPhone bị hack chỉ vì mở một trang web"}, {"id": 2, "phrases": ""},
              {"id": 3, "phrases": "Một chuỗi khai thác."}]
    assert [(x.id, x.start, x.end) for x in merged(s, script)] == [(1, 0, 2.7), (3, 2.7, 8)]
    assert check_script(s, script, rate=4.0) == []  # 9 syllables fit 2.7 s, not 1.3 s
    script[0]["phrases"] = " "
    assert any("tiêu đề" in p for p in check_script(s, script, rate=4.0))
