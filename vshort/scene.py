"""The neon style's scene.json: the vocabulary the scene agent writes in (names of icons, layouts, slots, verbs and the number
of a phrase, never a coordinate), checked on load, and the phrase table it writes against."""
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from vshort.fit import Placement, phrase_times

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
            elif kinds[i] == "link" and (gone := [e for e in ends[i] if e not in keep]):
                problems.append(f"{where}: giữ nối {i!r} mà không giữ {', '.join(map(repr, gone))}, đầu của nó")
            elif kinds[i] == "node" and i in coords and slots is not None:
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
            elif want and kinds[x] != want:
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
            if isinstance(ln.get("a"), str) and isinstance(ln.get("b"), str):
                ends.setdefault(ln.get("id"), (ln["a"], ln["b"]))
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
