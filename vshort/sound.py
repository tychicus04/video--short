"""The soundtrack of final.mp4: the voice, a few sound effects on the picture's biggest changes of scene, one loudness."""
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


NAMES = ("whoosh", "pop", "whoosh")  # by time order


def cues(changes: list[tuple[float, float]], ps) -> list[Cue]:
    """At most three accents, on the strongest changes of scene (`plates.scene_changes`: source time, strength) that
    the video shows (`retime` pieces `ps`), none in the title line, none closer than SPACE to a stronger one."""
    from vshort.retime import to_output
    shown = [(at, m) for t, m in changes if (at := to_output(ps, t)) is not None and at >= ps[0].dst_end]
    picked: list[float] = []
    for at, _ in sorted(shown, key=lambda c: -c[1]):
        if len(picked) < len(NAMES) and all(abs(at - x) >= SPACE for x in picked):
            picked.append(at)
    return [Cue(name, at) for name, at in zip(NAMES, sorted(picked))]


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
