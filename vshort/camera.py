"""The camera on the mechanism canvas: each beat framed so what it touches fills the safe area, a soft glide between
beats, and a pull back to the whole canvas at the end so the chain reads A to Z."""
from vshort import kit

MAX_ZOOM = 2.0  # deeper and the pencil looks like a close-up, not a diagram
PAD = 40  # px of canvas kept around what a beat touches
MOVE_S = 0.8  # s of the glide from one beat's frame to the next
OUT_S = 1.2  # s of the pull back to the whole canvas
OUT_LEAD = 2.0  # the pull back starts at least this long before the canvas ends
DRIFT = 0.03  # a held frame creeps this much closer (kallaway-style: the picture never stands still)


def view(box: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """(cx, cy, zoom) that fits `box` (plus PAD) into the safe area, never showing past the canvas; 1x is FULL."""
    x0, y0, x1, y1 = box
    sw, sh = kit.SAFE[2] - kit.SAFE[0], kit.SAFE[3] - kit.SAFE[1]
    z = min(max(min(sw / (x1 - x0 + 2 * PAD), sh / (y1 - y0 + 2 * PAD)), 1.0), MAX_ZOOM)
    cx = min(max((x0 + x1) / 2, kit.SX / z), kit.W - (kit.W - kit.SX) / z)
    cy = min(max((y0 + y1) / 2, kit.SY / z), kit.H - (kit.H - kit.SY) / z)
    return float(cx), float(cy), float(z)


def drifted(v: tuple[float, float, float]) -> tuple[float, float, float]:
    """The frame v after a hold: DRIFT closer, same centre (a deeper zoom only widens where the centre may sit)."""
    return v[0], v[1], v[2] * (1 + DRIFT)


def keys(spans: list[tuple[float, float]], boxes: list, lead: float) -> list[tuple[float, float, float, float]]:
    """(t, cx, cy, zoom) keys: beat i framed on boxes[i] (None: the whole canvas) from `lead` s before the first beat,
    creeping DRIFT closer while it holds, a MOVE_S glide at each beat start, and the last beat pulled back to FULL
    before the canvas ends."""
    views = [kit.FULL if b is None else view(b) for b in boxes]
    out = [(spans[0][0] - lead, *views[0])]
    for (s, e), prev, v in zip(spans[1:], views, views[1:]):
        out += [(s, *drifted(prev)), (min(s + MOVE_S, e), *v)]
    s, e = spans[-1]
    t_out = max(s + MOVE_S, s + 0.5 * (e - s), e - OUT_LEAD)
    return out + [(t_out, *drifted(views[-1])), (t_out + OUT_S, *kit.FULL)]


def glides(ks: list[tuple[float, float, float, float]]) -> list[tuple[float, float]]:
    """The stretches where the camera really moves: a glide or the pull back, not a held frame's drift."""
    def same(a, b) -> bool:
        return a[1:3] == b[1:3] and max(a[3], b[3]) <= min(a[3], b[3]) * (1 + DRIFT) + 1e-9
    return [(a[0], b[0]) for a, b in zip(ks, ks[1:]) if not same(a, b)]


def at(ks: list[tuple[float, float, float, float]], t: float) -> tuple[float, float, float]:
    """The camera at t: eased between the keys around it, held before the first and after the last."""
    if t <= ks[0][0]:
        return ks[0][1:]
    for a, b in zip(ks, ks[1:]):
        if t < b[0]:
            u = kit.ease((t - a[0]) / (b[0] - a[0])) if b[0] > a[0] else 1.0
            return tuple(p + (q - p) * u for p, q in zip(a[1:], b[1:]))
    return ks[-1][1:]
