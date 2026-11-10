import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vshort import compose, hf, media
from vshort.layout import TUNNEL_HALF
from vshort.render import BAR, STRIPE, TEAL, YELLOW
from vshort.textfit import _font

ROOT = Path(__file__).resolve().parent.parent
needs_hf = pytest.mark.skipif(not hf.available(), reason="chưa cài vshort/neon (npm ci)")

MONO, BOLD, EXTRA = "IBMPlexMono-SemiBold.ttf", "BeVietnamPro-Bold.ttf", "BeVietnamPro-ExtraBold.ttf"
INK = 20 / 24
QUOTE = "AI không cần data center khổng lồ"


# ---- a hand-built runtime scene, in the shape of runtime-contract.md ----

def text_box(text, font, size, x, y, anchor="l"):
    """Measured like layout.text_box: 6 % over PIL's width, 2 px between the letters of a mono text, one font line tall."""
    f = _font(size, font)
    w = (f.getbbox(text)[2] + (2 * max(len(text) - 1, 0) if font == MONO else 0)) * 1.06
    x0 = x - {"l": 0, "m": w / 2, "r": w}[anchor]
    return [x0, y, x0 + w, y + sum(f.getmetrics())]


def wrap(s, font, size, width):
    """The lines s breaks into at `width` px, measured with text_box's 6 % margin."""
    lines, cur = [], ""
    for word in s.split():
        if text_box(f"{cur} {word}".strip(), font, size, 0, 0)[2] <= width:
            cur = f"{cur} {word}".strip()
        else:
            lines, cur = lines + [cur] * bool(cur), word
    return lines + [cur]


def icon(id, name, x, y, size=84, tone="normal", kind="icon", stroke=3.5, **more):
    h = (INK * size + stroke) / 2
    return {"id": id, "kind": kind, "icon": name, "x": x, "y": y, "size": size, "tone": tone,
            "box": [x - h, y - h, x + h, y + h], **more}


def text(kind, id, s, font, size, x, y, tone, anchor="l", align="left", **more):
    box = text_box(s, font, size, x, y, anchor)
    if kind == "chip":
        box = [box[0] - 19, box[1] - 7, box[2] + 19, box[3] + 7]
    return {"id": id, "kind": kind, "text": s, "font": font, "size": size, "tone": tone, "box": box, "align": align, **more}


def link(id, a, b, x1, y1, x2, y2, style="solid", tone="normal"):
    return {"id": id, "kind": "link", "a": a, "b": b, "style": style, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "tone": tone,
            "box": [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]}


def small_scene():
    """6 s: the title bar typed 0.4-1.2 s, two nodes switched on at 2.0 and 2.2 s, a link, a chip, a dot running along the
    link, the right node turning red, two captions."""
    return {
        "total": 6.0,
        "title": {"lines": ["TIÊU ĐỀ THỬ NGHIỆM"], "size": 46, "t0": 0.4, "t1": 1.2, "out": 1.6},
        "captions": [[0.3, 3.0, "Câu phụ đề thứ nhất"], [3.0, 5.9, "Câu thứ hai, trắng và rõ"]],
        "elements": [
            icon("a", "server", 180, 560),
            icon("b", "user", 480, 560),
            link("ab", "a", "b", 226, 560, 434, 560),
            link("tun", "a", "b", 150, 430, 510, 430, "tunnel"),
            text("label", "a.label", "Máy chủ", BOLD, 22, 180, 612, "normal", "m", "center", of="a"),
            text("chip", "c", "KIỂM CHỨNG", MONO, 22, 60, 250, "claim", align="center"),
        ],
        "actions": [
            {"t": 2.0, "do": "on", "ids": ["a"]},
            {"t": 2.2, "do": "on", "ids": ["b"]},
            {"t": 2.6, "do": "draw", "ids": ["ab", "tun"], "d": 0.5},
            {"t": 2.6, "do": "type", "ids": ["a.label"], "d": 0.4},
            {"t": 3.0, "do": "type", "ids": ["c"], "d": 0.6},
            {"t": 3.7, "do": "flow", "ids": ["ab"], "dir": "a-b", "repeat": 2, "d": 0.6},
            {"t": 4.9, "do": "tone", "ids": ["b"], "to": "risk"},
        ],
    }


def redraw_scene():
    """A node and its link switched on (0.2 s), switched off (1.0 s), then drawn (2.0 s): a draw must not hide what an earlier
    `on` showed, and a draw after an `off` must draw again."""
    return {"total": 3.4, "title": None, "captions": [],
            "elements": [icon("a", "server", 180, 560), link("ab", "a", "b", 226, 560, 434, 560)],
            "actions": [{"t": 0.2, "do": "on", "ids": ["a", "ab"]}, {"t": 1.0, "do": "off", "ids": ["a", "ab"], "d": 0.35},
                        {"t": 2.0, "do": "draw", "ids": ["a", "ab"], "d": 0.5}]}


def red_flow_scene():
    """A red link between two red nodes, a dot running along it from 0.8 s (3 passes of 0.8 s: to 3.2 s), the link and its nodes
    fading out at 1.6 s. The dot is part of the link: red like it, and gone when it is."""
    return {"total": 3.4, "title": None, "captions": [],
            "elements": [icon("a", "server", 180, 560, tone="risk"), icon("b", "user", 480, 560, tone="risk"),
                         link("ab", "a", "b", 226, 560, 434, 560, tone="risk")],
            "actions": [{"t": 0.2, "do": "on", "ids": ["a", "b", "ab"]},
                        {"t": 0.8, "do": "flow", "ids": ["ab"], "dir": "a-b", "repeat": 3, "d": 0.8},
                        {"t": 1.6, "do": "off", "ids": ["a", "b", "ab"], "d": 0.35}]}


def recolour_flow_scene():
    """A cyan link, a dot running along it from 0.8 s (3 passes of 0.8 s), the link turning red at 1.4 s: the dot goes on, red."""
    return {"total": 3.4, "title": None, "captions": [],
            "elements": [icon("a", "server", 180, 560), icon("b", "user", 480, 560), link("ab", "a", "b", 226, 560, 434, 560)],
            "actions": [{"t": 0.2, "do": "on", "ids": ["a", "b", "ab"]},
                        {"t": 0.8, "do": "flow", "ids": ["ab"], "dir": "a-b", "repeat": 3, "d": 0.8},
                        {"t": 1.4, "do": "tone", "ids": ["ab"], "to": "risk"}]}


def full_scene():
    """Every kind and every action once. The kit throws on what it does not know, so validate reaching the end means it knows them."""
    els = [
        text("section", "s.label", "TÁC VỤ AI", MONO, 22, 60, 190, "normal"),
        icon("hub", "shield-check", 330, 560, 150, "normal", stroke=4),
        icon("n1", "server", 150, 560),
        icon("n2", "user", 510, 560),
        icon("n2b", "user-x", 510, 560, tone="risk", of="n2"),
        icon("bd", "lock", 480, 520, 34, "claim", kind="badge", stroke=2.5, of="n2"),
        link("l1", "hub", "n1", 218, 560, 196, 560),
        link("l2", "hub", "n2", 442, 560, 464, 560, "dashed"),
        link("l3", "n1", "n2", 150, 400, 510, 400, "tunnel"),
        {"id": "t1", "kind": "tile", "x": 150, "y": 485, "size": 30, "tone": "normal", "box": [135, 470, 165, 500]},
        text("label", "n1.label", "Máy chủ", BOLD, 22, 150, 612, "normal", "m", "center", of="n1"),
        text("chip", "chip", "CHỈ ĐỌC", MONO, 22, 400, 250, "claim", align="center"),
        {"id": "st", "kind": "statement", "text": "Mỗi máy chỉ thấy một phần", "lines": ["Mỗi máy chỉ thấy", "một phần"],
         "font": EXTRA, "size": 44, "tone": None, "box": [150, 870, 570, 982], "lh": 56},
        {"id": "q", "kind": "quote", "text": QUOTE, "lines": wrap(QUOTE, EXTRA, 54, 480),
         "who": "OPENMATTER TUYÊN BỐ", "font": EXTRA, "size": 54, "tone": "claim", "box": [60, 380, 600, 750], "lh": 69},
        {"id": "h", "kind": "hero", "icon": "shield-check", "x": 330, "y": 554, "size": 170, "tone": "safe",
         "label": "BẰNG CHỨNG", "label_box": text_box("BẰNG CHỨNG", MONO, 30, 330, 756, "m"), "box": [235, 460, 425, 800]},
    ]
    acts = [
        {"t": 0.2, "do": "type", "ids": ["s.label"], "d": 0.5},
        {"t": 0.5, "do": "draw", "ids": ["hub", "n1", "n2", "bd"], "d": 0.5},
        {"t": 0.6, "do": "draw", "ids": ["l1", "l2", "l3"], "d": 0.4},
        {"t": 0.8, "do": "on", "ids": ["t1", "chip"]},
        {"t": 1.0, "do": "type", "ids": ["n1.label", "chip", "st"], "d": 0.6},
        {"t": 1.2, "do": "move", "ids": ["t1"], "from": [[330, 560]], "d": 0.6},
        {"t": 1.4, "do": "flow", "ids": ["l1"], "dir": "b-a", "repeat": 1, "d": 0.85},
        {"t": 2.0, "do": "tone", "ids": ["hub"], "to": "risk"},
        {"t": 2.2, "do": "tone", "ids": ["n1", "n1.label"], "to": "claim"},
        {"t": 2.4, "do": "tone", "ids": ["st"], "to": "safe"},
        {"t": 2.6, "do": "tone", "ids": ["n1"], "to": "dim"},
        {"t": 2.8, "do": "tone", "ids": ["n1"], "to": "normal"},
        {"t": 3.0, "do": "swap", "ids": ["n2", "n2b"]},
        {"t": 3.4, "do": "off", "ids": ["s.label", "hub", "n1", "l1", "l2", "l3", "t1", "chip", "st", "bd", "n1.label"], "d": 0.35},
        {"t": 3.6, "do": "draw", "ids": ["q"], "d": 0.6},
        {"t": 3.8, "do": "type", "ids": ["q"], "d": 1.2},
        {"t": 4.8, "do": "off", "ids": ["q", "n2b"]},
        {"t": 5.0, "do": "draw", "ids": ["h"], "d": 0.5},
        {"t": 5.1, "do": "type", "ids": ["h"], "d": 0.5},
    ]
    return {"total": 6.0, "title": None, "captions": [[0.0, 6.0, "Phụ đề"]], "elements": els, "actions": acts}


# ---- write_composition ----

def embedded(html: str) -> dict:
    m = re.search(r"window\.SCENE = (.*?);</script>", html, re.S)
    return json.loads(m.group(1))


def test_write_composition_has_everything(tmp_path):
    rt = small_scene()
    rt["captions"][0][2] = 'a "</script><b>" & <!-- tricky'  # a text must never close the script tag
    out = compose.write_composition(rt, tmp_path / "comp")
    assert out == tmp_path / "comp"
    for name in ("index.html", "kit.js", "kit.css", "icons.json", "gsap.min.js", "anm-logo.png", "BeVietnamPro-Bold.ttf",
                 "BeVietnamPro-ExtraBold.ttf", "IBMPlexMono-SemiBold.ttf"):
        assert (out / name).is_file(), name
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'data-duration="6.0"' in html and 'data-composition-id="main"' in html
    # laid out on 720 x 1280 (every number of layout.py), drawn 1.5 times as large: text and 3 px strokes stay sharp on a phone
    assert 'data-width="1080"' in html and 'data-height="1920"' in html and "scale(1.5)" in (out / "kit.css").read_text()
    assert embedded(html) == rt
    assert html.count("</script>") == html.count("<script")  # nothing the scene says ends a script early
    assert "cdn" not in html and "http" not in html  # nothing comes from the network


# ---- rendered ----

@pytest.fixture(scope="module")
def small_render(tmp_path_factory):
    d = tmp_path_factory.mktemp("small")
    comp = compose.write_composition(small_scene(), d / "comp")
    out = d / "small.mp4"
    hf.render(comp, out)
    return comp, out


def frame_at(path, t):
    """The frame in layout pixels: the kit draws its 720 x 1280 picture 1.5 times as large, and the boxes below are layout.py's."""
    return np.asarray(Image.fromarray(media.frame_at(path, t)).resize((720, 1280), Image.LANCZOS))


def count(frame, box, ok):
    x0, y0, x1, y1 = box
    part = frame[y0:y1, x0:x1].astype(int)
    return int(ok(part[..., 0], part[..., 1], part[..., 2]).sum())


@needs_hf
def test_composition_validates_clean(small_render):
    assert hf.validate(small_render[0]) == []


@needs_hf
def test_renders_a_small_scene(small_render):
    _, out = small_render
    teal = TEAL[:3]
    # the title bar: at t1 the box is open and its words typed
    bar = frame_at(out, 1.2)
    assert count(bar, (300, 700, 600, 820), lambda r, g, b: (abs(r - teal[0]) < 14) & (abs(g - teal[1]) < 14) & (abs(b - teal[2]) < 14)) > 5000
    assert count(bar, (116, 700, 600, 820), lambda r, g, b: (r > 230) & (g > 230) & (b > 230)) > 300  # the white words
    # render.title_card's geometry: the stripe and the box fill their rectangles and stop at their edges
    near = lambda c: lambda r, g, b: (abs(r - c[0]) < 14) & (abs(g - c[1]) < 14) & (abs(b - c[2]) < 14)
    inner = lambda b, m: (b[0] + m, b[1] + m, b[2] - m, b[3] - m)
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    assert count(bar, inner(STRIPE, 2), near(YELLOW)) > 0.95 * area(inner(STRIPE, 2))
    assert count(bar, (BAR[0] + 4, BAR[1] + 4, BAR[2] - 4, 722), near(teal)) > 0.95 * area((BAR[0] + 4, BAR[1] + 4, BAR[2] - 4, 722))
    assert count(bar, (BAR[2] + 4, BAR[1], 700, BAR[3]), near(teal)) < 20 and count(bar, (0, BAR[1], STRIPE[0] - 3, BAR[3]), near(YELLOW)) < 20
    gone = frame_at(out, 3.0)  # the bar has rolled back (1.6 + 0.65 s)
    assert count(gone, (94, 680, 662, 843), lambda r, g, b: abs(b - teal[2]) < 8) < 50
    # the left node: nothing before its `on`, blue half a second after
    blue = lambda r, g, b: (b > 200) & (r < 120)
    assert count(frame_at(out, 1.5), (140, 520, 220, 600), blue) < 5
    assert count(frame_at(out, 2.5), (140, 520, 220, 600), blue) > 100
    # the second caption in white, in the band above y 1140
    assert count(frame_at(out, 4.45), (102, 1080, 618, 1140), lambda r, g, b: (r > 230) & (g > 230) & (b > 230)) > 300
    assert count(frame_at(out, 1.5), (102, 1080, 618, 1140), lambda r, g, b: (r > 230) & (g > 230) & (b > 230)) > 300  # the first
    # the logo's white plate
    assert count(frame_at(out, 1.5), (480, 30, 690, 76), lambda r, g, b: (r > 240) & (g > 240) & (b > 240)) > 1500
    # a dot of #BFF6FF runs along the link at 4.0 s; the line itself is not that pale
    assert count(frame_at(out, 4.0), (226, 540, 434, 580), lambda r, g, b: (r > 150) & (g > 230) & (b > 240)) > 20
    assert count(frame_at(out, 3.5), (226, 540, 434, 580), lambda r, g, b: (r > 150) & (g > 230) & (b > 240)) < 5
    # a tunnel's two rails stand layout.TUNNEL_HALF either side of its line, and nothing is drawn on the line itself
    rail = lambda y: count(frame_at(out, 4.0), (200, y - 1, 460, y + 2), lambda r, g, b: (b > 150) & (r < 120))  # a link is drawn at .75
    assert rail(430 - TUNNEL_HALF) > 200 and rail(430 + TUNNEL_HALF) > 200 and rail(430) < 5
    # the right node has turned red by 5.4 s, and was cyan before
    red = lambda r, g, b: (r > 200) & (b < 150) & (g < 120)
    assert count(frame_at(out, 4.5), (440, 520, 520, 600), red) < 5
    assert count(frame_at(out, 5.4), (440, 520, 520, 600), red) > 100


@needs_hf
def test_a_draw_neither_hides_an_earlier_on_nor_pops_in_after_an_off(tmp_path):
    comp = compose.write_composition(redraw_scene(), tmp_path / "comp")
    out = tmp_path / "redraw.mp4"
    hf.render(comp, out)
    cyan = lambda r, g, b: (b > 150) & (r < 120)  # the link is drawn at .75, so its blue stays under 200
    ink = lambda t: (count(frame_at(out, t), (140, 520, 220, 600), cyan), count(frame_at(out, t), (226, 550, 434, 570), cyan))
    shown, gone, growing, drawn = ink(0.7), ink(1.6), ink(2.1), ink(2.8)
    assert shown[0] > 100 and shown[1] > 200  # `on` at 0.2 s shows the whole node and link, though a draw comes at 2.0 s
    assert max(gone) < 5  # `off`
    assert growing[0] < shown[0] / 2 and growing[1] < shown[1] / 2  # 0.1 s into the draw: it starts from nothing again
    assert drawn[0] > 0.9 * shown[0] and drawn[1] > 0.9 * shown[1]


@needs_hf
def test_a_flow_dot_takes_its_links_colour_and_goes_with_it(tmp_path):  # it used to be cyan in its own root, and outlive the link
    comp = compose.write_composition(red_flow_scene(), tmp_path / "comp")
    out = tmp_path / "flow.mp4"
    hf.render(comp, out)
    along = (226, 530, 434, 590)
    cyan = lambda r, g, b: (b > 150) & (g > 150) & (r < g - 40)
    lit = lambda r, g, b: (r > 150) | (g > 150) | (b > 150)
    mid = frame_at(out, 1.2)  # half way along the first pass
    assert count(mid, along, lambda r, g, b: (r > 240) & (g > 120) & (b > 120)) > 20  # the dot is there, a pale red
    assert count(mid, along, cyan) < 5  # and the red link has not gained a colour
    assert count(frame_at(out, 2.6), along, lit) < 5  # the link has faded (2.0 s): the dot, still running, went with it


@needs_hf
def test_a_flow_dot_goes_on_running_when_its_link_changes_colour(tmp_path):
    comp = compose.write_composition(recolour_flow_scene(), tmp_path / "comp")
    out = tmp_path / "recolour.mp4"
    hf.render(comp, out)
    along = (226, 530, 434, 590)
    cyan = lambda r, g, b: (b > 150) & (g > 150) & (r < g - 40)
    pale_red = lambda r, g, b: (r > 240) & (g > 120) & (b > 120)
    before, after = frame_at(out, 1.2), frame_at(out, 2.4)  # the colour changes at 1.4 s, the cross-fade is over by 1.75 s
    assert count(before, along, cyan) > 20 and count(before, along, pale_red) < 5  # still cyan
    assert count(after, along, pale_red) > 20  # the dot is still there, now pale red
    assert count(after, along, cyan) < 5  # and the link has only the one colour


@needs_hf
def test_every_kind_and_action_builds(tmp_path):
    comp = compose.write_composition(full_scene(), tmp_path / "comp")
    assert hf.validate(comp) == []


@needs_hf
def test_a_text_wider_than_its_box_fails_validate(tmp_path):
    rt = small_scene()
    label = next(e for e in rt["elements"] if e["id"] == "a.label")
    label["box"][2] = label["box"][0] + 40  # layout gives a box 6 % wider than its text, never narrower
    comp = compose.write_composition(rt, tmp_path / "comp")
    assert any("a.label" in e and "wider" in e for e in hf.validate(comp))


def test_the_kit_keeps_hyperframes_rules():
    kit = (ROOT / "vshort" / "neon" / "kit.js").read_text(encoding="utf-8")
    assert "Math.random" not in kit and not re.search(r"repeat:\s*-", kit) and "Infinity" not in kit
    assert not re.search(r"\b(display|visibility)\s*:", kit.replace("display:none", ""))  # nothing animates them


@needs_hf
def test_an_unknown_action_fails_validate(tmp_path):
    rt = small_scene()
    rt["actions"].append({"t": 5.0, "do": "explode", "ids": ["a"]})
    comp = compose.write_composition(rt, tmp_path / "comp")
    assert any("explode" in e for e in hf.validate(comp))
