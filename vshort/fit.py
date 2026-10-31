"""Fit Vietnamese voice clips into the English sentence windows and lay out the subtitle phrases."""
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vshort.media import FF
from vshort.script import Sentence, syllables
from vshort.tts import Clip

RATE = 24000
GAP = 0.1  # minimum silence between two sentences


@dataclass
class Placement:
    id: int
    start: float
    dur: float
    tempo: float
    overflow: float


def place(sentences: list[Sentence], clips: list[Clip], cut: float, max_tempo: float = 1.10) -> list[Placement]:
    """Start each clip on its sentence (or after the previous clip spills), speeding up at most max_tempo."""
    length = {c.id: c.duration for c in clips}
    out, prev_end = [], float("-inf")
    for k, s in enumerate(sentences):
        start = max(s.start, prev_end + GAP)
        next_start = sentences[k + 1].start if k + 1 < len(sentences) else cut
        available = max(next_start - start, 1e-6)
        tempo = min(max(1.0, length[s.id] / available), max_tempo)
        dur = length[s.id] / tempo
        out.append(Placement(s.id, start, dur, tempo, max(0.0, start + dur - next_start)))
        prev_end = start + dur
    return out


def too_long(placements: list[Placement], tol: float = 0.25) -> list[int]:
    """Sentences spilling too far into the next one; the last one may not spill at all (the video ends)."""
    last = len(placements) - 1
    return [p.id for k, p in enumerate(placements) if p.overflow > (0.0 if k == last else tol)]


def _load(clip: Clip, tempo: float) -> np.ndarray:
    """Clip as 24 kHz mono int16, sped up by tempo (pitch kept)."""
    af = ["-filter:a", f"atempo={tempo}"] if tempo > 1.0001 else []
    raw = subprocess.run(
        [FF, "-loglevel", "error", "-i", str(clip.path), *af, "-ar", str(RATE), "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16)


def build_narration(placements: list[Placement], clips: list[Clip], total: float, out_wav: Path) -> None:
    by_id = {c.id: c for c in clips}
    track = np.zeros(round(total * RATE), np.int32)
    for p in placements:
        a = _load(by_id[p.id], p.tempo)
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
