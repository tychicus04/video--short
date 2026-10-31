"""Clean plates: per scene, a caption-free patch pasted over every old caption.

`frags` are real captions (after merge_text): a blanked UI label counts as clean background.
"""
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from vshort.captions import INK, X0, X1, Fragment
from vshort.media import frame_at, iter_frames, probe

PLATE_HALF_H = 50  # old caption boxes (with shadow) are ~92 px tall, centred on their text band; plates reach a little past
PAD_X = 26


@dataclass
class Plate:
    name: str
    x: int
    y: int
    start: float
    end: float
    method: str  # "clean" | "lama"
    moving: bool


def scene_cuts(video: Path) -> list[float]:
    cuts, prev = [], None
    for t, f in iter_frames(video):
        small = f[::4, ::4].astype(np.int16)  # 180x320
        if prev is not None and np.abs(small - prev).mean() > 25:
            cuts.append(t)
        prev = small
    return cuts


def first_blank(video: Path, after: float) -> float | None:
    """First near-uniform frame after `after` — NotebookLM fades into its logo outro through a blank screen."""
    for t, f in iter_frames(video, start=after):
        if f.std() < 3:
            return t
    return None


def _text_columns(video: Path, spans: list[tuple[float, float]], y0: int, y1: int,
                  window: tuple[float, float]) -> tuple[int, int]:
    """Columns where one caption's frame differs strongly from the next one's.

    Dark strokes on the light caption box change by ~200 grey levels from caption to caption;
    compression flicker on art edges by ~20. Full caption width when there is nothing to compare.
    """
    times = [(a + b) / 2 for a, b in spans]
    if spans[0][0] - 0.05 > window[0]:  # just before the first caption appears
        times.insert(0, spans[0][0] - 0.05)
    if spans[-1][1] + 0.05 < window[1]:  # just after the last one goes
        times.append(spans[-1][1] + 0.05)
    fr = [frame_at(video, t, gray=True)[y0:y1, X0:X1].astype(np.int16) for t in times]
    hit = np.zeros(X1 - X0, bool)
    for p, q in zip(fr, fr[1:]):
        hit |= (np.abs(p - q) > 100).sum(0) > 3
    cols = np.where(hit)[0]
    return (X0 + int(cols[0]), X0 + int(cols[-1])) if len(cols) else (X0, X1)


def _clean_time(covered: list[tuple[float, float]], wa: float, wb: float, target: float) -> float | None:
    """A moment in the scene [wa, wb) with no caption in this band, as close to target as possible."""
    edge = 0.034  # one frame of margin against fades
    gaps, t = [], wa + edge
    for c0, c1 in sorted(covered):
        if c0 - edge > t:
            gaps.append((t, c0 - edge))
        t = max(t, c1 + edge)
    if wb - edge > t:
        gaps.append((t, wb - edge))
    picks = [min(max(target, g0), g1) for g0, g1 in gaps]
    return min(picks, key=lambda p: abs(p - target)) if picks else None


def _moving(video: Path, a: float, b: float, y0: int, y1: int) -> bool:
    d = min(0.1, (b - a) / 4)
    fr = [frame_at(video, t, gray=True).astype(np.int16) for t in (a + d, (a + b) / 2, b - d)]
    keep = np.ones(fr[0].shape, bool)
    keep[y0:y1] = False
    return bool(max(np.abs(p - q)[keep].mean() for p, q in zip(fr, fr[1:])) > 3.0)


def _lama(lama_path: Path) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    import torch

    model = torch.jit.load(str(lama_path), map_location="cpu").eval()

    def run(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            out = model(torch.from_numpy(img / 255.0).permute(2, 0, 1)[None].float(),
                        torch.from_numpy(mask.astype(np.float32))[None, None])
        return np.clip(out[0].permute(1, 2, 0).numpy() * 255, 0, 255).astype(np.uint8)[: img.shape[0]]

    return run


def build_plates(
    video: Path,
    frags: list[Fragment],
    out_dir: Path,
    lama_path: Path,
    inpaint: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
) -> list[Plate]:
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    edges = [0.0, *scene_cuts(video), info.duration]
    # a caption left on screen across a cut needs a plate in every scene it touches
    groups: dict[tuple[int, int, int], list[tuple[float, float]]] = {}
    for f in frags:
        for w in range(len(edges) - 1):
            a, b = max(f.start, edges[w]), min(f.end, edges[w + 1])
            if b - a > 1e-3:
                groups.setdefault((w, f.y0, f.y1), []).append((a, b))

    plates = []
    for (w, by0, by1), spans in sorted(groups.items()):
        wa, wb = edges[w], edges[w + 1]
        a, b = min(s for s, _ in spans), max(e for _, e in spans)
        mid = (by0 + by1) // 2
        c0, c1 = _text_columns(video, sorted(spans), by0, by1, (wa, wb))
        # even edges: yuv420 overlay rounds odd positions down, which would leave a 1 px sliver of the old box
        y0, y1 = max(mid - PLATE_HALF_H, 0) // 2 * 2, min(-(-(mid + PLATE_HALF_H) // 2) * 2, info.height)
        x0, x1 = max(c0 - PAD_X, 0) // 2 * 2, min(-(-(c1 + PAD_X) // 2) * 2, info.width)
        covered = [(f.start, f.end) for f in frags if (f.y0, f.y1) == (by0, by1) and f.end > wa and f.start < wb]
        clean_t = _clean_time(covered, wa, wb, (a + b) / 2)
        if clean_t is not None:
            patch, method = frame_at(video, clean_t)[y0:y1, x0:x1], "clean"
        else:
            inpaint = inpaint or _lama(lama_path)
            img = frame_at(video, (a + b) / 2)
            c_top = max(y0 - 244, 0) // 8 * 8
            c_bot = min(c_top + -(-(y1 + 224 - c_top) // 8) * 8, info.height // 8 * 8)
            mask = np.zeros(img.shape[:2], bool)
            mask[y0:y1, x0:x1] = True
            res = inpaint(img[c_top:c_bot], mask[c_top:c_bot])
            patch, method = res[y0 - c_top : y1 - c_top, x0:x1], "lama"
        plate = Plate(f"p{len(plates):02d}", x0, y0, round(a, 4), round(b, 4), method,
                      _moving(video, a, b, y0, y1))
        Image.fromarray(patch).save(out_dir / f"{plate.name}.png")
        plates.append(plate)
    (out_dir / "plates.json").write_text(json.dumps([asdict(p) for p in plates], indent=1))
    return plates
