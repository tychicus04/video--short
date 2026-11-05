"""Reference cards (the SVGs an agent writes into visuals/) that write themselves out: the border pencilled in first, so the cut
between two pictures never lands on blank paper, then each element wiped in from the left, one after another."""
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image, ImageDraw

from vshort import kit
from vshort.visuals import MIN_CONTRAST, PAPER

ET.register_namespace("", "http://www.w3.org/2000/svg")  # so a re-serialised element keeps its plain name
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
W, H, SS = kit.W, kit.H, kit.SS
# in every render, never an element of their own: they paint nothing, but what is drawn may refer to them
ALWAYS = {"defs", "style", "title", "desc", "metadata", "linearGradient", "radialGradient", "pattern", "marker", "clipPath",
          "mask", "symbol", "filter"}
LEAD_INK = 0.01  # with no frame, the first elements are there at the cut until they cover this share of the card's box
SHARE = 0.6  # the elements are written out within this share of the line, so the card is whole well before it ends
WIPE = 0.5  # the longest one element takes to be wiped in
EDGE = 36  # the soft edge of a wipe, in 2x pixels
BORDER_SHARE = 0.5  # a frame is at least this share of the card's width
INK = 8  # alpha from which a pixel counts as ink
PAD = 24  # the room the camera keeps round the card
GREY = (74, 74, 74)  # the stroke grey agents are told to use (#4a4a4a)
SEED = 11
SETTLE = 0.3  # once drawn, the pencilled frame eases into the SVG's own straight rect, so the finished card is the SVG


@dataclass(frozen=True)
class Piece:
    """One element of the card and when it is written: from t0 to t1 (t1 == t0: there at once). `box` in 1x image pixels."""
    t0: float
    t1: float
    box: tuple[float, float, float, float]
    border: bool


@dataclass
class _Layer:
    box: tuple[float, float, float, float]
    x: int  # where the crop sits, 2x pixels
    y: int
    mask: Image.Image  # the element's alpha, whole
    rgb: Image.Image | tuple  # its colours; for the border, the pencil colour
    alpha: np.ndarray | None = None
    pencil: tuple | None = None  # the frame only: its outline (shifted to the crop's origin), line width and crop size
    drawn: Image.Image | None = None  # the frame only: the whole pencil outline


def _num(el, key, default=0.0) -> float:
    return float(el.get(key, default))


def _style(el, key) -> str:
    m = re.search(rf"(?:^|;)\s*{key}\s*:\s*([^;]+)", el.get("style", ""))
    return (m.group(1) if m else el.get(key, "")).strip()


def _grey(text: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", text)
    if not m:
        return GREY
    h = m.group(1)
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _frame_of(el, ink_w: float, card_w: float):
    """(pts, colour, width) when `el` is a rect with no fill, as wide as the card is, that can be pencilled; else None."""
    if el.tag.rsplit("}", 1)[-1] != "rect" or ink_w < BORDER_SHARE * card_w or el.get("transform"):
        return None
    if _style(el, "fill") not in ("none", "transparent") and _style(el, "fill-opacity") != "0":
        return None
    if _style(el, "stroke-dasharray") not in ("", "none"):
        return None
    try:
        x, y, w, h = (_num(el, k) for k in ("x", "y", "width", "height"))
        r = min(_num(el, "rx", _num(el, "ry", 0)), w / 2, h / 2)
        sw = float(_style(el, "stroke-width") or 1)
    except ValueError:
        return None
    pts = kit._rrect(x, y, x + w, y + h, r) if r > 0 else [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    return pts, _grey(_style(el, "stroke")), max(1, round(sw))


def _render(shell: ET.Element) -> np.ndarray:
    png = cairosvg.svg2png(bytestring=ET.tostring(shell), output_width=W * SS, output_height=H * SS)
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


@lru_cache(maxsize=16)
def _layers(path: str, mtime: int, size: int) -> list[_Layer]:
    """Each element of the file that leaves ink, in drawing order; the one that is the frame carries its pencil outline."""
    root = ET.parse(path).getroot()
    shared = [c for c in root if isinstance(c.tag, str) and c.tag.rsplit("}", 1)[-1] in ALWAYS]
    kids = [c for c in root if isinstance(c.tag, str) and c.tag.rsplit("}", 1)[-1] not in ALWAYS]
    found = []
    for el in kids:
        shell = ET.Element(root.tag, root.attrib)
        shell.extend(shared + [el])
        a = _render(shell)
        ys, xs = np.nonzero(a[..., 3] >= INK)
        if len(xs):
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            crop = a[y0:y1, x0:x1]
            found.append((el, _Layer(tuple(float(v) / SS for v in (x0, y0, x1, y1)), int(x0), int(y0), Image.fromarray(crop[..., 3].copy()),
                                     Image.fromarray(crop[..., :3].copy()), crop[..., 3].copy())))
    if not found:
        return []
    card_w = max(l.box[2] for _, l in found) - min(l.box[0] for _, l in found)
    for el, lay in found:  # the first unfilled, wide rect is the frame, wherever it sits in the file
        pencil = _frame_of(el, lay.box[2] - lay.box[0], card_w)
        if pencil:
            pts, color, width = pencil
            ox, oy = int(lay.box[0]) - width - 4, int(lay.box[1]) - width - 4
            ex, ey = int(lay.box[2]) + width + 5, int(lay.box[3]) + width + 5
            exact = Image.new("L", ((ex - ox) * SS, (ey - oy) * SS))  # the rect as the SVG draws it, on the pencil's crop
            exact.paste(lay.mask, (lay.x - ox * SS, lay.y - oy * SS))
            lay.x, lay.y, lay.mask, lay.rgb, lay.alpha = ox * SS, oy * SS, exact, color, None
            lay.pencil = ([(px - ox, py - oy) for px, py in pts], width, (ex - ox, ey - oy))
            lay.drawn = _pencil(lay, 1.0)
            break
    return [lay for _, lay in found]


def _pencil(lay: _Layer, p: float) -> Image.Image:
    """The first fraction p of the frame's outline, as a mask the size of its crop (2x)."""
    pts, width, (w, h) = lay.pencil
    mask = Image.new("L", (w * SS, h * SS))
    kit._stroke(ImageDraw.Draw(mask), pts, p, 255, width, SEED)
    return mask


def _wiped(lay: _Layer, p: float) -> Image.Image:
    """The element's alpha, uncovered from the left up to a soft edge as p goes 0 → 1."""
    w = lay.alpha.shape[1]
    ramp = np.clip((p * (w + EDGE) - np.arange(w)) / EDGE, 0, 1)
    return Image.fromarray((lay.alpha * ramp[None, :]).astype(np.uint8))


def _leading(layers: list[_Layer], box) -> int:
    """How many of the first elements, in file order, it takes to put LEAD_INK of `box` in ink (all of them if never)."""
    x0, y0, x1, y1 = (int(v * SS) for v in box)
    img = Image.new("RGB", (W * SS, H * SS), PAPER)
    for n, lay in enumerate(layers, 1):
        img.paste(lay.rgb, (lay.x, lay.y), lay.mask)
        ink = np.abs(np.asarray(img.crop((x0, y0, x1, y1))).astype(int) - PAPER).max(2) > MIN_CONTRAST
        if ink.mean() >= LEAD_INK:
            return n
    return len(layers)


class Card:
    """A reference card as a sequence: `pieces` say when each element is written, `frame(t)` is the card at t (1440×2560, on paper).

    The border takes [start - xf/2, start], so it is whole when the render cuts to the card (the picture before it is
    still fading out for half of xf); the other elements share the first SHARE of [start, end]. A card with no border
    has its first elements there from start - xf/2, as many as it takes to fill LEAD_INK of its box. At and after `end` the
    card is whole."""

    def __init__(self, svg: Path, start: float, end: float, xf: float):
        self.svg, self.start, self.end, self.xf = Path(svg), start, end, xf
        st = self.svg.stat()
        layers = _layers(str(self.svg.resolve()), st.st_mtime_ns, st.st_size)
        outline = next((l for l in layers if l.pencil), None)
        lead = start - xf / 2
        boxes = [l.box for l in layers]
        self.ink_box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                        max(b[3] for b in boxes)) if boxes else (0.0, 0.0, float(W), float(H))
        here = 1 if outline else _leading(layers, self.ink_box)  # written at once: the frame, or the first elements
        order = ([outline] if outline else []) + [l for l in layers if l is not outline]  # the order they are written in
        slot = SHARE * (end - start) / max(len(order) - here, 1)
        times = {}
        for n, lay in enumerate(order):
            if n == 0 and outline:
                times[id(lay)] = (lead, start)
            elif n < here:
                times[id(lay)] = (lead, lead)
            else:
                t0 = start + (n - here) * slot
                times[id(lay)] = (t0, t0 + min(WIPE, slot))
        self._settled = min(start + SETTLE, end)  # the frame is the SVG's own rect from here on
        self.pieces: list[Piece] = [Piece(*times[id(l)], l.box, l is outline) for l in order]
        self._timed = [(l, times[id(l)]) for l in layers]  # painted in the file's order

    def frame(self, t: float) -> Image.Image:
        img = Image.new("RGB", (W * SS, H * SS), PAPER)
        for lay, (t0, t1) in self._timed:
            p = 1.0 if t >= t1 else 0.0 if t < t0 else kit.ease((t - t0) / (t1 - t0))
            if p <= 0:
                continue
            if lay.pencil:
                if p < 1:
                    mask = _pencil(lay, p)
                elif t >= self._settled:
                    mask = lay.mask
                else:
                    mask = Image.blend(lay.drawn, lay.mask, kit.ease((t - t1) / (self._settled - t1)))
                img.paste(lay.rgb, (lay.x, lay.y), mask)
            else:
                img.paste(lay.rgb, (lay.x, lay.y), lay.mask if p >= 1 else _wiped(lay, p))
        return img


def cap(card: Card) -> float:
    """The most the camera may zoom on the card and still keep its ink, with PAD on each side, inside the 720 px width."""
    x0, _, x1, _ = card.ink_box
    return W / (x1 - x0 + 2 * PAD)
