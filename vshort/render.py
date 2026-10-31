"""Final video: fixed low subtitles in NotebookLM's caption style, clean plates, no watermark, no outro, new voice."""
import subprocess
from pathlib import Path

from vshort.captions import Fragment
from vshort.media import FF, probe
from vshort.plates import Plate
from vshort.textfit import FONTS, MAX_TEXT_W, text_width

W, H = 720, 1280
EM = 1000 / 1354  # libass sizes fonts by win ascent+descent; Patrick Hand's em is 0.739 of that
LINE_H, CAP_EM, PAD_X, PAD_Y = 62, 50, 22, 12
SUB_Y = 1150  # every caption box is centred here, on NotebookLM's own low caption band
INK, BOX = "3A3434", "D6DEE2"  # ASS BGR, sampled from NotebookLM's captions: dark grey ink on a light grey box
WATERMARK = "delogo=x=524:y=1232:w=180:h=32"


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
        x0, y0 = round((W - w) / 2), round(SUB_Y - h / 2)
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


def outro_cut(frags: list[Fragment], cuts: list[float], duration: float, blank: float | None = None) -> float:
    """The NotebookLM logo outro starts at the first scene cut or blank frame after the last caption."""
    last = max(f.end for f in frags)
    after = [c for c in cuts if c >= last - 1e-3] + ([blank] if blank is not None else [])
    return min(after, default=duration)


def compose(src: Path, narration: Path, ass: Path, plates: list[Plate], plates_dir: Path, cut: float, out: Path) -> None:
    fps = probe(src).fps
    inputs, chain, last = [], [f"[0:v]{WATERMARK}[v0]"], "v0"
    for i, pl in enumerate(plates, 2):
        inputs += ["-i", str(plates_dir / f"{pl.name}.png")]
        n0, n1 = round(pl.start * fps), round(pl.end * fps)  # frame numbers: rounded seconds can miss a frame
        chain.append(f"[{last}][{i}:v]overlay={pl.x}:{pl.y}:enable='between(n,{n0},{n1 - 1})'[v{i}]")
        last = f"v{i}"
    chain.append(f"[{last}]ass={ass.name}:fontsdir={FONTS}[out]")
    subprocess.run(
        [FF, "-loglevel", "error", "-y", "-i", str(src), "-i", str(narration), *inputs, "-t", str(cut),
         "-filter_complex", ";".join(chain), "-map", "[out]", "-map", "1:a",
         "-af", f"afade=t=out:st={max(cut - 0.25, 0)}:d=0.25",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out.resolve())],
        cwd=ass.parent, check=True,
    )
