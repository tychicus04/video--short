import pytest

from vshort.fit import Placement
from vshort.retime import FAST, Piece, pieces, to_output
from vshort.script import Sentence


def _one(S: float, T: float, blank=lambda t: False) -> Piece:
    """One line in the middle of a video: its English span is S s from 10.0, its Vietnamese span T s from 20.0."""
    lines = [Sentence(1, 0.0, 10.0, "a."), Sentence(2, 10.0, 10.0 + S, "b."), Sentence(3, 10.0 + S, 99.0, "c.")]
    place = [Placement(1, 0.0, 19.5), Placement(2, 20.0, T - 0.5), Placement(3, 20.0 + T, 5.0)]
    return pieces(lines, place, 30.0 + T, 200.0, blank)[1]


def test_shorter_vietnamese_speeds_up():
    p = _one(6, 5)
    assert (p.src, p.dst, p.dst_end) == (10.0, 20.0, 25.0)
    assert p.speed == pytest.approx(1.2) and p.src_end == pytest.approx(16.0) and p.hold == 0 and p.dropped == 0


def test_speed_is_capped_and_the_tail_dropped():
    p = _one(9, 4)
    assert p.speed == FAST and p.src_end == pytest.approx(16.0) and p.dropped == pytest.approx(3.0) and p.hold == 0


def test_longer_vietnamese_plays_at_1x_then_holds():
    p = _one(4, 5)
    assert p.speed == 1 and p.src_end == pytest.approx(14.0) and p.hold == pytest.approx(1.0)


def test_long_hold_slows_down_first():
    p = _one(4, 7)  # a 3 s hold at 1x: slowed to 1/1.25, so 5 s of play and 2 s held
    assert p.speed == pytest.approx(0.8) and p.src_end == pytest.approx(14.0) and p.hold == pytest.approx(2.0)


def test_blank_hold_frame_steps_back_to_a_drawn_one():
    p = _one(4, 5, blank=lambda t: t > 13.5 + 1e-9)  # the span ends on bare paper (the next scene fading in)
    assert p.src_end == pytest.approx(13.5) and p.hold == pytest.approx(1.5)


def test_a_wholly_blank_span_is_left_as_it_is():
    p = _one(4, 5, blank=lambda t: True)
    assert p.src_end == pytest.approx(14.0) and p.hold == pytest.approx(1.0)


def test_a_very_short_line_is_still_a_valid_piece():
    p = _one(3, 0.3)
    assert p.speed == FAST and p.dropped == pytest.approx(2.55) and p.dst_end > p.dst


def test_first_line_starts_at_zero_and_last_stops_before_notebooklm_logo():
    lines = [Sentence(1, 0.1, 2.6, "a."), Sentence(2, 2.6, 81.07, "b.")]
    ps = pieces(lines, [Placement(1, 0.2, 2.5), Placement(2, 3.2, 70.0)], 80.0, 79.7)
    assert ps[0].src == 0.0 and ps[0].dst == 0.0
    assert ps[1].src_end <= 79.7 and ps[1].dst_end == 80.0


RAILS_EN = [0.1, 2.67, 10.03, 15.3, 19.0, 21.4, 27.3, 34.5, 41.63, 45.13, 50.2, 56.67, 62.2, 68.17, 70.17, 75.63]
RAILS_VI = [0.2, 3.2, 9.78, 15.26, 18.98, 21.52, 26.18, 31.68, 37.8, 40.52, 45.54, 51.06, 56.12, 61.52, 63.72, 68.5]


def _rails() -> list[Piece]:
    ends = RAILS_EN[1:] + [81.07]
    lines = [Sentence(i + 1, a, b, "x.") for i, (a, b) in enumerate(zip(RAILS_EN, ends))]
    place = [Placement(i + 1, s, 1.0) for i, s in enumerate(RAILS_VI)]
    return pieces(lines, place, 86.18, 82.83 - 3.1)


def test_pieces_tile_the_output():
    ps = _rails()
    assert ps[0].dst == 0 and ps[-1].dst_end == 86.18
    assert all(a.dst_end == b.dst for a, b in zip(ps, ps[1:]))
    assert all(a.src_end <= b.src for a, b in zip(ps, ps[1:]))


def test_rails_numbers_match_the_spike():
    ps = _rails()
    assert ps[6].speed == pytest.approx(7.2 / 5.5)  # line 7: 7.20 s of English into 5.50 s
    assert max(p.hold for p in ps[:15]) < 0.6  # the spike held 0.53 s at most before the closing line
    assert ps[15].speed == pytest.approx(0.8) and ps[15].src_end == pytest.approx(79.73)  # the 17 s closing line


def test_to_output_maps_and_skips_dropped_tails():
    ps = [_one(9, 4)]  # plays 10→16 at 1.5x into 20→24; 16→19 dropped
    assert to_output(ps, 13.0) == pytest.approx(22.0)
    assert to_output(ps, 17.0) is None and to_output(ps, 5.0) is None


def test_blank_at_tells_bare_paper_from_a_drawing(make_video, tmp_path):
    from vshort.retime import blank_at
    blank = blank_at(make_video(tmp_path, scenes=[(0, 2, "drawn")], captions=[]))  # cream page, a dark bar from 1 s
    assert blank(0.5) and not blank(1.5) and not blank(99.0)
