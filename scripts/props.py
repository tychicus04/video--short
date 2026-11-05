"""The everyday props kit: each prop built from plain strokes (lines, boxes, circles, arcs) in the 0–100 cell of the
shape library, so curves come out smooth. Writes assets/shapes/<slug>.json (never over a file already there) and
assets/shapes/props-sheet.png (every prop, then the hinged ones open) for Tai to approve.

    uv run python scripts/props.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vshort import kit, shapes  # noqa: E402


def line(*pts):
    return [[x, y] for x, y in zip(pts[::2], pts[1::2])]


def rect(x0, y0, x1, y1):
    return line(x0, y0, x1, y0, x1, y1, x0, y1, x0, y0)


def arc(cx, cy, r, a0, a1, n=16):
    return [[cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))]
            for k in range(n + 1)]


def circle(cx, cy, r, n=24):
    return arc(cx, cy, r, 0, 360, n)


def rrect(x0, y0, x1, y1, r):
    pts = arc(x1 - r, y0 + r, r, -90, 0, 5) + arc(x1 - r, y1 - r, r, 0, 90, 5) + arc(x0 + r, y1 - r, r, 90, 180, 5)
    pts += arc(x0 + r, y0 + r, r, 180, 270, 5)
    return pts + [pts[0]]


PROPS = {
    "the-nhan-vien": ("thẻ nhân viên", [
        rrect(0, 14, 100, 82, 8), rect(8, 28, 36, 70), circle(22, 42, 6, 16), arc(22, 62, 10, 180, 360, 8),
        line(46, 38, 90, 38), line(46, 52, 90, 52), line(46, 66, 76, 66), line(40, 20, 60, 20)], None),
    "may-quet": ("máy quét", [
        rrect(20, 0, 80, 44, 6), rect(28, 8, 60, 24), circle(70, 14, 4, 12), rrect(32, 30, 68, 37, 3),
        line(50, 44, 50, 96), line(34, 96, 66, 96)], None),
    "bang-ten": ("bảng tên", [
        rect(0, 0, 100, 70), rect(8, 12, 24, 24), line(30, 18, 70, 18), rect(8, 30, 24, 42), line(30, 36, 70, 36),
        rect(8, 48, 24, 60), line(30, 54, 62, 54)], None),
    "barie": ("barie", [
        rect(0, 30, 10, 100), rect(5, 36, 100, 44), line(30, 36, 36, 44), line(55, 36, 61, 44), line(80, 36, 86, 44),
        line(0, 100, 14, 100)], {"strokes": [1, 2, 3, 4], "pivot": [5, 40], "turn": -78}),
    "cua": ("cửa", [rect(0, 0, 60, 100), rect(6, 6, 54, 100), circle(46, 55, 3, 12)],
            {"strokes": [1, 2], "pivot": [6, 50], "squash": 0.2}),
    "toa-nha": ("tòa nhà", [line(0, 18, 50, 0, 100, 18), rect(4, 18, 96, 64), rect(44, 42, 56, 64)], None),
    # no door: room for floors (boxes) inside, e.g. "máy ảo" over "máy chủ host" (reviewer 03/11: the door cut a label)
    "toa-nha-tang": ("tòa nhà nhiều tầng", [line(0, 16, 50, 0, 100, 16), rect(4, 16, 96, 72)], None),
    "phong": ("phòng", [rect(0, 0, 100, 56), rect(10, 12, 38, 56), rect(52, 12, 88, 32)], None),
    "chot-bao-ve": ("chốt bảo vệ", [line(0, 18, 50, 0, 100, 18), rect(8, 18, 92, 100), rect(20, 30, 80, 62)], None),
    "ket-sat": ("két sắt", [
        rrect(0, 0, 100, 90, 6), rect(10, 10, 90, 80), circle(50, 45, 14, 20), line(50, 31, 50, 38), line(72, 39, 72, 51),
        line(10, 90, 18, 98), line(82, 90, 90, 98)], {"strokes": [1, 2, 3, 4], "pivot": [10, 45], "squash": 0.15}),
    "hom-thu": ("hòm thư", [
        line(20, 58, 20, 30) + arc(50, 30, 30, 180, 360, 12)[1:] + line(80, 30, 80, 58, 20, 58),
        line(30, 58, 30, 34) + arc(50, 34, 20, 180, 360, 10)[1:] + line(70, 34, 70, 58), line(80, 40, 92, 40, 92, 24, 84, 24),
        line(50, 58, 50, 100), line(38, 100, 62, 100)], None),
    "kien-hang": ("kiện hàng", [
        rect(0, 30, 70, 100), line(0, 30, 30, 0, 100, 0, 70, 30), line(70, 100, 100, 70, 100, 0), line(30, 30, 60, 0)],
        None),
    "xe-giao-hang": ("xe giao hàng", [
        rect(0, 0, 62, 40), line(62, 10, 84, 10, 100, 26, 100, 40, 62, 40), line(66, 14, 82, 14, 94, 26, 66, 26, 66, 14),
        circle(20, 44, 8, 16), circle(80, 44, 8, 16)], None),
    "camera-an-ninh": ("camera an ninh", [
        line(20, 20, 80, 30, 80, 50, 20, 40, 20, 20), line(80, 30, 90, 32, 90, 48, 80, 50), line(40, 43, 40, 70),
        line(28, 70, 52, 70)], None),
    "hang-rao": ("hàng rào", [line(x, 0, x, 40) for x in (2, 26, 50, 74, 98)] + [line(0, 12, 100, 12), line(0, 30, 100, 30)],
                 None),
    "cau-thang": ("cầu thang", [
        line(0, 100, 0, 80, 20, 80, 20, 60, 40, 60, 40, 40, 60, 40, 60, 20, 80, 20, 80, 0, 100, 0), line(0, 100, 100, 100),
        line(100, 0, 100, 100)], None),
}


def doc(slug: str) -> dict:
    name, strokes, hinge = PROPS[slug]
    out = {"name": name, "strokes": [[[round(x, 1), round(y, 1)] for x, y in s] for s in strokes]}
    return out | ({"hinge": hinge} if hinge else {})


def opened_row(docs: dict[str, dict]) -> Image.Image:
    """The hinged props drawn by the kit, fully open."""
    hinged = [s for s, d in docs.items() if "hinge" in d]
    row = Image.new("RGB", (len(hinged) * (shapes.CELL + 4), shapes.CELL), "white")
    for n, slug in enumerate(hinged):
        box = (20, 20, shapes.CELL - 20, shapes.CELL - 20)
        th = {"id": slug, "kind": "shape", "box": list(box), "strokes": shapes.strokes_in_box(docs[slug], box),
              "hinge": shapes.hinge_in_box(docs[slug], box)}
        frame = kit.draw([th], [kit.Act("draw", slug, 0, 0.8), kit.Act("open", slug, 1, 1.8)], 3.0)
        row.paste(frame.crop((0, 0, shapes.CELL, shapes.CELL)), (n * (shapes.CELL + 4), 0))
    return row


def main() -> int:
    docs = {slug: doc(slug) for slug in PROPS}
    bad = [p for slug, d in docs.items() for p in shapes.problems(d, slug)]
    changed = [s for s, d in docs.items() if (f := shapes.LIBRARY / f"{s}.json").exists() and json.loads(f.read_text()) != d]
    if bad or changed:  # the library only grows: a prop drawn differently gets a new name
        print("\n".join(bad + [f"{s}.json đã có trong thư viện với nét khác: đặt tên mới, không sửa" for s in changed]))
        return 1
    for slug, d in docs.items():
        if not (shapes.LIBRARY / f"{slug}.json").exists():
            (shapes.LIBRARY / f"{slug}.json").write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "shapes").mkdir()
        for slug, d in docs.items():
            (Path(tmp) / "shapes" / f"{slug}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        top = shapes.sheet(Path(tmp))
    bottom = opened_row(docs)
    sheet = Image.new("RGB", (top.width, top.height + bottom.height + 8), "white")
    sheet.paste(top, (0, 0))
    sheet.paste(bottom, (0, top.height + 8))
    sheet.save(shapes.LIBRARY / "props-sheet.png")
    print(f"{len(docs)} đạo cụ; tờ xem trước: {shapes.LIBRARY / 'props-sheet.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
