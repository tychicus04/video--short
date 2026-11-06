"""Final video: NotebookLM's own video retimed to the new voice, fixed low subtitles in NotebookLM's caption style,
the ANM outro in place of NotebookLM's (the only logo)."""
import math
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from vshort.media import FF, probe
from vshort.textfit import FONTS, MAX_TEXT_W, UI_BOTTOM, text_width

W, H = 720, 1280
FPS = 30
XF = 0.4  # the outro fades in from the last frame over this long
EM = 1000 / 1354  # libass sizes fonts by win ascent+descent; Patrick Hand's em is 0.739 of that
LINE_H, CAP_EM, PAD_X, PAD_Y = 62, 50, 22, 12
SUB_BOTTOM = UI_BOTTOM - 11  # every caption box stands on this line, clear of the platforms' description (was centred
# at 1150, half under it); a two-line title grows upwards
INK, BOX = "3A3434", "D6DEE2"  # ASS BGR, sampled from NotebookLM's captions: dark grey ink on a light grey box
LOGO = Path(__file__).resolve().parent.parent / "assets" / "brand" / "anm-logo.png"
SHIELD_W = 185  # the logo's shield ends here; its words start at x 188
OUTRO = LOGO.with_name("anm-outro.mp4")  # appended to every video; `vshort outro` redraws it, or drop in any 720x1280 clip
OUTRO_S = 2.5  # length of the drawn outro


PAPER = (238, 234, 226)  # the outro's page


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _paper() -> Image.Image:
    noise = np.random.default_rng(7).normal(0, 1.1, (H, W, 1))  # a little grain, the same every time (as drawn at 2x, then halved)
    return Image.fromarray((np.array(PAPER) + noise).clip(0, 255).astype(np.uint8))


@lru_cache
def _logo() -> tuple[Image.Image, Image.Image]:
    """(outro shield, outro words), scaled once. The logo is only on the outro: Tai dropped the corner mark (05/11)."""
    im = Image.open(LOGO).convert("RGBA")
    shield = im.crop((0, 0, SHIELD_W, im.height))
    shield = shield.resize((round(shield.width * 300 / shield.height), 300), Image.LANCZOS)
    words = im.crop((SHIELD_W + 3, 0, im.width, im.height))
    words = words.resize((600, round(words.height * 600 / words.width)), Image.LANCZOS)
    return shield, words


def end_card(t: float, paper: Image.Image) -> Image.Image:
    """The outro at t s: the shield grows in, then the words wipe in from the left."""
    shield, words = _logo()
    img = paper.copy()
    p = _ease(t / 0.5)
    if p:
        s = shield.resize((max(1, round(shield.width * (0.7 + 0.3 * p))), max(1, round(shield.height * (0.7 + 0.3 * p)))))
        s.putalpha(s.getchannel("A").point(lambda a: round(a * p)))
        img.paste(s, (round((W - s.width) / 2), round(560 - s.height / 2)), s)
    if q := round(words.width * _ease((t - 0.5) / 0.8)):
        w = words.crop((0, 0, q, words.height))
        img.paste(w, ((W - words.width) // 2, 760), w)
    return img


def export_outro(out: Path = OUTRO) -> None:
    """end_card alone as an mp4 with a silent track (vshort's 24 kHz mono), to append to this or any other video."""
    paper = _paper()
    tmp = out.resolve().with_name(f"{out.stem}.tmp{out.suffix}")  # every render reads `out`: never leave it half-written
    cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-map", "0:v", "-map", "1:a", "-t", str(OUTRO_S),
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", str(tmp)]
    try:
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as p:
            for n in range(math.ceil(OUTRO_S * FPS)):
                p.stdin.write(end_card(n / FPS, paper).tobytes())
            p.stdin.close()
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, cmd)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def fs(em: float) -> int:
    return round(em / EM)


def _wrap(text: str, max_w: float) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if cur and text_width(cand) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    return lines + [cur]


def _balanced(text: str) -> list[str]:
    n = len(_wrap(text, MAX_TEXT_W))
    lo, hi = 200, MAX_TEXT_W  # narrowest width that keeps the same line count
    while lo < hi:
        mid = (lo + hi) // 2
        if len(_wrap(text, mid)) <= n:
            hi = mid
        else:
            lo = mid + 1
    return _wrap(text, lo)


def _rect(x0: int, y0: int, x1: int, y1: int) -> str:
    return f"m {x0} {y0} l {x1} {y0} {x1} {y1} {x0} {y1}"


def _ts(t: float) -> str:
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _shape(start: float, end: float, color: str, path: str) -> str:
    return f"Dialogue: 1,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H{color}&}}{path}{{\\p0}}\n"


def _text(start: float, end: float, x: int, y: int, body: str) -> str:
    return f"Dialogue: 2,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{\\an5\\pos({x},{y})}}{body}\n"


def build_ass(phrases: list[tuple[float, float, str]]) -> str:
    ev = []
    for start, end, t in phrases:
        lines = _balanced(t.replace("*", ""))
        h = len(lines) * LINE_H + 2 * PAD_Y
        w = round(max(text_width(ln) for ln in lines) + 2 * PAD_X)
        x0, y0 = round((W - w) / 2), SUB_BOTTOM - h
        ev.append(_shape(start, end, BOX, _rect(x0, y0, x0 + w, y0 + h)))
        for i, ln in enumerate(lines):
            ev.append(_text(start, end, W // 2, y0 + PAD_Y + LINE_H * i + LINE_H // 2, ln))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Patrick Hand,{fs(CAP_EM)},&H00{INK},&H00{INK},&H00{INK},&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return head + "".join(ev)


COLOR = ("scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
         "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")


def render_pieces(ps, clean: Path, stills: list[tuple[Path, float, float]], ass: Path, audio: Path, total: float,
                  out: Path, outro: Path | None = OUTRO) -> None:
    """final.mp4 from NotebookLM's own video: each retime piece played, sped or held; patched stills `(file, from, to)`
    (output seconds) over it; the subtitles; then the `outro` clip faded in from the last frame. One ffmpeg run."""
    ins = ["-i", str(clean.resolve()), "-i", str(audio.resolve())]
    for f, _, _ in stills:
        ins += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(f.resolve())]
    one = 1 / FPS
    g = []
    for k, p in enumerate(ps):
        end = max(p.src_end, p.src + one)  # at least one frame to play, so there is one to hold
        g.append(f"[0:v]trim=start={p.src:.4f}:end={end:.4f},setpts=(PTS-STARTPTS)/{p.speed:.6f},fps={FPS},"
                 f"tpad=stop_mode=clone:stop_duration={p.hold + 2 * one:.4f},"
                 f"trim=duration={p.dst_end - p.dst:.4f},setpts=PTS-STARTPTS,fps={FPS}[p{k}]")  # trim forgets the rate
    g.append("".join(f"[p{k}]" for k in range(len(ps))) + f"concat=n={len(ps)}:v=1:a=0,fps={FPS},format=rgb24[v0]")
    last = "v0"
    for j, (_, a, b) in enumerate(stills):
        g.append(f"[{2 + j}:v]scale={W}:{H},format=rgb24[s{j}];"
                 f"[{last}][s{j}]overlay=0:0:format=rgb:enable='between(t,{a:.4f},{b:.4f})'[v{j + 1}]")
        last = f"v{j + 1}"
    g.append(f"[{last}]ass={ass.name}:fontsdir={FONTS},{COLOR}[m]")
    extra = probe(outro).duration if outro else 0.0
    if outro:
        g.append(f"[m]tpad=stop_mode=clone:stop_duration={XF},fps={FPS},settb=AVTB[mx];"  # xfade wants a set frame rate
                 f"[{2 + len(stills)}:v]fps={FPS},scale={W}:{H},format=rgb24,{COLOR},settb=AVTB[o];"
                 f"[mx][o]xfade=transition=fade:duration={XF}:offset={total:.4f}[v]")
        ins += ["-i", str(outro.resolve())]
    else:
        g.append("[m]null[v]")
    g.append("[1:a]apad[a]")
    tmp = out.resolve().with_name(f"{out.stem}.tmp{out.suffix}")  # a failed render must not replace a good `out`
    cmd = [FF, "-loglevel", "error", "-y", *ins, "-filter_complex", ";".join(g), "-map", "[v]", "-map", "[a]",
           "-t", f"{total + extra:.4f}", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp)]
    try:
        subprocess.run(cmd, check=True, cwd=ass.parent)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
