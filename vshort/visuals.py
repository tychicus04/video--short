"""Turn stills into frames: patch wrong on-screen text, redraw references as SVG or pencil-filtered photos."""
import io
from datetime import date
from functools import lru_cache
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from vshort.textfit import FONTS

PAPER = (238, 234, 226)
W, H = 720, 1280
SUBTITLE = (0, 1094, W, 1206)  # patched text must stay readable: out of the subtitle band and the watermark corner
WATERMARK = (524, 1232, 704, 1264)
MIN_PATCH_EM = 14
SLOT = (640, 920)  # photos fit inside this, centred at (360, 520)
CREDIT_Y, CREDIT_EM, CREDIT_W = 996, 26, 680  # below the slot (ends y 980), above the subtitle band
LUMA = np.array([0.299, 0.587, 0.114])


@lru_cache
def _font(name: str, em: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), em)


def _fit_em(text: str, w: int, h: int) -> int:
    """Largest Be Vietnam Pro Bold size with ink <= 60 % of the box high and 8 px narrower than it; 0 if none."""
    for em in range(h, 0, -1):
        l, t, r, b = _font("BeVietnamPro-Bold.ttf", em).getbbox(text)
        if r - l <= w - 8 and b - t <= 0.6 * h:
            return em
    return 0


def patch_text(img: Image.Image, box: tuple[int, int, int, int], text: str) -> Image.Image:
    """Cover the box with the colour of its edge and write `text` in the ink colour of what was there."""
    x0, y0, x1, y1 = box
    crop = np.asarray(img.convert("RGB").crop(box)).astype(float)
    ring = np.ones(crop.shape[:2], bool)
    ring[2:-2, 2:-2] = False
    fill = np.median(crop[ring], axis=0)
    pix = crop.reshape(-1, 3)[np.argsort(crop.reshape(-1, 3) @ LUMA)]
    k = max(1, len(pix) // 20)  # darkest 5 %; the lightest 5 % when the old text was light on a dark fill
    dark, light = np.median(pix[:k], axis=0), np.median(pix[-k:], axis=0)
    ink = max((dark, light), key=lambda c: abs(c @ LUMA - fill @ LUMA))
    w, h = x1 - x0, y1 - y0
    patch = Image.new("RGB", (w, h), tuple(int(c) for c in fill))
    font = _font("BeVietnamPro-Bold.ttf", _fit_em(text, w, h))
    l, t, r, b = font.getbbox(text)
    ImageDraw.Draw(patch).text(((w - l - r) / 2, (h - t - b) / 2), text, fill=tuple(int(c) for c in ink), font=font)
    out = img.convert("RGB")
    out.paste(patch, (x0, y0))
    return out


def pencil(photo: Image.Image, credit: str) -> Image.Image:
    """Photo as a pencil sketch (gray, inverted blur, colour dodge) on paper with a thin frame and a credit line."""
    flat = Image.alpha_composite(Image.new("RGBA", photo.size, "white"), photo.convert("RGBA")).convert("L")
    flat = ImageOps.contain(flat, SLOT, Image.LANCZOS)
    g = np.asarray(flat).astype(float)
    blur = np.asarray(ImageOps.invert(flat).filter(ImageFilter.GaussianBlur(10))).astype(float)
    sketch = np.clip(g * 255 / np.maximum(255 - blur, 1), 0, 255)
    rgb = (sketch[..., None] * np.array(PAPER) / 255).astype(np.uint8)  # white becomes paper
    canvas = Image.new("RGB", (W, H), PAPER)
    x, y = 360 - flat.width // 2, 520 - flat.height // 2
    canvas.paste(Image.fromarray(rgb), (x, y))
    d = ImageDraw.Draw(canvas)
    d.rectangle((x - 3, y - 3, x + flat.width + 2, y + flat.height + 2), outline=(140, 140, 140), width=2)
    em = CREDIT_EM
    while em > 8 and _font("PatrickHand-Regular.ttf", em).getlength(credit) > CREDIT_W:
        em -= 1
    d.text((W / 2, CREDIT_Y), credit, fill=(74, 74, 74), font=_font("PatrickHand-Regular.ttf", em), anchor="mt")
    return canvas


def svg_frame(path: Path) -> Image.Image:
    png = cairosvg.svg2png(url=str(path), output_width=W, output_height=H)
    art = Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", art.size, PAPER + (255,)), art).convert("RGB")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _hits(box, area) -> bool:
    return box[0] < area[2] and box[2] > area[0] and box[1] < area[3] and box[3] > area[1]


def _patch_problems(it: dict, ids: set[int]) -> list[str]:
    probs, pids, box, text = [], it.get("ids"), it.get("box"), it.get("text")
    if not isinstance(pids, list) or not pids or not all(_int(i) for i in pids):
        probs.append("ids phải là danh sách số nguyên, không rỗng")
    elif missing := [i for i in pids if i not in ids]:
        probs.append(f"id {missing} không có trong stills.json")
    if not isinstance(text, str) or not text.strip() or "\n" in text:
        return probs + ["text phải là một dòng chữ, không rỗng"]
    if not isinstance(box, list) or len(box) != 4 or not all(_int(v) for v in box):
        return probs + [f"box {box} phải là [x0, y0, x1, y1] số nguyên"]
    if not (0 <= box[0] < box[2] <= W and 0 <= box[1] < box[3] <= H):
        return probs + [f"box {box} vượt khung {W}x{H} hoặc ngược chiều (cần 0 ≤ x0 < x1 ≤ {W}, 0 ≤ y0 < y1 ≤ {H})"]
    if _hits(box, SUBTITLE):
        probs.append(f"box {box} chạm vùng phụ đề (y {SUBTITLE[1]}–{SUBTITLE[3]})")
    if _hits(box, WATERMARK):
        probs.append(f"box {box} chạm góc watermark (x {WATERMARK[0]}–{WATERMARK[2]}, y {WATERMARK[1]}–{WATERMARK[3]})")
    if _fit_em(text, box[2] - box[0], box[3] - box[1]) < MIN_PATCH_EM:
        probs.append(f"text {text!r} không vừa box {box} (cần chữ cao ít nhất {MIN_PATCH_EM} px)")
    return probs


def _reference_problems(it: dict, ids: set[int], run_dir: Path) -> list[str]:
    probs, i, file = [], it.get("id"), it.get("file")
    if not _int(i) or i not in ids:
        probs.append(f"id {i} không có trong stills.json")
    if not isinstance(file, str) or not file:
        probs.append("thiếu file")
    else:
        try:
            path, root = (run_dir / file).resolve(), (run_dir / "visuals").resolve()
            if root not in path.parents:
                probs.append(f"file {file} phải nằm trong visuals/")
            elif not path.is_file():
                probs.append(f"không thấy file {file}")
        except (OSError, ValueError):  # e.g. a NUL byte in the name
            probs.append(f"file {file!r} không hợp lệ")
    src = it.get("source")
    if not isinstance(src, str) or not src.startswith(("http://", "https://")):
        probs.append(f"thiếu source (URL http/https của nguồn): {src!r}")
    try:
        date.fromisoformat(it.get("accessed"))
    except (TypeError, ValueError):
        probs.append(f"accessed phải là ngày YYYY-MM-DD: {it.get('accessed')!r}")
    if it["kind"] == "photo" and not (isinstance(it.get("credit"), str) and it["credit"].strip()):
        probs.append("photo thiếu credit (dòng nguồn vẽ dưới ảnh)")
    return probs


def validate(items: list[dict], ids: set[int], run_dir: Path) -> list[str]:
    """Every problem in visuals.json, one line each; [] when it is safe to build frames."""
    probs, refs = [], {}
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict):
            probs.append(f"mục {n}: phải là object JSON")
            continue
        kind = it.get("kind")
        if kind == "patch":
            found = _patch_problems(it, ids)
        elif kind in ("svg", "photo"):
            found = _reference_problems(it, ids, run_dir)
            if _int(it.get("id")):
                if it["id"] in refs:
                    found.append(f"id {it['id']} đã có hình ở mục {refs[it['id']]}")
                refs.setdefault(it["id"], n)
        else:
            found = [f"kind {kind!r} không hợp lệ (patch, svg hoặc photo)"]
        probs += [f"visuals.json mục {n} ({kind}): {p}" for p in found]
    return probs
