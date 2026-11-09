"""Final video: NotebookLM's own video retimed to the new voice, fixed low subtitles in NotebookLM's caption style,
the magazine's title bar over the spoken title, its logo top right, the ANM outro in place of NotebookLM's."""
import math
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

from vshort.media import FF, probe
from vshort.textfit import FONTS, MAX_TEXT_W, UI_BOTTOM, UI_RIGHT, text_width

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
LOGO_XY, LOGO_W = (470, 24), 230  # the magazine's logo top right, in its own colours, the whole video (Tai, 07/11)
# the magazine's reel title bar, as in Tai's "Thanh tiêu đề short video.png" (3375x6000) scaled to 720x1280
STRIPE, BAR = (59, 680, 79, 843), (94, 680, 662, 843)
YELLOW, TEAL = (250, 255, 0, 255), (32, 107, 136, 255)
TITLE_XY = STRIPE[:2]  # the bar's clip is drawn from here
TEXT_L, TEXT_R = BAR[0] + 22, UI_RIGHT  # the title stays left of the platforms' buttons
TITLE_FONT = FONTS / "BeVietnamPro-ExtraBold.ttf"
TITLE_OUT = 0.65  # the box rolls back right to left in 0.45 s, then the stripe shrinks in 0.2 s


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


def title_fit(text: str) -> tuple[int, list[str]] | None:
    """(font size, lines) of the title in capitals: the biggest size that fits 2 lines, else 3 small ones; None when
    even that does not fit (then there is no bar and the subtitle keeps the line)."""
    text = " ".join(text.upper().split())
    for size in range(46, 23, -1):
        font = ImageFont.truetype(str(TITLE_FONT), size)
        lines, cur = [], ""
        for w in text.split():
            cand = f"{cur} {w}".strip()
            if cur and font.getlength(cand) > TEXT_R - TEXT_L:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
        if max(font.getlength(ln) for ln in lines) <= TEXT_R - TEXT_L and (len(lines) <= 2 or len(lines) == 3 and size <= 32):
            return size, lines
    return None


def title_times(start: float, end: float) -> tuple[float, float, float]:
    """(typing starts, typing ends, the bar starts to leave) for a title said from `start` to `end` s."""
    t0 = max(0.5, start)  # the box is open by 0.65 s
    t1 = max(t0 + 0.5, end - 0.1)
    return t0, t1, max(t1, end) + 0.3


def _ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def title_card(t: float, fit: tuple[int, list[str]], t0: float, t1: float, out: float) -> Image.Image:
    """The bar at t s, drawn from TITLE_XY: the stripe grows from its middle, the box wipes in left to right, the title
    is typed from t0 to t1 (a cursor only while typing), and from `out` the box rolls back right to left with its text,
    then the stripe shrinks."""
    size, lines = fit
    font = ImageFont.truetype(str(TITLE_FONT), size)
    x0, y0 = TITLE_XY
    img = Image.new("RGBA", (BAR[2] - x0 + 1, BAR[3] - y0 + 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stripe = min(_ease_out(t / 0.25), 1 - _ease_out((t - out - 0.45) / 0.2))
    box = min(_ease_out((t - 0.15) / 0.5), 1 - _ease_out((t - out) / 0.45))
    if stripe > 0:
        mid, half = (STRIPE[1] + STRIPE[3]) / 2 - y0, (STRIPE[3] - STRIPE[1]) / 2 * stripe
        d.rectangle((STRIPE[0] - x0, round(mid - half), STRIPE[2] - x0, round(mid + half)), fill=YELLOW)
    if box <= 0:
        return img
    right = round(BAR[0] + (BAR[2] - BAR[0]) * box) - x0
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rectangle((BAR[0] - x0, BAR[1] - y0, right, BAR[3] - y0), fill=TEAL)
    pitch = round(size * 1.32)
    y = (BAR[1] + BAR[3]) / 2 - pitch * len(lines) / 2 - y0
    n = round(sum(map(len, lines)) * max(0.0, min(1.0, (t - t0) / (t1 - t0))))
    cursor = (TEXT_L - x0, y)
    for ln in lines:
        if part := ln[:n]:
            ld.text((TEXT_L - x0, y), part, font=font, fill="white")
            cursor = (TEXT_L - x0 + font.getlength(part) + 8, y)
        n -= len(part)
        y += pitch
    if t0 <= t < t1:
        cx, cy = cursor
        ld.rectangle((cx, cy + size * 0.18, cx + max(3, size // 9), cy + size * 1.12), fill=YELLOW)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle((BAR[0] - x0, 0, right, img.height), fill=255)  # the rolled-back part takes its text
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    img.alpha_composite(layer)
    return img


def export_title(text: str, start: float, end: float, out: Path) -> bool:
    """The title bar for a title said from `start` to `end` s, as a clip with alpha from 0 s; False (and no clip) when
    the title does not fit the bar."""
    if (fit := title_fit(text)) is None:
        out.unlink(missing_ok=True)
        return False
    t0, t1, leave = title_times(start, end)
    w, h = title_card(0, fit, t0, t1, leave).size
    tmp = out.resolve().with_name(f"{out.stem}.tmp{out.suffix}")
    cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(FPS),
           "-i", "-", "-c:v", "png", str(tmp)]
    try:
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as p:
            for k in range(math.ceil((leave + TITLE_OUT) * FPS) + 1):
                p.stdin.write(title_card(k / FPS, fit, t0, t1, leave).tobytes())
            p.stdin.close()
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, cmd)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True


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
                  out: Path, outro: Path | None = OUTRO, title: Path | None = None) -> None:
    """final.mp4 from NotebookLM's own video: each retime piece played, sped or held; patched stills `(file, from, to)`
    (output seconds) over it; the `title` bar clip (export_title) and the logo over those; the subtitles; then the
    `outro` clip faded in from the last frame. One ffmpeg run."""
    ins = ["-i", str(clean.resolve()), "-i", str(audio.resolve())]
    for f, _, _ in stills:
        ins += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(f.resolve())]
    ins += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(LOGO)]
    if title:
        ins += ["-i", str(title.resolve())]
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
    k = 2 + len(stills)  # the logo's input, then the title's
    g.append(f"[{k}:v]scale={LOGO_W}:-1,format=rgba,fade=t=in:d=0.3:alpha=1[lg];"
             f"[{last}][lg]overlay={LOGO_XY[0]}:{LOGO_XY[1]}:format=rgb:eof_action=pass[vl]")
    last, k = "vl", k + 1
    if title:
        g.append(f"[{k}:v]format=rgba[tt];[{last}][tt]overlay={TITLE_XY[0]}:{TITLE_XY[1]}:format=rgb:eof_action=pass[vt]")
        last, k = "vt", k + 1
    g.append(f"[{last}]ass={ass.name}:fontsdir={FONTS},{COLOR}[m]")
    extra = probe(outro).duration if outro else 0.0
    if outro:
        g.append(f"[m]tpad=stop_mode=clone:stop_duration={XF},fps={FPS},settb=AVTB[mx];"  # xfade wants a set frame rate
                 f"[{k}:v]fps={FPS},scale={W}:{H},format=rgb24,{COLOR},settb=AVTB[o];"
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


def render_neon(visuals: Path, audio: Path, total: float, out: Path, outro: Path | None = OUTRO) -> None:
    """final.mp4 of the neon style: the diagram HyperFrames rendered (`visuals`, silent, `total` s), the voice with its accents
    (`audio`), in BT.709, then the `outro` clip faded in from the last frame. One ffmpeg run."""
    ins = ["-i", str(visuals.resolve()), "-i", str(audio.resolve())]
    extra = probe(outro).duration if outro else 0.0
    g = [f"[0:v]fps={FPS},scale={W}:{H},{COLOR}[m]"]
    if outro:
        g.append(f"[m]tpad=stop_mode=clone:stop_duration={XF},fps={FPS},settb=AVTB[mx];"  # xfade wants a set frame rate
                 f"[2:v]fps={FPS},scale={W}:{H},format=rgb24,{COLOR},settb=AVTB[o];"
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
        subprocess.run(cmd, check=True)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
