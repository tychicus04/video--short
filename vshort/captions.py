"""Find the burned-in caption fragments of a NotebookLM short and cut reading sheets for them."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from vshort.media import iter_frames, probe

INK = 90  # darker than this = text or line art
X0, X1 = 60, 660  # captions are centred; ignore the frame edges


@dataclass
class Fragment:
    i: int
    start: float
    end: float
    y0: int
    y1: int
    text: str | None = None


def find_bands(video: Path) -> list[tuple[int, int]]:
    """Row bands where dark ink comes and goes (captions); static art lines never toggle."""
    prev, toggles, n = None, None, 0
    for _, f in iter_frames(video, fps=6):
        ink = f[:, X0:X1] < INK
        if prev is not None:
            hit = (ink ^ prev).sum(1) > 12
            toggles = hit.astype(int) if toggles is None else toggles + hit
            n += 1
        prev = ink
    rows = np.where(toggles >= max(1, 0.05 * n))[0] if n else []
    bands, start = [], None
    for a, b in zip(rows, list(rows[1:]) + [None]):
        start = a if start is None else start
        if b is None or b - a > 12:
            y0, y1 = int(start) - 8, int(a) + 8
            if 40 <= y1 - y0 <= 120:
                bands.append((y0, y1))
            start = None
    return bands


def detect_fragments(video: Path) -> list[Fragment]:
    bands = find_bands(video)
    frags, cur, prev = [], None, None
    t = 0.0
    for t, f in iter_frames(video):
        regions = [f[a:b, X0:X1].astype(np.int16) for a, b in bands]
        ink = [int((r < INK).sum()) for r in regions]
        band = int(np.argmax(ink)) if ink and max(ink) > 150 else None
        changed = prev is None or band != prev[0] or (
            band is not None and np.abs(regions[band] - prev[1][band]).mean() > 6
        )
        if changed:
            if cur:
                cur.end = t
                frags.append(cur)
            cur = Fragment(len(frags), t, t, *bands[band]) if band is not None else None
        prev = (band, regions)
    if cur:
        cur.end = t + 1 / probe(video).fps
        frags.append(cur)
    return frags


def write_sheets(video: Path, frags: list[Fragment], out_dir: Path, per_sheet: int = 22) -> list[Path]:
    """Stack each fragment's caption crop (from its middle frame) with its index, per_sheet per image."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = probe(video).fps
    want = {round((f.start + f.end) / 2 * fps): f for f in frags}
    crops = {}
    for t, frame in iter_frames(video):
        f = want.get(round(t * fps))
        if f:
            crops[f.i] = Image.fromarray(frame[f.y0 : f.y1, 30:690])
    sheets = []
    for k in range(0, len(frags), per_sheet):
        part = [crops[f.i] for f in frags[k : k + per_sheet]]
        sheet = Image.new("L", (720, sum(c.height for c in part)), 255)
        draw, y = ImageDraw.Draw(sheet), 0
        for f, c in zip(frags[k : k + per_sheet], part):
            sheet.paste(c, (60, y))
            draw.text((4, y + c.height // 2 - 6), str(f.i), fill=0)
            y += c.height
        path = out_dir / f"sheet{k // per_sheet:02d}.png"
        sheet.save(path)
        sheets.append(path)
    return sheets
