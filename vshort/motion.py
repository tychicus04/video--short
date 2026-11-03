"""motion.json: the mechanism of the video drawn on one canvas, beat by beat, written from the brief before the voice
exists — checked, timed, previewed as a sheet. Earlier beats fade back as the voice moves on; one red actor runs
through the whole canvas."""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vshort import camera, kit, shapes
from vshort.fit import GAP, LEAD, Placement, phrase_fracs
from vshort.script import syllables
from vshort.textfit import FONTS
from vshort.visuals import SAFE_TLDS, _int, _strip_marks

# syllables any label may use besides the narration's own words
COMMON = frozenset("điện thoại máy tính chủ dữ liệu hệ thống hacker kẻ tấn công nghe lén mạng trình duyệt người dùng nạn "
                   "nhân gói tin tệp mật khẩu nhắn ví tiền thư khóa đã bị chiếm lấy cắp trang web an toàn lõi lớp bảo vệ "
                   # the everyday props kit and the moves of its scenes
                   "thẻ chìa cửa barie tòa nhà phòng két sắt phong bì hòm kiện hàng xe giao camera rào bảng tên danh sách "
                   "quét bản sao kẹp cho vào đúng sai tầng cầu thang viên kỹ sư khách".split())
MAX_SEEN, MAX_BEATS = 7, 6
BEAT_EST = 3.0  # s per beat: the timing of a design, before any line is spoken
SYL = 0.2  # s per syllable: the voice before the timeline exists
MIN_ACT = 0.3  # shortest action, even at the very end of a line
LEAD_IN = 0.35  # what opens the canvas starts drawing in the crossfade into it (half the gap + half the fade): no blank page
ACTS = ("move", "bounce", "red", "pulse", "hide", "attach", "open", "close")
DUR = {"draw": kit.DRAW, "red": kit.TURN, "hide": kit.HIDE, "move": kit.MOVE, "bounce": kit.MOVE, "attach": kit.MOVE,
       "open": kit.OPEN, "close": kit.OPEN}
MOVERS = ", ".join(sorted(kit.MOVERS))
MARKS = ("crack", "check", "cross")  # small marks: no label, not counted as things in view
KINDS = kit.BOXED | kit.POINTED | {"path"}
AREA = f"vùng an toàn x {kit.SAFE[0]}–{kit.SAFE[2]}, y {kit.SAFE[1]}–{kit.SAFE[3]}"
SHEET_W = 240
JUMP = 20  # px a mover may be off the start of the path it then runs along


OLD = "motion.json dạng cũ (scenes): viết lại theo dạng nhịp (beats)"


@dataclass
class Scene:
    lines: list[int]
    things: list[dict]
    acts: list[kit.Act]
    cams: list[tuple[float, float, float, float]] = field(default_factory=list)  # camera keys; [] is FULL throughout

    def view(self, t: float) -> tuple[float, float, float]:
        return camera.at(self.cams, t) if self.cams else kit.FULL


def load(path: Path) -> dict | None:
    """The scene file; None when there is none or it says null (no animation). Bad JSON raises ValueError."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def lines(doc) -> set[int]:
    got = doc.get("lines") if isinstance(doc, dict) else None
    return {i for i in got if _int(i)} if isinstance(got, list) else set()


def clashes(items: list, animated: set[int]) -> list[str]:
    """References of visuals.json on animated lines: the animation replaces the frame, so the reference is wasted."""
    return [f"visuals.json mục {n} ({it['kind']}): câu {it['id']} đã có hình động (motion.json); chọn câu khác"
            for n, it in enumerate(items, 1)
            if isinstance(it, dict) and it.get("kind") in ("svg", "photo") and _int(it.get("id"))
            and it["id"] in animated]


def _spoken(script: list[dict]) -> dict[int, str]:
    return {r["id"]: r["phrases"] for r in script if r["phrases"].strip()}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _xy(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(map(_num, v))


def _words(text: str) -> list[str]:
    return [w for w in (_strip_marks(tok).lower() for tok in text.replace("|", " ").split()) if w]


def _inside(box) -> bool:
    x0, y0, x1, y1 = kit.SAFE
    return box[0] >= x0 and box[1] >= y0 and box[2] <= x1 and box[3] <= y1


def _metaphor(run_dir: Path | None) -> set[str]:
    """The words of the approved metaphor (RUN/an-du.md): a label or say may use them; none when there is no file."""
    f = run_dir / "an-du.md" if run_dir else None
    return set(_words(f.read_text(encoding="utf-8"))) if f and f.exists() else set()


def _text_problems(what: str, text, said: set[str], extra: frozenset | set = frozenset()) -> list[str]:
    if not isinstance(text, str) or not text.strip() or "\n" in text:
        return [f"{what} phải là một dòng chữ, không rỗng"]
    probs = []
    if len(text) > kit.MAX_LABEL:
        probs.append(f"{what} {text!r} dài {len(text)} ký tự (tối đa {kit.MAX_LABEL})")
    for w in _words(text):
        if not (w in said or w in extra or w in COMMON or (len(w) == 1 and w.isalnum())
                or ("." in w and w.endswith(SAFE_TLDS))):
            probs.append(f"{what} {text!r}: chữ {w!r} không có trong lời đọc của đoạn này hay danh sách danh từ thường")
    return probs


def _thing_problems(th, said: set[str], run_dir: Path | None, extra: frozenset | set = frozenset()) -> list[str]:
    if not isinstance(th, dict):
        return ["thing phải là object"]
    tid, kind = th.get("id"), th.get("kind")
    what = f"thing {tid!r}"
    if not isinstance(tid, str) or not tid:
        return ["thing thiếu id (chuỗi)"]
    if not isinstance(kind, str) or kind not in KINDS:
        return [f"{what}: kind {kind!r} không hợp lệ ({', '.join(sorted(KINDS))})"]
    probs = []
    if kind in kit.BOXED:
        box = th.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(map(_num, box)) and box[0] < box[2] and box[1] < box[3]):
            return [f"{what}: box phải là [x0, y0, x1, y1] với x0 < x1, y0 < y1"]
        if kind == "shape":
            doc = shapes.find(th.get("shape"), run_dir)
            if doc is None:
                return [f"{what}: không có hình {th.get('shape')!r} trong RUN/shapes/ hay thư viện assets/shapes/"]
            if bad := shapes.problems(doc, th["shape"]):
                return [f"{what}: {p}" for p in bad]
    elif kind == "path":
        pts = th.get("points")
        if not (isinstance(pts, list) and len(pts) >= 2 and all(map(_xy, pts))):
            return [f"{what}: points phải là danh sách từ 2 điểm [x, y]"]
        if th.get("label"):
            probs.append(f"{what}: path không có nhãn")
    else:
        if not _xy(th.get("xy")):
            return [f"{what}: xy phải là [x, y]"]
        if kind == "icon" and (not isinstance(th.get("icon"), str) or th["icon"] not in kit.ICONS):
            return [f"{what}: icon {th.get('icon')!r} không hợp lệ ({', '.join(sorted(kit.ICONS))})"]
        if kind == "text" and not th.get("label"):
            return [f"{what}: text cần label"]
        if kind in MARKS and th.get("label"):
            probs.append(f"{what}: {kind} không có nhãn")
    if "role" in th and (kind != "figure" or th["role"] not in kit.ROLES):
        probs.append(f"{what}: role chỉ dùng cho figure, một trong {', '.join(sorted(kit.ROLES))}")
    if not isinstance(th.get("color", "ink"), str) or th.get("color", "ink") not in kit.COLORS:
        probs.append(f"{what}: color {th['color']!r} không hợp lệ ({', '.join(kit.COLORS)})")
    if "label" in th:
        found = _text_problems("nhãn", th["label"], said, extra)
        probs += [f"{what}: {p}" for p in found]
        if not found and kind == "box" and kit.label_em(th) == 0:
            probs.append(f"{what}: nhãn {th['label']!r} không vừa hộp ở cỡ chữ nhỏ nhất {kit.MIN_LABEL_EM}")
    if "means" in th:  # the technical half: only words of the brief or the voice, never the metaphor's own
        probs += ([f"{what}: means cần label (means là dòng nghĩa dưới nhãn)"] if not th.get("label") else
                  [f"{what}: {p}" for p in _text_problems("means", th["means"], said)])
    if "url" in th:
        url = th["url"]
        if kind not in ("phone", "computer"):
            probs.append(f"{what}: chỉ phone và computer có url")
        elif not isinstance(url, str) or not url.lower().endswith(SAFE_TLDS) or " " in url:
            probs.append(f"{what}: url {url!r} phải là tên chung kết thúc bằng {', '.join(SAFE_TLDS)}")
    if not probs:
        box = kit.bbox(th)
        if not _inside(box):
            probs.append(f"{what}: nằm ngoài {AREA} (khung {[round(v) for v in box]})")
    return probs + _at_problems(what, th)


def _act_problems(m: int, a, things: dict[str, dict], said: set[str], hinged: frozenset | set = frozenset(),
                  extra: frozenset | set = frozenset()) -> list[str]:
    if not isinstance(a, dict):
        return [f"act {m}: phải là object"]
    do, tid = a.get("do"), a.get("thing")
    what = f"act {m} ({do})"
    if do not in ACTS:
        return [f"act {m}: do {do!r} không hợp lệ ({', '.join(ACTS)})"]
    if not isinstance(tid, str) or tid not in things:
        return [f"{what}: thing {tid!r} không có trong things"]
    th, probs = things[tid], []
    if do in ("move", "bounce", "attach") and th["kind"] not in kit.MOVERS:
        probs.append(f"{what}: {tid!r} ({th['kind']}) không được di chuyển hay gắn — chỉ {MOVERS}")
    if do == "attach":
        on = a.get("on")
        if not isinstance(on, str) or on == tid or things.get(on, {}).get("kind") not in kit.MOVERS:
            probs.append(f"{what}: on {on!r} phải là id một thứ di chuyển được ({MOVERS}), khác {tid!r}")
        if not _xy(a.get("offset", [0, 0])):
            probs.append(f"{what}: offset phải là [x, y] (chỗ nó nằm trên thứ mang nó)")
    elif "on" in a or "offset" in a:
        probs.append(f"{what}: on và offset chỉ dùng với attach")
    if do == "pulse" and th["kind"] != "dot":
        probs.append(f"{what}: chỉ dot mới pulse")
    if do in ("open", "close") and tid not in hinged:
        probs.append(f"{what}: {tid!r} không có phần mở/đóng (hinge trong file hình thư viện)")
    if "say" in a:
        if do != "red" or th["kind"] != "box":
            probs.append(f"{what}: say chỉ dùng với red trên một box")
        elif th["box"][3] - th["box"][1] < kit.SAY_BOX_H:
            probs.append(f"{what}: box {tid!r} thấp hơn {kit.SAY_BOX_H} px, không đủ chỗ cho say dưới nhãn")
        else:
            probs += [f"{what}: {p}" for p in _text_problems("say", a["say"], said, extra)]
    if do not in ("move", "bounce") and ("to" in a or "path" in a):
        probs.append(f"{what}: to và path chỉ dùng với move hoặc bounce")
    if "vanish" in a and (do != "move" or not isinstance(a["vanish"], bool)):
        probs.append(f"{what}: vanish chỉ dùng với move, true hoặc false")
    if "dur" in a and not (_num(a["dur"]) and MIN_ACT <= a["dur"] <= 5):
        probs.append(f"{what}: dur phải là số giây từ {MIN_ACT} đến 5")
    if do in ("move", "bounce"):
        has_to, has_path = "to" in a, "path" in a
        if do == "bounce" and (has_path or not has_to):
            probs.append(f"{what}: bounce cần to, không có path")
        elif has_to == has_path:
            probs.append(f"{what}: move cần đúng một trong to hoặc path")
        elif has_to and not _xy(a["to"]):
            probs.append(f"{what}: to phải là [x, y]")
        elif has_path and (not isinstance(a["path"], str) or things.get(a["path"], {}).get("kind") != "path"):
            probs.append(f"{what}: path {a['path']!r} không phải một thing kind path")
        elif th["kind"] in kit.MOVERS:
            ends = [a["to"]] if has_to else things[a["path"]]["points"]
            if not all(_inside(kit.bbox(kit.at_pos(th, p))) for p in ends):
                probs.append(f"{what}: {tid!r} đi ra ngoài {AREA}")
    return probs + _at_problems(what, a)




def _at_problems(what: str, d: dict) -> list[str]:
    if "at" in d and not (_num(d["at"]) and 0 <= d["at"] <= 1):
        return [f"{what}: at {d['at']!r} phải là số 0–1 (vị trí trong nhịp)"]
    return []


def _actor_problems(doc: dict, things: dict[str, dict]) -> list[str]:
    """The red actor is drawn in beat 1 and runs through the whole canvas: never hidden, never vanishing."""
    actor = doc.get("actor")
    th = things.get(actor) if isinstance(actor, str) else None
    if th is None or th["kind"] not in ("dot", "figure"):
        return [f"motion.json: actor {actor!r} phải là id của một thing kind dot hoặc figure (kẻ tấn công đi suốt đoạn)"]
    probs = [] if th["beat"] == 1 else [f"motion.json: actor {actor!r} phải được vẽ ở nhịp 1"]
    for k, b in enumerate(doc["beats"], 1):
        for a in b.get("acts", []):
            if a["thing"] == actor and (a["do"] == "hide" or a.get("vanish")):
                probs.append(f"motion.json nhịp {k}: actor {actor!r} không được hide hay vanish — nó đi suốt đoạn")
    return probs


def _order_problems(sc: Scene) -> list[str]:
    """Acts before their thing is drawn or after it is gone, and more than MAX_SEEN things in view at once."""
    drawn = {a.thing: a.t0 for a in sc.acts if a.do == "draw"}
    gone: dict[str, float] = {}
    for a in sc.acts:
        if a.do == "hide" or (a.do == "move" and a.vanish):
            gone[a.thing] = min(gone.get(a.thing, math.inf), a.t1)
    probs = []
    for a in sc.acts:
        if a.do in ("draw", "dim", "undim", "plain"):
            continue
        if a.t0 < drawn[a.thing] - 1e-9:
            probs.append(f"motion.json: {a.do} của {a.thing!r} bắt đầu trước khi nó được vẽ")
        elif a.t0 > gone.get(a.thing, math.inf) + 1e-9:
            probs.append(f"motion.json: {a.do} của {a.thing!r} bắt đầu sau khi nó đã bị xóa")
    by_id = {th["id"]: th for th in sc.things}
    for a in sc.acts:  # a path move starts where its path does: the mover must already be there
        if a.do == "move" and a.path:
            x, y = kit._position(by_id[a.thing], [b for b in sc.acts if b.t0 < a.t0], a.t0, by_id)
            if (gap := math.hypot(x - a.path[0][0], y - a.path[0][1])) > JUMP:
                probs.append(f"motion.json: {a.thing!r} nhảy {gap:.0f} px tới đầu path lúc {a.t0:.1f} s: cho nó tới đầu path "
                             "trước (move to), hoặc đừng bỏ nhịp đưa nó tới đó")
    counted = [th["id"] for th in sc.things
               if th["kind"] not in ("path", *MARKS) and (th["kind"] != "dot" or th.get("label"))]
    for t in sorted(drawn[i] for i in counted):
        seen = [i for i in counted if drawn[i] <= t + 1e-9 < gone.get(i, math.inf)]
        if len(seen) > MAX_SEEN:
            probs.append(f"motion.json: {len(seen)} thứ cùng hiện ({', '.join(seen)}), tối đa {MAX_SEEN}")
            break
    return probs


def _attach_loops(beats: list[dict]) -> list[str]:
    """Things carried, through attach, by something they themselves carry."""
    on: dict[str, set[str]] = {}
    for b in beats:
        for a in b.get("acts", []):
            if a["do"] == "attach":
                on.setdefault(a["thing"], set()).add(a["on"])

    def loop(path: list[str]) -> list[str] | None:
        for nxt in sorted(on.get(path[-1], ())):
            if nxt in path:
                return path[path.index(nxt):] + [nxt]
            if found := loop(path + [nxt]):
                return found
        return None

    for start in sorted(on):
        if found := loop([start]):
            return [f"motion.json: attach tạo vòng ({' → '.join(found)}): một thứ không mang được thứ đang mang nó"]
    return []


def brief_words(brief_md: str) -> set[str]:
    """The words of the brief: what a label may say before there is a Vietnamese script."""
    return set(_words(brief_md))


def design_problems(doc, said: set[str], run_dir: Path | None) -> list[str]:
    """Every problem of the canvas in motion.json, one line each; [] when it is safe to draw. `said`: the words a
    label may use besides COMMON."""
    if not isinstance(doc, dict):
        return ["motion.json phải là một object JSON (hoặc null khi không có hình động)"]
    if "scenes" in doc:
        return [OLD]
    probs = [f"motion.json: thiếu {key}: {why}" for key, why in
             (("note", "một dòng ghi vì sao có hình động này"), ("idea", "một câu: cả khung nói gì"))
             if not (isinstance(doc.get(key), str) and doc[key].strip())]
    beats, things = doc.get("beats"), doc.get("things")
    if not isinstance(beats, list) or not 1 <= len(beats) <= MAX_BEATS:
        return probs + [f"motion.json: beats phải là danh sách 1–{MAX_BEATS} nhịp"]
    if not isinstance(things, list) or not things:
        return probs + ["motion.json: things phải là danh sách, không rỗng"]
    by_id, meta = {}, _metaphor(run_dir)
    for th in things:
        probs += [f"motion.json: {p}" for p in _thing_problems(th, said, run_dir, meta)]
        if isinstance(th, dict) and isinstance(th.get("id"), str):
            if not (_int(th.get("beat")) and 1 <= th["beat"] <= len(beats)):
                probs.append(f"motion.json: thing {th['id']!r}: beat {th.get('beat')!r} phải là số nhịp 1–{len(beats)}")
            if th["id"] in by_id:
                probs.append(f"motion.json: thing {th['id']!r} trùng id")
            by_id[th["id"]] = th
    for k, b in enumerate(beats, 1):
        if not isinstance(b, dict):
            probs.append(f"motion.json nhịp {k}: phải là object")
            continue
        if not (isinstance(b.get("idea"), str) and b["idea"].strip()):
            probs.append(f"motion.json nhịp {k}: thiếu idea: một dòng nói bước cơ chế của nhịp")
        if not isinstance(b.get("acts", []), list):
            probs.append(f"motion.json nhịp {k}: acts phải là danh sách")
        v = b.get("view")
        if "view" in b and not (isinstance(v, list) and len(v) == 4 and all(map(_num, v)) and v[0] < v[2]
                                and v[1] < v[3] and _inside(v)):
            probs.append(f"motion.json nhịp {k}: view phải là [x0, y0, x1, y1] trong {AREA}")
    if probs:
        return probs
    hinged = {i for i, th in by_id.items() if th.get("kind") == "shape" and "hinge" in (shapes.find(th["shape"], run_dir) or {})}
    for k, b in enumerate(beats, 1):
        for m, a in enumerate(b.get("acts", []), 1):
            probs += [f"motion.json nhịp {k}: {p}" for p in _act_problems(m, a, by_id, said, hinged, meta)]
    if probs:
        return probs
    probs += _attach_loops(beats)
    probs += _actor_problems(doc, by_id)
    return probs or _order_problems(timed(doc, *estimated(doc), run_dir))


def estimated(doc: dict) -> tuple[list[float], float]:
    """Beat starts and the end of the canvas at BEAT_EST s a beat: a design's timing, before any voice."""
    n = len(doc["beats"])
    return [BEAT_EST * k for k in range(n)], BEAT_EST * n


def timed(doc: dict, starts: list[float | None], end: float, run_dir: Path | None) -> Scene:
    """The canvas on the video's clock: beat k+1 starts at starts[k] (None: dropped) and the canvas ends at `end`.

    A thing of a dropped beat is drawn at the start of the next kept beat (none left: not drawn, nor acted on); the
    acts of a dropped beat are left out. As each beat starts, things drawn earlier that it does not touch dim, things it
    touches again undim; the actor never dims.
    """
    kept = [k for k, s in enumerate(starts) if s is not None]
    span = {k: (starts[k], starts[kept[i + 1]] if i + 1 < len(kept) else end) for i, k in enumerate(kept)}

    def when(k: int, at: float, do: str, dur: float) -> tuple[float, float]:
        s, e = span[k]
        t0 = s + (e - s) * at
        return t0, math.inf if do == "pulse" else min(t0 + dur, max(e, t0 + MIN_ACT))

    things, acts, home = [], [], {}
    for th in doc["things"]:
        k = next((k for k in kept if k >= th["beat"] - 1), None)
        if k is None:
            continue
        at = th.get("at", 0) if k == th["beat"] - 1 else 0
        t0, t1 = when(k, at, "draw", kit.DRAW)
        if k == kept[0] and not at:
            t0 -= LEAD_IN
        if th["kind"] == "shape":
            doc_ = shapes.find(th["shape"], run_dir)
            th = th | {"strokes": shapes.strokes_in_box(doc_, th["box"])}
            if hinge := shapes.hinge_in_box(doc_, th["box"]):
                th["hinge"] = hinge
        things.append(th)
        acts.append(kit.Act("draw", th["id"], t0, t1))
        home[th["id"]] = k
    paths = {th["id"]: [tuple(p) for p in th["points"]] for th in things if th["kind"] == "path"}
    touched: dict[int, set[str]] = {k: {i for i, h in home.items() if h == k} for k in kept}
    for k in kept:
        for a in doc["beats"][k].get("acts", []):
            if a["thing"] not in home or ("path" in a and a["path"] not in paths):
                continue
            touched[k] |= {a["thing"], a.get("path")} - {None}
            acts.append(kit.Act(a["do"], a["thing"], *when(k, a.get("at", 0), a["do"], a.get("dur", DUR.get(a["do"], 0))),
                                to=tuple(a["to"]) if "to" in a else None, path=paths.get(a.get("path")),
                                say=a.get("say", ""), vanish=a.get("vanish", False), on=a.get("on", ""),
                                offset=tuple(a["offset"]) if "offset" in a else None))
    gone = {a.thing: a.t0 for a in sorted(acts, key=lambda a: -a.t0) if a.do == "hide" or a.vanish}
    dim: set[str] = set()
    for k in kept[1:]:
        s = span[k][0]
        for i, h in home.items():
            if i == doc.get("actor") or h >= k or gone.get(i, math.inf) <= s:
                continue
            if (i in touched[k]) == (i in dim):
                acts.append(kit.Act("undim" if i in dim else "dim", i, s, s + kit.TURN))
                dim ^= {i}
    for th in things:  # a means line goes plain as the next kept beat starts
        later = [k for k in kept if k > home[th["id"]]]
        if th.get("means") and later:
            s = span[later[0]][0]
            acts.append(kit.Act("plain", th["id"], s, s + kit.TURN))
    return Scene(list(doc.get("lines", [])), things, acts, _cams(doc, kept, span, touched, things, acts))


def _cams(doc: dict, kept: list[int], span: dict, touched: dict[int, set[str]], things: list[dict],
          acts: list[kit.Act]) -> list[tuple[float, float, float, float]]:
    """Camera keys: each kept beat framed on its `view`, or on all it draws, moves or acts on (a mover where the beat
    finds it and where it leaves it)."""
    if not kept:
        return []
    by_id = {th["id"]: th for th in things}
    boxes = []
    for k in kept:
        if "view" in doc["beats"][k]:
            boxes.append(tuple(doc["beats"][k]["view"]))
            continue
        s, e = span[k]
        got = []
        for i in touched[k] & by_id.keys():
            th = by_id[i]
            if th["kind"] in kit.MOVERS:
                got += [kit.bbox(kit.at_pos(th, kit._position(th, acts, t, by_id))) for t in (s, e)]
            else:
                got.append(kit.bbox(th))
        boxes.append((min(b[0] for b in got), min(b[1] for b in got), max(b[2] for b in got), max(b[3] for b in got))
                     if got else None)
    return camera.keys([span[k] for k in kept], boxes, LEAD_IN)


def design_sheet(doc: dict, run_dir: Path | None) -> Image.Image:
    """One row, a column per beat: the canvas as each beat ends, on the estimated timing — A to Z, left to right."""
    starts, end = estimated(doc)
    return _sheet(timed(doc, starts, end, run_dir), [*starts[1:], end])


def _sheet(sc: Scene, ends: list[float]) -> Image.Image:
    h = round(SHEET_W * kit.H / kit.W)
    img = Image.new("RGB", (44 + len(ends) * (SHEET_W + 4), h), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 28)
    for c, t in enumerate(ends):
        frame = kit.draw(sc.things, sc.acts, t - 0.01, sc.view(t - 0.01)).resize((SHEET_W, h), Image.LANCZOS)
        img.paste(frame, (44 + c * (SHEET_W + 4), 0))
        d.text((44 + c * (SHEET_W + 4) + 6, 6), str(c + 1), fill="black", font=font)
    return img


def estimate(script: list[dict]) -> list[Placement]:
    """The spoken lines back to back at SYL s per syllable: timing before the voice exists."""
    out, t = [], LEAD
    for i, phrases in _spoken(script).items():
        dur = max(syllables(phrases), 1) * SYL
        out.append(Placement(i, t, dur))
        t += dur + GAP
    return out


def _lines_problems(want, text: dict[int, str]) -> list[str]:
    """The animated lines: spoken, back to back, not the title, at most half of the video."""
    if not (isinstance(want, list) and want and all(_int(i) for i in want)):
        return ["motion.bind.json: lines phải là danh sách id câu, không rỗng"]
    if missing := [i for i in want if i not in text]:
        return [f"motion.bind.json: lines có câu {missing} không có lời trong script.vi.json"]
    spoken, probs = list(text), []
    k = spoken.index(want[0])
    if spoken[k:k + len(want)] != want:
        probs.append(f"motion.bind.json: lines {want} phải là các câu có lời liền nhau, đúng thứ tự")
    if spoken[0] in want:
        probs.append(f"motion.bind.json: lines không được có câu {spoken[0]} (câu tiêu đề)")
    # ponytail: syllables stand in for seconds; the timeline does not exist yet
    if 2 * sum(syllables(text[i]) for i in want) > sum(syllables(t) for t in text.values()):
        probs.append("motion.bind.json: đoạn hình động dài hơn nửa video (tính theo số âm tiết lời đọc)")
    return probs


def _cue_problems(k: int, cue, want: list[int], text: dict[int, str]) -> list[str]:
    what = f"motion.bind.json nhịp {k}"
    if not isinstance(cue, dict) or not _int(cue.get("line")):
        return [f"{what}: phải là {{\"line\": id, \"phrase\": n, \"at\": 0–1}} hoặc null (bỏ nhịp)"]
    line = cue["line"]
    if line not in want:
        return [f"{what}: line {line} không thuộc lines {want}"]
    probs, n = [], len(text[line].split("|"))
    phrase = cue.get("phrase", 1)
    if not _int(phrase) or not 1 <= phrase <= n:
        probs.append(f"{what}: phrase {phrase!r} ngoài 1–{n} (câu {line} có {n} cụm)")
    if not _num(cue.get("at", 0)) or not 0 <= cue.get("at", 0) <= 1:
        probs.append(f"{what}: at {cue.get('at')!r} phải là số 0–1")
    return probs


def _rebound(th, labels: dict, means: dict):
    """One thing with the bind's label and means; a means of "" is dropped."""
    if not (isinstance(th, dict) and isinstance(th.get("id"), str)):
        return th
    i = th["id"]
    if i in labels:
        th = th | {"label": labels[i]}
    if i in means:
        th = th | {"means": means[i]} if means[i] else {k: v for k, v in th.items() if k != "means"}
    return th


def bound(doc: dict, bind: dict) -> dict:
    """The canvas with the bind's labels, means and lines: what render, visuals and the checks of the voice use."""
    labels, means = bind.get("labels") or {}, bind.get("means") or {}
    labels = {i: v for i, v in labels.items() if isinstance(i, str)} if isinstance(labels, dict) else {}
    means = {i: v for i, v in means.items() if isinstance(i, str)} if isinstance(means, dict) else {}
    return doc | {"lines": list(bind["lines"]), "things": [_rebound(th, labels, means) for th in doc["things"]]}


def _starts(bind: dict, placements: list[Placement], script: list[dict]) -> tuple[list[float | None], float]:
    """Seconds of each beat's cue (None: dropped) and the end of the last animated line."""
    text, at = _spoken(script), {p.id: p for p in placements}

    def when(cue: dict) -> float:
        p = at[cue["line"]]
        f0, f1 = phrase_fracs(text[cue["line"]])[cue.get("phrase", 1) - 1]
        return p.start + p.dur * (f0 + (f1 - f0) * cue.get("at", 0))

    last = at[bind["lines"][-1]]
    return [None if c is None else when(c) for c in bind["beats"]], last.start + last.dur


def bind_problems(doc, bind, script: list[dict], run_dir: Path | None, visuals: list | None = None) -> list[str]:
    """Every problem of motion.bind.json against the canvas (assumed to pass design_problems) and the script."""
    if not isinstance(bind, dict):
        return ["motion.bind.json phải là một object JSON"]
    if not (isinstance(doc, dict) and "scenes" not in doc and isinstance(doc.get("beats"), list)
            and isinstance(doc.get("things"), list)):
        return design_problems(doc, set(), run_dir)  # no canvas to bind to: say what is wrong with it
    text = _spoken(script)
    probs = [] if isinstance(bind.get("note"), str) and bind["note"].strip() else [
        "motion.bind.json: thiếu note: một dòng ghi nhịp nào bỏ và vì sao"]
    want = bind.get("lines")
    if bad := _lines_problems(want, text):
        return probs + bad
    cues, n = bind.get("beats"), len(doc["beats"])
    if not isinstance(cues, list) or len(cues) != n:
        return [f"motion.bind.json: beats phải có {n} phần tử (một mốc mỗi nhịp, null để bỏ nhịp)"]
    for k, c in enumerate(cues, 1):
        if c is not None:
            probs += _cue_problems(k, c, want, text)
    labels = bind.get("labels", {})
    ids = {th["id"] for th in doc["things"] if isinstance(th, dict) and isinstance(th.get("id"), str) and "label" in th}
    if not isinstance(labels, dict) or not all(isinstance(i, str) and i in ids for i in labels):
        probs.append("motion.bind.json: labels phải là {\"<id thing có nhãn>\": \"<nhãn mới>\"}")
    means = bind.get("means", {})
    mids = {th["id"] for th in doc["things"] if isinstance(th, dict) and isinstance(th.get("id"), str) and "means" in th}
    if not isinstance(means, dict) or not all(isinstance(i, str) and i in mids and isinstance(v, str)
                                              for i, v in means.items()):
        probs.append("motion.bind.json: means phải là {\"<id thing có means>\": \"<chữ trong lời>\" hoặc \"\" (bỏ)}")
    if probs:
        return probs
    kept = [(k, c) for k, c in enumerate(cues, 1) if c is not None]
    if len(kept) < 2:
        return [f"motion.bind.json: chỉ còn {len(kept)} nhịp, cần ít nhất 2 (không thì dùng ảnh tĩnh)"]
    k, first = kept[0]
    if first["line"] != want[0] or first.get("phrase", 1) != 1 or first.get("at", 0):
        probs.append(f"motion.bind.json nhịp {k}: nhịp giữ lại đầu tiên phải mở đoạn: câu {want[0]}, cụm 1, at 0")
    order = [(want.index(c["line"]), c.get("phrase", 1), c.get("at", 0)) for _, c in kept]
    if order != sorted(order) or len(set(order)) < len(order):
        probs.append("motion.bind.json: mốc các nhịp giữ lại phải tăng dần theo lời đọc; bỏ (null) nhịp đọc lệch thứ tự")
    said = {w for i in want for w in _words(text[i])}
    doc = bound(doc, bind)
    probs += design_problems(doc, said, run_dir)  # the labels again, now against the words of the voice
    if not probs:
        probs += _order_problems(timed(doc, *_starts(bind, estimate(script), script), run_dir))
    if visuals is not None:
        probs += clashes(visuals, set(want))
    return probs


def bind_timed(doc: dict, bind: dict, placements: list[Placement], script: list[dict], run_dir: Path | None) -> Scene:
    """The canvas on the voice: each kept beat starts on its cue, the canvas ends with the last animated line."""
    return timed(bound(doc, bind), *_starts(bind, placements, script), run_dir)


def bind_sheet(doc: dict, bind: dict, script: list[dict], run_dir: Path | None) -> Image.Image:
    """As design_sheet, a column per kept beat, on the timing estimated from the script."""
    starts, end = _starts(bind, estimate(script), script)
    kept = [s for s in starts if s is not None]
    return _sheet(timed(bound(doc, bind), starts, end, run_dir), [*kept[1:], end])
