"""Find when each burned-in caption fragment appears, and which band it sits in.

Usage: python detect.py VIDEO OUTDIR
Writes OUTDIR/segments.json and OUTDIR/crops/NN.png (one crop per fragment).
"""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 720, 1280, 30
BANDS = {"A": (895, 965), "B": (1110, 1185)}  # caption rows, full-res y
X0, X1 = 60, 660


def frames(video):
    p = subprocess.Popen(
        [FF, "-loglevel", "error", "-i", video, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE,
    )
    n = W * H
    while buf := p.stdout.read(n):
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W)


def main(video, out):
    out = Path(out)
    (out / "crops").mkdir(parents=True, exist_ok=True)
    prev, segs, cur = None, [], None
    for i, f in enumerate(frames(video)):
        bands = {k: f[a:b, X0:X1].astype(np.int16) for k, (a, b) in BANDS.items()}
        # caption = dark text pixels in the band
        ink = {k: int((v < 90).sum()) for k, v in bands.items()}
        band = max(ink, key=ink.get) if max(ink.values()) > 150 else None
        changed = prev is None or band != prev[0] or (
            band and np.abs(bands[band] - prev[1][band]).mean() > 6
        )
        if changed:
            if cur:
                cur["end"] = i / FPS
                segs.append(cur)
            cur = {"start": i / FPS, "band": band, "frame": i}
            if band:
                a, b = BANDS[band]
                Image.fromarray(f[a:b]).save(out / "crops" / f"{len(segs):03d}.png")
        prev = (band, bands)
    cur["end"] = (i + 1) / FPS
    segs.append(cur)
    (out / "segments.json").write_text(json.dumps(segs, indent=1))
    for n, s in enumerate(segs):
        print(n, f"{s['start']:6.2f}-{s['end']:6.2f}", s["band"])


if __name__ == "__main__":
    main(*sys.argv[1:])
