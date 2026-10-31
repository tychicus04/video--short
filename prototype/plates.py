"""Clean plates that hide the old band-A captions, so new subs can sit at one fixed spot.

Usage: python plates.py VIDEO
Writes plates/<name>.png (the patch) and plates/plates.json ({name, x, y, start, end}).
Scenes are static, so one cleaned frame per scene is pasted over the caption area.
"""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 720, 1280
Y0, Y1 = 884, 976  # band-A caption rows (pill is ~888-970)
CTX0, CTX1 = 640, 1200  # rows LaMa sees as context

# name, frame to clean, window it covers, needs inpainting[, fixed x-range when art lines flicker]
SCENES = [
    ("lock", 2.0, 0.0, 5.2667, True),
    ("phones", 8.0, 5.2667, 10.20, True, (150, 575)),  # bezel lines fool text_columns
    ("news", 12.5, 10.20, 14.9667, True),
    ("cut46", 45.9, 46.0333, 46.1333, False),  # band-A caption over the previous (clean) scene
    ("monitor", 49.0, 46.1333, 52.5333, True),
    ("update", 57.2, 52.5333, 57.30, False),  # captions are gone by 57.13
]


def frame(video, t, fmt="rgb24"):
    b = subprocess.run(
        [FF, "-loglevel", "error", "-i", video, "-ss", str(t), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", fmt, "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(b, np.uint8).reshape(H, W, -1).copy()


def text_columns(video, a, b):
    """Columns holding old caption text: dark pixels that come and go (art lines stay put)."""
    p = subprocess.run(
        [FF, "-loglevel", "error", "-ss", str(a), "-to", str(b), "-i", video, "-vf",
         f"fps=6,crop={W}:{Y1 - Y0}:0:{Y0}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    fr = np.frombuffer(p, np.uint8).reshape(-1, Y1 - Y0, W)
    ink = (fr < 90).mean(0)
    cols = np.where(((ink > 0.02) & (ink < 0.9)).sum(0) > 2)[0]
    return int(cols.min()), int(cols.max())


def main(video):
    out = HERE / "plates"
    out.mkdir(exist_ok=True)
    lama = torch.jit.load(str(HERE / "models" / "big-lama.pt"), map_location="cpu").eval()
    meta = []
    for name, t, a, b, inpaint, *xr in SCENES:
        img = frame(video, t)
        if inpaint:
            if xr:
                x0, x1 = xr[0]
            else:
                c0, c1 = text_columns(video, a, b)
                x0, x1 = max(c0 - 26, 0), min(c1 + 26, W)
            mask = np.zeros((H, W), np.float32)
            mask[Y0:Y1, x0:x1] = 1
            ctx = img[CTX0:CTX1] / 255.0
            with torch.inference_mode():
                res = lama(
                    torch.from_numpy(ctx).permute(2, 0, 1)[None].float(),
                    torch.from_numpy(mask[CTX0:CTX1])[None, None],
                )[0].permute(1, 2, 0).numpy()
            res = np.clip(res[: CTX1 - CTX0] * 255, 0, 255).astype(np.uint8)
            img[CTX0:CTX1] = np.where(mask[CTX0:CTX1, :, None] > 0, res, img[CTX0:CTX1])
        else:
            x0, x1 = 100, 620
        Image.fromarray(img[Y0:Y1, x0:x1]).save(out / f"{name}.png")
        Image.fromarray(img[CTX0:CTX1]).save(out / f"{name}_ctx.png")  # for eyeballing
        meta.append({"name": name, "x": x0, "y": Y0, "start": a, "end": b})
        print(name, x0, x1)
    (out / "plates.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
