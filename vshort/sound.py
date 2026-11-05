"""The soundtrack of final.mp4: the voice, a few sound effects on moments the picture already makes, one loudness."""
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vshort.media import FF

# CC0 1.0, synthesised with ffmpeg by github.com/howznguyen/shorts-kit (public/sfx); each is normalised to FX_LUFS.
# Drop in another file of the same name to change one.
SFX = Path(__file__).resolve().parent.parent / "assets" / "sfx"
RATE = 48000
LUFS, PEAK = -14.0, -2.0  # what YouTube, TikTok and Reels play at; true-peak ceiling, AAC adds 0.3–0.6 dB back
# brickwall at PEAK, 4x oversampled so it sees the peaks between samples: Gemini reads with true peaks up to +1 dB
LIMIT = f"aresample={4 * RATE},alimiter=limit={10 ** (PEAK / 20):.3f}:attack=1:release=50:level=false,aresample={RATE}"
UNDER = 3.0  # dB an effect sits under the voice (shorts-kit, by ear); past 6 it sounds like a mixing slip
FX_LUFS = -20.0
SPACE = 1.5  # s: an effect this soon after another is dropped


@dataclass(frozen=True)
class Cue:
    name: str  # file stem in SFX
    at: float  # s: where its loudest moment lands


def cues(segs, scenes) -> list[Cue]:
    """At most three accents: a whoosh on the cut into the drawn canvas, a glitch when the canvas first turns a thing
    red (the moment the attack lands), a pop on the cut to the first redrawn reference. A video that opens on one of
    them has no cut there and gets no effect."""
    def cut(pred) -> float | None:
        return next((s.start for s in segs if pred(s)), None) or None

    want = [("whoosh", cut(lambda s: s.scene is not None)),
            ("glitch", min((a.t0 for sc in scenes for a in sc.acts if a.do == "red"), default=None)),
            ("pop", cut(lambda s: s.group.startswith("v")))]
    out: list[Cue] = []
    for name, at in sorted(((n, t) for n, t in want if t is not None), key=lambda c: c[1]):
        if not out or at - out[-1].at >= SPACE:
            out.append(Cue(name, at))
    return out


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run([FF, "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _ff(pcm: np.ndarray, af: str, *out: str) -> subprocess.CompletedProcess:
    """Run `af` over mono float samples at RATE."""
    return subprocess.run([FF, "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", "-",
                           "-af", af, *out], input=pcm.astype(np.float32).tobytes(), capture_output=True, check=True)


def loudness(pcm: np.ndarray) -> float:
    """Integrated LUFS; -inf for silence."""
    log = _ff(pcm, "loudnorm=print_format=json", "-f", "null", "-").stderr.decode()
    return float(json.loads(log[log.rindex("{"):log.rindex("}") + 1])["input_i"])  # ffmpeg's summary lines follow it


def master(voice: Path, cues: list[Cue], total: float, out: Path) -> None:
    """`voice` with the effects, at least `total` s, at LUFS with true peaks under PEAK: a 48 kHz mono wav.

    A plain gain then the limiter, not loudnorm: it falls back to compressing the voice when the gain would clip, and
    then lands up to 1 LU short.
    """
    track = _decode(voice)
    track = np.pad(track, (0, max(0, round(total * RATE) - len(track))))
    if math.isfinite(loud := loudness(track)):
        for c in cues:
            fx = _decode(SFX / f"{c.name}.mp3") * 10 ** ((loud - UNDER - FX_LUFS) / 20)
            i = round(c.at * RATE) - int(np.argmax(np.convolve(fx * fx, np.ones(RATE // 100), "same")))
            if i < 0:
                fx, i = fx[-i:], 0
            n = max(0, min(len(fx), len(track) - i))
            track[i:i + n] += fx[:n]
        for _ in range(2):  # the limiter takes back some loudness (0.8 LU on a hot read): measure and lift once more
            track = np.frombuffer(_ff(track, f"volume={LUFS - loudness(track):.2f}dB,{LIMIT}", "-f", "f32le", "-").stdout,
                                  np.float32)
    _ff(track, "anull", "-c:a", "pcm_s16le", "-y", str(out))
