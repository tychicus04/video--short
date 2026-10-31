"""One fully drawn still per spoken line, picked from the clean video, plus the images an agent reads them from."""
from bisect import bisect_right
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vshort.media import iter_frames, probe
from vshort.textfit import FONTS

FPS = 10  # sampling rate for the search
AFTER, BEFORE = 0.25, 0.1  # around a cut the picture is still drawing in or already fading out
BLANK = 8  # gray std under this is bare paper
TIE = 0.99  # scores within 1 % of the best count as equal; the later frame wins (more of it is drawn)
GRID, LABEL = 40, 80
SHEET_COLS, SHEET_W = 5, 288  # sheet.png: 5 stills per row, 288 px wide each


def scene_of(t: float, cuts: list[float]) -> int:
    return bisect_right(cuts, t)


def _best(video: Path, a: float, b: float, cuts: list[float]) -> tuple[float, float]:
    """(score, time) of the most drawn frame in [a, b); (0, midpoint) when every sample is next to a cut."""
    scored = [(float(f.std()), t) for t, f in iter_frames(video, fps=FPS, start=a, end=b)
              if not any(c - BEFORE < t < c + AFTER for c in cuts)]
    if not scored:
        return 0.0, (a + b) / 2
    top = max(s for s, _ in scored)
    return top, max(t for s, t in scored if s >= top * TIE)


def pick_still(video: Path, a: float, b: float, cuts: list[float]) -> float:
    best = _best(video, a, b, cuts)
    if best[0] < BLANK:  # the line's window is paper or a fade-in: take the drawn part of the same scene
        k = scene_of((a + b) / 2, cuts)
        wide = _best(video, cuts[k - 1] if k else 0.0, cuts[k] if k < len(cuts) else probe(video).duration, cuts)
        if wide[0] > best[0]:
            best = wide
    return best[1]


def _label(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont) -> None:
    d.rectangle(d.textbbox(xy, text, font=font), fill=(255, 255, 255))
    d.text(xy, text, fill=(200, 0, 90), font=font)


def grid_image(img: Image.Image) -> Image.Image:
    """The still under a light grid every 40 px, with coordinates every 80 px, to read patch boxes off."""
    out = img.convert("RGBA")
    over = Image.new("RGBA", out.size)
    d = ImageDraw.Draw(over)
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 14)
    for v in range(0, max(out.size), GRID):
        a = 130 if v % LABEL == 0 else 60
        d.line([(v, 0), (v, out.height)], fill=(255, 0, 110, a))
        d.line([(0, v), (out.width, v)], fill=(255, 0, 110, a))
    out = Image.alpha_composite(out, over)
    d = ImageDraw.Draw(out)
    for v in range(LABEL, max(out.size), LABEL):
        if v < out.width:
            _label(d, (v + 2, 2), str(v), font)
        if v < out.height:
            _label(d, (2, v + 2), str(v), font)
    return out.convert("RGB")


def contact_sheet(stills: list[tuple[int, Image.Image]]) -> Image.Image:
    h = round(SHEET_W * stills[0][1].height / stills[0][1].width)
    rows = -(-len(stills) // SHEET_COLS)
    sheet = Image.new("RGB", (SHEET_COLS * SHEET_W, rows * h), "white")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 28)
    for n, (i, img) in enumerate(stills):
        x, y = n % SHEET_COLS * SHEET_W, n // SHEET_COLS * h
        sheet.paste(img.resize((SHEET_W - 2, h - 2)), (x + 1, y + 1))
        _label(d, (x + 6, y + 4), str(i), font)
    return sheet
