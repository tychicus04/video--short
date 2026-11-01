import numpy as np

from vshort.kit import Act, H, RED, W, bbox, draw, label_em

PHONE = {"id": "p", "kind": "phone", "box": [180, 170, 540, 1010], "label": "trang web hợp pháp", "color": "green",
         "url": "tin-tuc.example"}
DOT = {"id": "d", "kind": "dot", "xy": [400, 550], "label": "mã độc"}


def _ink(img, box):
    """Pixels clearly darker than paper inside box."""
    a = np.asarray(img.crop(box).convert("L")).astype(int)
    return int((a < 180).sum())


def _red(img, box):
    a = np.asarray(img.crop(box).convert("RGB")).astype(int)
    return bool((np.abs(a - np.array(RED)) < 40).all(axis=2).any())


def test_nothing_shows_before_its_draw_act():
    img = draw([PHONE], [Act("draw", "p", 1.0, 1.8)], 0.5)
    assert img.size == (W, H) and _ink(img, (0, 0, W, H)) == 0


def test_draw_on_grows_then_holds():
    acts = [Act("draw", "p", 0.0, 0.8)]
    half, done, later = (_ink(draw([PHONE], acts, t), (0, 0, W, H)) for t in (0.4, 0.8, 3.0))
    assert 0 < half < done and abs(done - later) < 0.02 * done


def test_bbox_includes_the_label_above_a_phone():
    x0, y0, x1, y1 = bbox(PHONE)
    assert y0 < 170 - 20 and y1 >= 1010 and x0 <= 180 and x1 >= 540


def test_label_em_shrinks_then_gives_up():
    assert label_em({**PHONE, "label": "A"}) == 44
    # Patrick Hand "trang web hợp pháp" is 304 px at em 44, 221 px at em 32
    assert 32 <= label_em({"id": "b", "kind": "box", "box": [300, 300, 600, 400], "label": "trang web hợp pháp"}) < 44
    assert label_em({"id": "b", "kind": "box", "box": [300, 300, 480, 400], "label": "trang web hợp pháp"}) == 0


def test_move_ends_at_the_target_and_vanish_erases():
    acts = [Act("draw", "d", 0, 0.8), Act("move", "d", 1.0, 2.0, to=(200, 300))]
    img = draw([DOT], acts, 2.5)
    assert _red(img, (185, 285, 215, 315)) and not _red(img, (385, 535, 415, 565))
    gone = draw([DOT], [acts[0], Act("move", "d", 1.0, 2.0, to=(200, 300), vanish=True)], 2.5)
    assert not _red(gone, (185, 285, 215, 315))


def test_red_turns_the_outline_red():
    acts = [Act("draw", "p", 0, 0.8), Act("red", "p", 1.0, 1.6, say="đã bị chiếm")]
    assert not _red(draw([PHONE], acts, 0.9), (170, 160, 550, 1020))
    assert _red(draw([PHONE], acts, 2.0), (170, 160, 550, 1020))


def test_a_flying_icon_never_leaves_the_top_of_the_safe_area():
    key = {"id": "k", "kind": "icon", "icon": "key", "xy": [100, 130], "label": "mật khẩu"}
    acts = [Act("draw", "k", 0, 0.8), Act("move", "k", 1.0, 2.0, to=(620, 130))]
    assert all(_ink(draw([key], acts, t), (0, 0, W, 58)) == 0 for t in (1.3, 1.5, 1.7))


def test_a_short_vanishing_move_is_whole_when_it_starts():
    keep = [Act("draw", "d", 0, 0.8), Act("move", "d", 1.0, 1.3, to=(200, 300))]
    gone = [keep[0], Act("move", "d", 1.0, 1.3, to=(200, 300), vanish=True)]
    assert np.array_equal(np.asarray(draw([DOT], gone, 1.0)), np.asarray(draw([DOT], keep, 1.0)))


def test_the_message_icon_has_no_stroke_across_the_bubble():
    msg = {"id": "m", "kind": "icon", "icon": "message", "xy": [360, 500]}  # bubble 312..408 x 445..507
    assert _ink(draw([msg], [Act("draw", "m", 0, 0.8)], 1.0), (330, 455, 390, 495)) == 0
