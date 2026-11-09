"""The neon style's scene.json: the vocabulary the scene agent writes in (names of icons, layouts, slots, verbs and the number
of a phrase, never a coordinate), checked on load, and the phrase table it writes against; then `resolve` times it to the voice
into the runtime JSON the browser animates (runtime-contract.md) and `check` refuses what overlaps, leaves the safe zone, shows
more than two colours, stalls or prints a number or name the brief lacks."""
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from vshort import render
from vshort.fit import Placement, phrase_times
from vshort.script import names, unknown_numbers
from vshort.textfit import UI_RIGHT, UI_RIGHT_FROM, UI_TOP

LEAD = 0.15  # a picture comes in this long before the phrase it belongs to is said
TONES = ("normal", "risk", "claim", "safe")
LAYOUTS = ("none", "center", "pair", "chain", "ring", "grid")
LINK_STYLES = ("solid", "dashed", "tunnel")
VERBS = {"show": {"ids"}, "draw": {"ids"}, "state": {"ids", "to"}, "flow": {"link", "dir"}, "badge": {"node", "icon"},
         "swap": {"node", "icon"}, "split": {"node", "to"}, "merge": {"from", "into"}, "chip": {"text"},
         "quote": {"text", "who"}, "statement": {"text"}, "hero": {"icon"}, "dim": {"ids"}, "hide": {"ids"}}
ICONS = Path(__file__).parent / "neon" / "icons.json"
# Args that name something the section declared (or keeps) and what each must name: "node", "link", or either (None). A list of
# ids is always a list once loaded: `split`'s `to` and `merge`'s `from` may be written as one id. `state`'s `to` is a tone.
REFS = {"ids": None, "link": "link", "node": "node", "into": "node", "near": "node", "from": "node", "to": "node"}
MANY_IDS = ("ids", "from", "to")
KIND_NAME = {"node": "nút", "link": "đường nối"}
# The only keys scene.json has: no coordinate, no colour, nothing a typo could turn into a silent default.
SECTION_KEYS = {"id", "label", "tone", "layout", "nodes", "links", "beats", "keep"}
NODE_KEYS, LINK_KEYS = {"id", "icon", "label", "slot"}, {"id", "a", "b", "style"}
BEAT_KEYS = {"at", "do", "delay"}  # plus the verb's own (VERBS) and these optional ones
OPTIONAL = {"chip": {"near", "tone"}, "quote": {"tone"}, "hero": {"label", "tone"}, "flow": {"repeat"}}


@dataclass(frozen=True)
class Phrase:
    i: int  # 0 is the title sentence
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Node:
    id: str
    icon: str
    label: str
    slot: str


@dataclass(frozen=True)
class Link:
    id: str
    a: str
    b: str
    style: str  # one of LINK_STYLES


@dataclass(frozen=True)
class Beat:
    at: int  # the phrase it belongs to
    do: str  # a key of VERBS
    args: dict  # the rest of the beat except `at`, `do` and `delay`; a flow's `repeat` is always there (2 if not written)
    delay: float = 0.0


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    tone: str
    layout: str
    nodes: tuple[Node, ...]
    links: tuple[Link, ...]
    beats: tuple[Beat, ...]
    keep: tuple[str, ...]


@dataclass(frozen=True)
class Scene:
    sections: tuple[Section, ...]


class SceneError(Exception):
    """Every problem found, not only the first; `str()` is one per line."""

    def __init__(self, problems: list[str] | str):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("\n".join(self.problems))


@cache
def icons() -> dict[str, list[str]]:
    """Icon name -> the `d` of each of its paths, in a 24×24 box, stroke 2 (Lucide, ISC: its notice is in the file)."""
    return {k: v for k, v in json.loads(ICONS.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def phrase_table(timeline: dict, script: list[dict]) -> list[Phrase]:
    """Every subtitle phrase, numbered from 0 (the title sentence) in the order they are said: what a beat's `at` points at."""
    placements = [Placement(**p) for p in timeline["placements"]]
    return [Phrase(i, s, e, t) for i, (s, e, t) in enumerate(phrase_times(placements, script))]


def beat_time(b: Beat, table: list[Phrase]) -> float:
    return table[b.at].start - LEAD + b.delay


def load_scene(data: dict) -> Scene:
    """The scene in `data`, or a SceneError with every problem at once: each names the section, the beat and the wrong value."""
    from vshort import layout  # here, not at the top: layout imports SceneError and Section from this module

    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise SceneError("scene.json cần khóa sections, một danh sách các mục")
    known_icons, problems = icons(), []
    declared: dict[str, str] = {}  # id of a node or link -> its section; ids are unique across the scene
    kinds: dict[str, str] = {}  # id -> "node" or "link"
    coords: dict[str, tuple[float, float]] = {}  # node id -> the spot of the slot it was declared on
    ends: dict[str, tuple[str, str]] = {}  # link id -> its two nodes
    alive: set[str] = set()  # on screen at the end of the section before: all that `keep` can carry on
    sections: list[Section] = []

    def need(d: dict, keys: list[str], where: str) -> None:
        problems.extend(f"{where}: thiếu {k} (chữ)" for k in keys if not isinstance(d.get(k), str) or not d[k])

    def text(d: dict, key: str, where: str) -> str:
        v = d.get(key, "")
        if not isinstance(v, str):
            problems.append(f"{where}: {key} phải là chữ, không phải {v!r}")
        return v if isinstance(v, str) else ""

    def entries(d: dict, key: str, where: str, kind: type) -> list[tuple[int, object]]:
        v = d.get(key, [])
        if not isinstance(v, list):
            problems.append(f"{where}: {key} phải là danh sách")
            return []
        problems.extend(f"{where}: {key}[{j}] sai kiểu: {x!r}" for j, x in enumerate(v) if not isinstance(x, kind))
        return [(j, x) for j, x in enumerate(v) if isinstance(x, kind)]

    def one_of(value, options, what: str, where: str) -> None:
        if value not in options:
            problems.append(f"{where}: {what} lạ {value!r} (có: {', '.join(options)})")

    def icon(value, where: str) -> None:
        if isinstance(value, str) and value not in known_icons:
            problems.append(f"{where}: icon lạ {value!r} (tên có trong vshort/neon/icons.json)")

    def extra(d: dict, allowed: set[str], where: str) -> None:
        problems.extend(f"{where}: khóa lạ {k!r} (chỉ có: {', '.join(sorted(allowed))})" for k in d if k not in allowed)

    for k, raw in enumerate(data["sections"]):
        if not isinstance(raw, dict):
            problems.append(f"mục #{k}: phải là một đối tượng, không phải {raw!r}")
            continue
        sid = raw["id"] if isinstance(raw.get("id"), str) and raw["id"] else f"#{k}"
        where = f"mục {sid}"
        need(raw, ["id"], where)
        extra(raw, SECTION_KEYS, where)
        if sid in [s.id for s in sections]:
            problems.append(f"{where}: trùng id mục")
        tone, lay = raw.get("tone", "normal"), raw.get("layout", "none")
        one_of(tone, TONES, "tone", where)
        one_of(lay, LAYOUTS, "layout", where)
        slots = layout.SLOTS.get(lay) if isinstance(lay, str) else None  # a layout that does not exist is already reported
        own: set[str] = set()
        taken: dict[str, str] = {}  # slot of this section -> the node that stands on it

        def declare(i, w: str, kind: str) -> None:
            if not isinstance(i, str) or not i:
                return
            if i in own:
                problems.append(f"{w}: trùng id {i!r} trong mục {sid}")
            elif i in declared:
                problems.append(f"{w}: id {i!r} đã dùng ở mục {declared[i]}")
            own.add(i)
            kinds.setdefault(i, kind)

        def take(slot: str, i: str, w: str) -> None:
            if slot in taken:
                problems.append(f"{w}: slot {slot!r} đã có nút {taken[slot]!r}")
            else:
                taken[slot] = i

        keep = [x for _, x in entries(raw, "keep", where, str)]
        for i in keep:
            if i not in alive:
                problems.append(f"{where}: keep nhắc tới {i!r}, mà mục trước không còn {i!r} (chưa khai báo hoặc không được giữ)")
            elif kinds.get(i) == "link" and (gone := [e for e in ends.get(i, ()) if e not in keep]):
                problems.append(f"{where}: giữ nối {i!r} mà không giữ {', '.join(map(repr, gone))}, đầu của nó")
            elif kinds.get(i) == "node" and i in coords and slots is not None:
                # a node does not move: it stays where it stood, so the new layout needs a slot at exactly that spot
                at = next((s for s, xy in slots.items() if all(abs(a - b) < 0.5 for a, b in zip(xy, coords[i]))), None)
                if at is None:
                    problems.append(f"{where}: giữ {i!r} ({coords[i][0]:.0f}, {coords[i][1]:.0f}) nhưng bố cục {lay} không có ô ở đó")
                else:
                    take(at, i, f"{where}, giữ {i}")
        nodes = []
        for _, n in entries(raw, "nodes", where, dict):
            w = f"{where}, nút {n.get('id')}"
            need(n, ["id", "icon", "slot"], w)
            extra(n, NODE_KEYS, w)
            declare(n.get("id"), w, "node")
            icon(n.get("icon"), w)
            slot = n.get("slot")
            if slots is not None and isinstance(slot, str):
                if slot not in slots:
                    problems.append(f"{w}: slot {slot!r} không có trong bố cục {lay} (có: {', '.join(slots) or 'không có slot nào'})")
                else:
                    take(slot, n.get("id"), w)
                    if isinstance(n.get("id"), str):
                        coords.setdefault(n["id"], slots[slot])
            nodes.append(Node(n.get("id", ""), n.get("icon", ""), text(n, "label", w), n.get("slot", "")))
        def ref(w: str, key: str, x: str, want: str | None) -> None:
            if x not in own and x not in keep:
                problems.append(f"{w}: {key} nhắc tới {x!r}, mục {sid} chưa khai báo (cũng không có trong keep)")
            elif want and kinds.get(x, want) != want:  # a keep that was refused has no kind: it is already reported
                problems.append(f"{w}: {key} nhắc tới {x!r}, là {KIND_NAME[kinds[x]]}, mà ở đây cần {KIND_NAME[want]}")

        links = []
        for _, ln in entries(raw, "links", where, dict):
            w = f"{where}, nối {ln.get('id')}"
            need(ln, ["id", "a", "b"], w)
            extra(ln, LINK_KEYS, w)
            declare(ln.get("id"), w, "link")
            one_of(ln.get("style", "solid"), LINK_STYLES, "style", w)
            for end in ("a", "b"):
                if isinstance(ln.get(end), str):
                    ref(w, end, ln[end], "node")
            if all(isinstance(ln.get(k), str) for k in ("id", "a", "b")):
                ends.setdefault(ln["id"], (ln["a"], ln["b"]))
            links.append(Link(ln.get("id", ""), ln.get("a", ""), ln.get("b", ""), ln.get("style", "solid")))
        beats = []
        for j, b in entries(raw, "beats", where, dict):
            w = f"{where}, nhịp {j}"
            need(b, ["do"], w)
            at, do, delay = b.get("at"), b.get("do"), b.get("delay", 0.0)
            if not isinstance(at, int) or isinstance(at, bool):
                problems.append(f"{w}: 'at' phải là số cụm (số nguyên), không phải {at!r}")
            elif at == 0:
                problems.append(f"{w}: cụm 0 là câu tiêu đề, nhịp đặt từ cụm 1")
            elif at < 0:
                problems.append(f"{w}: cụm {at} không có")
            if isinstance(delay, bool) or not isinstance(delay, (int, float)):
                problems.append(f"{w}: delay phải là số giây, không phải {delay!r}")
            if not isinstance(do, str):
                continue
            if do not in VERBS:
                problems.append(f"{w}: động từ lạ {do!r} (có: {', '.join(VERBS)})")
                continue
            extra(b, BEAT_KEYS | VERBS[do] | OPTIONAL.get(do, set()), w)
            args = {key: v for key, v in b.items() if key not in ("at", "do", "delay")}
            if lack := sorted(VERBS[do] - args.keys()):
                problems.append(f"{w}: {do} thiếu {', '.join(lack)}")
            need(args, [key for key in ("text", "who", "icon") if key in args], w)
            if "label" in args:
                text(args, "label", w)
            for key, want in REFS.items():
                if key not in args or (key == "to" and do != "split"):
                    continue
                if key in MANY_IDS and isinstance(args[key], str):
                    args[key] = [args[key]]
                names = args[key] if key in MANY_IDS else [args[key]]
                if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
                    problems.append(f"{w}: {key} phải là {'danh sách id' if key in MANY_IDS else 'một id'}, không phải {args[key]!r}")
                    continue
                for x in names:
                    ref(w, key, x, want)
            if do == "state" and "to" in args:
                one_of(args["to"], TONES, "to", w)
            if "tone" in args:
                one_of(args["tone"], TONES, "tone", w)
            if do in ("badge", "swap", "hero"):
                icon(args.get("icon"), w)
            if do == "flow":
                if "dir" in args:
                    one_of(args["dir"], ("a-b", "b-a"), "dir", w)
                rep = args.setdefault("repeat", 2)
                if isinstance(rep, bool) or not isinstance(rep, int) or rep < 1:
                    problems.append(f"{w}: repeat phải là số lần hữu hạn từ 1, không phải {rep!r}")
            if isinstance(at, int) and isinstance(delay, (int, float)):
                beats.append(Beat(at, do, args, float(delay)))
        for i in own:
            declared.setdefault(i, sid)
        alive = own | set(keep)
        sections.append(Section(sid, text(raw, "label", where), tone if tone in TONES else "normal",
                                lay if lay in LAYOUTS else "none", tuple(nodes), tuple(links), tuple(beats), tuple(keep)))
    if problems:
        raise SceneError(problems)
    return Scene(tuple(sections))


# ---- timing and checking

MAX_GAP, MAX_TONES, DIM = 5.0, 2, 0.35  # longest stretch with nothing changing; colours at once; opacity of a dimmed element
TOP, RIGHT, RIGHT_FROM_Y, CAPTION_BAND = UI_TOP, UI_RIGHT, UI_RIGHT_FROM, (1000, 1140)  # the safe zone's edges, px
LIT = 0.6  # an element this opaque or more counts as a colour on the screen
OFF, DRAW, HERO_DRAW, MOVE, FLOW = 0.35, 0.6, 0.7, 0.6, 0.85  # seconds: an `off`, a stroke-draw, a hero's, a tile's flight, one pass
STAGGER = 0.08  # between the tiles of a split or a merge
EPS = 0.002  # times are rounded to the millisecond; two that close are the same moment
KIND_VI = {"icon": "nút", "badge": "badge", "tile": "mảnh", "link": "nối", "label": "nhãn", "section": "nhãn mục",
           "chip": "chip", "statement": "câu lớn", "quote": "lời trích", "hero": "hero"}
TONE_VI = {"normal": "xanh dương", "risk": "đỏ", "claim": "vàng", "safe": "xanh lá"}
TEXTS = {"label", "section", "chip", "statement", "quote"}  # the rest but links (and a hero's label, below) are solid
CHECKED_TEXT = {"chip": ("text",), "statement": ("text",), "quote": ("text", "who"), "hero": ("label",), "section": ("text",)}


def _s(t: float, digits: int = 1) -> str:
    return f"{t:.{digits}f}".replace(".", ",") + " s"


def _typed(text: str) -> float:
    return round(min(2.0, max(0.3, 0.05 * len(text))), 2)  # seconds to type `text`: 20 letters a second, within 0.3-2


def _parts(e: dict) -> list[tuple[str, object]]:
    """What an element draws, as ("text", box), ("solid", box) or ("link", the link): a hero's icon is solid and its label text
    (its `box` holds both, with the empty corners between them)."""
    from vshort import layout

    if e["kind"] == "link":
        return [("link", e)]
    if e["kind"] == "hero":
        h = (layout.INK * e["size"] + layout.STROKE["hero"]) / 2
        return [("solid", [e["x"] - h, e["y"] - h, e["x"] + h, e["y"] + h])] + [("text", e["label_box"])] * bool(e["label"])
    return [("text" if e["kind"] in TEXTS else "solid", e["box"])]


def _touch(p: tuple[str, object], q: tuple[str, object]) -> bool:
    """Whether two parts come within 4 px: text on text, text on a solid, a solid on a solid, text on a link (not a solid on one)."""
    from vshort import layout

    (ka, a), (kb, b) = p, q
    if kb == "link":
        return ka == "text" and layout.segment_hits_box(b, a)
    return ka != "link" and layout.boxes_overlap(a, b)


def _name(e: dict) -> str:
    said = e.get("text") or e.get("label")
    return f"{KIND_VI[e['kind']]} {e['id']!r}" + (f" {said!r}" if said else "")


class _Screen:
    """What is on screen as the actions leave it: the one replay `resolve` (what is shown, what is gone) and `check` (what overlaps,
    which colours) both read. An element is there from its first showing action (on, draw, type, move, a swap's new icon, a
    colour) until its `off` has run its course; a swap takes the old icon away at once."""

    def __init__(self):
        self.tone: dict[str, str | None] = {}
        self.dim: set[str] = set()
        self.first: dict[str, float] = {}  # id -> when it was first shown
        self.out: dict[str, tuple[float, float]] = {}  # id -> (when its off starts, how long it takes)

    def add(self, els: list[dict]) -> None:
        self.tone.update((e["id"], e["tone"]) for e in els)

    def apply(self, a: dict) -> None:
        t, do, ids = a["t"], a["do"], a["ids"]
        if do == "off":
            self.out.update((i, (t, a.get("d", OFF))) for i in ids)
        elif do == "swap":
            self.out[ids[0]] = (t, 0.0)
            self._show(ids[1:], t)
        elif do == "tone":  # a colour ends at opacity 1, dim at DIM: either shows what was not shown
            for i in ids:
                if a["to"] == "dim":
                    self.dim.add(i)
                else:
                    self.tone[i] = a["to"]
                    self.dim.discard(i)
            self._show(ids, t)
        elif do != "flow":  # on, draw, type, move: each ends at opacity 1, so a dimmed element is whole again
            self.dim.difference_update(ids)
            self._show(ids, t)

    def _show(self, ids: list[str], t: float) -> None:
        for i in ids:
            self.first.setdefault(i, t)
            self.out.pop(i, None)

    def visible(self, i: str) -> bool:
        """Shown and not turned off, whatever the time."""
        return i in self.first and i not in self.out

    def present(self, i: str, t: float) -> bool:
        return i in self.first and (i not in self.out or t < self.out[i][0] + self.out[i][1] - EPS)

    def opacity(self, i: str, t: float) -> float:
        o = DIM if i in self.dim else 1.0
        if i in self.out:
            t0, d = self.out[i]
            o *= (1 - min(1.0, max(0.0, (t - t0) / d))) ** 2 if d > 0 else 0.0  # the off's power1.out
        return o if i in self.first else 0.0


class _Reel:
    """The video as `resolve` builds it: every element placed so far, the actions that move them, and what they leave on screen."""

    def __init__(self):
        self.els: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.actions: list[dict] = []
        self.screen = _Screen()
        self.face: dict[str, str] = {}  # node id -> the icon showing for it (its own, or the last swap's)

    def add(self, new: list[dict]) -> None:
        self.els += new
        self.by_id.update((e["id"], e) for e in new)
        self.screen.add(new)

    def emit(self, t: float, do: str, ids, **more) -> None:
        if ids := list(dict.fromkeys(ids)):
            self.actions.append({"t": round(t, 3), "do": do, "ids": ids, **more})
            self.screen.apply(self.actions[-1])

    def group(self, i: str) -> list[str]:
        """A node and what belongs to it (its label, its badges, its swap icons), or a link alone."""
        return [e["id"] for e in self.els if i in (e["id"], e.get("of"))]

    def own(self, i: str) -> list[str]:
        """What comes on screen with `i`: a node brings its label."""
        return [e["id"] for e in self.els if e["id"] == i or (e.get("of") == i and e["kind"] == "label")]

    def visible(self, ids) -> list[str]:
        return [i for i in ids if self.screen.visible(i)]


def resolve(sc: Scene, table: list[Phrase], title: str, total: float, said: tuple[float, float]) -> dict:
    """The runtime JSON (runtime-contract.md): the title bar, the captions, every element `layout.place` made for every section,
    and the actions that show them, each timed to the phrase its beat belongs to. `said` is when the title is spoken: the first
    placement's start and end (not the table's row 0, which runs on to the next sentence), so the bar finishes typing at the
    frame `cover.py` grabs. Raises a SceneError with every problem found."""
    from vshort import layout

    problems = [f"mục {s.id}: chưa có nhịp nào, không biết hiện lúc nào" for s in sc.sections if not s.beats]
    problems += [f"mục {s.id}, nhịp {j} ({b.do}): cụm {b.at} không có (bảng có cụm 1–{len(table) - 1})"
                 for s in sc.sections for j, b in enumerate(s.beats) if not 0 < b.at < len(table)]
    if problems:
        raise SceneError(problems)
    reel, alive, last, prev = _Reel(), [], 0.0, None  # alive: what the section before left on screen
    for sec in sc.sections:
        sid = sec.id
        order = sorted(((round(beat_time(b, table), 3), k, b) for k, b in enumerate(sec.beats)), key=lambda x: x[:2])
        t0, keep = order[0][0], set(sec.keep)
        # a kept node, its label, badges and swap icons stay; its tiles, like every chip, quote, statement and hero, do not (Ruling 13)
        stay = [e for e in alive if e["id"] in keep or (e.get("of") in keep and e["kind"] != "tile")]
        if prev and t0 - OFF < last - EPS:
            problems.append(f"mục {sid} mở lúc {_s(t0, 2)} (mục {prev} tắt từ {_s(t0 - OFF, 2)}), mà mục {prev} còn nhịp lúc {_s(last, 2)}")
        try:  # the swap icons are not passed: they stand where the node's icon does
            new = layout.place(sec, [e for e in stay if e["kind"] != "icon" or "of" not in e])
        except SceneError as e:
            problems += e.problems
            break
        mark = len(reel.actions)
        kept_ids = {e["id"] for e in stay}
        reel.emit(t0 - OFF, "off", reel.visible(e["id"] for e in alive if e["id"] not in kept_ids), d=OFF)
        reel.add(new)
        alive = stay + new
        if f"{sid}.label" in reel.by_id:
            reel.emit(t0, "type", [f"{sid}.label"], d=_typed(sec.label))
        for t, k, b in order:
            _beat(reel, f"{sid}.{k}", t, b)
        last, prev = max((a["t"] for a in reel.actions[mark:]), default=t0), sid
    ids = [e["id"] for e in reel.els]
    problems += [f"id phần tử {i!r} trùng: đổi id của nút, nối hay mục" for i in dict.fromkeys(ids) if ids.count(i) > 1]
    if problems:
        raise SceneError(problems)
    fit = render.title_fit(title)
    bar = None
    if fit:
        t0, t1, out = render.title_times(*said)
        bar = {"lines": fit[1], "size": fit[0], "t0": t0, "t1": t1, "out": out}
    return {"total": total, "title": bar,
            "captions": [[p.start, p.end, p.text.replace("*", "")] for p in (table[1:] if bar else table)],  # plain: the kit writes them as is
            "elements": reel.els, "actions": sorted(reel.actions, key=lambda a: a["t"])}  # stable: same-time actions keep their order


def _beat(reel: _Reel, eid: str, t: float, b: Beat) -> None:
    """The actions of one beat (`eid` is the id of what it makes: "<section>.<k>")."""
    a, by_id, screen = b.args, reel.by_id, reel.screen
    if b.do in ("show", "draw"):
        ids = [x for i in a["ids"] for x in reel.own(i)]
        labels = [x for x in ids if by_id[x]["kind"] == "label"]
        shapes = [x for x in ids if x not in labels]
        if b.do == "show":
            reel.emit(t, "on", shapes)
        else:
            reel.emit(t, "draw", shapes, d=DRAW)
        if labels:
            reel.emit(t, "type", labels, d=_typed(max((by_id[x]["text"] for x in labels), key=len)))
    elif b.do in ("state", "dim", "hide"):
        ids = list(dict.fromkeys(x for i in a["ids"] for x in reel.group(i)))
        shown = reel.visible(ids)
        if b.do == "hide":
            reel.emit(t, "off", shown, d=OFF)
        else:
            reel.emit(t, "tone", shown, to="dim" if b.do == "dim" else a["to"])
        for x in ids:  # not yet shown: it will come in that colour
            if b.do == "state" and x not in screen.first:
                by_id[x]["tone"] = screen.tone[x] = a["to"]
    elif b.do == "flow":
        reel.emit(t, "flow", [a["link"]], dir=a["dir"], repeat=a.get("repeat", 2), d=FLOW)
    elif b.do == "badge":
        reel.emit(t, "on", [eid])
    elif b.do == "swap":
        old = reel.face.get(a["node"], a["node"])
        if eid not in screen.first:  # it comes in the colour the icon it replaces has now: a state may have changed it since `place`
            by_id[eid]["tone"] = screen.tone[eid] = screen.tone[old]
        reel.emit(t, "swap", [old, eid])
        reel.face[a["node"]] = eid
    elif b.do == "split":
        src = by_id[a["node"]]
        for j, nid in enumerate(a["to"]):
            by_id[f"{eid}.{j}"]["of"] = nid  # a tile hangs over its node: a hide, a dim or a state of the node reaches it too
            reel.emit(t + j * STAGGER, "move", [f"{eid}.{j}"], d=MOVE, **{"from": [[src["x"], src["y"]]]})
    elif b.do == "merge":
        into = by_id[a["into"]]
        for j, nid in enumerate(a["from"]):
            tile, src = by_id[f"{eid}.{j}"], by_id[nid]
            # `place` rests all the tiles on one spot over `into` (they overlap there on purpose, and `check` lets them); each flies
            # in from the same spot over its own node, and goes off on arrival
            rise = into["y"] - into["size"] / 2 - tile["y"]
            start = round(t + j * STAGGER, 3)
            reel.emit(start, "move", [tile["id"]], d=MOVE, **{"from": [[src["x"], src["y"] - src["size"] / 2 - rise]]})
            reel.emit(start + MOVE + 0.1, "off", [tile["id"]], d=0.3)
    elif b.do == "chip":
        reel.emit(t, "on", [eid])
    elif b.do == "statement":
        reel.emit(t, "type", [eid], d=_typed(a["text"]))
    elif b.do == "quote":
        reel.emit(t, "draw", [eid], d=DRAW)
        reel.emit(t + 0.1, "type", [eid], d=_typed(a["who"] + a["text"]))
    elif b.do == "hero":
        reel.emit(t, "draw", [eid], d=HERO_DRAW)
        if a.get("label"):
            reel.emit(t + 0.2, "type", [eid], d=_typed(a["label"]))


def check(rt: dict, brief: str) -> list[str]:
    """What is wrong with the resolved scene, one sentence each, naming the elements and the time. Replays the actions and looks
    at every moment something changes: overlaps (text on text, text on an icon, a badge, a tile or a link, an icon on an icon;
    pieces of one split or merge may touch), the safe zone, more than MAX_TONES colours, more than MAX_GAP s with no change, and
    every number or name in the diagram's words against the brief."""
    els, acts = {e["id"]: e for e in rt["elements"]}, sorted(rt["actions"], key=lambda a: a["t"])
    out, seen, screen = [], set(), _Screen()
    screen.add(rt["elements"])

    def report(key, msg: str) -> None:
        if key not in seen:  # one mistake, one line: not again at every moment it lasts
            seen.add(key)
            out.append(msg)

    n = 0
    while n < len(acts):
        t = acts[n]["t"]
        while n < len(acts) and acts[n]["t"] == t:
            screen.apply(acts[n])
            n += 1
        if not 0 <= t <= rt["total"]:
            report(("out", t), f"{_s(t)}: hành động ngoài video (dài {_s(rt['total'])}): " + ", ".join(repr(i) for i in acts[n - 1]["ids"]))
        here = [i for i in screen.first if screen.present(i, t)]
        for k, i in enumerate(here):
            e = els[i]
            if ("zone", i) not in seen:
                seen.add(("zone", i))
                x0, y0, x1, y1 = e["box"]
                if y0 < TOP:
                    out.append(f"{_s(t)}: {_name(e)} ở y {y0:.0f}, trên y {TOP} (chỉ có logo ở đó)")
                if y1 > CAPTION_BAND[0]:
                    out.append(f"{_s(t)}: {_name(e)} xuống y {y1:.0f}, vào dải phụ đề (từ y {CAPTION_BAND[0]})")
                if y1 > RIGHT_FROM_Y and x1 > RIGHT:
                    out.append(f"{_s(t)}: {_name(e)} sang x {x1:.0f} dưới y {RIGHT_FROM_Y}, quá x {RIGHT} (nút của nền tảng)")
            for j in here[k + 1:]:
                a, b = sorted((e, els[j]), key=lambda x: x["kind"] == "link")  # a link goes second
                # the tiles of one split or merge fly to the same place on purpose: they are one piece of animation
                one = a["kind"] == b["kind"] == "tile" and a["id"].rpartition(".")[0] == b["id"].rpartition(".")[0]
                if not one and any(_touch(p, q) for p in _parts(a) for q in _parts(b)):
                    report(frozenset((a["id"], b["id"])), f"{_s(t)}: {_name(a)} đè lên {_name(b)}")
        lit: dict[str, list[str]] = {}
        for i in here:
            if screen.tone[i] is not None and screen.opacity(i, t) >= LIT:
                lit.setdefault(screen.tone[i], []).append(i)
        if len(lit) > MAX_TONES:
            who = "; ".join(f"{TONE_VI[k]} ({', '.join(map(repr, v[:3]))})" for k, v in lit.items())
            report(frozenset(lit), f"{_s(t)}: {len(lit)} màu neon cùng lúc, tối đa {MAX_TONES}: {who}")
    # with no bar the title is a caption, which holds the line until the spoken title ends: beats start after it
    start = rt["title"]["out"] if rt.get("title") else rt["captions"][0][1] if rt.get("captions") else 0.0
    marks = [start] + sorted({a["t"] for a in acts if start < a["t"] < rt["total"]}) + [rt["total"]]
    for x, y in zip(marks, marks[1:]):
        if y - x > MAX_GAP + EPS:
            out.append(f"{_s(x)} đến {_s(y)}: hơn {MAX_GAP:g} giây không có nhịp hình")
    for i, t in screen.first.items():
        e = els[i]
        for key in CHECKED_TEXT.get(e["kind"], ()):
            text = e.get(key) or ""
            if bad := unknown_numbers(text, brief):
                out.append(f"{_s(t)}: {_name(e)}: số {', '.join(bad)} không có trong brief")
            # ponytail: all-capitals text gets the number check only, because capitals cannot tell a name from a word there
            # ("PHẢI TIN?" would flag every word); the reviewer agent reads those against the brief. A section label is exempt.
            if e["kind"] != "section" and not text.isupper():
                lack = sorted(w for w in names(text) if not re.search(rf"(?<!\w){re.escape(w)}(?!\w)", brief, re.I))
                if lack:
                    out.append(f"{_s(t)}: {_name(e)}: tên {', '.join(lack)} không có trong brief")
    return out
