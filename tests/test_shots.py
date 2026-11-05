import pytest

from vshort.fit import Placement
from vshort.render import EDGE, H, MIN_ZOOM, W
from vshort.shots import (CREEP, KEEP, LEAD, SNAP, Beat, beats, camera_at, changes, frame_box, gap_problems,
                          schema_problems)

SCRIPT = [
    {"id": 3, "phrases": "Máy chủ của bạn | ở *Hà Nội* | năm 2024"},
    {"id": 4, "phrases": "Xác thực Authenticated | mã hóa Cryptography an toàn hơn 5,5 lần"},
]
POP = {"text": "Hà Nội", "box": [100, 200, 300, 280]}
MARK = {"shape": "circle", "box": [100, 300, 400, 500]}
FOCUS = (100, 100, 600, 1000)  # mid-image: its framing is not pushed against an edge, so a creep leaves the centre alone


def check(doc):
    return schema_problems(doc, SCRIPT, {3, 4}, lambda s: s == "internet")


def beat(t, **kw):
    return Beat(t, kw.get("focus", KEEP), kw.get("mark"), kw.get("doodle"), kw.get("pop"))


def test_beat_time_follows_phrase_and_at():
    p = Placement(id=3, start=10, dur=6)
    out = beats([{"phrase": 2, "at": 0.5, "mark": MARK}], "a b | c d e f", p)
    assert out[0].t == pytest.approx(10 + (2 / 6 + 0.5 * 4 / 6) * 6)


def test_beats_keep_the_three_meanings_of_focus():
    rows = [{"mark": MARK}, {"phrase": 2, "focus": None}, {"phrase": 3, "focus": [1, 2, 3, 4], "pop": POP}]
    out = beats(rows, "a | b | c", Placement(1, 0, 3))
    assert out[0].focus is KEEP and out[1].focus is None and out[2].focus == (1, 2, 3, 4)
    assert out[0].mark == MARK and out[2].pop == POP and out[0].pop is None and out[0].doodle is None


def test_a_good_plan_passes():
    plan = {"3": [
        {"focus": list(FOCUS), "mark": MARK},
        {"phrase": 2, "at": 0.5, "focus": None, "pop": POP},
        {"phrase": 3, "doodle": {"shape": "internet", "box": [500, 200, 700, 400]}, "pop": {"text": "bạn ở", "box": POP["box"]}},
    ], "4": [{"pop": {"text": "Cryptography", "box": POP["box"]}}]}  # a whole word of 12 characters: the longest allowed
    assert check(plan) == []


@pytest.mark.parametrize("doc, word", [
    ({"3": [{"phrase": 0, "focus": None}]}, "phrase 0"),
    ({"3": [{"phrase": 4, "focus": None}]}, "phrase 4"),
    ({"3": [{"at": 1.5, "focus": None}]}, "at 1.5"),
    ({"3": [{"focus": [300, 300, 100, 500]}]}, "ngược chiều"),
    ({"3": [{"mark": {"shape": "star", "box": MARK["box"]}}]}, "mark shape"),
    ({"3": [{"doodle": {"shape": "no-such-shape", "box": MARK["box"]}}]}, "thư viện"),
    ({"3": [{"pop": {"text": "Bắc Kinh", "box": POP["box"]}}]}, "nguyên văn"),
    ({"4": [{"pop": {"text": "Authenticated", "box": POP["box"]}}]}, "12 ký tự"),
    ({"3": [{"pop": {"text": "202", "box": POP["box"]}}]}, "nguyên văn"),  # a pop never cuts a number or a word short
    ({"4": [{"pop": {"text": "Authenticate", "box": POP["box"]}}]}, "nguyên văn"),
    ({"3": [{"pop": {"text": "Hà Nộ", "box": POP["box"]}}]}, "nguyên văn"),
    ({"3": [{"pop": {"text": "ủ c", "box": POP["box"]}}]}, "nguyên văn"),
    ({"4": [{"pop": {"text": "5", "box": POP["box"]}}]}, "nguyên văn"),  # "5,5" is one number
    ({"3": [{}]}, "ít nhất một"),
    ({"9": [{"focus": None}]}, "không thuộc các câu"),
    ({"3": [{"phrase": 2, "focus": None}, {"phrase": 1, "focus": None}]}, "tăng dần"),
    ({"3": [{"phrase": 1 + i // 2, "at": i % 2 * 0.5, "pop": {"text": t, "box": POP["box"]}}
            for i, t in enumerate(["Máy chủ", "Hà Nội", "2024", "bạn"])]}, "tối đa"),
], ids=["phrase-0", "phrase-too-big", "at", "box-reversed", "shape", "doodle", "pop-not-said", "pop-13-chars",
        "pop-cut-number", "pop-cut-word", "pop-cut-last-word", "pop-inside-two-words", "pop-cut-decimal", "empty-beat", "id-not-allowed", "descending", "four-pops"])
def test_schema_rejects_each_bad_field(doc, word):
    probs = check(doc)
    assert len(probs) == 1 and word in probs[0] and probs[0].startswith("shots.json câu ")


def test_a_problem_names_its_line_and_beat():
    (prob,) = check({"3": [{"focus": None}, {"phrase": 9, "focus": None}]})
    assert prob.startswith("shots.json câu 3 nhịp 2: ")


def test_short_line_needs_no_beats():
    assert gap_problems(5, 0.0, 1.8, []) == []
    assert gap_problems(5, 0.0, 2.0, []) == []
    probs = gap_problems(5, 0.0, 4.5, [1.0])
    assert len(probs) == 1 and "2,0" in probs[0]


def test_gaps_are_measured_between_changes_and_the_line_ends():
    assert gap_problems(5, 10.0, 15.5, [11.5, 13.0, 14.5]) == []
    assert len(gap_problems(5, 10.0, 15.5, [11.5, 14.0])) == 1  # only 11.5 -> 14.0 is over
    assert gap_problems(5, 10.0, 15.5, [9.8, 11.5, 13.0, 14.5]) == []  # a change just before the line counts at its start


def test_changes_come_lead_before_the_words_sorted():
    bs = [beat(5.0, mark=MARK), beat(3.0, mark=MARK)]
    assert changes(bs, [4.0]) == pytest.approx([3.0 - LEAD, 4.0, 5.0 - LEAD])


def test_tiny_focus_is_capped_and_window_stays_inside():
    s, cx, cy = frame_box((700, 1270, 704, 1274), 1.5)
    assert s == 1.5
    eps = 1e-9
    assert cx - W / s / 2 >= EDGE - eps and cx + W / s / 2 <= W - EDGE + eps
    assert cy - H / s / 2 >= -eps and cy + H / s / 2 <= H + eps


def test_frame_box_fits_the_box_with_margin_and_none_is_the_wide_shot():
    s, cx, cy = frame_box(FOCUS, 3.0)
    assert s == pytest.approx(min(W / (500 * 1.15), H / (900 * 1.15)))
    assert (cx, cy) == pytest.approx((350, 550))
    assert frame_box(None, 1.5) == pytest.approx((MIN_ZOOM, W / 2, H / 2))
    assert frame_box((0, 0, W, H), 1.5)[0] == MIN_ZOOM  # a box that is the whole picture never zooms below the edge crop
    assert frame_box((0, 0, 4, 4), 0.5)[0] == MIN_ZOOM  # a cap under the edge crop gives way to it


def test_camera_snaps_then_creeps():
    bs = [beat(5.0, focus=FOCUS)]
    want = frame_box(FOCUS, 1.5)
    assert camera_at(bs, 4.0, 4.0, 1.5) == pytest.approx((MIN_ZOOM, W / 2, H / 2))
    s, cx, cy = camera_at(bs, 4.7, 4.0, 1.5)
    assert s == pytest.approx(MIN_ZOOM * (1 + CREEP * 0.7)) and (cx, cy) == pytest.approx((W / 2, H / 2))  # wide, still drifting
    assert camera_at(bs, 5.0 - LEAD + SNAP / 2, 4.0, 1.5)[0] < want[0]  # half way
    assert camera_at(bs, 5.05, 4.0, 1.5) == pytest.approx(want)
    s, cx, cy = camera_at(bs, 6.05, 4.0, 1.5)
    assert s == pytest.approx(want[0] * (1 + CREEP)) and (cx, cy) == pytest.approx(want[1:])


def test_creep_stops_at_the_cap():
    bs = [beat(5.0, focus=(0, 0, 100, 100))]
    assert camera_at(bs, 9.0, 4.0, 1.5)[0] == 1.5


def test_keep_focus_holds_previous_framing():
    bs = [beat(5.0, focus=FOCUS), beat(7.0, mark=MARK)]
    _, cx0, cy0 = camera_at(bs, 6.9, 4.0, 1.5)
    _, cx1, cy1 = camera_at(bs, 7.5, 4.0, 1.5)
    assert (cx1, cy1) == pytest.approx((cx0, cy0)) and (cx1, cy1) == pytest.approx((350, 550))


def test_null_focus_pulls_back_to_the_wide_shot():
    bs = [beat(5.0, focus=FOCUS), beat(7.0, focus=None)]
    s, cx, cy = camera_at(bs, 7.5, 4.0, 1.5)
    assert s == pytest.approx(MIN_ZOOM * (1 + CREEP * (7.5 - (7.0 - LEAD + SNAP)))) and (cx, cy) == pytest.approx((W / 2, H / 2))
    assert camera_at(bs, 6.9, 4.0, 1.5)[0] > s


def test_a_snap_that_starts_before_the_last_one_ended_is_continuous():
    bs = [beat(5.0, focus=FOCUS), beat(5.1, focus=(300, 300, 400, 400))]  # 0.1 s apart: the second cuts into the first
    for t in (5.0 - LEAD, 5.1 - LEAD, 5.0 - LEAD + SNAP, 5.1 - LEAD + SNAP):
        assert camera_at(bs, t - 1e-9, 4.0, 1.5) == pytest.approx(camera_at(bs, t + 1e-9, 4.0, 1.5), abs=1e-4)
