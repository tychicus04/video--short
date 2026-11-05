"""Nhịp hình: a change every ~2 s on stills and reference cards, each tied to the words being said.
The beat plan (RUN/shots.json): its schema, the time of each beat and the camera that snaps to each focus."""
from dataclasses import dataclass
from typing import Callable

from vshort.fit import Placement, phrase_fracs
from vshort.kit import ease

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
    return f"{x:.1f}".replace(".", ",")


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
            elif text not in said:
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
