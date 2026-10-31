"""Final video: title bar, fixed bottom subtitles, clean plates, no watermark, no outro, new voice."""
import subprocess
from pathlib import Path

from vshort.captions import Fragment
from vshort.media import FF, probe
from vshort.plates import Plate
from vshort.textfit import FONTS, MAX_TEXT_W, text_width

W, H = 720, 1280
EM = 1000 / 1526  # libass sizes fonts by win ascent+descent; this font's em is 0.655 of that
LINE_H, CAP_EM, PAD_X, PAD_Y = 58, 40, 28, 26
MIN_BOX_W = 480  # widest old low caption is ~435 px: always cover it
SUB_BOTTOM = 1204  # every caption box sits on this line; old low captions span y 1101-1194
WHITE, YELLOW, BOX = "&HFFFFFF&", "&H00D4FF&", "&H121212&"
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


def _fix_stars(lines: list[str]) -> list[str]:
    """A highlight may span a line break: close it on one line, reopen it on the next."""
    out, open_ = [], False
    for ln in lines:
        s = ("*" if open_ else "") + ln
        open_ = s.count("*") % 2 == 1
        out.append(s + ("*" if open_ else ""))
    return out


def _colorize(line: str) -> str:
    parts = line.split("*")
    return "".join((f"{{\\1c{YELLOW}}}" if i % 2 else f"{{\\1c{WHITE}}}") + p for i, p in enumerate(parts) if p)


def _rrect(x0: int, y0: int, x1: int, y1: int, r: int) -> str:
    return (
        f"m {x0 + r} {y0} l {x1 - r} {y0} b {x1} {y0} {x1} {y0} {x1} {y0 + r} "
        f"l {x1} {y1 - r} b {x1} {y1} {x1} {y1} {x1 - r} {y1} "
        f"l {x0 + r} {y1} b {x0} {y1} {x0} {y1} {x0} {y1 - r} "
        f"l {x0} {y0 + r} b {x0} {y0} {x0} {y0} {x0 + r} {y0}"
    )


def _ts(t: float) -> str:
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _shape(start: float, end: float, color: str, path: str) -> str:
    return f"Dialogue: 1,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{color}}}{path}{{\\p0}}\n"


def _text(start: float, end: float, x: int, y: int, body: str, style: str = "Cap") -> str:
    return f"Dialogue: 2,{_ts(start)},{_ts(end)},{style},,0,0,0,,{{\\an5\\pos({x},{y})}}{body}\n"


def build_ass(phrases: list[tuple[float, float, str]], kicker: str, title: str, cut: float) -> str:
    ev = []
    for start, end, t in phrases:
        lines = _fix_stars(_balanced(t))
        h = len(lines) * LINE_H + 2 * PAD_Y
        w = max(max(text_width(ln) for ln in lines) + 2 * PAD_X, MIN_BOX_W)
        x0, y0 = round((W - w) / 2), SUB_BOTTOM - h
        ev.append(_shape(start, end, BOX, _rrect(x0, y0, x0 + round(w), y0 + h, 18)))
        for i, ln in enumerate(lines):
            ev.append(_text(start, end, W // 2, y0 + PAD_Y + LINE_H * i + LINE_H // 2, _colorize(ln)))
    ev.append(_shape(0, cut, BOX, _rrect(0, -20, W, 104, 0)))
    ev.append(_shape(0, cut, YELLOW, _rrect(0, 101, W, 104, 0)))
    ev.append(_text(0, cut, W // 2, 30, f"{{\\1c{YELLOW}\\fsp4}}{kicker}", "Kicker"))
    ev.append(_text(0, cut, W // 2, 70, title, "Title"))
    title_em = 38
    while text_width(title, title_em) > W - 48:
        title_em -= 1
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Be Vietnam Pro ExtraBold,{fs(CAP_EM)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Title,Be Vietnam Pro ExtraBold,{fs(title_em)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Kicker,Be Vietnam Pro Bold,{fs(20)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

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
