"""Lay the Vietnamese voice clips back to back and time the subtitle phrases on them."""
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vshort.media import FF
from vshort.script import syllables
from vshort.tts import Clip

RATE = 24000
GAP = 0.5  # silence between two sentences: a breath, as NotebookLM leaves
LEAD = 0.2  # before the first
TAIL = 0.5  # after the last


@dataclass
class Placement:
    id: int
    start: float
    dur: float


MAX_TEMPO = 0.05  # the voice is played at most this much faster or slower: more is heard
INSIDE = 0.5  # s inside the window a corrected voice lands, not on its edge


def tempo(clips: list[Clip], lo: float, hi: float) -> float:
    """How much faster (> 1) or slower the clips must play for `total(sequence(clips))` to fall in lo–hi s: 1.0 when it already
    does, else what lands it INSIDE the nearer edge, within MAX_TEMPO. Gemini reads 4.2 to 4.65 syllables a second from one run
    to the next, so a length counted in syllables is 4 s out either way (four neon runs, 10/11/2026)."""
    speech = sum(c.duration for c in clips)
    rest = LEAD + GAP * (len(clips) - 1) + TAIL
    if lo <= speech + rest <= hi:
        return 1.0
    want = (hi - INSIDE if speech + rest > hi else lo + INSIDE) - rest
    return round(min(1 + MAX_TEMPO, max(1 - MAX_TEMPO, speech / want)), 4)


def sequence(clips: list[Clip], tempo: float = 1.0) -> list[Placement]:
    """Clips in the order given, each GAP after the one before; the first starts at LEAD. Each lasts its length at `tempo`."""
    out, t = [], LEAD
    for c in clips:
        out.append(Placement(c.id, t, c.duration / tempo))
        t += c.duration / tempo + GAP
    return out


def total(placements: list[Placement]) -> float:
    return placements[-1].start + placements[-1].dur + TAIL


def _load(clip: Clip, tempo: float = 1.0) -> np.ndarray:
    """Clip as 24 kHz mono int16, played at `tempo` (the pitch stays)."""
    raw = subprocess.run(
        [FF, "-loglevel", "error", "-i", str(clip.path), *(["-af", f"atempo={tempo}"] if tempo != 1 else []),
         "-ar", str(RATE), "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16)


def build_narration(placements: list[Placement], clips: list[Clip], total: float, out_wav: Path, tempo: float = 1.0) -> None:
    by_id = {c.id: c for c in clips}
    track = np.zeros(round(total * RATE), np.int32)
    for p in placements:
        a = _load(by_id[p.id], tempo)
        i = round(p.start * RATE)
        n = max(0, min(len(a), len(track) - i))
        track[i : i + n] += a[:n]
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(np.clip(track, -32768, 32767).astype(np.int16).tobytes())


def phrase_fracs(phrases: str) -> list[tuple[float, float]]:
    """Start and end of each `|` phrase of a line, as fractions of the line, by share of syllables."""
    weights = [max(syllables(x), 1) for x in phrases.split("|")]
    ends = np.cumsum(weights) / sum(weights)
    return [(float(a), float(b)) for a, b in zip([0.0, *ends[:-1]], ends)]


def phrase_times(placements: list[Placement], script: list[dict]) -> list[tuple[float, float, str]]:
    """Subtitle entries: the first sentence whole, then each `|` phrase timed by its share of syllables."""
    text = {row["id"]: row["phrases"] for row in script}
    entries = []
    for k, p in enumerate(placements):
        if k == 0:
            entries.append([p.start, text[p.id].replace("|", " ").strip()])
            continue
        for ph, (f0, _) in zip(text[p.id].split("|"), phrase_fracs(text[p.id])):
            entries.append([p.start + p.dur * f0, ph.strip()])
    entries[0][0] = 0.0
    last_end = placements[-1].start + placements[-1].dur
    ends = [e[0] for e in entries[1:]] + [last_end]
    return [(s, e, ph) for (s, ph), e in zip(entries, ends)]
