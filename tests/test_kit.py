import numpy as np
import pytest

from vshort import kit
from vshort.kit import GREEN, SAFE, Act, H, RED, W, bbox, draw, label_em

PHONE = {"id": "p", "kind": "phone", "box": [180, 170, 540, 1010], "label": "trang web hợp pháp", "color": "green",
         "url": "tin-tuc.example"}
DOT = {"id": "d", "kind": "dot", "xy": [400, 550], "label": "mã độc"}


def _ink(img, box):
    """Pixels clearly darker than paper inside box."""
    a = np.asarray(img.crop(box).convert("L")).astype(int)
    return int((a < 180).sum())


def _colour(img, box, colour):
    a = np.asarray(img.crop(box).convert("RGB")).astype(int)
    return bool((np.abs(a - np.array(colour)) < 40).all(axis=2).any())


def _red(img, box):
    return _colour(img, box, RED)


def test_nothing_shows_before_its_draw_act():
    img = draw([PHONE], [Act("draw", "p", 1.0, 1.8)], 0.5)
    assert img.size == (W, H) and _ink(img, (0, 0, W, H)) == 0


def test_view_moves_and_enlarges_the_ink():
    acts = [Act("draw", "d", 0.0, 0.8)]
    img = draw([DOT | {"xy": [250, 350]}], acts, 2.0, view=(250.0, 350.0, 2.0))
    assert _ink(img, (330, 543, 390, 603)) > 0 and _ink(img, (240, 340, 260, 360)) == 0


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


def test_a_shape_draws_its_strokes():
    th = {"id": "m", "kind": "shape", "shape": "x", "box": [200, 300, 500, 600], "label": "bộ nhớ",
          "strokes": [[(200, 300), (500, 600)], [(200, 600), (500, 300)]]}
    assert _ink(draw([th], [Act("draw", "m", 0, 0.8)], 1.0), (200, 300, 500, 600)) > 500
    assert bbox(th)[1] < 300  # the label sits above, as on a server


def test_safe_area_clears_the_logo():
    assert SAFE[1] == 96


def test_dim_fades_towards_paper_and_undim_brings_it_back():
    box = (170, 160, 550, 1020)
    mean = lambda acts, t: np.asarray(draw([PHONE], acts, t).crop(box).convert("L")).astype(float).mean()
    on = [Act("draw", "p", 0, 0.8)]
    dim = on + [Act("dim", "p", 1.0, 1.6)]
    back = dim + [Act("undim", "p", 2.0, 2.6)]
    assert mean(dim, 2.0) > mean(on, 2.0) + 1
    assert mean(back, 3.0) == pytest.approx(mean(on, 3.0))


FIG = {"id": "f", "kind": "figure", "xy": [200, 300], "label": "kỹ sư"}
KEY = {"id": "k", "kind": "icon", "icon": "key", "xy": [600, 600]}


def test_attached_thing_follows_its_moving_parent():
    acts = [Act("draw", "f", 0, 0.8), Act("draw", "k", 0, 0.8),
            Act("attach", "k", 0.0, 0.5, on="f", offset=(0, 5)), Act("move", "f", 1.0, 2.0, to=(500, 300))]
    by_id = {"f": FIG, "k": KEY}
    assert kit._position(KEY, acts, 2.5, by_id) == (500, 305)
    assert kit._position(KEY, acts, 0.25, by_id) != (600, 600)  # on its way over


def test_a_later_move_takes_an_attached_thing_off_its_parent():
    acts = [Act("attach", "k", 0.0, 0.5, on="f", offset=(0, 5)), Act("move", "k", 1.0, 2.0, to=(600, 900)),
            Act("move", "f", 2.5, 3.5, to=(500, 300))]
    assert kit._position(KEY, acts, 4.0, {"f": FIG, "k": KEY}) == (600, 900)


def test_standing_legs_are_symmetric_walking_legs_spread():
    (l0, r0), (l1, r1) = kit._legs(0, 0, 0.0), kit._legs(0, 0, 1.0)
    assert [(-x, y) for x, y in l0] == r0
    assert abs(r1[-1][0] - l1[-1][0]) > abs(r0[-1][0] - l0[-1][0])


def test_figure_roles_and_colour():
    atk = FIG | {"id": "a", "role": "attacker"}
    img = draw([atk], [Act("draw", "a", 0, 0.8)], 2.0)
    assert _red(img, (150, 180, 250, 400))  # the attacker is drawn red by default
    hood, plain = (bbox(FIG | {"role": r})[1] for r in ("attacker", None))
    assert hood == plain  # the box always leaves room for a hood


def test_check_and_cross_draw_in_their_colours():
    img = draw([{"id": "c", "kind": "check", "xy": [300, 300]}, {"id": "x", "kind": "cross", "xy": [500, 300]}],
               [Act("draw", "c", 0, 0.8), Act("draw", "x", 0, 0.8)], 2.0)
    assert _colour(img, (260, 260, 340, 340), GREEN) and _red(img, (460, 260, 540, 340))


def test_shape_prop_moves_by_its_centre():
    th = {"id": "m", "kind": "shape", "shape": "x", "box": [100, 100, 200, 200],
          "strokes": [[(100, 100), (200, 200)], [(100, 200), (200, 100)]]}
    img = draw([th], [Act("draw", "m", 0, 0.8), Act("move", "m", 1.0, 2.0, to=(400, 400))], 3.0)
    assert _ink(img, (350, 350, 450, 450)) > 100 and _ink(img, (100, 100, 200, 200)) == 0


ARM = {"id": "b", "kind": "shape", "shape": "barie", "box": [100, 100, 300, 300], "strokes": [[(100, 200), (300, 200)]],
       "hinge": {"strokes": [0], "pivot": (100, 200), "turn": -80, "squash": None}}


def test_open_turns_the_hinged_strokes():
    acts = [Act("draw", "b", 0, 0.8), Act("open", "b", 1.0, 1.8)]
    shut, opened = draw([ARM], acts, 0.9), draw([ARM], acts, 2.5)
    assert _ink(shut, (260, 190, 300, 210)) > 0 and _ink(opened, (260, 190, 300, 210)) == 0
    assert _ink(opened, (90, 0, 140, 190)) > 0
    closed = draw([ARM], acts + [Act("close", "b", 3.0, 3.8)], 4.5)
    assert _ink(closed, (260, 190, 300, 210)) > 0


def test_squash_folds_a_door_towards_its_hinge():
    door = ARM | {"hinge": {"strokes": [0], "pivot": (100, 200), "turn": None, "squash": 0.2}}
    opened = draw([door], [Act("draw", "b", 0, 0.8), Act("open", "b", 1.0, 1.8)], 2.5)
    assert _ink(opened, (100, 190, 140, 210)) > 0 and _ink(opened, (200, 190, 300, 210)) == 0


def test_means_line_shows_then_goes_plain():
    th = {"id": "f", "kind": "figure", "xy": [300, 300], "label": "thẻ", "means": "chứng chỉ"}
    acts = [Act("draw", "f", 0, 0.8), Act("plain", "f", 2.0, 2.6)]
    line = (200, 455, 400, 492)  # under the label at y 425
    assert _ink(draw([th], acts, 1.0), line) > 0 and _ink(draw([th], acts, 3.0), line) == 0
    assert bbox(th)[3] > bbox(th | {"means": ""})[3]


def test_means_of_a_server_stays_above_it():
    th = {"id": "s", "kind": "server", "box": [200, 400, 520, 600], "label": "bảo vệ", "means": "máy chủ"}
    assert bbox(th)[3] == 600 and bbox(th)[1] < bbox(th | {"means": ""})[1]
    up = (200, 305, 520, 338)  # the label, pushed up to make room for the means line under it
    assert _ink(draw([th], [Act("draw", "s", 0, 0.8)], 1.0), up) > 0
    assert _ink(draw([th | {"means": ""}], [Act("draw", "s", 0, 0.8)], 1.0), up) == 0


def test_pen_tip_shows_only_while_drawing():
    line = {"id": "l", "kind": "path", "points": [[100, 600], [600, 600]]}
    acts = [Act("draw", "l", 0.0, 1.0)]
    assert _ink(draw([line], acts, 0.5), (345, 560, 385, 595)) > 0
    assert _ink(draw([line], acts, 1.5), (345, 560, 385, 595)) == 0
