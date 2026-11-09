"""Where a neon section's things stand. Each layout is a table of named slots on the 660 px wide picture; `place` turns one
section into runtime elements with absolute boxes, labels and chips found by trying spots so nothing lands on a link, an
icon or other text. The browser only animates what is placed here."""
import math
from dataclasses import dataclass

from vshort.scene import Beat, SceneError, Section
from vshort.textfit import UI_RIGHT, UI_RIGHT_FROM, UI_TOP, _font

C = (330.0, 560.0)  # the centre, where a hub stands
_RING_ANGLES = (0, 50, 130, 180, 230, 310)  # degrees; y grows downwards, so 50 is below and to the right

SLOTS: dict[str, dict[str, tuple[float, float]]] = {
    "none": {},
    "center": {"hub": C},
    # `below` stands 220 under the hub, not 200: at 200 (330, 760) the hub's label fits only at the 4 px fallback, 0.25 px past the 4 px
    # margin from `below`'s tile, too fragile (the font files are untracked downloads and may differ between the Mac and pve2)
    # the slots stand 230 / 220 px from the hub, so a link to it shows 72 / 62 px of line once cut at both ends (SHORT + SHORT_HUB = 158;
    # at 180 px it was a 22 px stub); `above` at 340 keeps its split tile (y - 83) clear of the section-label band (190 - 230)
    "pair": {"hub": C, "left": (100, 560), "right": (560, 560), "above": (330, 340), "below": (330, 780)},
    "ring": {"hub": C} | {f"r{k}": (C[0] + 228 * math.cos(math.radians(a)), C[1] + 228 * math.sin(math.radians(a)))
                          for k, a in enumerate(_RING_ANGLES)},
    "chain": {f"c{k}": (330, 330 + 150 * k) for k in range(4)},
    # the rows are 200 apart, not 170: a label under the top row and a tile over the bottom row need room between them, and 200 keeps
    # the labels at the 8 px gap with room to spare (175 would also pass)
    "grid": {f"g{k}": ((162, 330, 498)[k % 3], (460, 660)[k // 3]) for k in range(6)},
}

ICON, HUB = 84, 150  # an icon's side at a normal slot / at the hub
INK = 20 / 24  # an icon's paths fill this much of its square: Lucide draws inside a 20 × 20 live area of its 24 × 24 grid
STROKE = {"icon": 3.5, "hub": 4, "badge": 2.5, "hero": 4.5, "tile": 2.5}  # px, the kit's (runtime-contract "Strokes")
SHORT, SHORT_HUB = 46, 112  # a link stops this far from the centre of a normal / hub-sized node
MIN_LINK = 48  # a link with less line than this showing between its two cut ends is refused: a flow dot would hop along a stub
BADGE, TILE, HERO = 34, 30, 170  # sides of a badge, a split tile and the hero icon
TUNNEL_HALF = 6  # a `tunnel` link is two rails this far either side of its line; the kit draws them there
LABEL_FONT, LABEL_SIZE, LABEL_MAX = "BeVietnamPro-Bold.ttf", 22, 140  # a node's label; wider than 140 px is an error
MONO, EXTRA = "IBMPlexMono-SemiBold.ttf", "BeVietnamPro-ExtraBold.ttf"
SPACING = 2  # px between the letters of every IBM Plex Mono text (the spike's .lbl)
ALIGN = {"l": "left", "m": "center"}
CHIP_PAD = (19, 7)  # the spike's chip: padding 4 × 16 and a 3 px border, around the text
SECTION_XY = (60, 190)
LEFT_EDGE, RIGHT_EDGE = 40, 680  # nothing nearer the sides (y < 535: the logo's edge and a margin; below: UI_RIGHT)
DIAGRAM = (250, 900)  # labels and chips next to a node stay in these rows
HARD = (UI_TOP, 999)  # everything else: below the top bar, and (y >= 1000 is the caption band) above the captions
# How far from the icon's ink, in the order tried. 4 comes after 8 only because in a full ring r0's and r3's label under the icon
# (at 8) comes within 3 px of the next node's tile; it is tried only when 8 is blocked.
LABEL_GAPS, CHIP_GAPS = (8, 4, 16, 24, 32, 40), (12, 24, 36, 48, 60, 72, 84)
FREE_CHIPS = (60, 12)  # a chip without `near`: the left column, and the gap between two of them
HERO_LABEL_Y = 756
QUOTE_W = 480  # how wide a quote's words may run: the spike starts them at x 96, y 458 inside the bubble


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float


STATEMENT_BAND = Box(60, 870, 612, 990)
QUOTE_BOX = Box(60, 380, 600, 750)


def _xyxy(b: "Box | list[float]") -> tuple[float, float, float, float]:
    return (b.x0, b.y0, b.x1, b.y1) if isinstance(b, Box) else tuple(b)


def boxes_overlap(a: Box | list[float], b: Box | list[float], margin: float = 4) -> bool:
    """True when the two boxes touch or come nearer than `margin`."""
    ax0, ay0, ax1, ay1 = _xyxy(a)
    bx0, by0, bx1, by1 = _xyxy(b)
    return ax0 < bx1 + margin and bx0 < ax1 + margin and ay0 < by1 + margin and by0 < ay1 + margin


def segment_hits_box(link: dict, box: Box | list[float], margin: float = 4) -> bool:
    """True when the link's line (a `tunnel`'s two rails too) comes within `margin` of the box."""
    m = margin + (TUNNEL_HALF if link.get("style") == "tunnel" else 0)
    x0, y0, x1, y1 = _xyxy(box)
    px, py, dx, dy = link["x1"], link["y1"], link["x2"] - link["x1"], link["y2"] - link["y1"]
    t0, t1 = 0.0, 1.0  # Liang-Barsky: the part of the segment inside the box grown by the margin
    for p, q in ((-dx, px - (x0 - m)), (dx, x1 + m - px), (-dy, py - (y0 - m)), (dy, y1 + m - py)):
        if p == 0:
            if q < 0:
                return False
        elif p < 0:
            t0 = max(t0, q / p)
        else:
            t1 = min(t1, q / p)
    return t0 <= t1


def _line(font: str, size: int) -> int:
    return sum(_font(size, font).getmetrics())  # ascent + descent: the height of a line of this font


def text_box(text: str, font: str, size: int, x: float, y: float, anchor: str = "l") -> Box:
    """The line `text` takes, drawn at `size`: 6 % wider than PIL measures (IBM Plex Mono is drawn with 2 px between letters, so
    those count too), as tall as the font's line. `x` is its left edge (anchor "l"), its middle ("m") or its right edge ("r");
    `y` is its top."""
    f = _font(size, font)
    w = (f.getbbox(text)[2] + (SPACING * max(len(text) - 1, 0) if font == MONO else 0)) * 1.06
    x0 = x - {"l": 0, "m": w / 2, "r": w}[anchor]
    return Box(x0, y, x0 + w, y + _line(font, size))


def _lst(b: Box) -> list[float]:
    return [round(v, 2) for v in _xyxy(b)]


def _inside(b: Box, top: float, bottom: float) -> bool:
    """In the safe zone: clear of the sides, the top bar, the caption band, and (below y 535) the buttons on the right."""
    eps = 1e-6
    return (b.x0 >= LEFT_EDGE - eps and b.y0 >= top - eps and b.y1 <= bottom + eps
            and b.x1 <= (UI_RIGHT if b.y1 > UI_RIGHT_FROM else RIGHT_EDGE) + eps)


def _wrap(text: str, font: str, size: int, width: float, max_lines: int) -> list[str] | None:
    """The lines `text` breaks into at `width`, or None when that takes more than `max_lines` or a word is wider than a line."""
    fit = lambda s: text_box(s, font, size, 0, 0).x1 <= width
    lines, cur = [], ""
    for word in text.split():
        if fit(f"{cur} {word}".strip()):
            cur = f"{cur} {word}".strip()
        else:
            lines, cur = lines + [cur] * bool(cur), word
    lines.append(cur)
    return lines if len(lines) <= max_lines and all(map(fit, lines)) else None


def _balanced(text: str, font: str, size: int, width: float) -> list[str] | None:
    """`_wrap` into at most 2 lines, with its cut kept, except when the second line is one orphan word ("Cập nhật ngay hôm | nay"):
    then the cut moves back to the latest point that leaves two or more words below and still fits `width`; if none does, the
    greedy cut stays. (Not a rebalance of every statement: a cut moved mid-sentence splits Vietnamese compounds, Ruling 36.)
    None when it will not fit, as `_wrap`."""
    lines = _wrap(text, font, size, width, 2)
    if lines is None or len(lines) < 2 or len(lines[1].split()) > 1:
        return lines
    words = text.split()
    for k in range(len(words) - 2, 0, -1):  # k words on the first line, the rest (at least 2) on the second
        cut = [" ".join(words[:k]), " ".join(words[k:])]
        if all(text_box(ln, font, size, 0, 0).x1 <= width for ln in cut):
            return cut
    return lines


def _icon(kind: str, id: str, name: str, x: float, y: float, size: float, tone: str, **more) -> dict:
    h = (size * INK + STROKE["hub" if kind == "icon" and size >= HUB else kind]) / 2  # the drawn ink: live area plus the stroke
    return {"id": id, "kind": kind, "icon": name, "x": x, "y": y, "size": size, "tone": tone,
            "box": _lst(Box(x - h, y - h, x + h, y + h)), **more}


def _text(kind: str, id: str, text: str, font: str, size: int, b: Box, tone: str | None, **more) -> dict:
    return {"id": id, "kind": kind, "text": text, "font": font, "size": size, "tone": tone, "box": _lst(b), **more}


def _short(icon: dict) -> int:
    return SHORT_HUB if icon["size"] >= HUB else SHORT


def _spots(ib: Box, w: float, h: float, gap: float, order: str):
    """The four places a w × h box can stand `gap` from the icon box `ib`, in the order of `order`'s letters (a bove, b elow,
    l eft, r ight). Below is slid sideways, just enough, when it would leave the picture."""
    cx, cy = (ib.x0 + ib.x1) / 2, (ib.y0 + ib.y1) / 2
    for side in order:
        if side == "b":
            y = ib.y1 + gap
            lim = UI_RIGHT if y + h > UI_RIGHT_FROM else RIGHT_EDGE
            x = min(max(cx - w / 2, LEFT_EDGE), lim - w)
            yield Box(x, y, x + w, y + h)
        elif side == "a":
            yield Box(cx - w / 2, ib.y0 - gap - h, cx + w / 2, ib.y0 - gap)
        elif side == "l":
            yield Box(ib.x0 - gap - w, cy - h / 2, ib.x0 - gap, cy + h / 2)
        else:
            yield Box(ib.x1 + gap, cy - h / 2, ib.x1 + gap + w, cy + h / 2)


def place(section: Section, kept: list[dict] = ()) -> list[dict]:
    """Every element the section's nodes, links and beats need, with absolute boxes: this section's own, never the `kept` ones
    (runtime elements still on screen from the section before: they stay where they are, and everything is placed around them).
    Nodes, links, badges and tiles stand where their slot says; a node's label and a chip with `near` take the first spot that
    is free (nothing within 4 px of a link, an icon or other text) and inside the safe zone. All problems come at once."""
    sid, tone = section.id, section.tone
    slots = SLOTS[section.layout]
    icons = {e["id"]: e for e in kept if e["kind"] == "icon"}
    out: list[dict] = []
    solid = [e["box"] for e in kept if e["kind"] != "link"]  # what text may not touch
    segs = [e for e in kept if e["kind"] == "link"]
    problems: list[str] = []

    def put(e: dict, obstacle: bool = True) -> None:
        out.append(e)
        if obstacle:
            (segs if e["kind"] == "link" else solid).append(e if e["kind"] == "link" else e["box"])

    def free(b: Box, top: float = DIAGRAM[0], bottom: float = DIAGRAM[1]) -> bool:
        return (_inside(b, top, bottom) and not any(boxes_overlap(b, o) for o in solid)
                and not any(segment_hits_box(s, b) for s in segs))

    def node(nid: str, where: str) -> dict:
        if nid not in icons:
            raise SceneError(f"{where}: nút {nid!r} không có chỗ (mục {sid} chưa khai báo và không giữ nó)")
        return icons[nid]

    for n in section.nodes:
        x, y = slots[n.slot]
        icons[n.id] = _icon("icon", n.id, n.icon, x, y, HUB if n.slot == "hub" else ICON, tone)
        put(icons[n.id])
    for ln in section.links:
        a, b = node(ln.a, f"nối {ln.id}"), node(ln.b, f"nối {ln.id}")
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        d, sa, sb = math.hypot(dx, dy), _short(a), _short(b)
        if d - sa - sb < MIN_LINK:
            problems.append(f"nối {ln.id}: {ln.a} và {ln.b} quá gần nhau để nối (chỉ thấy {max(d - sa - sb, 0):.0f} px đường, "
                            f"cần ít nhất {MIN_LINK})")
            continue
        ux, uy = dx / d, dy / d
        x1, y1, x2, y2 = a["x"] + ux * sa, a["y"] + uy * sa, b["x"] - ux * sb, b["y"] - uy * sb
        put({"id": ln.id, "kind": "link", "a": ln.a, "b": ln.b, "style": ln.style, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
             "tone": tone, "box": [round(v, 2) for v in (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))]})

    if section.label:
        b = text_box(section.label, MONO, 22, *SECTION_XY)
        if _inside(b, *HARD):
            put(_text("section", f"{sid}.label", section.label, MONO, 22, b, tone, align=ALIGN["l"]))
        else:
            problems.append(f"nhãn mục {sid}: dài quá, ra ngoài vùng an toàn")

    chips: list[tuple[int, Beat]] = []  # tried last, once everything that has its own spot is down
    for k, bt in enumerate(section.beats):
        a, eid, where = bt.args, f"{sid}.{k}", f"mục {sid}, nhịp {k} ({bt.do})"
        if bt.do == "badge":
            n = node(a["node"], where)
            put(_icon("badge", eid, a["icon"], n["x"] - 0.6 * n["size"], n["y"] - 0.74 * n["size"], BADGE, tone,
                      of=a["node"], beat=k))
        elif bt.do == "swap":
            n = node(a["node"], where)
            put(_icon("icon", eid, a["icon"], n["x"], n["y"], n["size"], n["tone"], of=a["node"], beat=k), obstacle=False)
        elif bt.do in ("split", "merge"):  # a tile for each piece
            ends = a["to"] if bt.do == "split" else a["from"]  # where the pieces go (split) or come from (merge)
            node(a["node"] if bt.do == "split" else a["into"], where)
            for nid in ends:
                node(nid, where)
            # a split's tiles rest over the nodes they go to; a merge's all rest over `into`, on one spot, where they become one
            # piece (Task 6's `move` flies each from its own node's spot to there)
            for j, rest in enumerate(ends if bt.do == "split" else [a["into"]] * len(ends)):
                n = node(rest, where)
                ty, h = n["y"] - n["size"] / 2 - 41, (TILE + STROKE["tile"]) / 2  # it hangs above the icon, as in the spike
                put({"id": f"{eid}.{j}", "kind": "tile", "beat": k, "x": n["x"], "y": ty, "size": TILE, "tone": tone,
                     "box": _lst(Box(n["x"] - h, ty - h, n["x"] + h, ty + h))})
        elif bt.do == "hero":
            label = a.get("label", "")
            lb = text_box(label, MONO, 30, C[0], HERO_LABEL_Y, "m") if label else Box(C[0], HERO_LABEL_Y, C[0], HERO_LABEL_Y)
            hero = _icon("hero", eid, a["icon"], C[0], C[1] - 6, HERO, a.get("tone", "safe"), beat=k, label=label, label_box=_lst(lb))
            if label:  # the hero's box holds its label too, so every check sees it
                hero["box"] = [f(p, q) for f, p, q in zip((min, min, max, max), hero["box"], hero["label_box"])]
            if label and not _inside(lb, *HARD):
                problems.append(f"nhãn của hero ({where}): dài quá, ra ngoài vùng an toàn")
            out.append(hero)
        elif bt.do == "statement":
            band = STATEMENT_BAND
            if (lines := _balanced(a["text"], EXTRA, 44, band.x1 - band.x0)) is None:
                problems.append(f"câu lớn {a['text']!r} ({where}): dài quá, hơn 2 dòng trong dải chữ")
                continue
            w, lh = max(text_box(s, EXTRA, 44, 0, 0).x1 for s in lines), _line(EXTRA, 44)
            x0 = (band.x0 + band.x1 - w) / 2  # the lines are centred in their box, and the box in the band
            out.append(_text("statement", eid, a["text"], EXTRA, 44, Box(x0, band.y0, x0 + w, band.y0 + lh * len(lines)), None,
                             beat=k, lines=lines, lh=lh))
        elif bt.do == "quote":
            if (lines := _wrap(a["text"], EXTRA, 54, QUOTE_W, 4)) is None:
                problems.append(f"lời trích {a['text']!r} ({where}): dài quá, hơn 4 dòng trong bong bóng")
                continue
            if text_box(a["who"], MONO, 24, 0, 0).x1 > QUOTE_W:
                problems.append(f"lời trích {a['text']!r} ({where}): tên người nói {a['who']!r} dài quá")
                continue
            out.append(_text("quote", eid, a["text"], EXTRA, 54, QUOTE_BOX, a.get("tone", "claim"), beat=k, who=a["who"],
                             lines=lines, lh=_line(EXTRA, 54)))
        elif bt.do == "chip":
            chips.append((k, bt))

    for n in section.nodes:
        if not n.label:
            continue
        ic = icons[n.id]
        t = text_box(n.label, LABEL_FONT, LABEL_SIZE, 0, 0)
        if t.x1 > LABEL_MAX:
            problems.append(f"nhãn của {n.id}: rộng {t.x1:.0f} px, tối đa {LABEL_MAX}")
            continue
        spots = (s for g in LABEL_GAPS for s in _spots(Box(*ic["box"]), t.x1, t.y1, g, "balr"))
        if (b := next((s for s in spots if free(s)), None)) is None:
            problems.append(f"nhãn của {n.id}: không còn chỗ trống")
        else:
            put(_text("label", f"{n.id}.label", n.label, LABEL_FONT, LABEL_SIZE, b, tone, align=ALIGN["m"], of=n.id))

    y = 250 if section.label else 190  # where the next chip without `near` may start
    for k, bt in chips:
        text = bt.args["text"]
        t = text_box(text, MONO, 22, 0, 0)
        w, h = t.x1 + 2 * CHIP_PAD[0], t.y1 + 2 * CHIP_PAD[1]
        if near := bt.args.get("near"):
            ic = node(near, f"mục {sid}, nhịp {k} (chip)")
            spots = (s for g in CHIP_GAPS for s in _spots(Box(*ic["box"]), w, h, g, "abrl"))
            b, who = next((s for s in spots if free(s)), None), f" cạnh {near}"
        else:  # the left column, top down: the first place that is free
            x = FREE_CHIPS[0]
            b = next((Box(x, yy, x + w, yy + h) for yy in range(math.ceil(y), DIAGRAM[1], 4)
                      if free(Box(x, yy, x + w, yy + h), UI_TOP)), None)
            who = ""
            if b:
                y = b.y1 + FREE_CHIPS[1]
        if b is None:
            problems.append(f"chip {text!r}{who}: không còn chỗ trống")
        else:
            put(_text("chip", f"{sid}.{k}", text, MONO, 22, b, bt.args.get("tone", "claim"), align=ALIGN["m"], beat=k))

    if problems:
        raise SceneError(problems)
    return out
