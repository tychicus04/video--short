"""motion.json: the animated stretch of a video — checked, timed on the voice, previewed as a sheet."""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vshort import kit
from vshort.fit import GAP, LEAD, Placement, phrase_fracs
from vshort.script import syllables
from vshort.textfit import FONTS
from vshort.visuals import SAFE_TLDS, _int, _strip_marks

# syllables any label may use besides the narration's own words
COMMON = frozenset("điện thoại máy tính chủ dữ liệu hệ thống hacker kẻ tấn công nghe lén mạng trình duyệt người dùng nạn "
                   "nhân gói tin tệp mật khẩu nhắn ví tiền thư khóa đã bị chiếm lấy cắp trang web an toàn lõi lớp bảo vệ"
                   .split())
MAX_SCENES, MAX_SEEN = 4, 4
SYL = 0.2  # s per syllable: the voice before the timeline exists
MIN_ACT = 0.3  # shortest action, even at the very end of a line
ACTS = ("move", "bounce", "red", "pulse", "hide")
DUR = {"draw": kit.DRAW, "red": kit.TURN, "hide": kit.HIDE, "move": kit.MOVE, "bounce": kit.MOVE}
KINDS = kit.BOXED | kit.POINTED | {"path"}
AREA = f"vùng an toàn x {kit.SAFE[0]}–{kit.SAFE[2]}, y {kit.SAFE[1]}–{kit.SAFE[3]}"
SHEET_W = 240


@dataclass
class Scene:
    lines: list[int]
    things: list[dict]
    acts: list[kit.Act]


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


def _text_problems(what: str, text, said: set[str]) -> list[str]:
    if not isinstance(text, str) or not text.strip() or "\n" in text:
        return [f"{what} phải là một dòng chữ, không rỗng"]
    probs = []
    if len(text) > kit.MAX_LABEL:
        probs.append(f"{what} {text!r} dài {len(text)} ký tự (tối đa {kit.MAX_LABEL})")
    for w in _words(text):
        if not (w in said or w in COMMON or (len(w) == 1 and w.isalnum()) or ("." in w and w.endswith(SAFE_TLDS))):
            probs.append(f"{what} {text!r}: chữ {w!r} không có trong lời đọc của đoạn này hay danh sách danh từ thường")
    return probs


def _cue_problems(what: str, cue, scene_lines: list[int], text: dict[int, str]) -> list[str]:
    if not isinstance(cue, dict) or not _int(cue.get("line")):
        return [f"{what}: when phải là {{\"line\": id, \"phrase\": n, \"at\": 0–1}}"]
    line = cue["line"]
    if line not in scene_lines:
        return [f"{what}: when.line {line} không thuộc cảnh này (lines {scene_lines})"]
    probs, n = [], len(text[line].split("|"))
    phrase = cue.get("phrase", 1)
    if not _int(phrase) or not 1 <= phrase <= n:
        probs.append(f"{what}: when.phrase {phrase!r} ngoài 1–{n} (câu {line} có {n} cụm)")
    if not _num(cue.get("at", 0)) or not 0 <= cue.get("at", 0) <= 1:
        probs.append(f"{what}: when.at {cue.get('at')!r} phải là số 0–1")
    return probs


def _thing_problems(th, scene_lines: list[int], text: dict[int, str], said: set[str]) -> list[str]:
    if not isinstance(th, dict):
        return ["thing phải là object"]
    tid, kind = th.get("id"), th.get("kind")
    what = f"thing {tid!r}"
    if not isinstance(tid, str) or not tid:
        return ["thing thiếu id (chuỗi)"]
    if kind not in KINDS:
        return [f"{what}: kind {kind!r} không hợp lệ ({', '.join(sorted(KINDS))})"]
    probs = []
    if kind in kit.BOXED:
        box = th.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(map(_num, box)) and box[0] < box[2] and box[1] < box[3]):
            return [f"{what}: box phải là [x0, y0, x1, y1] với x0 < x1, y0 < y1"]
    elif kind == "path":
        pts = th.get("points")
        if not (isinstance(pts, list) and len(pts) >= 2 and all(map(_xy, pts))):
            return [f"{what}: points phải là danh sách từ 2 điểm [x, y]"]
        if th.get("label"):
            probs.append(f"{what}: path không có nhãn")
    else:
        if not _xy(th.get("xy")):
            return [f"{what}: xy phải là [x, y]"]
        if kind == "icon" and th.get("icon") not in kit.ICONS:
            return [f"{what}: icon {th.get('icon')!r} không hợp lệ ({', '.join(sorted(kit.ICONS))})"]
        if kind == "text" and not th.get("label"):
            return [f"{what}: text cần label"]
        if kind == "crack" and th.get("label"):
            probs.append(f"{what}: crack không có nhãn")
    if th.get("color", "ink") not in kit.COLORS:
        probs.append(f"{what}: color {th['color']!r} không hợp lệ ({', '.join(kit.COLORS)})")
    if "label" in th:
        found = _text_problems("nhãn", th["label"], said)
        probs += [f"{what}: {p}" for p in found]
        if not found and kind == "box" and kit.label_em(th) == 0:
            probs.append(f"{what}: nhãn {th['label']!r} không vừa hộp ở cỡ chữ nhỏ nhất {kit.MIN_LABEL_EM}")
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
    if "when" in th:
        probs += _cue_problems(what, th["when"], scene_lines, text)
    return probs


def _act_problems(m: int, a, things: dict[str, dict], scene_lines, text, said) -> list[str]:
    if not isinstance(a, dict):
        return [f"act {m}: phải là object"]
    do, tid = a.get("do"), a.get("thing")
    what = f"act {m} ({do})"
    if do not in ACTS:
        return [f"act {m}: do {do!r} không hợp lệ ({', '.join(ACTS)})"]
    if tid not in things:
        return [f"{what}: thing {tid!r} không có trong cảnh"]
    th, probs = things[tid], []
    if do in ("move", "bounce") and th["kind"] not in kit.MOVERS:
        probs.append(f"{what}: {tid!r} ({th['kind']}) không được di chuyển — chỉ dot và icon")
    if do == "pulse" and th["kind"] != "dot":
        probs.append(f"{what}: chỉ dot mới pulse")
    if "say" in a:
        probs += ([f"{what}: say chỉ dùng với red"] if do != "red" else
                  [f"{what}: {p}" for p in _text_problems("say", a["say"], said)])
    if "vanish" in a and (do != "move" or not isinstance(a["vanish"], bool)):
        probs.append(f"{what}: vanish chỉ dùng với move, true hoặc false")
    if "dur" in a and not (_num(a["dur"]) and 0 < a["dur"] <= 5):
        probs.append(f"{what}: dur phải là số giây trong (0, 5]")
    if do in ("move", "bounce"):
        has_to, has_path = "to" in a, "path" in a
        if do == "bounce" and (has_path or not has_to):
            probs.append(f"{what}: bounce cần to, không có path")
        elif has_to == has_path:
            probs.append(f"{what}: move cần đúng một trong to hoặc path")
        elif has_to and not _xy(a["to"]):
            probs.append(f"{what}: to phải là [x, y]")
        elif has_path and things.get(a["path"], {}).get("kind") != "path":
            probs.append(f"{what}: path {a['path']!r} không phải path trong cảnh")
        elif th["kind"] in kit.MOVERS:
            ends = [a["to"]] if has_to else things[a["path"]]["points"]
            if not all(_inside(kit.bbox({**th, "xy": p})) for p in ends):
                probs.append(f"{what}: {tid!r} đi ra ngoài {AREA}")
    return probs + _cue_problems(what, a.get("when"), scene_lines, text)


def _scene_problems(sc, text: dict[int, str], said: set[str]) -> list[str]:
    if not isinstance(sc, dict):
        return ["phải là object"]
    sl, things, acts = sc.get("lines"), sc.get("things"), sc.get("acts", [])
    if not (isinstance(sl, list) and sl and all(_int(i) and i in text for i in sl)):
        return [f"lines {sl!r} phải là danh sách id câu có lời, không rỗng"]
    probs = [] if isinstance(sc.get("idea"), str) and sc["idea"].strip() else ["thiếu idea: một dòng nói ý của cảnh"]
    if not isinstance(things, list) or not things:
        return probs + ["things phải là danh sách, không rỗng"]
    if not isinstance(acts, list):
        return probs + ["acts phải là danh sách"]
    by_id = {}
    for th in things:
        probs += _thing_problems(th, sl, text, said)
        if isinstance(th, dict) and isinstance(th.get("id"), str):
            if th["id"] in by_id:
                probs.append(f"thing {th['id']!r} trùng id")
            by_id[th["id"]] = th
    if probs:
        return probs
    for m, a in enumerate(acts, 1):
        probs += _act_problems(m, a, by_id, sl, text, said)
    return probs


def _order_problems(n: int, sc: Scene) -> list[str]:
    """Acts before their thing is drawn or after it is gone, and more than MAX_SEEN things in view at once."""
    drawn = {a.thing: a.t0 for a in sc.acts if a.do == "draw"}
    gone: dict[str, float] = {}
    for a in sc.acts:
        if a.do == "hide" or (a.do == "move" and a.vanish):
            gone[a.thing] = min(gone.get(a.thing, math.inf), a.t1)
    probs = []
    for a in sc.acts:
        if a.do != "draw" and a.t0 < drawn[a.thing] - 1e-9:
            probs.append(f"motion.json cảnh {n}: {a.do} của {a.thing!r} bắt đầu trước khi nó được vẽ")
        elif a.do != "draw" and a.t0 > gone.get(a.thing, math.inf) + 1e-9:
            probs.append(f"motion.json cảnh {n}: {a.do} của {a.thing!r} bắt đầu sau khi nó đã bị xóa")
    counted = [th["id"] for th in sc.things
               if th["kind"] not in ("path", "crack") and (th["kind"] != "dot" or th.get("label"))]
    for t in sorted(drawn[i] for i in counted):
        seen = [i for i in counted if drawn[i] <= t + 1e-9 < gone.get(i, math.inf)]
        if len(seen) > MAX_SEEN:
            probs.append(f"motion.json cảnh {n}: {len(seen)} thứ cùng hiện ({', '.join(seen)}), tối đa {MAX_SEEN}")
            break
    return probs


def validate(doc, script: list[dict], visuals: list | None = None) -> list[str]:
    """Every problem in motion.json, one line each; [] when it is safe to animate."""
    if not isinstance(doc, dict):
        return ["motion.json phải là một object JSON (hoặc null khi không có hình động)"]
    text = _spoken(script)
    spoken = list(text)
    probs = [] if isinstance(doc.get("note"), str) and doc["note"].strip() else [
        "motion.json: thiếu note: một dòng ghi vì sao chọn các câu này"]
    want = doc.get("lines")
    if not (isinstance(want, list) and want and all(_int(i) for i in want)):
        return probs + ["motion.json: lines phải là danh sách id câu, không rỗng"]
    if missing := [i for i in want if i not in text]:
        return probs + [f"motion.json: lines có câu {missing} không có lời trong script.vi.json"]
    k = spoken.index(want[0])
    if spoken[k:k + len(want)] != want:
        probs.append(f"motion.json: lines {want} phải là các câu có lời liền nhau, đúng thứ tự")
    if spoken[0] in want:
        probs.append(f"motion.json: lines không được có câu {spoken[0]} (câu tiêu đề)")
    # ponytail: syllables stand in for seconds; the timeline does not exist yet
    if 2 * sum(syllables(text[i]) for i in want) > sum(syllables(t) for t in text.values()):
        probs.append("motion.json: đoạn hình động dài hơn nửa video (tính theo số âm tiết lời đọc)")
    scenes = doc.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        return probs + [f"motion.json: scenes phải là danh sách 1–{MAX_SCENES} cảnh"]
    said = {w for i in want for w in _words(text[i])}
    for n, sc in enumerate(scenes, 1):
        probs += [f"motion.json cảnh {n}: {p}" for p in _scene_problems(sc, text, said)]
    split = [sc.get("lines") for sc in scenes if isinstance(sc, dict)]
    if [i for sl in split if isinstance(sl, list) for i in sl] != want:
        probs.append(f"motion.json: lines của các cảnh {split} phải chia đúng lines {want}, theo thứ tự")
    if not probs:
        for n, sc in enumerate(timed(doc, estimate(script), script), 1):
            probs += _order_problems(n, sc)
    if visuals is not None:
        probs += clashes(visuals, set(want))
    return probs


def estimate(script: list[dict]) -> list[Placement]:
    """The spoken lines back to back at SYL s per syllable: timing before the voice exists."""
    out, t = [], LEAD
    for i, phrases in _spoken(script).items():
        dur = max(syllables(phrases), 1) * SYL
        out.append(Placement(i, t, dur))
        t += dur + GAP
    return out


def timed(doc: dict, placements: list[Placement], script: list[dict]) -> list[Scene]:
    """Scenes with every cue resolved to seconds on the video: a draw act per thing, then the file's acts."""
    text, at = _spoken(script), {p.id: p for p in placements}

    def when(cue: dict) -> tuple[float, float]:
        p = at[cue["line"]]
        f0, f1 = phrase_fracs(text[cue["line"]])[cue.get("phrase", 1) - 1]
        return p.start + p.dur * (f0 + (f1 - f0) * cue.get("at", 0)), p.start + p.dur

    def act(do: str, cue: dict, dur: float) -> tuple[float, float]:
        t0, end = when(cue)
        return t0, math.inf if do == "pulse" else min(t0 + dur, max(end, t0 + MIN_ACT))

    out = []
    for sc in doc["scenes"]:
        acts = [kit.Act("draw", th["id"], *act("draw", th.get("when", {"line": sc["lines"][0]}), kit.DRAW))
                for th in sc["things"]]
        paths = {th["id"]: [tuple(p) for p in th["points"]] for th in sc["things"] if th["kind"] == "path"}
        for a in sc.get("acts", []):
            acts.append(kit.Act(a["do"], a["thing"], *act(a["do"], a["when"], a.get("dur", DUR.get(a["do"], 0))),
                                to=tuple(a["to"]) if "to" in a else None, path=paths.get(a.get("path")),
                                say=a.get("say", ""), vanish=a.get("vanish", False)))
        out.append(Scene(list(sc["lines"]), sc["things"], acts))
    return out


def sheet(doc: dict, script: list[dict]) -> Image.Image:
    """One row per scene: its frames at 25/50/75/100 % of the scene, on the estimated timing."""
    at = {p.id: p for p in estimate(script)}
    scenes = timed(doc, list(at.values()), script)
    h = round(SHEET_W * kit.H / kit.W)
    img = Image.new("RGB", (44 + 4 * (SHEET_W + 4), len(scenes) * (h + 4)), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 28)
    for r, sc in enumerate(scenes):
        a, last = at[sc.lines[0]].start, at[sc.lines[-1]]
        b = last.start + last.dur
        d.text((8, r * (h + 4) + 8), str(r + 1), fill="black", font=font)
        for c, q in enumerate((0.25, 0.5, 0.75, 1.0)):
            frame = kit.draw(sc.things, sc.acts, a + (b - a) * q).resize((SHEET_W, h), Image.LANCZOS)
            img.paste(frame, (44 + c * (SHEET_W + 4), r * (h + 4)))
    return img
