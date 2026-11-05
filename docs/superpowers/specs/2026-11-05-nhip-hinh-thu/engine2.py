"""Spike #2 engine: shots that snap, pencil marks glued to the picture (drawn in screen space through the camera), cards that
build up from SVG elements, hand-lettered pops. Imports repo code, edits nothing in it."""
import math, re, sys
import numpy as np
import cairosvg, io
from PIL import Image, ImageChops, ImageDraw, ImageFont
sys.path.insert(0, "/Users/Apple/video-pipeline")
from vshort import kit
from vshort.render import draw as cam_crop, MIN_ZOOM, EDGE, W, H, FPS
from vshort.textfit import FONTS
from vshort.visuals import PAPER

S = "/private/tmp/claude-501/-Users-Apple-video-pipeline/629cdd43-9de2-404d-b37e-b2b8406e21ac/scratchpad/spike"
SS, TR = 2, 0.25  # stroke supersampling; length of a snap
GRAPHITE = (43, 43, 43)
GRAIN = Image.fromarray((205 + 50 * np.random.default_rng(3).uniform(0, 1, (H, W))).astype(np.uint8))
clamp = kit.clamp
eo = lambda x: 1 - (1 - clamp(x)) ** 3


# ---------- shapes (image coordinates) ----------
def bez(p0, p1, p2, p3, n=40):
    t = np.linspace(0, 1, n)[:, None]
    p = [np.array(v, float) for v in (p0, p1, p2, p3)]
    return [tuple(v) for v in (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]]


def ellipse(cx, cy, rx, ry, tilt=0.0, start=-100, sweep=385, grow=0.06, n=2.0):
    pts = []
    for a in np.linspace(0, sweep, 90):
        r = 1 + grow * a / 360
        c, sn = math.cos(math.radians(start + a)), math.sin(math.radians(start + a))
        x, y = rx * r * math.copysign(abs(c) ** (2 / n), c), ry * r * math.copysign(abs(sn) ** (2 / n), sn)
        pts.append((cx + x * math.cos(tilt) - y * math.sin(tilt), cy + x * math.sin(tilt) + y * math.cos(tilt)))
    return pts


def head(pts, size=40, spread=28):
    (x0, y0), (x1, y1) = pts[-6], pts[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    return [[(x1 - size * math.cos(a + s), y1 - size * math.sin(a + s)), (x1, y1)] for s in (math.radians(spread), -math.radians(spread))]


def rrect(x0, y0, x1, y1, r):
    pts = [(x0 + r, y0)]
    for cx, cy, a0 in [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]:
        pts += [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(a0, a0 + 91, 15)]
    return pts + [pts[0]]


def circle(cx, cy, r, seed_start=-90):
    return ellipse(cx, cy, r, r, start=seed_start, sweep=370, grow=0.04)


def star(cx, cy, r):
    pts = []
    for k in range(6):
        a = math.radians(-90 + 144 * k)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ---------- marks: pieces = (polyline, seed, a, b); drawn on while progress q is in a..b ----------
class Mark:
    def __init__(self, pieces, t0, dur, w=6, seed=1, out=None):
        self.pieces, self.t0, self.dur, self.w, self.out = pieces, t0, dur, w, out

    def fade(self, t):
        return 1.0 if self.out is None or t < self.out else clamp(1 - (t - self.out) / 0.18)

    def at(self, t):
        q = eo((t - self.t0) / self.dur)
        return [(pts, seed, clamp((q - a) / (b - a)), self.w) for pts, seed, a, b in self.pieces]


def one(pts, seed, t0, dur, w=6, out=None):
    return Mark([(pts, seed, 0, 1)], t0, dur, w, out=out)


def arrow(pts, seed, t0, dur, w=6, out=None):
    return Mark([(pts, seed, 0, .78), *[(h, seed + 7 + j, .78, 1) for j, h in enumerate(head(pts))]], t0, dur, w, out=out)


def multi(strokes, seed, t0, dur, w=6, out=None):
    """Several strokes drawn one after another within dur."""
    n = len(strokes)
    return Mark([(s, seed + 5 * k, k / n, (k + 1) / n) for k, s in enumerate(strokes)], t0, dur, w, out=out)


class Pop:
    """Hand-lettered word that pops in with a small overshoot; xy centre in image px, size = em in image px."""

    def __init__(self, text, xy, size, t0, tilt=-4, anim=0.32):
        self.text, self.xy, self.size, self.t0, self.tilt, self.anim = text, xy, size, t0, tilt, anim

    def scale(self, t):
        u = (t - self.t0) / self.anim
        if u <= 0:
            return 0
        if u >= 1:
            return 1
        return eo(u) * (1 + 0.18 * math.sin(math.pi * u))


_fcache = {}


def pfont(px):
    if px not in _fcache:
        _fcache[px] = ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), px)
    return _fcache[px]


def paste_pop(img, pop, t, cam):
    k = pop.scale(t)
    if k <= 0.02:
        return
    s, cx, cy = cam
    x0, y0 = cx - W / s / 2, cy - H / s / 2
    px = max(8, int(pop.size * s * k))
    f = pfont(px)
    l, tp, r, b = f.getbbox(pop.text, anchor="mm")
    lay = Image.new("L", (int(r - l) + 40, int(b - tp) + 40))
    ImageDraw.Draw(lay).text((20 - l, 20 - tp), pop.text, font=f, fill=255, anchor="mm")
    lay = lay.rotate(pop.tilt, resample=Image.BICUBIC, expand=True)
    sx, sy = (pop.xy[0] - x0) * s, (pop.xy[1] - y0) * s
    img.paste(GRAPHITE, (int(sx - lay.width / 2), int(sy - lay.height / 2)), lay)


def _layer(marks, t, s, x0, y0):
    main = sec = None
    for m in marks:
        for pts, seed, p, w in m.at(t):
            if p <= 0:
                continue
            if main is None:
                main, sec = Image.new("L", (W * SS, H * SS)), Image.new("L", (W * SS, H * SS))
                dm, ds = ImageDraw.Draw(main), ImageDraw.Draw(sec)
            for d, sd, wd in ((dm, seed, w), (ds, seed + 101, w - 2)):
                q, cum = kit._wobble(tuple(map(tuple, pts)), sd)
                q = q[cum <= cum[-1] * p]
                if len(q) < 2:
                    continue
                d.line([((x - x0) * s * SS, (y - y0) * s * SS) for x, y in q], fill=255, width=int(wd * SS), joint="curve")
    if main is None:
        return None
    return ImageChops.multiply(ImageChops.lighter(main.reduce(SS), sec.reduce(SS).point(lambda v: int(v * 0.6))), GRAIN)


def paste_marks(img, marks, t, cam):
    s, cx, cy = cam
    x0, y0 = cx - W / s / 2, cy - H / s / 2
    live = [m for m in marks if t >= m.t0 and m.fade(t) > 0]
    groups = [[m for m in live if m.fade(t) >= 1]] + [[m] for m in live if m.fade(t) < 1]
    for g in groups:
        if not g:
            continue
        mask = _layer(g, t, s, x0, y0)
        if mask is not None:
            f = g[0].fade(t)
            img.paste(GRAPHITE, (0, 0), mask if f >= 1 else mask.point(lambda v: int(v * f)))


# ---------- worlds ----------
class StillWorld:
    def __init__(self, path):
        self.img = Image.open(path).convert("RGB").resize((W * 2, H * 2), Image.BICUBIC)

    def get(self, t):
        return self.img


_FONT_FILES = {False: "BeVietnamPro-Regular.ttf", True: "BeVietnamPro-Bold.ttf"}
HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280" width="720" height="1280">'


class Item:
    """One SVG element rendered alone at 2x; kind text/bar/dot. rgb + alpha cropped to its ink box."""

    def __init__(self, frag, t0, t1):
        png = cairosvg.svg2png(bytestring=(HEAD + frag + "</svg>").encode(), output_width=W * 2, output_height=H * 2)
        a = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))
        ys, xs = np.where(a[..., 3] > 6)
        self.x0, self.y0, self.x1, self.y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        c = a[self.y0:self.y1, self.x0:self.x1]
        self.rgb = Image.fromarray(c[..., :3].copy())
        self.alpha = c[..., 3].astype(np.float32)
        self.t0, self.t1 = t0, t1
        self.kind = "dot" if frag.startswith("<circle") else "text"
        self.frag = frag
        m = re.search(r">([^<]+)</text>", frag)
        self.text = m.group(1) if m else ""
        g = re.search(r'font-size="(\d+)"', frag)
        self.size = int(g.group(1)) if g else 0
        self.bold = 'font-weight="bold"' in frag
        self.base_y = float(re.search(r'<text[^>]* y="([\d.]+)"', frag).group(1)) if m else 0

    def box(self):  # image px
        return self.x0 / 2, self.y0 / 2, self.x1 / 2, self.y1 / 2

    def span(self, w0, w1):
        """x range (image px) of words w0..w1-1 of this text line."""
        f = ImageFont.truetype(str(FONTS / _FONT_FILES[self.bold]), 100)
        words = self.text.split(" ")
        pre = lambda n: f.getlength(" ".join(words[:n])) + (f.getlength(" ") if n else 0) * 0
        tot = f.getlength(self.text)
        bx0, _, bx1, _ = self.box()
        a = f.getlength(" ".join(words[:w0]) + (" " if w0 else "")) / tot
        b = f.getlength(" ".join(words[:w1])) / tot
        return bx0 + (bx1 - bx0) * a, bx0 + (bx1 - bx0) * b

    def paste(self, world, t):
        p = clamp((t - self.t0) / (self.t1 - self.t0))
        if p <= 0:
            return
        h, w = self.alpha.shape
        if self.kind == "dot":
            k = 1 + 0.25 * math.sin(math.pi * p) if p < 1 else 1
            k *= max(p, 0.15) ** 0.5 if p < 1 else 1
            im, al = self.rgb, Image.fromarray(self.alpha.astype(np.uint8))
            if abs(k - 1) > 0.01:
                nw, nh = max(2, int(w * k)), max(2, int(h * k))
                im, al = im.resize((nw, nh)), al.resize((nw, nh))
            world.paste(im, (self.x0 + w // 2 - im.width // 2, self.y0 + h // 2 - im.height // 2), al)
            return
        if p >= 1:
            a = self.alpha
        else:  # left-to-right soft wipe
            f = 36
            front = p * (w + f)
            ramp = np.clip((front - np.arange(w)) / f, 0, 1)
            a = self.alpha * ramp[None, :]
        world.paste(self.rgb, (self.x0, self.y0), Image.fromarray(a.astype(np.uint8)))


class CardWorld:
    def __init__(self, svg_path, schedule):
        """schedule: list of (substring of the element, t0, t1); every non-border/line element needs one."""
        frags, grp = [], None
        for line in open(svg_path).read().splitlines()[1:-1]:
            s = line.strip()
            if s.startswith("<g "):
                grp = s
            elif s == "</g>":
                grp = None
            elif grp:
                frags.append(grp + s + "</g>")
            else:
                frags.append(s)
        self.items, self.border, self.line = [], None, None
        for fr in frags:
            if fr.startswith("<rect") and 'fill="none"' in fr:
                g = lambda k: float(re.search(rf'{k}="([\d.]+)"', fr).group(1))
                self.border = (g("x"), g("y"), g("x") + g("width"), g("y") + g("height"), g("rx"))
                continue
            if fr.startswith("<line"):
                g = lambda k: float(re.search(rf'{k}="([\d.]+)"', fr).group(1))
                self.line = ((g("x1"), g("y1")), (g("x2"), g("y2")))
                continue
            if fr.startswith("<circle"):
                key = f"<dot{sum(i.kind == 'dot' for i in self.items) + 1}>"
            elif fr.startswith("<rect"):
                key = "<bar>"
            else:
                key = re.search(r">([^<]+)</text>", fr).group(1)
            hit = [(a, b) for sub, a, b in schedule if sub in key]
            self.items.append(Item(fr, *(hit[0] if hit else (0, 0.01))))
        self.paper = Image.new("RGB", (W * 2, H * 2), PAPER)
        self.dim = None  # (t0, t1, amount): the text fades towards the paper once the voice has moved on

    def find(self, substr):
        return next(i for i in self.items if substr in i.text)

    def get(self, t):
        w = self.paper.copy()
        for it in self.items:
            it.paste(w, t)
        if self.dim and t > self.dim[0]:
            w = Image.blend(w, self.paper, self.dim[2] * clamp((t - self.dim[0]) / (self.dim[1] - self.dim[0])))
        return w


# ---------- segments ----------
class Key:
    def __init__(self, t, ix, iy, s, ox=350, oy=570, ds=0.03, dx=0.0, dy=0.0):
        """Framing at time t: image point (ix,iy) lands at screen (ox,oy), scale s; then a creep of ds/s per second."""
        self.t, self.s, self.ds, self.dx, self.dy = t, s, ds, dx, dy
        self.cx, self.cy = ix + (360 - ox) / s, iy + (640 - oy) / s


def pose(k, t):
    e = max(0.0, t - k.t)
    return k.s * (1 + k.ds * e), k.cx + k.dx * e, k.cy + k.dy * e


def fit_cam(s, cx, cy):
    s = max(s, MIN_ZOOM)
    ww, wh = W / s, H / s
    return s, min(max(cx, EDGE + ww / 2), W - EDGE - ww / 2), min(max(cy, wh / 2), H - wh / 2)


class Seg:
    def __init__(self, start, end, world, keys, marks=(), pops=()):
        self.start, self.end, self.world, self.keys, self.marks, self.pops = start, end, world, keys, list(marks), list(pops)

    def cam(self, t):
        i = max([j for j, k in enumerate(self.keys) if k.t <= t] or [0])
        k = self.keys[i]
        s, cx, cy = pose(k, t)
        if i and t < k.t + TR:
            s0, cx0, cy0 = pose(self.keys[i - 1], k.t)
            u = eo((t - k.t) / TR)
            s, cx, cy = math.exp(math.log(s0) + (math.log(s) - math.log(s0)) * u), cx0 + (cx - cx0) * u, cy0 + (cy - cy0) * u
        return fit_cam(s, cx, cy)

    def render(self, t):
        cam = self.cam(t)
        img = cam_crop(self.world.get(t), *cam)
        paste_marks(img, self.marks, t, cam)
        for p in self.pops:
            paste_pop(img, p, t, cam)
        return img

    def activity(self):
        """Intervals in which something visibly changes (for the 1.5 s rule check)."""
        iv = [(k.t, k.t + TR) for k in self.keys[1:]]
        iv += [(m.t0, m.t0 + m.dur) for m in self.marks]
        iv += [(p.t0, p.t0 + p.anim) for p in self.pops]
        if isinstance(self.world, CardWorld):
            iv += [(i.t0, i.t1) for i in self.world.items]
        return iv
