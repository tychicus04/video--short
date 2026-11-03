"""Hand-drawn animation kit: things draw themselves in pencil on paper, dots and icons move, things turn red."""
import math
import zlib
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vshort.textfit import FONTS
from vshort.visuals import PAPER

W, H, SS = 720, 1280, 2  # frames are drawn at SS x and reduced: smooth pencil lines
INK, RED, GREEN, BLUE, GRAY = (62, 62, 68), (196, 48, 40), (60, 140, 80), (70, 110, 160), (150, 150, 155)
COLORS = {"ink": INK, "red": RED, "green": GREEN, "blue": BLUE}
SAFE = (40, 96, 680, 1050)  # above the subtitle band, under the logo (top right, y 24–80)
SX, SY = (SAFE[0] + SAFE[2]) / 2, (SAFE[1] + SAFE[3]) / 2  # the camera's centre on screen
FULL = (SX, SY, 1.0)  # (cx, cy, zoom): the whole canvas, drawn as it is
LABEL_EM, SMALL_EM, MIN_LABEL_EM, MAX_LABEL = 44, 34, 32, 20
DRAW, TURN, HIDE, MOVE = 0.8, 0.6, 0.4, 1.2  # seconds: draw on, turn red, erase, default move/bounce
OPEN = 0.8  # seconds: a hinged part opens or closes
DIM = 0.55  # how far a thing the voice has moved on from fades towards the paper
BOXED = {"phone", "computer", "server", "box", "wall", "shape"}  # take `box`
POINTED = {"person", "icon", "dot", "text", "crack", "figure", "check", "cross"}  # take `xy`
ICONS = {"key", "message", "wallet", "file", "lock", "mail"}
MOVERS = {"dot", "icon", "figure", "shape"}  # a shape moves by the centre of its box
ROLES = {"guard", "attacker"}  # a figure's role: a cap, or a hood (and red)
DOT_R = 13
SAY_BOX_H = 100  # a box needs this height to hold its label and a say line under it
TOP = {"dot": DOT_R, "icon": 55, "figure": 112}  # ink above a mover's centre (a shape: half its box)
STEP_HZ, SWING, BOB = 2.0, 12.0, 6.0  # a walking figure: steps a second, leg spread in degrees, bob in px


@dataclass
class Act:
    do: str  # draw | move | bounce | red | pulse | hide | dim | undim
    thing: str
    t0: float
    t1: float
    to: tuple[float, float] | None = None
    path: list[tuple[float, float]] | None = None
    say: str = ""
    vanish: bool = False
    on: str = ""  # attach: the mover it is carried by from then on
    offset: tuple[float, float] | None = None  # attach: where on the carrier it sits


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def ease(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


@lru_cache
def _font(em: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), em)


@lru_cache(maxsize=1)
def _paper() -> Image.Image:
    noise = np.random.default_rng(7).normal(0, 2.2, (H * SS, W * SS, 1))
    return Image.fromarray((np.array(PAPER) + noise).clip(0, 255).astype(np.uint8))


@lru_cache(maxsize=4096)
def _wobble(pts: tuple, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """A polyline densified and pushed sideways a little, like a pencil line; with its running length."""
    p = np.asarray(pts, float)
    out = [p[0]]
    for a, b in zip(p, p[1:]):
        n = max(2, int(np.hypot(*(b - a)) / 4))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    q = np.array(out)
    d = np.gradient(q, axis=0)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1) / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9)
    s = np.arange(len(q))
    r = np.random.default_rng(seed)
    f1, f2, p1, p2 = r.uniform(0.02, 0.05), r.uniform(0.1, 0.2), r.uniform(0, 6), r.uniform(0, 6)
    q = q + nrm * (1.3 * (np.sin(s * f1 + p1) + 0.4 * np.sin(s * f2 + p2)))[:, None]
    return q, np.concatenate([[0], np.cumsum(np.hypot(*np.diff(q, axis=0).T))])


def screen(view, x: float, y: float) -> tuple[float, float]:
    """Where canvas point (x, y) lands on the frame through the camera `view` = (cx, cy, zoom)."""
    cx, cy, z = view
    return (x - cx) * z + SX, (y - cy) * z + SY


def _stroke(d: ImageDraw.ImageDraw, pts, p: float, color, width: int, seed: int, dash: int = 0, view=FULL) -> None:
    """The first fraction p of a wobbly polyline (by length), optionally dashed; wobbled on the canvas, then seen
    through the camera."""
    if p <= 0 or len(pts) < 2:
        return
    q, cum = _wobble(tuple(map(tuple, pts)), seed)
    keep = cum <= cum[-1] * p
    q, cum = q[keep], cum[keep]
    if view != FULL:
        q = (q - view[:2]) * view[2] + (SX, SY)
        width, dash = width * view[2], dash * view[2]
    q, width = q * SS, round(width * SS)
    if len(q) < 2:
        return
    if not dash:
        d.line([tuple(v) for v in q], fill=color, width=width, joint="curve")
        return
    on = (cum // dash) % 2 == 0
    run: list[tuple] = []
    for v, o in zip(q, on):
        if o:
            run.append(tuple(v))
        elif run:
            if len(run) > 1:
                d.line(run, fill=color, width=width)
            run = []
    if len(run) > 1:
        d.line(run, fill=color, width=width)


def _rrect(x0, y0, x1, y1, r) -> list[tuple[float, float]]:
    pts = []
    for cx, cy, a0 in [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]:
        pts += [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(a0, a0 + 91, 10)]
    return pts + [pts[0]]


def _along(pts, p: float) -> tuple[float, float]:
    a = np.asarray(pts, float)
    seg = np.hypot(*np.diff(a, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = cum[-1] * clamp(p)
    k = min(int(np.searchsorted(cum, s, side="right")) - 1, len(seg) - 1)
    u = (s - cum[k]) / seg[k] if seg[k] else 0
    return tuple(a[k] + (a[k + 1] - a[k]) * u)


def _write(img: Image.Image, xy, text: str, em: int, p: float, color, view=FULL) -> None:
    """Handwriting: the text wiped in from left to right, centred on xy (drawn on a small layer: fast)."""
    if p <= 0 or not text:
        return
    if view != FULL:
        xy, em = screen(view, *xy), max(1, round(em * view[2]))
    f = _font(em * SS)
    l, t, r, b = f.getbbox(text, anchor="mm")
    x, y = xy[0] * SS, xy[1] * SS
    layer = Image.new("RGBA", (int(r - l) + 8, int(b - t) + 8))
    ImageDraw.Draw(layer).text((4 - l, 4 - t), text, font=f, fill=color, anchor="mm")
    layer = layer.crop((0, 0, max(1, int(layer.width * clamp(p))), layer.height))
    img.paste(layer, (int(x + l) - 4, int(y + t) - 4), layer)


def _color(thing: dict) -> tuple[int, int, int]:
    default = {"dot": "red", "wall": "blue", "check": "green", "cross": "red"}.get(thing["kind"], "ink")
    if thing.get("role") == "attacker":
        default = "red"
    return COLORS[thing.get("color", default)]


def label_em(thing: dict) -> int:
    """Em of the label: fitted inside a box (0 when it cannot be), fixed elsewhere."""
    kind, text = thing["kind"], thing.get("label", "")
    if kind in ("icon", "dot"):
        return SMALL_EM
    if kind != "box":
        return LABEL_EM
    x0, _, x1, _ = thing["box"]
    for em in range(LABEL_EM, MIN_LABEL_EM - 1, -1):
        if _font(em).getlength(text) <= x1 - x0 - 32:
            return em
    return 0


def _label_at(thing: dict, xy=None) -> tuple[float, float]:
    """Centre of the label (for movers, relative to where the thing is now)."""
    kind = thing["kind"]
    if kind in BOXED:
        x0, y0, x1, y1 = thing["box"]
        return ((x0 + x1) / 2, (y0 + y1) / 2) if kind == "box" else ((x0 + x1) / 2, y0 - 34)
    x, y = xy or thing["xy"]
    return {"person": (x, y + 105), "icon": (x, y + 55), "dot": (x, y + 48), "text": (x, y),
            "figure": (x, y + 125)}.get(kind, (x, y))


def _bezier(p0, p1, p2, p3, n: int = 12) -> list[tuple[float, float]]:
    return [tuple((1 - u) ** 3 * a + 3 * (1 - u) ** 2 * u * b + 3 * (1 - u) * u * u * c + u ** 3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3)) for u in np.linspace(0, 1, n)]


def _legs(x: float, y: float, spread: float) -> list[list[tuple[float, float]]]:
    """Left and right leg, hip to foot; spread 0 stands (mirror images), 1 is a full stride (feet SWING degrees out)."""
    a = math.radians(SWING * spread)
    out = []
    for side in (-1, 1):
        fx, fy = side * (2 * math.cos(a) + 52 * math.sin(a)), 52 * math.cos(a) - 2 * math.sin(a)
        out.append([(x + 14 * side, y + 40), (x + 14 * side + fx, y + 40 + fy)])
    return out


def _figure(x: float, y: float, spread: float, role) -> list[list[tuple[float, float]]]:
    """A figure as in the approved sketch: round head, rounded torso, two legs; a cap (guard) or a hood (attacker)."""
    def at(pts):
        return [(x + px, y + py) for px, py in pts]

    head = [(x + 24 * math.cos(u), y - 70 + 24 * math.sin(u)) for u in np.linspace(0, 2 * math.pi, 25)]
    torso = _bezier((-36, 40), (-38, -10), (-26, -38), (0, -40)) + _bezier((0, -40), (26, -38), (38, -10), (36, 40))[1:]
    out = [head, at(torso + [(-36, 40)]), *_legs(x, y, spread)]
    if role == "guard":
        out += [at(_bezier((-28, -84), (-20, -106), (20, -106), (28, -84)) + [(-28, -84)]), at([(26, -86), (46, -82)])]
    elif role == "attacker":
        out.append(at(_bezier((-34, -60), (-42, -114), (42, -114), (34, -60)) + [(30, -38)]))
    return out


def at_pos(thing: dict, xy) -> dict:
    """The thing moved so its anchor (`xy`, or the centre of its box) is at xy."""
    if "box" not in thing:
        return thing | {"xy": [xy[0], xy[1]]}
    x0, y0, x1, y1 = thing["box"]
    dx, dy = xy[0] - (x0 + x1) / 2, xy[1] - (y0 + y1) / 2
    out = thing | {"box": [x0 + dx, y0 + dy, x1 + dx, y1 + dy]}
    if "strokes" in thing:
        out["strokes"] = [[(px + dx, py + dy) for px, py in s] for s in thing["strokes"]]
    if thing.get("hinge"):
        px, py = thing["hinge"]["pivot"]
        out["hinge"] = thing["hinge"] | {"pivot": (px + dx, py + dy)}
    return out


def _hinged(strokes: list[tuple[list, int, int]], hinge: dict, level: float) -> list[tuple[list, int, int]]:
    """The strokes with the hinged ones opened `level` of the way: turned about the pivot or folded towards it."""
    px, py = hinge["pivot"]
    if hinge.get("turn") is not None:
        a = math.radians(hinge["turn"] * level)
        c, s = math.cos(a), math.sin(a)
        move = lambda x, y: (px + (x - px) * c - (y - py) * s, py + (x - px) * s + (y - py) * c)  # noqa: E731
    else:
        k = 1 - (1 - hinge["squash"]) * level
        move = lambda x, y: (px + (x - px) * k, y)  # noqa: E731
    return [([move(*p) for p in pts], w, dash) if n in hinge["strokes"] else (pts, w, dash)
            for n, (pts, w, dash) in enumerate(strokes)]


def _shape(thing: dict) -> list[tuple[list, int, int]]:
    """(polyline, width, dash) strokes of a still thing, in frame px."""
    kind = thing["kind"]
    if kind in BOXED:
        x0, y0, x1, y1 = thing["box"]
        w, h, cx = x1 - x0, y1 - y0, (x0 + x1) / 2
        if kind == "wall":
            return [(_rrect(x0, y0, x1, y1, 30), 4, 18)]
        if kind == "shape":
            return [(pts, 3, 0) for pts in thing["strokes"]]  # a library shape, scaled into its box by motion
        if kind == "box":
            return [(_rrect(x0, y0, x1, y1, min(22, h / 3)), 3, 0)]
        if kind == "server":
            slots = [[(x0 + 14, y0 + h * k / 3), (x1 - 14, y0 + h * k / 3)] for k in (1, 2)]
            leds = [_rrect(x0 + 20, y0 + h * (k + 0.5) / 3 - 5, x0 + 30, y0 + h * (k + 0.5) / 3 + 5, 5) for k in range(3)]
            return [(_rrect(x0, y0, x1, y1, 10), 3, 0)] + [(s, 3, 0) for s in slots] + [(s, 3, 0) for s in leds]
        if kind == "computer":
            ym = y0 + 0.8 * h
            return [(_rrect(x0, y0, x1, ym, 14), 3, 0), ([(cx, ym), (cx, y1)], 3, 0),
                    ([(cx - w / 4, y1), (cx + w / 4, y1)], 3, 0)]
        out = [(_rrect(x0, y0, x1, y1, min(50, w / 6)), 3, 0), ([(cx - 40, y1 - 28), (cx + 40, y1 - 28)], 3, 0)]
        return out  # phone
    if kind == "path":
        pts = [tuple(p) for p in thing["points"]]
        out = [(pts, 3, 0)]
        if thing.get("arrow"):
            (ax, ay), (bx, by) = pts[-2], pts[-1]
            a = math.atan2(by - ay, bx - ax)
            head = [(bx - 22 * math.cos(a - s), by - 22 * math.sin(a - s)) for s in (0.45, -0.45)]
            out.append(([head[0], (bx, by), head[1]], 3, 0))
        return out
    x, y = thing["xy"]
    if kind == "crack":
        return [([(x - 30, y), (x - 18, y - 11), (x - 6, y + 11), (x + 6, y - 11), (x + 18, y + 11), (x + 30, y)], 5, 0)]
    if kind == "person":
        head = [(x + 24 * math.cos(a), y - 55 + 24 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 25)]
        return [(head, 4, 0), ([(x, y - 31), (x, y + 30)], 4, 0), ([(x - 38, y), (x, y - 20), (x + 38, y)], 4, 0),
                ([(x - 30, y + 75), (x, y + 30), (x + 30, y + 75)], 4, 0)]
    if kind == "icon":
        return [(s, 5, 0) for s in _icon(thing["icon"], x, y - 15)]
    if kind == "figure":
        return [(s, 4, 0) for s in _figure(x, y, 0.0, thing.get("role"))]
    if kind == "check":
        return [([(x - 24, y), (x - 8, y + 18), (x + 26, y - 22)], 5, 0)]
    if kind == "cross":
        return [([(x - 20, y - 20), (x + 20, y + 20)], 5, 0), ([(x + 20, y - 20), (x - 20, y + 20)], 5, 0)]
    return []


def _icon(name: str, x: float, y: float) -> list[list]:
    if name == "key":
        return [_rrect(x - 40, y - 40, x, y, 18), [(x - 6, y - 10), (x + 40, y + 36), (x + 26, y + 48), (x + 14, y + 36)]]
    if name == "message":
        return [_rrect(x - 48, y - 40, x + 48, y + 22, 14), [(x - 18, y + 22), (x - 34, y + 48), (x - 4, y + 22)]]
    if name == "wallet":
        return [_rrect(x - 48, y - 34, x + 48, y + 36, 10),
                [(x + 10, y - 8), (x + 48, y - 8), (x + 48, y + 14), (x + 10, y + 14), (x + 10, y - 8)]]
    if name == "file":
        return [[(x - 34, y - 44), (x + 14, y - 44), (x + 34, y - 24), (x + 34, y + 44), (x - 34, y + 44), (x - 34, y - 44)],
                [(x + 14, y - 44), (x + 14, y - 24), (x + 34, y - 24)], [(x - 20, y), (x + 20, y)],
                [(x - 20, y + 20), (x + 20, y + 20)]]
    if name == "lock":
        arc = [(x + 24 * math.cos(a), y - 6 + 24 * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 13)]
        return [_rrect(x - 36, y - 6, x + 36, y + 44, 8), arc]
    return [_rrect(x - 48, y - 32, x + 48, y + 32, 6), [(x - 48, y - 32), (x, y + 6), (x + 48, y - 32)]]  # mail


def _screen(thing: dict) -> tuple[tuple, list[list], tuple, int]:
    """Address bar, page lines, url centre and url em of a phone or computer showing a web page."""
    x0, y0, x1, y1 = thing["box"]
    if thing["kind"] == "phone":
        bar, top, bottom = (x0 + 30, y0 + 65, x1 - 30, y0 + 125), y0 + 180, y1 - 80
    else:
        bar, top, bottom = (x0 + 16, y0 + 16, x1 - 16, y0 + 62), y0 + 92, y0 + 0.8 * (y1 - y0) - 20
    lines = [[(x0 + 50, y), (x1 - 50 - 50 * (k % 3), y)] for k, y in enumerate(np.arange(top, bottom, 50))]
    em = 32
    while em > 20 and _font(em).getlength(thing["url"]) > bar[2] - bar[0] - 20:
        em -= 1
    return bar, lines, ((bar[0] + bar[2]) / 2, (bar[1] + bar[3]) / 2), em


def bbox(thing: dict) -> tuple[float, float, float, float]:
    """Extent of the thing including its label (a mover where it starts)."""
    kind = thing["kind"]
    if kind in BOXED:
        x0, y0, x1, y1 = thing["box"]
    elif kind == "path":
        a = np.asarray(thing["points"], float)
        x0, y0, x1, y1 = *a.min(0), *a.max(0)
    else:
        x, y = thing["xy"]
        rx, top, bottom = {"person": (38, 79, 75), "icon": (50, 55, 33), "dot": (DOT_R, DOT_R, DOT_R),
                           "crack": (30, 11, 11), "text": (0, 0, 0), "figure": (40, 112, 92),
                           "check": (26, 22, 22), "cross": (26, 22, 22)}[kind]
        x0, y0, x1, y1 = x - rx, y - top, x + rx, y + bottom
    if thing.get("label") and kind not in ("path", "crack"):
        em = label_em(thing) or MIN_LABEL_EM
        lx, ly = _label_at(thing)
        l, t, r, b = _font(em).getbbox(thing["label"], anchor="mm")
        x0, y0, x1, y1 = min(x0, lx + l), min(y0, ly + t), max(x1, lx + r), max(y1, ly + b)
    return float(x0), float(y0), float(x1), float(y1)


def _anchor(thing: dict) -> tuple[float, float]:
    if "xy" in thing:
        return tuple(thing["xy"])
    x0, y0, x1, y1 = thing["box"]
    return (x0 + x1) / 2, (y0 + y1) / 2


def _top(thing: dict) -> float:
    return (thing["box"][3] - thing["box"][1]) / 2 if thing["kind"] == "shape" else TOP[thing["kind"]]


def _position(thing: dict, acts: list[Act], t: float, by_id: dict[str, dict] | None = None) -> tuple[float, float]:
    """Where a mover is at t: its moves, bounces and attaches applied in order. Once attached it rides on its carrier
    (`by_id` finds it) until a later move or bounce of its own takes it off, from where it was carried to."""
    pos, held = _anchor(thing), None

    def carried(at: float) -> tuple[float, float]:
        cx, cy = _position(by_id[held[0]], acts, at, by_id)
        return cx + held[1][0], cy + held[1][1]

    for a in sorted((a for a in acts if a.thing == thing["id"] and a.do in ("move", "bounce", "attach") and a.t0 <= t),
                    key=lambda a: a.t0):
        if held:
            pos, held = carried(a.t0), None
        u = clamp((t - a.t0) / max(a.t1 - a.t0, 1e-6))
        if a.do == "attach":
            if a.on not in (by_id or {}):
                continue
            off = a.offset or (0.0, 0.0)
            cx, cy = _position(by_id[a.on], acts, min(t, a.t1), by_id)
            if u < 1:
                e = ease(u)
                pos = (pos[0] + (cx + off[0] - pos[0]) * e, pos[1] + (cy + off[1] - pos[1]) * e)
            else:
                pos, held = (cx + off[0], cy + off[1]), (a.on, off)
        elif a.do == "bounce":
            s = math.sin(math.pi * u)
            pos = (pos[0] + (a.to[0] - pos[0]) * s, pos[1] + (a.to[1] - pos[1]) * s) if u < 1 else pos
        elif a.path:
            pos = _along(a.path, ease(u))
        else:
            e, (fx, fy), (tx, ty) = ease(u), pos, a.to
            arc = min(120, 0.25 * math.hypot(tx - fx, ty - fy)) * math.sin(math.pi * e)
            pos = (fx + (tx - fx) * e, max(fy + (ty - fy) * e - arc, SAFE[1] + _top(thing)))  # arc stays in SAFE
    return carried(t) if held else pos


def _shown(thing: dict, acts: list[Act], t: float) -> float:
    """How much of the thing is drawn at t: draws on, erased by hide or a vanishing move."""
    mine = [a for a in acts if a.thing == thing["id"]]
    on = max((ease((t - a.t0) / max(a.t1 - a.t0, 1e-6)) for a in mine if a.do == "draw" and a.t0 <= t), default=0.0)
    for a in mine:
        if a.do == "hide" and t >= a.t0:
            on *= 1 - ease((t - a.t0) / max(a.t1 - a.t0, 1e-6))
        elif a.do == "move" and a.vanish and t >= (fade := max(a.t0, a.t1 - HIDE)):
            on *= 1 - ease((t - fade) / max(a.t1 - fade, 1e-6))
    return on


def _opened(mine: list[Act], t: float) -> float:
    """How far the thing's hinged part is open at t (0 to 1): open and close acts in order."""
    level = 0.0
    for a in sorted((a for a in mine if a.do in ("open", "close") and a.t0 <= t), key=lambda a: a.t0):
        level += ((1.0 if a.do == "open" else 0.0) - level) * ease((t - a.t0) / max(a.t1 - a.t0, 1e-6))
    return level


def _dimmed(mine: list[Act], t: float) -> float:
    """How far the thing has faded towards the paper at t (0 to DIM): dim and undim acts in order."""
    level = 0.0
    for a in sorted((a for a in mine if a.do in ("dim", "undim") and a.t0 <= t), key=lambda a: a.t0):
        level += ((DIM if a.do == "dim" else 0.0) - level) * ease((t - a.t0) / max(a.t1 - a.t0, 1e-6))
    return level


def _draw_thing(img: Image.Image, d: ImageDraw.ImageDraw, thing: dict, acts: list[Act], t: float, view=FULL,
                by_id: dict[str, dict] | None = None) -> None:
    f = _shown(thing, acts, t)
    if f <= 0:
        return
    kind, seed = thing["kind"], zlib.crc32(thing["id"].encode())
    mine = [a for a in acts if a.thing == thing["id"]]
    reds = [a for a in mine if a.do == "red" and a.t0 <= t]
    r = min(f, max((ease((t - a.t0) / max(a.t1 - a.t0, 1e-6)) for a in reds), default=0.0))
    dim = _dimmed(mine, t)
    fade = (lambda c: tuple(round(v + (p - v) * dim) for v, p in zip(c, PAPER))) if dim else (lambda c: c)
    ink, red, gray, blue = map(fade, (INK, RED, GRAY, BLUE))
    color = fade(_color(thing))
    outline = blue if kind == "wall" else red if kind == "crack" else color if kind in ("check", "cross") else ink
    if kind in MOVERS:
        x, y = _position(thing, acts, t, by_id)
        if kind == "dot":
            glow = any(a.do == "pulse" and a.t0 <= t <= a.t1 for a in mine)
            fill = red if r else color
            sx, sy = screen(view, x, y)
            z = view[2]
            rad = DOT_R * f * z
            if glow:
                g = (rad + (8 + 6 * (0.5 + 0.5 * math.sin(t * 5))) * z) * SS
                d.ellipse((sx * SS - g, sy * SS - g, sx * SS + g, sy * SS + g), outline=fill, width=round(2 * SS * z))
            d.ellipse((sx * SS - rad * SS, sy * SS - rad * SS, sx * SS + rad * SS, sy * SS + rad * SS), fill=fill)
        elif kind == "icon":
            for k, s in enumerate(_icon(thing["icon"], x, y - 15)):
                _stroke(d, s, f, red if r else color, 5, seed + k, view=view)
        else:
            if kind == "figure":
                px, py = _position(thing, acts, t - 0.05, by_id)
                spread = abs(math.sin(math.pi * STEP_HZ * t)) if math.hypot(x - px, y - py) > 0.5 else 0.0
                strokes, base = [(s, 4, 0) for s in _figure(x, y - BOB * spread, spread, thing.get("role"))], color
            else:
                moved = at_pos(thing, (x, y))
                strokes, base = _shape(moved), outline
                if moved.get("hinge") and (level := _opened(mine, t)):
                    strokes = _hinged(strokes, moved["hinge"], level)
            for k, (pts, w, dash) in enumerate(strokes):
                _stroke(d, pts, f, base, w, seed + k, dash, view)
                if r:
                    _stroke(d, pts, r, red, w + 2, seed + k, dash, view)
        lx, ly = _label_at(at_pos(thing, (x, y)) if kind == "shape" else thing, (x, y))
    else:
        strokes = _shape(thing)
        if thing.get("hinge") and (level := _opened(mine, t)):
            strokes = _hinged(strokes, thing["hinge"], level)
        for k, (pts, w, dash) in enumerate(strokes):
            _stroke(d, pts, f, outline, w, seed + k, dash, view)
            if r:
                _stroke(d, pts, r, red, w + 2, seed + k, dash, view)
        if thing.get("url"):
            bar, lines, uxy, uem = _screen(thing)
            _stroke(d, _rrect(*bar, 14), f, ink, 3, seed + 50, view=view)
            for k, ln in enumerate(lines):
                _stroke(d, ln, f, gray, 3, seed + 60 + k, view=view)
            _write(img, uxy, thing["url"], uem, (f - 0.3) / 0.7, ink, view)
        if kind in ("path", "crack"):
            return
        lx, ly = _label_at(thing)
    label, em = thing.get("label", ""), label_em(thing) or MIN_LABEL_EM
    say = next((a.say for a in reversed(reds) if a.say), "") if kind == "box" else ""
    if say:
        ly -= 0.55 * em
    _write(img, (lx, ly), label, em, (f - 0.3) / 0.7, color, view)
    if r:
        _write(img, (lx, ly), label, em, r * 2, red, view)
    if say:
        _write(img, (lx, ly + 1.1 * em), say, SMALL_EM, r * 2 - 0.4, red, view)


def draw(things: list[dict], acts: list[Act], t: float, view=FULL) -> Image.Image:
    """The W x H frame at time t through the camera `view` (FULL: the whole canvas): every thing in list order, later
    ones on top. The paper stays put; only the ink is moved and enlarged."""
    img = _paper().copy()
    d = ImageDraw.Draw(img)
    by_id = {th["id"]: th for th in things}
    for thing in things:
        _draw_thing(img, d, thing, acts, t, view, by_id)
    return img.reduce(SS)
