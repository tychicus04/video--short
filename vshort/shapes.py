"""The shape library: things the kit has no drawing for, kept as data — strokes in a 0–100 cell that the kit draws in
its own pencil, so a new shape matches the old ones. Add only: a shape in the library is never changed."""
import json
import re
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vshort import kit
from vshort.textfit import FONTS

LIBRARY = Path(__file__).resolve().parent.parent / "assets" / "shapes"
SLUG = re.compile(r"[a-z0-9-]+")
MAX_STROKES, MAX_POINTS = 12, 40  # simple enough to read small
CELL = 240  # px of one shape on the sheet


def _point(v) -> bool:
    return (isinstance(v, list) and len(v) == 2
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c <= 100 for c in v))


def problems(doc, slug: str) -> list[str]:
    """What is wrong with one shape file, one line each; [] when it is fine."""
    what = f"hình {slug!r}"
    if not SLUG.fullmatch(slug):
        return [f"{what}: tên file chỉ dùng a-z, 0-9 và '-' (ví dụ bo-nho.json)"]
    if not isinstance(doc, dict):
        return [f"{what}: phải là object {{\"name\": ..., \"strokes\": [...]}}"]
    probs = [] if isinstance(doc.get("name"), str) and doc["name"].strip() else [f"{what}: thiếu name (tên tiếng Việt)"]
    strokes = doc.get("strokes")
    if not isinstance(strokes, list) or not 1 <= len(strokes) <= MAX_STROKES:
        return probs + [f"{what}: strokes phải có 1–{MAX_STROKES} nét"]
    for n, s in enumerate(strokes, 1):
        if not isinstance(s, list) or not 2 <= len(s) <= MAX_POINTS:
            probs.append(f"{what}: nét {n} phải có 2–{MAX_POINTS} điểm")
        elif not all(map(_point, s)):
            probs.append(f"{what}: nét {n} có điểm ngoài ô 0–100 (mỗi điểm là [x, y])")
    if "hinge" in doc and not _hinge_ok(doc["hinge"], len(strokes)):
        probs.append(f"{what}: hinge phải là {{\"strokes\": [chỉ số nét, không trùng], \"pivot\": [x, y] trong ô 0–100}} "
                     "cùng đúng một trong \"turn\" (độ, −180…180, khác 0) hoặc \"squash\" (0,05…0,95)")
    return probs


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _hinge_ok(h, n: int) -> bool:
    """The strokes that open (turn about the pivot, or fold towards it) when the shape opens."""
    if not isinstance(h, dict) or ("turn" in h) == ("squash" in h):
        return False
    idx = h.get("strokes")
    if not (isinstance(idx, list) and idx and len(set(map(str, idx))) == len(idx)
            and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n for i in idx)):
        return False
    if "turn" in h:
        ok = _num(h["turn"]) and -180 <= h["turn"] <= 180 and h["turn"] != 0
    else:
        ok = _num(h["squash"]) and 0.05 <= h["squash"] <= 0.95
    return ok and _point(h.get("pivot"))


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def find(slug: str, run_dir: Path | None) -> dict | None:
    """The shape: the run's own copy first, then the library."""
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        return None
    for d in ([run_dir / "shapes"] if run_dir else []) + [LIBRARY]:
        if (d / f"{slug}.json").exists():
            return _read(d / f"{slug}.json")
    return None


def check_run(run_dir: Path) -> list[str]:
    """Every shape in RUN/shapes: its own rules, and none may change a library shape of the same name."""
    probs = []
    for f in sorted((run_dir / "shapes").glob("*.json")):
        doc = _read(f)
        if doc is None:
            probs.append(f"shapes/{f.name} không phải JSON hợp lệ")
            continue
        probs += problems(doc, f.stem)
        if (LIBRARY / f.name).exists() and _read(LIBRARY / f.name) != doc:
            probs.append(f"hình {f.stem!r} đã có trong thư viện với nét khác: đặt tên mới, không sửa hình đã có")
    return probs


def _fit(doc: dict, box) -> tuple[float, float, float]:
    """Scale and offset that put the strokes into box, aspect kept, centred: cell (x, y) → (ox + k x, oy + k y)."""
    xs = [p[0] for s in doc["strokes"] for p in s]
    ys = [p[1] for s in doc["strokes"] for p in s]
    x0, y0, x1, y1 = box
    k = min((x1 - x0) / max(max(xs) - min(xs), 1e-9), (y1 - y0) / max(max(ys) - min(ys), 1e-9))
    ox = x0 + ((x1 - x0) - k * (max(xs) - min(xs))) / 2 - k * min(xs)
    oy = y0 + ((y1 - y0) - k * (max(ys) - min(ys))) / 2 - k * min(ys)
    return k, ox, oy


def strokes_in_box(doc: dict, box) -> list[list[tuple[float, float]]]:
    """The strokes scaled into box, aspect kept, centred."""
    k, ox, oy = _fit(doc, box)
    return [[(ox + k * x, oy + k * y) for x, y in s] for s in doc["strokes"]]


def hinge_in_box(doc: dict, box) -> dict | None:
    """The shape's hinge with its pivot where strokes_in_box puts it; None when the shape has none."""
    h = doc.get("hinge")
    if h is None:
        return None
    k, ox, oy = _fit(doc, box)
    return {"strokes": list(h["strokes"]), "pivot": (ox + k * h["pivot"][0], oy + k * h["pivot"][1]),
            "turn": h.get("turn"), "squash": h.get("squash")}


def sheet(run_dir: Path) -> Image.Image:
    """The run's shapes side by side, each in a CELL px square with its name under it: drawn as the kit draws them."""
    docs = [(f.stem, _read(f)) for f in sorted((run_dir / "shapes").glob("*.json"))]
    docs = [(s, d) for s, d in docs if not problems(d, s)]
    h = CELL + 64
    img = Image.new("RGB", (max(1, len(docs)) * (CELL + 4), h), "white")
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 18)
    for n, (slug, doc) in enumerate(docs):
        cell = kit._paper().crop((0, 0, CELL * kit.SS, h * kit.SS))
        d = ImageDraw.Draw(cell)
        for k, pts in enumerate(strokes_in_box(doc, (20, 20, CELL - 20, CELL - 20))):
            kit._stroke(d, pts, 1.0, kit.INK, 3, zlib.crc32(slug.encode()) + k)
        cell = cell.reduce(kit.SS)
        for k, line in enumerate((slug, doc["name"])):  # two lines: a long name must not run into the next cell
            ImageDraw.Draw(cell).text((CELL / 2, CELL + 16 + 26 * k), line, fill="black", font=font, anchor="mm")
        img.paste(cell, (n * (CELL + 4), 0))
    return img
