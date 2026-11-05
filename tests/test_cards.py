import io
from pathlib import Path

import cairosvg
import numpy as np
import pytest
from PIL import Image

from vshort import cards
from vshort.cards import Card, cap
from vshort.visuals import PAPER

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280" width="720" height="1280">'
BORDER = '<rect x="60" y="400" width="600" height="380" rx="18" fill="none" stroke="#4a4a4a" stroke-width="3"/>'
LINES = ('<g font-family="Be Vietnam Pro, sans-serif" font-size="32" fill="#222" text-anchor="middle">'
         '<text x="360" y="520">Synology strongly urges all users</text><text x="360" y="566">to update DSM immediately.</text></g>')
DOT = '<circle cx="120" cy="680" r="20" fill="#bfe9f0" stroke="#4a4a4a" stroke-width="3"/>'
SOURCE = ('<text x="40" y="1010" font-family="Be Vietnam Pro, sans-serif" font-size="22" fill="#4a4a4a">'
          'Nguồn: Synology, 29/10/2026</text>')


def _svg(tmp_path, *parts, name="the.svg"):
    path = tmp_path / name
    path.write_text(HEAD + "".join(parts) + "</svg>", encoding="utf-8")
    return path


def _ink(img, box=None, scale=2):
    a = np.abs(np.asarray(img.convert("RGB")).astype(int) - PAPER).max(2) > 40
    if box:
        x0, y0, x1, y1 = (int(v * scale) for v in box)
        a = a[y0:y1, x0:x1]
    return a


def _sides(ink):
    return ink[:12], ink[-12:], ink[:, :12], ink[:, -12:]


def _off(card, img):
    """The most any pixel of `img` differs from a whole 2x render of the card's SVG on paper: a missing element shows."""
    png = cairosvg.svg2png(url=str(card.svg), output_width=1440, output_height=2560)
    art = Image.open(io.BytesIO(png)).convert("RGBA")
    whole = Image.alpha_composite(Image.new("RGBA", art.size, PAPER + (255,)), art).convert("RGB")
    return np.abs(np.asarray(img).astype(int) - np.asarray(whole).astype(int)).max()


def test_card_reveals_in_order_and_ends_whole(tmp_path):
    card = Card(_svg(tmp_path, BORDER, LINES, DOT, SOURCE), 1.0, 4.0, 0.4)
    border, lines, dot, source = card.pieces
    assert [p.border for p in card.pieces] == [True, False, False, False]
    assert (border.t0, border.t1) == (0.8, 1.0)
    assert lines.t0 == 1.0 and lines.t0 < dot.t0 < source.t0 and source.t1 <= 4.0
    assert card.frame(0.79).size == (1440, 2560) and not _ink(card.frame(0.79)).any()  # nothing before the border starts
    mid = _ink(card.frame(0.9)).sum()
    assert 0 < mid < _ink(card.frame(1.0)).sum()  # the border is on its way, whole at the cut
    sides = lambda img: [m.sum() for m in _sides(_ink(img, tuple(v + d for v, d in zip(border.box, (-2, -2, 2, 2)))))]
    assert all(a >= 0.9 * b > 0 for a, b in zip(sides(card.frame(1.0)), sides(card.frame(4.0))))  # all four sides are there at the cut
    for p in (lines, dot, source):  # each element has no ink a hair before it starts and all of it when done
        assert not _ink(card.frame(p.t0 - 0.01), p.box).any()
        assert _ink(card.frame(p.t1), p.box).any()
    half = _ink(card.frame((lines.t0 + lines.t1) / 2), lines.box)
    assert 0 < half.sum() < _ink(card.frame(lines.t1), lines.box).sum()
    left, right = np.split(half[:, : half.shape[1] // 2 * 2], 2, axis=1)  # wiped from the left
    assert left.sum() > right.sum()
    end = card.frame(4.0)
    assert end.mode == "RGB" and end.size == (1440, 2560)
    assert _off(card, end) <= 4
    assert np.array_equal(np.asarray(card.frame(9.0)), np.asarray(end))  # after the line it stays whole


def test_card_never_blank_at_the_cut(tmp_path):
    card = Card(_svg(tmp_path, BORDER, LINES, SOURCE), 2.0, 5.0, 0.4)
    x0, y0, x1, y1 = card.ink_box
    area = (x1 - x0) * (y1 - y0) * 4
    assert _ink(card.frame(2.0), card.ink_box).sum() >= 0.01 * area
    bare = Card(_svg(tmp_path, LINES, SOURCE, name="bare.svg"), 2.0, 5.0, 0.4)  # no border: the first elements are there early
    assert bare.pieces[0].t0 == 1.8 and not any(p.border for p in bare.pieces)
    assert _ink(bare.frame(2.0), bare.ink_box).mean() >= 0.01


def test_a_borderless_timeline_is_not_nearly_blank_at_the_cut():
    card = Card(Path(__file__).parent / "data" / "moc-va.svg", 2.0, 5.0, 0.4)  # a real card: a line, two dots, texts, a source
    assert not any(p.border for p in card.pieces)
    assert _ink(card.frame(1.8), card.ink_box).mean() >= 0.01  # from the moment the cut starts
    assert _ink(card.frame(2.0), card.ink_box).mean() >= 0.01
    first, last = card.pieces[0], card.pieces[-1]
    assert first.t0 == first.t1 == 1.8 and last.t1 > 2.0  # something is still written out after the cut
    assert _off(card, card.frame(5.0)) <= 4


@pytest.mark.parametrize("parts", [
    ('<defs><style>.a{fill:#222}</style></defs>', '<g id="a"><text class="a" x="40" y="500" font-size="30">Hai dòng</text>'
     '<line x1="40" y1="520" x2="400" y2="520" stroke="#4a4a4a" stroke-width="3"/></g>', DOT, SOURCE),
    (LINES,),  # a single element
    ('<title>t</title>', '<rect x="100" y="300" width="100" height="100" fill="none" stroke="#4a4a4a" stroke-width="3"/>',
     '<rect x="60" y="600" width="600" height="300" fill="#bfe9f0"/>', SOURCE),  # a small frame is not the card's frame
    ('<rect x="0" y="300" width="100%" height="400" fill="none" stroke="#4a4a4a" stroke-width="3"/>', DOT),  # not pencilled
])
def test_card_without_border_or_with_groups_still_ends_whole(tmp_path, parts):
    card = Card(_svg(tmp_path, *parts), 1.0, 3.0, 0.4)
    assert card.pieces and not any(p.border for p in card.pieces)
    assert _ink(card.frame(1.0)).any()
    assert [p.t0 for p in card.pieces] == sorted(p.t0 for p in card.pieces)
    assert _off(card, card.frame(3.0)) <= 4


def test_border_is_the_first_unfilled_wide_rect_even_when_not_first(tmp_path):
    card = Card(_svg(tmp_path, '<rect x="80" y="420" width="560" height="300" fill="#eee"/>', BORDER, LINES), 1.0, 3.0, 0.4)
    assert card.pieces[0].border and card.pieces[0].t0 == 0.8
    assert card.frame(3.0).getpixel((1440 // 2, 2 * 440)) == (238, 238, 238)  # the filled rect is there, the border over it
    assert _off(card, card.frame(3.0)) <= 4


MARKER = ('<marker id="m" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">'
          '<path d="M0,0 L8,4 L0,8 z" fill="#c43028"/></marker>')
GRADIENT = ('<linearGradient id="g"><stop offset="0" stop-color="#bfe9f0"/><stop offset="1" stop-color="#e8b0a0"/></linearGradient>')
CLIP = '<clipPath id="c"><rect x="100" y="500" width="200" height="100"/></clipPath>'


@pytest.mark.parametrize("defs, user", [
    (MARKER, '<line x1="100" y1="700" x2="500" y2="700" stroke="#4a4a4a" stroke-width="4" marker-end="url(#m)"/>'),
    (GRADIENT, '<rect x="100" y="300" width="500" height="120" fill="url(#g)"/>'),
    (CLIP, '<circle cx="200" cy="550" r="120" fill="#bfe9f0" stroke="#4a4a4a" stroke-width="3" clip-path="url(#c)"/>'),
])
def test_definitions_outside_defs_are_not_elements_and_reach_what_uses_them(tmp_path, defs, user):
    card = Card(_svg(tmp_path, BORDER, defs, user, LINES), 1.0, 3.0, 0.4)  # as top-level children, not inside <defs>
    assert len(card.pieces) == 3  # the frame, what uses the definition, the text: the definition itself is no piece
    assert _off(card, card.frame(3.0)) <= 4


def test_a_border_on_the_edge_of_the_picture_is_drawn_and_ends_whole(tmp_path):
    card = Card(_svg(tmp_path, '<rect x="0" y="0" width="720" height="1280" fill="none" stroke="#4a4a4a" stroke-width="3"/>', DOT), 1.0, 3.0, 0.4)
    assert card.pieces[0].border and _ink(card.frame(1.0)).any() and _off(card, card.frame(3.0)) <= 4


def test_blank_and_zero_length_cards_do_not_fail(tmp_path):
    blank = Card(_svg(tmp_path), 1.0, 3.0, 0.4)
    assert blank.pieces == [] and not _ink(blank.frame(2.0)).any() and cap(blank) > 0
    quick = Card(_svg(tmp_path, BORDER, LINES, SOURCE, name="q.svg"), 1.0, 1.0, 0.4)  # start == end
    assert _ink(quick.frame(1.0)).any() and _off(quick, quick.frame(1.0)) <= 4


def test_cap_keeps_the_card_text_inside(tmp_path):
    card = Card(_svg(tmp_path, BORDER, LINES), 1.0, 3.0, 0.4)  # a 600 px card
    assert cap(card) <= 720 / 648
    x0, _, x1, _ = card.ink_box
    assert x0 - 24 >= 0 and x1 + 24 <= 720 and cap(card) * (x1 - x0 + 48) <= 720 + 1e-6


def test_one_card_is_rendered_once(tmp_path, monkeypatch):
    path = _svg(tmp_path, BORDER, LINES, DOT)
    a = Card(path, 1.0, 3.0, 0.4)
    calls = []
    real = cards.cairosvg.svg2png
    monkeypatch.setattr(cards.cairosvg, "svg2png", lambda *a_, **k: calls.append(1) or real(*a_, **k))
    b = Card(path, 5.0, 8.0, 0.4)  # the same file on another line: not drawn again
    assert calls == [] and [p.box for p in a.pieces] == [p.box for p in b.pieces]
