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
GAP = 0.3  # silence between two sentences
LEAD = 0.2  # before the first
TAIL = 0.5  # after the last


@dataclass
class Placement:
    id: int
    start: float
    dur: float


def sequence(clips: list[Clip]) -> list[Placement]:
    """Clips in the order given, each GAP after the one before; the first starts at LEAD."""
    out, t = [], LEAD
    for c in clips:
        out.append(Placement(c.id, t, c.duration))
        t += c.duration + GAP
    return out


def total(placements: list[Placement]) -> float:
    return placements[-1].start + placements[-1].dur + TAIL


def _load(clip: Clip) -> np.ndarray:
    """Clip as 24 kHz mono int16."""
    raw = subprocess.run(
        [FF, "-loglevel", "error", "-i", str(clip.path), "-ar", str(RATE), "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16)


def build_narration(placements: list[Placement], clips: list[Clip], total: float, out_wav: Path) -> None:
    by_id = {c.id: c for c in clips}
    track = np.zeros(round(total * RATE), np.int32)
    for p in placements:
        a = _load(by_id[p.id])
        i = round(p.start * RATE)
        n = max(0, min(len(a), len(track) - i))
        track[i : i + n] += a[:n]
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(np.clip(track, -32768, 32767).astype(np.int16).tobytes())


def phrase_times(placements: list[Placement], script: list[dict]) -> list[tuple[float, float, str]]:
    """Subtitle entries: the first sentence whole, then each `|` phrase timed by its share of syllables."""
    text = {row["id"]: row["phrases"] for row in script}
    entries = []
    for k, p in enumerate(placements):
        phrases = [text[p.id].replace("|", " ").strip()] if k == 0 else [x.strip() for x in text[p.id].split("|")]
        weights = [max(syllables(x), 1) for x in phrases]
        t = p.start
        for ph, w in zip(phrases, weights):
            entries.append([t, ph])
            t += p.dur * w / sum(weights)
    entries[0][0] = 0.0
    last_end = placements[-1].start + placements[-1].dur
    ends = [e[0] for e in entries[1:]] + [last_end]
    return [(s, e, ph) for (s, ph), e in zip(entries, ends)]
