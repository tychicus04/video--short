import numpy as np
import pytest
from PIL import Image, ImageChops

from vshort.fit import Placement
from vshort.render import EDGE, H, MIN_ZOOM, W
from vshort.shots import (CREEP, DRAW, FADE, KEEP, LEAD, POP_PEAK, POP_T, SHAPES, SNAP, Beat, beats, camera_at, changes,
                          draw_overlays, frame_box, gap_problems, image_problems, ink_share, overlay_bbox, overlay_strokes,
                          schema_problems, to_screen)
from vshort.visuals import PAPER

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


# ---- pencil marks, doodles, pops and their picture checks ----

BOXES = {"middle": [250, 500, 470, 700], "edge": [0, 0, 120, 90], "far corner": [600, 1190, 720, 1280]}


def paper(w=720, h=1280):
    return Image.new("RGB", (w, h), PAPER)


def changed(a, b, box=None, tol=2):
    """Pixels where two images differ by more than tol (in a box of the 720x1280 frame)."""
    d = np.abs(np.asarray(a).astype(int) - np.asarray(b).astype(int)).max(2) > tol
    if box:
        k = a.width / 720
        x0, y0, x1, y1 = (int(v * k) for v in box)
        d = d[y0:y1, x0:x1]
    return int(d.sum())


def darkness(a, b, box):
    """How much ink a drawing adds to a box of the picture, as the sum of the differences."""
    x0, y0, x1, y1 = box
    return int(np.abs(np.asarray(a).astype(int) - np.asarray(b).astype(int))[y0:y1, x0:x1].sum())


def ink_bbox(a, b):
    return ImageChops.difference(a, b).convert("L").point(lambda v: 255 * (v > 2)).getbbox()


@pytest.mark.parametrize("where", BOXES)
@pytest.mark.parametrize("shape", SHAPES)
def test_each_mark_shape_has_strokes_inside_the_image(shape, where):
    strokes = overlay_strokes(beat(5.0, mark={"shape": shape, "box": BOXES[where]}))
    assert strokes and all(len(s) >= 2 for s in strokes)
    assert all(0 <= x <= 720 and 0 <= y <= 1280 for s in strokes for x, y in s)


def test_a_doodle_is_the_library_shape_scaled_into_its_box():
    box = [100, 200, 400, 420]
    strokes = overlay_strokes(beat(5.0, doodle={"shape": "internet", "box": box}))
    xs, ys = [p[0] for s in strokes for p in s], [p[1] for s in strokes for p in s]
    assert box[0] - 1 <= min(xs) and max(xs) <= box[2] + 1 and box[1] - 1 <= min(ys) and max(ys) <= box[3] + 1
    assert (max(xs) - min(xs) > 0.9 * (box[2] - box[0])) or (max(ys) - min(ys) > 0.9 * (box[3] - box[1]))
    assert overlay_strokes(beat(5.0, doodle={"shape": "no-such-shape", "box": box})) == []


def test_strokes_scale_with_the_image():
    b = beat(5.0, mark={"shape": "circle", "box": BOXES["middle"]})
    one, two = overlay_strokes(b), overlay_strokes(b, (1440, 2560))
    assert np.array(two) == pytest.approx(2 * np.array(one))


@pytest.mark.parametrize("ink_side, tail_is", [("left", "right"), ("right", "left")])
def test_arrow_comes_from_the_emptier_side(ink_side, tail_is):
    box = [250, 500, 470, 700]
    img = paper()
    patch = (60, 480, 240, 720) if ink_side == "left" else (480, 480, 660, 720)
    img.paste((20, 20, 20), patch)
    strokes = overlay_strokes(beat(5.0, mark={"shape": "arrow", "box": box}), img=img)
    (tx, ty) = strokes[0][0]
    assert (tx > box[2]) if tail_is == "right" else (tx < box[0])
    # the shaft is ~140 px long, ends 10 px from the box, and two barbs make the head
    shaft = strokes[0]
    assert 125 <= sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(shaft, shaft[1:])) <= 155
    gap = (shaft[-1][0] - box[2]) if tail_is == "right" else (box[0] - shaft[-1][0])
    assert gap == pytest.approx(10, abs=1.5) and len(strokes) == 3


def test_arrow_does_not_come_from_a_side_with_no_room():
    box = [10, 500, 230, 700]  # 10 px from the left edge: the tail cannot be there even if the right is full of ink
    img = paper()
    img.paste((20, 20, 20), (240, 480, 420, 720))
    strokes = overlay_strokes(beat(5.0, mark={"shape": "arrow", "box": box}), img=img)
    assert all(0 <= x <= 720 and 0 <= y <= 1280 for s in strokes for x, y in s)
    assert strokes[0][0][1] > box[3]  # right is full of ink and left has no room: it comes from below


def test_mark_draws_on_then_fades_when_the_next_mark_starts():
    first, second = [200, 500, 500, 700], [200, 800, 500, 850]
    bs = [beat(5.0, mark={"shape": "circle", "box": first}), beat(8.0, mark={"shape": "underline", "box": second})]
    img, s = paper(), 5.0 - LEAD
    assert draw_overlays(img, bs, s - 0.01) is img
    half, full = draw_overlays(img, bs, s + DRAW / 2), draw_overlays(img, bs, s + DRAW)
    assert 0 < changed(half, img) < changed(full, img)
    assert changed(full, img, first) > 500 and changed(full, img, [0, 760, 720, 900]) == 0
    assert changed(draw_overlays(img, bs, 8.0 - LEAD - 0.01), img, first) == changed(full, img, first)  # held till then
    mid = darkness(draw_overlays(img, bs, 8.0 - LEAD + FADE / 2), img, first)
    assert 0.3 * darkness(full, img, first) < mid < 0.7 * darkness(full, img, first)  # half gone
    assert changed(draw_overlays(img, bs, 8.0 - LEAD + FADE), img, first, tol=2) == 0
    assert changed(draw_overlays(img, bs, 8.0 - LEAD + FADE), img, second) > 0  # the new mark is up


def test_drawing_never_touches_the_picture_it_is_given():
    img = paper()
    before = img.copy()
    out = draw_overlays(img, [beat(5.0, mark={"shape": "cross", "box": BOXES["middle"]})], 6.0)
    assert out is not img and ImageChops.difference(img, before).getbbox() is None


def test_doodle_and_pop_stay_to_the_end_of_the_line():
    bs = [beat(5.0, doodle={"shape": "internet", "box": [100, 200, 300, 400]}, pop={"text": "2024", "box": [400, 200, 600, 280]}),
          beat(8.0, mark={"shape": "tick", "box": BOXES["middle"]})]
    img = paper()
    a, b = draw_overlays(img, bs, 5.0 - LEAD + 1.0), draw_overlays(img, bs, 12.0)
    assert changed(a, img, [100, 200, 300, 400]) > 300 and changed(a, img, [400, 200, 600, 280]) > 100
    assert changed(b, img, [100, 200, 300, 400]) == changed(a, img, [100, 200, 300, 400])
    assert changed(b, img, [400, 200, 600, 280]) == changed(a, img, [400, 200, 600, 280])


def test_pop_text_bounces_in():
    box = [200, 300, 520, 400]
    bs = [beat(5.0, pop={"text": "2024", "box": box})]
    img, s = paper(), 5.0 - LEAD
    start, peak, rest = (ink_bbox(draw_overlays(img, bs, s + dt), img) for dt in (0.02, POP_T * POP_PEAK, POP_T + 0.1))
    size = lambda bb: (bb[2] - bb[0]) * (bb[3] - bb[1])
    assert size(start) < size(rest) < size(peak)
    assert 1.04 < (peak[2] - peak[0]) / (rest[2] - rest[0]) < 1.12
    # the lettering is ~80 % of its box high, inside the box, and the box centre is the text centre
    assert box[0] <= rest[0] and rest[2] <= box[2] and box[1] <= rest[1] and rest[3] <= box[3]
    assert 0.6 * (box[3] - box[1]) < rest[3] - rest[1]
    assert abs((rest[0] + rest[2]) / 2 - 360) < 6 and abs((rest[1] + rest[3]) / 2 - 350) < 8


def test_a_long_pop_shrinks_to_its_box_width():
    box = [200, 300, 400, 400]  # 200 x 100: "Cryptography" at 80 % of 100 px high would be wider
    rest = ink_bbox(draw_overlays(paper(), [beat(5.0, pop={"text": "Cryptography", "box": box})], 9.0), paper())
    assert box[0] <= rest[0] and rest[2] <= box[2]


def test_overlays_on_a_card_frame_land_in_the_same_place_at_twice_the_size():
    bs = [beat(5.0, mark={"shape": "circle", "box": BOXES["middle"]}, pop={"text": "2024", "box": [100, 100, 300, 180]})]
    small, big = (draw_overlays(paper(k * 720, k * 1280), bs, 7.0) for k in (1, 2))
    a, b = ink_bbox(small, paper()), ink_bbox(big, paper(1440, 2560))
    assert b == pytest.approx([2 * v for v in a], abs=4)
    assert overlay_bbox(bs[0], (1440, 2560)) == pytest.approx([2 * v for v in overlay_bbox(bs[0])])
    assert max(abs(x - y) for x, y in zip(a, overlay_bbox(bs[0]))) < 8  # the bbox is where the ink is (give or take the pencil)


def test_overlay_bbox_covers_the_strokes_and_is_none_without_overlays():
    assert overlay_bbox(beat(5.0, focus=FOCUS)) is None
    x0, y0, x1, y1 = overlay_bbox(beat(5.0, mark={"shape": "underline", "box": [100, 300, 400, 340]}))
    assert x0 < 100 and x1 > 400 and y0 < 345 < y1


def test_ink_share_counts_pixels_that_differ_from_the_paper():
    img = paper()
    assert ink_share(img, [0, 0, 100, 100]) == 0
    img.paste((30, 30, 30), (0, 0, 50, 100))
    assert ink_share(img, [0, 0, 100, 100]) == pytest.approx(0.5)
    img.paste((PAPER[0] - 30, PAPER[1], PAPER[2]), (50, 0, 100, 100))  # a little off the paper colour is not ink
    assert ink_share(img, [0, 0, 100, 100]) == pytest.approx(0.5)
    assert ink_share(img, [0, 0, 100, 100]) == ink_share(img.resize((1440, 2560), Image.NEAREST), [0, 0, 100, 100])
    assert ink_share(img, [700, 1270, 720, 1280]) == 0 and ink_share(img, [5, 5, 5, 9]) == 0


def test_to_screen_follows_the_camera_like_render_draw():
    assert to_screen((100, 200, 300, 400), (1.0, 360, 640)) == pytest.approx((100, 200, 300, 400))
    assert to_screen((360, 640, 400, 700), (2.0, 360, 640)) == pytest.approx((360, 640, 440, 760))
    # a camera asking for a window off the picture is pulled back inside, exactly as draw() does
    assert to_screen((0, 0, 100, 100), (2.0, 0, 0)) == pytest.approx((0, 0, 200, 200))
    assert to_screen((620, 1180, 720, 1280), (2.0, 720, 1280)) == pytest.approx((520, 1080, 720, 1280))


WIDE = lambda t: (MIN_ZOOM, W / 2, H / 2)


def test_image_checks():
    ink = paper()
    ink.paste((40, 40, 40), (100, 300, 700, 700))  # a big dark picture
    mark = lambda box, shape="circle": beat(5.0, mark={"shape": shape, "box": box})
    # a mark needs ink under it, a doodle and a pop need paper
    (p,) = image_problems(7, [mark([200, 800, 400, 900])], ink, WIDE)
    assert p.startswith("shots.json câu 7 nhịp 1: ") and "giấy trống" in p
    assert image_problems(7, [mark([200, 400, 400, 500])], ink, WIDE) == []
    doodle = beat(5.0, doodle={"shape": "internet", "box": [200, 400, 400, 560]})
    (p,) = image_problems(7, [beat(4.0, focus=None), doodle], ink, WIDE)
    assert p.startswith("shots.json câu 7 nhịp 2: ") and "đè lên hình" in p
    assert image_problems(7, [doodle], paper(), WIDE) == []
    (p,) = image_problems(7, [beat(5.0, pop={"text": "2024", "box": [200, 400, 400, 500]})], ink, WIDE)
    assert "pop" in p and "đè lên hình" in p


@pytest.mark.parametrize("box, word", [
    ([620, 780, 680, 820], "nút"),  # x 650, y 800: under the like/comment column
    ([200, 1080, 400, 1120], "phụ đề"),  # y 1100: under the caption box
    ([200, 100, 400, 130], "thanh trên"),
    ([5, 400, 60, 450], "trái"),
    ([650, 300, 700, 340], "phải"),  # above the button column the margin is 24 px: x 696
])
def test_a_mark_outside_the_phones_safe_zone_names_the_side(box, word):
    img = Image.new("RGB", (720, 1280), (40, 40, 40))  # ink everywhere: only the zone is wrong
    (p,) = image_problems(7, [beat(5.0, mark={"shape": "tick", "box": box})], img, WIDE)
    assert word in p and p.startswith("shots.json câu 7 nhịp 1: ")


def test_a_mark_in_the_open_is_fine_and_each_side_is_named_once():
    img = Image.new("RGB", (720, 1280), (40, 40, 40))
    assert image_problems(7, [beat(5.0, mark={"shape": "tick", "box": [100, 300, 560, 700]})], img, WIDE) == []
    probs = image_problems(7, [beat(5.0, mark={"shape": "tick", "box": [620, 780, 680, 820]})], img, WIDE, end=12.0)
    assert len(probs) == 1  # at the end of drawing and at the end of the line: the same side, once


def test_the_camera_decides_what_the_phone_covers():
    img = Image.new("RGB", (720, 1280), (40, 40, 40))
    bs = [beat(5.0, mark={"shape": "tick", "box": [300, 500, 400, 560]})]
    assert image_problems(7, bs, img, WIDE) == []
    zoomed = lambda t: (2.0, 520, 640)  # the window now starts at x 340: the mark lands near the left edge of the screen
    assert any("trái" in p for p in image_problems(7, bs, img, zoomed))


def test_a_mark_is_checked_just_before_it_fades_not_after():
    img = Image.new("RGB", (720, 1280), (40, 40, 40))
    bs = [beat(5.0, mark={"shape": "tick", "box": [300, 500, 400, 560]}), beat(9.0, mark={"shape": "tick", "box": [300, 700, 400, 760]})]
    late = lambda t: WIDE(t) if t < 8.85 else (2.0, 520, 640)  # the camera moves off once the second mark has begun (8.8)
    probs = image_problems(7, bs, img, late)
    assert not any("nhịp 1" in p for p in probs)
