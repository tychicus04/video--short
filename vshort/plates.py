"""Old captions out of NotebookLM's video: `clean` removes them frame by frame (and the watermark) for the render,
which plays the video itself; `build_plates` is the per-scene patch the still pictures used.

`frags` are real captions (after merge_text): a blanked UI label counts as clean background.
"""
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from vshort.captions import INK, X0, X1, Fragment
from vshort.media import FF, frame_at, iter_frames, probe

WATERMARK = "delogo=x=524:y=1232:w=180:h=32"
# scene changes: frames LAG s apart, measured over a 180x320 copy at FPS. NotebookLM dissolves (≈0.5 s), so a frame's
# neighbour barely differs; half a second apart a new page has moved ≥ 15 % of the pixels by > 20 grey levels (Rails'
# softest, pencil page to pencil page) while an icon popping in moves ≤ 3 %
CHANGE_FPS, CHANGE_PIXELS, CHANGE_MEAN, CHANGE_GAP = 10, 0.12, 12.0, 1.0
# clean: the picture right around an old caption box (RING px) says what is under it. Within one NotebookLM scene it
# stands still (Rails, BOSSAI, NetamLoader: ≤ 1.2 grey levels first to last), so one inpainted plate serves the scene;
# across a dissolve the ring says how far the dissolve has gone, and the two scenes' plates are mixed by that much
GAP = 0.3  # s: captions of one band closer than this share their plates
PAD_T = 0.1  # s the fill starts before and ends after a caption: they fade in and out
RING = 8
ANCHOR = 2.0  # mean grey change of the ring since the last plate that needs a new one…
SETTLE, SETTLE_S = 0.5, 0.2  # …once the ring has stopped changing (< SETTLE over SETTLE_S)
FEATHER = 6  # px outside a box over which the fill fades into the picture
MARGIN = 96  # px of picture above and below a box that LaMa sees

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
        d = None if prev is None else np.abs(small - prev)
        # a low-contrast cut (dark theme, NetamLoader 11.73 s: mean 24.9) still changes > 30 % of the pixels by > 20
        # (cuts 28–96 %); a shape popping in mid-scene changes ~14 %, caption swaps ≤ 8 %
        if d is not None and (d.mean() > 25 or (d > 20).mean() > 0.3):
            cuts.append(t)
        prev = small
    return cuts


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


def scene_changes(video: Path, lag: float = 0.5) -> list[tuple[float, float]]:
    """(time, strength) of every change of scene, dissolves included: the strongest moment of each change."""
    small = [(t, f[::4, ::4].astype(np.int16)) for t, f in iter_frames(video, fps=CHANGE_FPS)]
    k = max(1, round(lag * CHANGE_FPS))
    peaks: list[tuple[float, float]] = []
    for (t, f), (_, g) in zip(small[k:], small):
        d = np.abs(f - g)
        if (d > 20).mean() < CHANGE_PIXELS or (m := float(d.mean())) < CHANGE_MEAN:
            continue
        if peaks and t - peaks[-1][0] < CHANGE_GAP:  # one change seen over several frames: keep its strongest
            if m > peaks[-1][1]:
                peaks[-1] = (t, m)
        else:
            peaks.append((t, m))
    return peaks


@dataclass(frozen=True)
class _Box:
    y0: int
    y1: int
    x0: int
    x1: int
    start: float
    end: float


def _boxes(video: Path, frags: list[Fragment]) -> list[_Box]:
    """Each caption's old box (with its shadow), on even pixels."""
    info, out = probe(video), []
    last = info.duration - 1 / info.fps  # frame_at finds nothing past the last frame
    for f in frags:
        mid = (f.y0 + f.y1) // 2
        c0, c1 = _text_columns(video, [(f.start, min(f.end, last))], f.y0, f.y1, (max(f.start - 0.3, 0.0), min(f.end + 0.3, last)))
        out.append(_Box(max(mid - PLATE_HALF_H, 0) // 2 * 2, -(-(mid + PLATE_HALF_H) // 2) * 2,
                        max(c0 - PAD_X, 0) // 2 * 2, -(-(c1 + PAD_X) // 2) * 2, f.start, f.end))
    return out


def _runs(boxes: list[_Box]) -> list[list[_Box]]:
    """Captions of one band, one after another: they share the plates under them."""
    runs: list[list[_Box]] = []
    for b in sorted(boxes, key=lambda b: (b.y0, b.start)):
        if runs and runs[-1][0].y0 == b.y0 and b.start - max(x.end for x in runs[-1]) < GAP:
            runs[-1].append(b)
        else:
            runs.append([b])
    return runs


def _lama_full(lama_path: Path) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    """LaMa over the rows around the mask only (time grows with the pixels: 4.6 s for 304 rows on the server)."""
    lama = _lama(lama_path)

    def run(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        rows = np.where(mask.any(1))[0]
        top = max(int(rows[0]) - MARGIN, 0) // 8 * 8
        bot = min(top + -(-(int(rows[-1]) + 1 + MARGIN - top) // 8) * 8, img.shape[0] // 8 * 8)
        out = img.copy()
        out[top:bot] = lama(img[top:bot], mask[top:bot])
        return out

    return run


class _Run:
    """One band's captions: the box they all fit in, its ring, and the inpainted plates (anchors) along the way."""

    def __init__(self, boxes: list[_Box], duration: float, height: int, width: int):
        self.boxes = boxes
        self.t0, self.t1 = max(min(b.start for b in boxes) - PAD_T, 0.0), min(max(b.end for b in boxes) + PAD_T, duration)
        self.y0, self.y1 = min(b.y0 for b in boxes), max(b.y1 for b in boxes)
        self.x0, self.x1 = min(b.x0 for b in boxes), max(b.x1 for b in boxes)
        self.e = (max(self.y0 - FEATHER, 0), min(self.y1 + FEATHER, height), max(self.x0 - FEATHER, 0),
                  min(self.x1 + FEATHER, width))  # the fill reaches FEATHER px past the box
        ring = np.zeros((height, width), bool)
        ring[max(self.y0 - RING, 0):self.y1 + RING, max(self.x0 - RING, 0):self.x1 + RING] = True
        ring[self.y0:self.y1, self.x0:self.x1] = False
        self.ring = ring
        self.times: list[float] = []
        self.rings: list[np.ndarray] = []
        self.anchors: list[int] = []  # indexes into times
        self.plates: list[np.ndarray] = []

    def sees(self, t: float) -> bool:
        return self.t0 <= t <= self.t1

    def pick_anchors(self, fps: float) -> None:
        settle = max(1, round(SETTLE_S * fps))
        r, anchors = self.rings, [0]
        for i in range(1, len(r)):
            moved = np.abs(r[i] - r[anchors[-1]]).mean() > ANCHOR
            still = i >= settle and np.abs(r[i] - r[i - settle]).mean() < SETTLE
            if moved and still:
                anchors.append(i)
        if len(r) > 1 and np.abs(r[-1] - r[anchors[-1]]).mean() > ANCHOR:  # ends mid-change
            anchors.append(len(r) - 1)
        self.anchors = anchors

    def fill(self, i: int) -> np.ndarray:
        """The plate for frame i of the run: between two anchors, mixed by how far the ring has gone from one to the other."""
        a = max((k for k in range(len(self.anchors)) if self.anchors[k] <= i), default=0)
        if a == len(self.anchors) - 1:
            return self.plates[a]
        ra, rb, r = self.rings[self.anchors[a]], self.rings[self.anchors[a + 1]], self.rings[i]
        d = rb - ra
        w = float(np.clip(((r - ra) * d).sum() / max(float((d * d).sum()), 1e-6), 0, 1))
        return (1 - w) * self.plates[a] + w * self.plates[a + 1]

    def alpha(self, t: float) -> np.ndarray:
        """Where the fill shows at t (over the run's reach): 1 in each box on screen around t, fading out past it."""
        y0, y1, x0, x1 = self.e
        al = np.zeros((y1 - y0, x1 - x0), np.float32)
        ys, xs = np.arange(y0, y1)[:, None], np.arange(x0, x1)[None, :]
        for b in self.boxes:
            if b.start - PAD_T <= t <= b.end + PAD_T:
                dy = np.maximum(np.maximum(b.y0 - ys, ys - (b.y1 - 1)), 0)
                dx = np.maximum(np.maximum(b.x0 - xs, xs - (b.x1 - 1)), 0)
                al = np.maximum(al, np.clip(1 - np.maximum(dy, dx) / (FEATHER + 1), 0, 1))
        return al[..., None]


def clean(src: Path, captions: list[Fragment], out: Path, lama_path: Path,
          inpaint: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None) -> dict:
    """`src` without its old captions and watermark, frame by frame, same size, rate and length; a summary for clean.json.

    Each band's run of captions gets inpainted plates only where the picture around it settles somewhere new (once per
    scene, as a rule); every frame in between mixes the two nearest plates by its ring (see _Run.fill).
    """
    began = time.monotonic()
    info = probe(src)
    runs = [_Run(r, info.duration, info.height, info.width) for r in _runs(_boxes(src, captions))]
    if runs:
        for t, f in iter_frames(src):  # pass 1: the rings
            for r in runs:
                if r.sees(t):
                    r.times.append(t)
                    r.rings.append(f[r.ring].astype(np.float32))
        inpaint = inpaint or _lama_full(lama_path)
        for r in runs:
            r.pick_anchors(info.fps)
            for i in r.anchors:
                img = frame_at(src, r.times[i])
                mask = np.zeros(img.shape[:2], bool)
                mask[r.y0:r.y1, r.x0:r.x1] = True
                y0, y1, x0, x1 = r.e
                r.plates.append(inpaint(img, mask)[y0:y1, x0:x1].astype(np.float32))
    tmp = out.resolve().with_name(f"{out.stem}.tmp{out.suffix}")
    cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{info.width}x{info.height}",
           "-r", str(info.fps), "-i", "-", "-vf", WATERMARK, "-c:v", "libx264", "-crf", "12", "-preset", "medium",
           "-pix_fmt", "yuv420p", str(tmp)]
    seen = {id(r): 0 for r in runs}
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as p:
        try:
            for t, f in iter_frames(src, gray=False):  # pass 2: the fills
                f = f.copy()
                for r in runs:
                    if not r.sees(t) or seen[id(r)] >= len(r.times):
                        continue
                    i = seen[id(r)]
                    seen[id(r)] += 1
                    y0, y1, x0, x1 = r.e
                    al = r.alpha(t)
                    f[y0:y1, x0:x1] = (al * r.fill(i) + (1 - al) * f[y0:y1, x0:x1]).round().astype(np.uint8)
                p.stdin.write(f.tobytes())
            p.stdin.close()
        except BaseException:
            p.kill()
            raise
    if p.returncode:
        tmp.unlink(missing_ok=True)
        raise subprocess.CalledProcessError(p.returncode, cmd)
    tmp.replace(out)
    return {"method": "ring-anchors", "seconds": round(time.monotonic() - began, 1),
            "boxes": [{"band": [r.y0, r.y1], "x": [r.x0, r.x1], "start": round(r.t0, 2), "end": round(r.t1, 2),
                       "plates": [round(r.times[i], 2) for i in r.anchors]} for r in runs]}
