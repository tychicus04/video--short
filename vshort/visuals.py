"""Turn stills into frames: patch wrong on-screen text, redraw references as SVG or pencil-filtered photos."""
import io
import re
import unicodedata
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
MIN_CONTRAST = 40  # colour distance from the fill that counts as old ink
MIN_SPAN, MIN_BAND, MIN_EM = 6, 4, 8  # old ink thinner than this is a rule or speck, not text; smallest font drawn
SLOT = (640, 920)  # photos fit inside this, centred at (360, 520); the credit goes 14 px under the photo (<= y 1030)
CREDIT_EM, MIN_CREDIT_EM, CREDIT_W = 26, 14, 680
SAFE_TLDS = (".example", ".test", ".invalid")  # reserved, never a real site
REAL_TLDS = {"com", "net", "org", "io", "co", "vn", "gov", "edu", "info", "app", "dev", "site", "xyz", "me", "ai"}
LUMA = np.array([0.299, 0.587, 0.114])


@lru_cache
def _font(name: str, em: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), em)


def _sans(bold: bool, em: int) -> ImageFont.FreeTypeFont:
    return _font("BeVietnamPro-Bold.ttf" if bold else "BeVietnamPro-Regular.ttf", em)


def _fit_em(text: str, bold: bool, w: int, h: float) -> int:
    """Largest size whose ink is at most `h` high and 8 px narrower than `w`; 0 if none."""
    l, t, r, b = _sans(bold, 100).getbbox(text)
    em = int(min((w - 8) / max(r - l, 1), h / max(b - t, 1)) * 100) + 1
    while em > 0:
        l, t, r, b = _sans(bold, em).getbbox(text)
        if r - l <= w - 8 and b - t <= h:
            break
        em -= 1
    return em


def _band(mask: np.ndarray) -> tuple[int, float]:
    """Height and centre row of the x-height band: the rows holding at least half the ink of the busiest row."""
    n = mask.sum(1)
    rows = np.flatnonzero(n >= 0.5 * n.max())
    return rows[-1] - rows[0] + 1, (rows[0] + rows[-1] + 1) / 2


def _drawn(text: str, bold: bool, em: int) -> np.ndarray:
    font = _sans(bold, em)
    l, t, r, b = font.getbbox(text)
    im = Image.new("L", (r + 4, b + 4))
    ImageDraw.Draw(im).text((0, 0), text, fill=255, font=font)
    return np.asarray(im) > 0.45 * 255


def _match_em(text: str, bold: bool, w: int, h: int, band: int) -> int:
    """Size whose x-height band is `band` px tall, but small enough for all the ink (marks, descenders) to fit."""
    cap = _fit_em(text, bold, w, h - 2)
    est = round(band * 100 / _band(_drawn(text, bold, 100))[0])
    sizes = {max(min(e, cap), MIN_EM) for e in range(est - 4, est + 5)}
    return min(sizes, key=lambda em: (abs(_band(_drawn(text, bold, em))[0] - band), -em))


def patch_text(img: Image.Image, box: tuple[int, int, int, int], text: str, bold: bool = False) -> Image.Image:
    """Cover the box with the colour of its edge and write `text` with the old text's x-height, baseline and ink."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    crop = np.asarray(img.convert("RGB").crop(box)).astype(float)
    ring = np.ones(crop.shape[:2], bool)
    ring[2:-2, 2:-2] = False
    fill = np.median(crop[ring], axis=0)
    dist = np.linalg.norm(crop - fill, axis=2)
    top = dist.max()
    mask = dist > max(MIN_CONTRAST, 0.45 * top)
    rows = np.flatnonzero(mask.any(1))
    span = rows[-1] - rows[0] + 1 if len(rows) else 0
    band, mid = _band(mask) if span else (0, 0)
    old = span >= MIN_SPAN and band >= MIN_BAND
    if old:
        ink = np.median(crop[dist >= 0.8 * top], axis=0)  # the strongest strokes, anti-aliasing left out
        em = _match_em(text, bold, w, h, band)
    else:  # nothing to copy from (blank box, a hairline): plain text at 60 % of the box height
        ink = (60,) * 3 if fill @ LUMA > 128 else (235,) * 3
        em = max(_fit_em(text, bold, w, 0.6 * h), MIN_EM)
    font = _sans(bold, em)
    l, t, r, b = font.getbbox(text)
    y = mid - _band(_drawn(text, bold, em))[1] if old else h / 2 - (t + b) / 2
    y = min(max(y, 1 - t), h - 1 - b)  # marks and descenders stay inside the box, 1 px from its edge
    patch = Image.new("RGB", (w, h), tuple(int(c) for c in fill))
    ImageDraw.Draw(patch).text(((w - l - r) / 2, y), text, fill=tuple(int(c) for c in ink), font=font)
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
    while em > MIN_CREDIT_EM and _font("PatrickHand-Regular.ttf", em).getlength(credit) > CREDIT_W:
        em -= 1
    d.text((W / 2, y + flat.height + 14), credit, fill=(74, 74, 74), font=_font("PatrickHand-Regular.ttf", em),
           anchor="mt")
    return canvas


def svg_frame(path: Path) -> Image.Image:
    png = cairosvg.svg2png(url=str(path), output_width=W, output_height=H)
    art = Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", art.size, PAPER + (255,)), art).convert("RGB")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _hits(box, area) -> bool:
    return box[0] < area[2] and box[2] > area[0] and box[1] < area[3] and box[3] > area[1]


def _strip_marks(word: str) -> str:
    """Drop punctuation and symbols (any script: quotes, ellipsis, brackets) from both ends of a word."""
    i, j = 0, len(word)
    while i < j and unicodedata.category(word[i])[0] in "PS":
        i += 1
    while j > i and unicodedata.category(word[j - 1])[0] in "PS":
        j -= 1
    return word[i:j]


def _real_domain(text: str) -> str:
    """The first word of `text` that is a web address on a common real TLD ('' when there is none)."""
    for word in re.split(r"[\s/:@?#]+", text):  # also cuts 'Link:apple.com', 'user@apple.com' and URLs apart
        word = _strip_marks(word)
        if "." in word and word.rsplit(".", 1)[1].lower() in REAL_TLDS:
            return word
    return ""


def _patch_problems(it: dict, ids: set[int]) -> list[str]:
    probs, pids, box, text = [], it.get("ids"), it.get("box"), it.get("text")
    bold = it.get("bold", False)
    if not isinstance(pids, list) or not pids or not all(_int(i) for i in pids):
        probs.append("ids phải là danh sách số nguyên, không rỗng")
    elif missing := [i for i in pids if i not in ids]:
        probs.append(f"id {missing} không có trong stills.json")
    if not isinstance(bold, bool):
        probs.append(f"bold phải là true hoặc false: {bold!r}")
    text_ok = isinstance(text, str) and bool(text.strip()) and "\n" not in text
    if not text_ok:
        probs.append("text phải là một dòng chữ, không rỗng")
    elif host := _real_domain(text):
        probs.append(f"text {text!r} có địa chỉ web thật ({host}); dùng tên chung kết thúc bằng {', '.join(SAFE_TLDS)}")
    box_ok = isinstance(box, list) and len(box) == 4 and all(_int(v) for v in box)
    if not box_ok:
        probs.append(f"box {box} phải là [x0, y0, x1, y1] số nguyên")
    elif not (0 <= box[0] < box[2] <= W and 0 <= box[1] < box[3] <= H):
        box_ok = False
        probs.append(f"box {box} vượt khung {W}x{H} hoặc ngược chiều (cần 0 ≤ x0 < x1 ≤ {W}, 0 ≤ y0 < y1 ≤ {H})")
    else:
        if _hits(box, SUBTITLE):
            probs.append(f"box {box} chạm vùng phụ đề (y {SUBTITLE[1]}–{SUBTITLE[3]})")
        if _hits(box, WATERMARK):
            probs.append(f"box {box} chạm góc watermark (x {WATERMARK[0]}–{WATERMARK[2]}, "
                         f"y {WATERMARK[1]}–{WATERMARK[3]})")
    if text_ok and box_ok and _fit_em(text, bold is True, box[2] - box[0], box[3] - box[1]) < MIN_PATCH_EM:
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
    if it["kind"] == "photo":
        credit = it.get("credit")
        if not isinstance(credit, str) or not credit.strip() or "\n" in credit:
            probs.append("photo thiếu credit: một dòng nguồn, vẽ dưới ảnh")
        elif _font("PatrickHand-Regular.ttf", MIN_CREDIT_EM).getlength(credit) > CREDIT_W:
            probs.append(f"credit {credit!r} quá dài: không vừa {CREDIT_W} px ở cỡ chữ nhỏ nhất")
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
