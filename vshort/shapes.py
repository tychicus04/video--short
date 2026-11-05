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
    return probs


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


def strokes_in_box(doc: dict, box) -> list[list[tuple[float, float]]]:
    """The strokes scaled into box, aspect kept, centred."""
    xs = [p[0] for s in doc["strokes"] for p in s]
    ys = [p[1] for s in doc["strokes"] for p in s]
    x0, y0, x1, y1 = box
    k = min((x1 - x0) / max(max(xs) - min(xs), 1e-9), (y1 - y0) / max(max(ys) - min(ys), 1e-9))
    ox = x0 + ((x1 - x0) - k * (max(xs) - min(xs))) / 2 - k * min(xs)
    oy = y0 + ((y1 - y0) - k * (max(ys) - min(ys))) / 2 - k * min(ys)
    return [[(ox + k * x, oy + k * y) for x, y in s] for s in doc["strokes"]]


SHEET_COLS = 6  # the library sheet wraps here: 25 shapes in one row would be too small to read


def sheet(run_dir: Path, library: bool = False) -> Image.Image:
    """The run's shapes side by side, each in a CELL px square with its name under it: drawn as the kit draws them.
    `library`: the library's too, in rows of SHEET_COLS; where a name is in both, the run's."""
    files = {f.stem: f for f in sorted((run_dir / "shapes").glob("*.json"))}
    if library:
        files = {f.stem: f for f in LIBRARY.glob("*.json")} | files
    docs = [(s, _read(files[s])) for s in sorted(files)]
    docs = [(s, d) for s, d in docs if not problems(d, s)]
    cols = max(1, min(len(docs), SHEET_COLS) if library else len(docs))
    h = CELL + 64
    img = Image.new("RGB", (cols * (CELL + 4), max(1, -(-len(docs) // cols)) * h), "white")
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 18)
    for n, (slug, doc) in enumerate(docs):
        cell = kit._paper().crop((0, 0, CELL * kit.SS, h * kit.SS))
        d = ImageDraw.Draw(cell)
        for k, pts in enumerate(strokes_in_box(doc, (20, 20, CELL - 20, CELL - 20))):
            kit._stroke(d, pts, 1.0, kit.INK, 3, zlib.crc32(slug.encode()) + k)
        cell = cell.reduce(kit.SS)
        for k, line in enumerate((slug, doc["name"])):  # two lines: a long name must not run into the next cell
            ImageDraw.Draw(cell).text((CELL / 2, CELL + 16 + 26 * k), line, fill="black", font=font, anchor="mm")
        img.paste(cell, (n % cols * (CELL + 4), n // cols * h))
    return img
