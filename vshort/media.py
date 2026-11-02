"""ffmpeg helpers: probe a video, iterate its frames, grab one exact frame."""
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np

FF = imageio_ffmpeg.get_ffmpeg_exe()


@dataclass(frozen=True)
class Probe:
    width: int
    height: int
    fps: float
    duration: float


def probe(video: Path) -> Probe:
    err = subprocess.run([FF, "-hide_banner", "-i", str(video)], capture_output=True, text=True).stderr
    w, h = map(int, re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})", err).groups())
    fps = float(re.search(r"([\d.]+) fps", err).group(1))
    hh, mm, ss = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return Probe(w, h, fps, int(hh) * 3600 + int(mm) * 60 + float(ss))


def iter_frames(
    video: Path,
    *,
    fps: float | None = None,
    crop: tuple[int, int, int, int] | None = None,
    gray: bool = True,
    start: float | None = None,
    end: float | None = None,
) -> Iterator[tuple[float, np.ndarray]]:
    """Yield (time, frame); crop is (w, h, x, y). Gray frames are HxW, colour frames HxWx3 RGB."""
    info = probe(video)
    w, h = (crop[0], crop[1]) if crop else (info.width, info.height)
    filters = ([f"fps={fps}"] if fps else []) + ([f"crop={w}:{h}:{crop[2]}:{crop[3]}"] if crop else [])
    cmd = [FF, "-loglevel", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video)]
    if end is not None:
        cmd += ["-t", str(end - (start or 0))]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    ch = 1 if gray else 3
    cmd += ["-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"]
    rate, n, size = fps or info.fps, 0, w * h * ch
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        while len(buf := p.stdout.read(size)) == size:
            f = np.frombuffer(buf, np.uint8).reshape((h, w) if gray else (h, w, 3))
            yield (start or 0) + n / rate, f
            n += 1
    finally:
        if p.poll() is None:  # caller stopped early: stop ffmpeg before it hits a broken pipe
            p.kill()
        p.stdout.close()
        p.wait()


def frame_at(video: Path, t: float, gray: bool = False) -> np.ndarray:
    """The first frame at or after t. Input-side seek: ffmpeg decodes from the keyframe before t and drops
    frames until t, so it is as exact as an output-side seek without decoding the video from the start."""
    info = probe(video)
    out = subprocess.run(
        [FF, "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    shape = (info.height, info.width) if gray else (info.height, info.width, 3)
    return np.frombuffer(out, np.uint8).reshape(shape).copy()
