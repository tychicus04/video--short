"""NotebookLM's own video under the Vietnamese voice: each line plays the stretch of video its English sentence had,
sped up or held to last as long as the Vietnamese does."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vshort.fit import Placement
from vshort.media import iter_frames
from vshort.script import Sentence
from vshort.stills import BLANK

FAST = 1.5  # at most this fast; a longer English stretch loses its tail
SLOW = 1.25  # a long hold first plays the stretch up to this much slower…
SLOW_AFTER = 1.5  # …when holding the last frame at 1x would take longer than this (s)
STEP = 0.1  # s a held frame on bare paper steps back by


@dataclass(frozen=True)
class Piece:
    id: int
    src: float  # s in clean.mp4 where the line's picture starts
    src_end: float  # s in clean.mp4 of the last frame played, then held
    dst: float  # s in final.mp4
    dst_end: float
    speed: float  # source seconds per output second while playing (>1 faster, <1 slower)
    hold: float  # s the frame at src_end is held at the end
    dropped: float  # s of the English stretch not shown (beyond FAST)


def pieces(lines: list[Sentence], placements: list[Placement], total: float, stop: float,
           blank: Callable[[float], bool] = lambda t: False) -> list[Piece]:
    """One piece per Vietnamese line. `lines` are the merged English sentences of the lines (same ids, same order as
    `placements`); `stop` is where NotebookLM's logo starts; `blank(t)` says the frame at t is bare paper."""
    assert [s.id for s in lines] == [p.id for p in placements], "lines and placements must be the same lines"
    out = []
    for i, (s, p) in enumerate(zip(lines, placements)):
        a = 0.0 if i == 0 else min(s.start, stop)
        b = min(lines[i + 1].start if i + 1 < len(lines) else s.end, stop)
        d0 = 0.0 if i == 0 else p.start
        d1 = placements[i + 1].start if i + 1 < len(placements) else total
        S, T = max(b - a, 0.0), d1 - d0
        if S >= T:
            speed = min(S / T, FAST)
            out.append(Piece(p.id, a, min(a + speed * T, b), d0, d1, speed, 0.0, max(S - speed * T, 0.0)))
            continue
        speed = 1.0 if T - S <= SLOW_AFTER else max(S / T, 1 / SLOW)
        end = b
        while blank(end) and end - STEP > a:  # never hold bare paper: step back to the drawn frame before it
            end -= STEP
        if blank(end):  # the whole stretch is paper: nothing better to hold
            end = b
        out.append(Piece(p.id, a, end, d0, d1, speed, T - (end - a) / speed, 0.0))
    return out


def to_output(ps: list[Piece], t: float) -> float | None:
    """Where the source moment t is shown in final.mp4; None when it is not (a dropped tail, outside every piece)."""
    for p in ps:
        if p.src <= t <= p.src_end:
            return p.dst + (t - p.src) / p.speed
    return None


def blank_at(video: Path, fps: float = 10) -> Callable[[float], bool]:
    """Whether the frame nearest t is bare paper (grey spread under stills.BLANK), sampled at `fps`."""
    spread = np.array([float(f[::2, ::2].std()) for _, f in iter_frames(video, fps=fps)])

    def blank(t: float) -> bool:
        return bool(len(spread)) and spread[min(max(round(t * fps), 0), len(spread) - 1)] < BLANK

    return blank
