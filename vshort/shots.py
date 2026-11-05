"""Nhịp hình: a change every ~2 s on stills and reference cards, each tied to the words being said.
The beat plan (RUN/shots.json): its schema, the time of each beat and the camera that snaps to each focus; the pencil
marks, doodles and hand-lettered pops each beat draws, and the checks of those against the picture and the phone's UI."""
import math
import re
import zlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from vshort import kit, shapes
from vshort.fit import Placement, phrase_fracs
from vshort.kit import ease
from vshort.textfit import UI_RIGHT, UI_RIGHT_FROM, UI_TOP
from vshort.visuals import LUMA, MIN_CONTRAST, PAPER, SUBTITLE

LEAD = 0.2  # the picture moves this long before the word
SNAP = 0.25  # the camera's move to a new framing
DRAW = 0.5  # a pencil mark draws itself in this long
MAX_GAP = 2.0  # longest stretch of a line with no visible change
MAX_ZOOM_STILL = 1.5  # a 720x1280 still goes soft past this
MAX_POPS = 3  # hand-lettered pops in one video
MAX_POP_LEN = 12
CREEP = 0.02  # relative zoom per second while a framing is held
SHAPES = ("circle", "arrow", "underline", "cross", "tick")
INK_MIN = 0.03  # share of a mark's box that must be ink
PAPER_MAX = 0.03  # share of a doodle's or pop's box that may be ink
FADE = 0.3  # a mark fades out this long once the next mark starts
POP_T = 0.35  # a pop's bounce: 0.6 -> 1.08 -> 1 of its size...
POP_PEAK = 0.6  # ...biggest this far through it
PENCIL = 6  # px of a mark's line at 720 wide; a doodle's is one less
MARGIN = 24  # clear of the screen's side edges
PAD = 0.15  # frame_box widens the box this much, so what it frames is not hard against the screen edge

KEEP = object()  # Beat.focus of a beat with no `focus`: hold the framing
_FIELDS = ("focus", "mark", "doodle", "pop")


@dataclass(frozen=True)
class Beat:
    t: float  # absolute seconds of its word
    focus: tuple[int, int, int, int] | None | object  # box to frame; None the wide shot; KEEP no change
    mark: dict | None
    doodle: dict | None
    pop: dict | None


def _frame() -> tuple[int, int, float, float]:
    """(W, H, MIN_ZOOM, EDGE) of the renderer, which imports this module and so cannot be imported at the top."""
    from vshort.render import EDGE, H, MIN_ZOOM, W
    return W, H, MIN_ZOOM, EDGE


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _secs(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _said(text: str, said: str) -> bool:
    """`text` is in `said` as whole words: "202" is not in "2024", nor "5" in "5,5"."""
    return re.search(rf"(?<!\w)(?<!\d[.,]){re.escape(text)}(?!\w)(?![.,]\d)", said) is not None


def _box_problems(what: str, box) -> list[str]:
    W, H, *_ = _frame()
    if not (isinstance(box, (list, tuple)) and len(box) == 4 and all(_int(v) for v in box)):
        return [f"{what}: box {box!r} phải là [x0, y0, x1, y1] số nguyên"]
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H):
        return [f"{what}: box {list(box)} vượt khung {W}x{H} hoặc ngược chiều (cần 0 ≤ x0 < x1 ≤ {W}, 0 ≤ y0 < y1 ≤ {H})"]
    return []


def _beat_problems(row: dict, n: int, said: str, doodle_ok: Callable[[str], bool]) -> list[str]:
    """What is wrong with one beat of a line of `n` phrases that says `said` (order and pop count: the caller's)."""
    probs = []
    if extra := sorted(set(row) - {"phrase", "at", *_FIELDS}):
        probs.append(f"trường lạ {extra} (chỉ có phrase, at, {', '.join(_FIELDS)})")
    phrase, at = row.get("phrase", 1), row.get("at", 0)
    if not (_int(phrase) and 1 <= phrase <= n):
        probs.append(f"phrase {phrase!r} ngoài 1–{n} (câu có {n} cụm)")
    if not (_num(at) and 0 <= at <= 1):
        probs.append(f"at {at!r} phải là số 0–1")
    if not any(f in row for f in _FIELDS):
        probs.append(f"phải có ít nhất một trong {', '.join(_FIELDS)}")
    if row.get("focus") is not None:
        probs += _box_problems("focus", row["focus"])
    for what in ("mark", "doodle", "pop"):
        if what not in row:
            continue
        item = row[what]
        if not isinstance(item, dict):
            probs.append(f'{what} phải là {{"box": [...], ...}}, không phải {item!r}')
            continue
        probs += _box_problems(what, item.get("box"))
        if what == "mark" and item.get("shape") not in SHAPES:
            probs.append(f"mark shape {item.get('shape')!r} không có trong {', '.join(SHAPES)}")
        elif what == "doodle" and not (isinstance(item.get("shape"), str) and doodle_ok(item["shape"])):
            probs.append(f"doodle shape {item.get('shape')!r} không có trong thư viện hình hay RUN/shapes")
        elif what == "pop":
            text = item.get("text")
            if not (isinstance(text, str) and text.strip()):
                probs.append("pop text phải là chữ, không rỗng")
            elif len(text) > MAX_POP_LEN:
                probs.append(f"pop text {text!r} dài {len(text)} ký tự, tối đa {MAX_POP_LEN} ký tự")
            elif not _said(text, said):
                probs.append(f"pop text {text!r} không có nguyên văn trong lời Việt của câu")
    return probs


def schema_problems(doc, script: list[dict], allowed: set[int], doodle_ok: Callable[[str], bool]) -> list[str]:
    """Every way `doc` (shots.json) breaks its form, one line each. `allowed`: the lines that may have beats."""
    if not isinstance(doc, dict):
        return ['shots.json phải là một object JSON {"<id câu>": [nhịp, ...]}']
    spoken = {r["id"]: r["phrases"] for r in script}
    probs, lines = [], []
    for key, rows in doc.items():
        try:
            lines.append((int(key), rows))
        except (TypeError, ValueError):
            probs.append(f"shots.json: khóa {key!r} phải là id câu (số nguyên)")
    pops = 0
    for id, rows in sorted(lines, key=lambda x: x[0]):
        if id not in allowed:
            probs.append(f"shots.json câu {id}: không thuộc các câu được lên nhịp (câu có lời, không phải hình động)")
            continue
        if not isinstance(rows, list) or not rows:
            probs.append(f"shots.json câu {id}: phải là danh sách nhịp, không rỗng")
            continue
        phrases = spoken.get(id, "")
        n, said = len(phrases.split("|")), " ".join(phrases.replace("|", " ").replace("*", "").split())
        prev = None
        for k, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                probs.append(f"shots.json câu {id} nhịp {k}: phải là object, không phải {row!r}")
                continue
            found = _beat_problems(row, n, said, doodle_ok)
            phrase, at = row.get("phrase", 1), row.get("at", 0)
            if _int(phrase) and 1 <= phrase <= n and _num(at) and 0 <= at <= 1:
                if prev is not None and (phrase, at) <= prev:
                    found.append(f"nhịp phải tăng dần theo (phrase, at): ({phrase}, {at}) không sau ({prev[0]}, {prev[1]})")
                prev = (phrase, at)
            if row.get("pop") is not None:
                pops += 1
                if pops > MAX_POPS:
                    found.append(f"pop thứ {pops} vượt tối đa {MAX_POPS} pop cho cả video")
            probs += [f"shots.json câu {id} nhịp {k}: {p}" for p in found]
    return probs


def beats(rows: list[dict], phrases: str, p: Placement) -> list[Beat]:
    """The beats of a line placed at `p`; `rows` passed schema_problems against `phrases`."""
    fracs, out = phrase_fracs(phrases), []
    for r in rows:
        f0, f1 = fracs[r.get("phrase", 1) - 1]
        focus = r["focus"] if "focus" in r else KEEP
        out.append(Beat(p.start + (f0 + r.get("at", 0) * (f1 - f0)) * p.dur,
                        tuple(focus) if isinstance(focus, list) else focus,
                        r.get("mark"), r.get("doodle"), r.get("pop")))
    return out


def _fit(s: float, cx: float, cy: float, cap: float) -> tuple[float, float, float]:
    """Framing at scale s (kept within MIN_ZOOM and cap) with the window pulled inside the picture, EDGE off its sides."""
    W, H, lo, edge = _frame()
    s = max(lo, min(s, cap))
    ww, wh = W / s, H / s
    return s, min(max(cx, edge + ww / 2), W - edge - ww / 2), min(max(cy, wh / 2), H - wh / 2)


def frame_box(box, cap: float) -> tuple[float, float, float]:
    """(scale, cx, cy) that shows `box` (widened by PAD) whole; None is the wide shot."""
    W, H, lo, _ = _frame()
    if box is None:
        return _fit(lo, W / 2, H / 2, cap)
    x0, y0, x1, y1 = box
    w, h = max(x1 - x0, 1) * (1 + PAD), max(y1 - y0, 1) * (1 + PAD)
    return _fit(min(W / w, H / h), (x0 + x1) / 2, (y0 + y1) / 2, cap)


def _hold(f: tuple[float, float, float], since: float, t: float, cap: float) -> tuple[float, float, float]:
    """Framing f held from `since`: it creeps in at CREEP a second, so a held picture is never quite still."""
    return _fit(f[0] * (1 + CREEP * max(0.0, t - since)), f[1], f[2], cap)


def _cam(moves: list[tuple[float, tuple[float, float, float]]], t: float, start: float, cap: float):
    """Camera at t given the moves begun by t, each from wherever the camera was when it began."""
    if not moves:
        return _hold(frame_box(None, cap), start, t, cap)
    (t0, to), before = moves[-1], moves[:-1]
    if t >= t0 + SNAP:
        return _hold(to, t0 + SNAP, t, cap)
    a, u = _cam(before, t0, start, cap), ease((t - t0) / SNAP)
    return a[0] * (to[0] / a[0]) ** u, a[1] + (to[1] - a[1]) * u, a[2] + (to[2] - a[2]) * u  # zoom by ratio, centre straight


def camera_at(bs: list[Beat], t: float, start: float, cap: float) -> tuple[float, float, float]:
    """(scale, cx, cy) at t of a line that starts at `start` on the wide shot: each beat with a focus snaps to it LEAD
    before its word, over SNAP; a beat without one holds the framing."""
    return _cam([(b.t - LEAD, frame_box(b.focus, cap)) for b in bs if b.focus is not KEEP and b.t - LEAD <= t], t, start, cap)


def changes(bs: list[Beat], extra: list[float]) -> list[float]:
    """When something visibly starts to change: every beat (LEAD before its word) and each `extra` (a card element)."""
    return sorted([b.t - LEAD for b in bs] + list(extra))


def gap_problems(id: int, start: float, end: float, times: list[float]) -> list[str]:
    """Stretches of the line [start, end] longer than MAX_GAP with no change; a line that short needs none."""
    pts = [start, *sorted(min(max(x, start), end) for x in times), end]
    return [f"shots.json câu {id}: từ {_secs(a - start)} s đến {_secs(b - start)} s của câu không có thay đổi nào "
            f"({_secs(b - a)} s, tối đa {_secs(MAX_GAP)} s): thêm nhịp ở khoảng này"
            for a, b in zip(pts, pts[1:]) if b - a > MAX_GAP + 1e-9]



# ---- pencil marks, doodles and pops ----

GAP, REACH = 10, 150  # an arrow stops GAP px off its box and its shaft is about REACH - GAP long
TILT = -3  # degrees a pop's lettering leans, as a hand's does
OVERLAYS = ("mark", "doodle", "pop")


def _out(x: float) -> float:
    """Ease-out: a pencil starts fast and slows into the end of its line."""
    return 1 - (1 - kit.clamp(x)) ** 3


def _bez(p0, p1, p2, p3, n: int = 40) -> list[tuple[float, float]]:
    pts = []
    for k in range(n):
        u = k / (n - 1)
        w = ((1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u ** 2, u ** 3)
        pts.append(tuple(sum(a * p[i] for a, p in zip(w, (p0, p1, p2, p3))) for i in (0, 1)))
    return pts


def _ellipse(cx, cy, rx, ry, start=-100, sweep=378, grow=0.06, n=2.4) -> list[tuple[float, float]]:
    """A round-cornered ellipse drawn clockwise from `start` degrees through ~1.05 turns, ending a little outside where it began."""
    pts = []
    for k in range(90):
        a = math.radians(start + sweep * k / 89)
        r, c, s = 1 + grow * sweep * k / 89 / 360, math.cos(a), math.sin(a)
        pts.append((cx + rx * r * math.copysign(abs(c) ** (2 / n), c), cy + ry * r * math.copysign(abs(s) ** (2 / n), s)))
    return pts


def _circle(x0, y0, x1, y1):
    return [_ellipse((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 + 12, (y1 - y0) / 2 + 12)]


def _underline(x0, y0, x1, y1):
    n = max(4, int((x1 - x0) / 25))
    return [[(x0 - 4 + (x1 - x0 + 8) * i / n, y1 + 8 + 3 * math.sin(2.2 * math.pi * i / n) - 4 * i / n) for i in range(n + 1)]]


def _cross(x0, y0, x1, y1):
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    return [[(x0, y0), (mx + 4, my - 3), (x1, y1)], [(x1, y0 + 3), (mx - 3, my + 3), (x0 + 2, y1 - 2)]]


def _tick(x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0
    return [[(x0 + 0.1 * w, y0 + 0.55 * h), (x0 + 0.35 * w, y0 + 0.9 * h), (x1 - 0.05 * w, y0 + 0.1 * h)]]


def _arrow(box, img) -> list[list[tuple[float, float]]]:
    """A curved shaft from the side of the box with the most blank paper to a tip GAP px off it, and a two-barbed head.
    A side with no REACH px of room to the picture's edge is out unless every side is."""
    W, H, *_ = _frame()
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax, ay = max(x1 - x0, 100) / 2, max(y1 - y0, 100) / 2  # a strip is at least 100 px across
    bg = _background(img) if img is not None else None
    sides = []  # (ink in the REACH - GAP px strip beside the box, has room, direction to the tail, middle of the box's side)
    for u in ((1, 0), (-1, 0), (0, 1), (0, -1)):  # a tie goes to the first
        edge = (cx + u[0] * (x1 - x0) / 2, cy + u[1] * (y1 - y0) / 2)
        far = (edge[0] + u[0] * REACH, edge[1] + u[1] * REACH)
        xs = sorted((edge[0] + u[0] * GAP, far[0])) if u[0] else (cx - ax, cx + ax)  # from where the tip stops, so the
        ys = sorted((edge[1] + u[1] * GAP, far[1])) if u[1] else (cy - ay, cy + ay)  # box's own outline is not counted
        sides.append((ink_share(img, (xs[0], ys[0], xs[1], ys[1]), bg) if img is not None else 0.0,
                      8 <= far[0] <= W - 8 and 8 <= far[1] <= H - 8, u, edge))
    _, _, u, edge = min([s for s in sides if s[1]] or sides, key=lambda s: s[0])
    tip = (edge[0] + u[0] * GAP, edge[1] + u[1] * GAP)

    def at(a, b, sgn):  # a px back from the tip along u, b px across
        return tip[0] + u[0] * a - u[1] * b * sgn, tip[1] + u[1] * a + u[0] * b * sgn

    sgn = min((1, -1), key=lambda g: math.dist(at(125, 35, g), (W / 2, H / 2)))  # bend towards the middle of the picture
    shaft = _bez(at(125, 35, sgn), at(95, 45, sgn), at(50, 8, sgn), tip)
    (hx, hy), (tx, ty) = shaft[-6], shaft[-1]
    a = math.atan2(ty - hy, tx - hx)
    return [shaft] + [[(tx - 34 * math.cos(a + s), ty - 34 * math.sin(a + s)), (tx, ty)] for s in (math.radians(28), -math.radians(28))]


_MARKS = {"circle": _circle, "underline": _underline, "cross": _cross, "tick": _tick}


def _strokes(kind: str, item: dict, run_dir, img) -> list[list[tuple[float, float]]]:
    """The strokes of a beat's mark or doodle in frame pixels (720x1280), none nearer the edge than the pencil is wide."""
    W, H, *_ = _frame()
    if kind == "doodle":
        doc = shapes.find(item["shape"], run_dir)
        out = shapes.strokes_in_box(doc, item["box"]) if doc else []
    elif item["shape"] == "arrow":
        out = _arrow(item["box"], img)
    else:
        out = _MARKS[item["shape"]](*item["box"])
    return [[(min(max(x, 4), W - 4), min(max(y, 4), H - 4)) for x, y in s] for s in out]


def overlay_strokes(beat: Beat, img_size=(720, 1280), run_dir=None, img: Image.Image | None = None) -> list[list[tuple[float, float]]]:
    """The strokes of the beat's mark then its doodle, in the pixels of an image of `img_size`. `img` (any size) is what an
    arrow looks at to come from the emptier side; without it, it comes from the first side with room."""
    k = img_size[0] / _frame()[0]
    return [[(x * k, y * k) for x, y in s] for kind in ("mark", "doodle") if getattr(beat, kind) is not None
            for s in _strokes(kind, getattr(beat, kind), run_dir, img)]


def _width(kind: str) -> int:
    return PENCIL if kind == "mark" else PENCIL - 1


@lru_cache(maxsize=256)
def _letters(text: str, px: int) -> Image.Image:
    """The ink of `text` in Patrick Hand at `px`, cropped to it."""
    f = kit._font(px)
    r, b = f.getbbox(text, anchor="la")[2:]
    lay = Image.new("L", (r + 16, b + 16))
    ImageDraw.Draw(lay).text((8, 8), text, font=f, fill=255, anchor="la")
    return lay.crop(lay.getbbox())


def _pop_layer(item: dict, k: float) -> Image.Image:
    """The pop's lettering at bounce size k, in SS-scaled pixels: ~80 % of its box high but never wider than the box."""
    x0, y0, x1, y1 = item["box"]
    w, h = _letters(item["text"], 100).size
    em = min(0.8 * (y1 - y0) / h, 0.92 * (x1 - x0) / w) * 100
    return _letters(item["text"], max(8, round(em * k * kit.SS))).rotate(TILT, resample=Image.BICUBIC, expand=True)


def _bounce(u: float) -> float:
    """A pop's size u of the way through its bounce: 0.6 up to 1.08 at POP_PEAK, then settling to 1."""
    if u >= 1:
        return 1.0
    if u < POP_PEAK:
        return 0.6 + 0.48 * _out(u / POP_PEAK)
    return 1.08 - 0.08 * ease((u - POP_PEAK) / (1 - POP_PEAK))


def _bbox(kind: str, b: Beat, run_dir, img) -> tuple[float, float, float, float]:
    """Frame-pixel box of a beat's mark, doodle or pop at rest, the pencil's width and wobble included."""
    item = getattr(b, kind)
    if kind == "pop":
        lay, (x0, y0, x1, y1) = _pop_layer(item, 1.0), item["box"]
        hw, hh = lay.width / kit.SS / 2, lay.height / kit.SS / 2
        return (x0 + x1) / 2 - hw, (y0 + y1) / 2 - hh, (x0 + x1) / 2 + hw, (y0 + y1) / 2 + hh
    pts = [p for s in _strokes(kind, item, run_dir, img) for p in s]
    if not pts:  # a doodle that is not in the library draws nothing
        return tuple(item["box"])
    xs, ys = zip(*pts)
    pad = _width(kind) / 2 + 2
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def overlay_bbox(beat: Beat, img_size=(720, 1280), run_dir=None, img: Image.Image | None = None):
    """The box around everything the beat draws (mark, doodle, pop-up lettering) in the pixels of an image of `img_size`;
    None if it draws nothing."""
    boxes = [_bbox(kind, beat, run_dir, img) for kind in OVERLAYS if getattr(beat, kind) is not None]
    if not boxes:
        return None
    k = img_size[0] / _frame()[0]
    x0, y0, x1, y1 = (f(v) * k for f, v in zip((min, min, max, max), zip(*boxes)))
    return x0, y0, x1, y1


def _next_mark(bs: list[Beat], i: int) -> float | None:
    """When the first mark after beat i starts to draw, if any."""
    return next((c.t - LEAD for c in bs[i + 1:] if c.mark is not None), None)


def _live(bs: list[Beat], t: float) -> list[tuple[Beat, str, float, float]]:
    """(beat, kind, start, opacity) of each mark, doodle and pop showing at t: a mark fades out FADE s from the start of the
    next one; a doodle and a pop stay to the end of the line."""
    out = []
    for i, b in enumerate(bs):
        start = b.t - LEAD
        for kind in OVERLAYS:
            if getattr(b, kind) is None or t < start:
                continue
            nxt = _next_mark(bs, i) if kind == "mark" else None
            opacity = 1.0 if nxt is None else 1 - kit.clamp((t - nxt) / FADE)
            if opacity > 0:
                out.append((b, kind, start, opacity))
    return out


def settled(bs: list[Beat]) -> float:
    """From this time on draw_overlays gives the same picture whatever t is: every mark and doodle drawn on, every pop
    bounced in. A mark that gives way to the next one is gone before that one is drawn on (FADE < DRAW)."""
    return max([b.t - LEAD + max(DRAW * (b.mark is not None or b.doodle is not None), POP_T * (b.pop is not None))
                for b in bs if b.mark or b.doodle or b.pop], default=0.0)


def _paint(d: ImageDraw.ImageDraw, strokes, q: float, width: int, opacity: float, seed: int) -> None:
    """The first fraction q of the strokes, one after another in proportion to their length, as a double pencil line: a
    paler thinner one under the main one."""
    lens = [sum(math.dist(a, b) for a, b in zip(s, s[1:])) for s in strokes]
    total, before, ps = sum(lens), 0.0, []
    for n in lens:
        ps.append((q * total - before) / n if n else 0.0)
        before += n
    for w, fill, sd in ((width - 2, 153, seed + 101), (width, 255, seed)):
        for k, (s, p) in enumerate(zip(strokes, ps)):
            kit._stroke(d, s, p, round(fill * opacity), w, sd + k)


@lru_cache(maxsize=4)
def _grain(size: tuple[int, int]) -> Image.Image:
    """Pencil on paper: a ruffle of 80-100 % that lets the paper through."""
    return Image.fromarray((205 + 50 * np.random.default_rng(3).uniform(size=(size[1], size[0]))).astype(np.uint8))


def _pencil(pic: Image.Image) -> tuple[int, int, int]:
    """Graphite on a light picture, paper-coloured pencil on a dark one."""
    return kit.INK if _background(pic) @ LUMA >= 128 else PAPER


def draw_overlays(img: Image.Image, bs: list[Beat], t: float, run_dir=None, ref: Image.Image | None = None) -> Image.Image:
    """A copy of `img` (720x1280, or a card frame at 2x) with every mark, doodle and pop showing at t drawn on in pencil:
    marks and doodles draw on over DRAW from LEAD before their word, a pop bounces in. `img` itself if none is showing.
    Where an arrow comes from and whether the pencil is graphite or light is judged by `ref` (a card's finished frame,
    so they do not change while it writes itself out), or by `img` without one."""
    live = _live(bs, t)
    if not live:
        return img
    pic = ref if ref is not None else img
    W, H, *_ = _frame()
    mask = Image.new("L", (W * kit.SS, H * kit.SS))
    d = ImageDraw.Draw(mask)
    for b, kind, start, opacity in sorted((e for e in live if e[1] != "pop"), key=lambda e: e[3]):  # the fading ones under
        item = getattr(b, kind)
        _paint(d, _strokes(kind, item, run_dir, pic), _out((t - start) / DRAW), _width(kind), opacity,
               zlib.crc32(f"{kind}{item['shape']}{item['box']}".encode()))
    for b, _, start, _ in (e for e in live if e[1] == "pop"):
        u = (t - start) / POP_T
        lay = _pop_layer(b.pop, _bounce(u)).point(lambda v: round(v * kit.clamp(u / 0.3)))
        (x0, y0, x1, y1) = b.pop["box"]
        mask.paste(255, (round((x0 + x1) / 2 * kit.SS - lay.width / 2), round((y0 + y1) / 2 * kit.SS - lay.height / 2)), lay)
    mask = ImageChops.multiply(mask.resize(img.size, Image.BOX), _grain(img.size))
    if mask.getbbox() is None:
        return img
    out = img.copy()
    out.paste(_pencil(pic), mask=mask)
    return out


# ---- checks against the picture and the phone's UI ----


def _background(img: Image.Image) -> np.ndarray:
    """The picture's own colour: the median of its pixels (sampled at 72x128), paper on a paper picture, dark on a dark one."""
    return np.median(np.asarray(img.resize((72, 128), Image.NEAREST).convert("RGB")).reshape(-1, 3), axis=0)


def ink_share(img: Image.Image, box, bg=None) -> float:
    """The share of the pixels in `box` (frame pixels; `img` may be at any size) that are further than MIN_CONTRAST from the
    picture's background (`bg`, by default the median colour of `img`)."""
    W, H, *_ = _frame()
    x0, y0, x1, y1 = box
    sx, sy = img.width / W, img.height / H
    x0, x1, y0, y1 = max(0, round(x0 * sx)), min(img.width, round(x1 * sx)), max(0, round(y0 * sy)), min(img.height, round(y1 * sy))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    crop = np.asarray(img.crop((x0, y0, x1, y1)).convert("RGB")).astype(int)
    return float((np.abs(crop - (_background(img) if bg is None else bg)).max(2) > MIN_CONTRAST).mean())


def to_screen(box, cam: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """`box` of the picture (frame pixels) on the 720x1280 screen when the camera is `cam`, as render.draw crops it."""
    W, H, *_ = _frame()
    s, cx, cy = cam
    ww, wh = W / s, H / s
    x0, y0 = min(max(cx - ww / 2, 0), W - ww), min(max(cy - wh / 2, 0), H - wh)
    return (box[0] - x0) * s, (box[1] - y0) * s, (box[2] - x0) * s, (box[3] - y0) * s


def _covered(box) -> list[str]:
    """What the phone draws over a screen `box`: the top bar, the caption box, the button column, or the screen's sides."""
    W, *_ = _frame()
    x0, y0, x1, y1 = box
    buttons = x1 > UI_RIGHT and y1 > UI_RIGHT_FROM
    return [side for hit, side in [
        (y0 < UI_TOP, f"thanh trên của TikTok/Reels/Shorts (y < {UI_TOP})"),
        (y1 > SUBTITLE[1], f"hộp phụ đề và tên kênh/mô tả (y > {SUBTITLE[1]})"),
        (x0 < MARGIN, f"mép trái màn hình (x < {MARGIN})"),
        (buttons, f"cột nút like/bình luận (x > {UI_RIGHT} từ y {UI_RIGHT_FROM} trở xuống)"),
        (x1 > W - MARGIN and not buttons, f"mép phải màn hình (x > {W - MARGIN})")] if hit]


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%".replace(".", ",")


STEP = 0.05  # image_problems looks at the camera this often while an item is up


def image_problems(id: int, bs: list[Beat], img: Image.Image, cam: Callable[[float], tuple], run_dir=None, *,
                   end: float, ref: Image.Image | None = None) -> list[str]:
    """What is wrong with the marks, doodles and pops of a line over its picture `img` (or `ref`, its finished frame, when
    `img` is still being written): a mark whose box is blank, a doodle or pop on top of the picture, and any of them
    where the phone draws over the screen. Blank and ink are measured from the picture's own colour. The camera is
    sampled every STEP s from when the item is drawn until it goes: when the next mark starts for a mark, at `end` (the
    line's end) for the rest. Each item is reported once, at the first time it is covered."""
    pic = ref if ref is not None else img
    bg = _background(pic)
    probs = []
    for n, b in enumerate(bs, 1):
        who = f"shots.json câu {id} nhịp {n}: "
        for kind in OVERLAYS:
            item = getattr(b, kind)
            if item is None:
                continue
            box, share = list(item["box"]), ink_share(pic, item["box"], bg)
            if kind == "mark" and share < INK_MIN:
                probs.append(who + f"mark: box {box} trúng giấy trống ({_pct(share)} điểm ảnh có mực, cần ≥ {_pct(INK_MIN)}): "
                             "đặt box ôm vật được chỉ")
            elif kind != "mark" and share > PAPER_MAX:
                probs.append(who + f"{kind}: box {box} đè lên hình ({_pct(share)} điểm ảnh có mực, tối đa {_pct(PAPER_MAX)}): "
                             "chọn chỗ giấy trống")
            nxt = _next_mark(bs, n - 1)
            lo, hi = sorted((b.t - LEAD + DRAW, nxt if kind == "mark" and nxt is not None else end))
            box_at = _bbox(kind, b, run_dir, pic)
            for when in [lo + STEP * k for k in range(int((hi - lo) / STEP + 1e-9))] + [hi]:
                on_screen = to_screen(box_at, cam(when))
                if sides := _covered(on_screen):
                    probs.append(who + f"{kind} bị che ở {'; '.join(sides)}: {_secs(when - b.t)} s sau lời của nhịp, trên màn hình nó nằm ở "
                                 f"x {on_screen[0]:.0f}–{on_screen[2]:.0f}, y {on_screen[1]:.0f}–{on_screen[3]:.0f}")
                    break
    return probs
