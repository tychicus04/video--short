"""Synthetic test media: videos with burned-in captions, silent WAVs."""
import io
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import pytest

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 720, 1280


def wav_bytes(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\0\0" * round(seconds * 24000))
    return buf.getvalue()


def write_silence(path: Path, seconds: float) -> None:
    path.write_bytes(wav_bytes(seconds))


def _frame(kind: str, t: float, t0: float, t1: float) -> np.ndarray:
    if kind == "jitter":  # cream background, an art line flickering across the ink threshold (compression noise)
        f = np.full((H, W, 3), (243, 239, 230), np.uint8)
        f[860:1000, 640:644] = 80 if round(t * 30) % 2 else 100
        return f
    if kind == "artbar":  # cream background, a static dark art bar under the right part of the captions
        f = np.full((H, W, 3), (243, 239, 230), np.uint8)
        f[860:1000, 500:560] = 0
        return f
    if kind == "label":  # cream background, a dark UI label sitting in the upper caption band
        f = np.full((H, W, 3), (243, 239, 230), np.uint8)
        f[905:955, 200:520] = 40
        return f
    if kind == "moving":
        f = np.full((H, W, 3), 160, np.uint8)
        x = 200 + round(200 * (t - t0) / (t1 - t0))
        f[400:520, x : x + 120] = 0
        return f
    if kind in ("drawn", "flash"):  # cream page, dark bar after 1 s (drawn) or after a 0.2 s checkerboard (flash)
        f = np.full((H, W, 3), (243, 239, 230), np.uint8)
        if kind == "flash" and t < t0 + 0.2:
            f[:] = ((np.indices((H, W)).sum(0) // 8 % 2) * 255)[..., None]
        elif t >= t0 + (1.0 if kind == "drawn" else 0.2):
            f[300:700, 200:520] = 60
        return f
    rgb = [int(kind[i : i + 2], 16) for i in (1, 3, 5)]
    return np.broadcast_to(np.array(rgb, np.uint8), (H, W, 3)).copy()


def _ass(captions) -> str:
    def ts(t):
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Old,Be Vietnam Pro,52,&H00202020,&H00202020,&H00E6E6E6,&H00E6E6E6,0,0,0,0,100,100,0,0,3,12,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return head + "".join(
        f"Dialogue: 0,{ts(a)},{ts(b)},Old,,0,0,0,,{{\\pos(360,{y})}}{text}\n" for a, b, y, text in captions
    )


@pytest.fixture
def make_video():
    def make(tmp_path: Path, scenes, captions, fps: int = 30) -> Path:
        out = tmp_path / f"v{len(list(tmp_path.glob('v*.mp4')))}.mp4"
        ass = tmp_path / f"{out.stem}.ass"
        ass.write_text(_ass(captions), encoding="utf-8")
        dur = max(e for _, e, _ in scenes)
        p = subprocess.Popen(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(dur),
             "-vf", f"ass={ass.name}:fontsdir={FONTS}", "-c:v", "libx264", "-crf", "12",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out.name],
            stdin=subprocess.PIPE, cwd=tmp_path,
        )
        for n in range(round(dur * fps)):
            t = n / fps
            kind, a, b = next((k, a, b) for a, b, k in scenes if a <= t < b)
            p.stdin.write(_frame(kind, t, a, b).tobytes())
        p.stdin.close()
        assert p.wait() == 0
        return out

    return make
