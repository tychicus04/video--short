"""Final video: fixed low subtitles in NotebookLM's caption style, clean plates, NotebookLM's watermark erased,
the ANM outro in place of NotebookLM's (the only logo), new voice."""
import math
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import groupby
from pathlib import Path

from PIL import Image

from vshort import kit, shots
from vshort.cards import Card, cap as card_cap
from vshort.fit import Placement
from vshort.media import FF, iter_frames, probe
from vshort.motion import Scene
from vshort.plates import Plate
from vshort.textfit import FONTS, MAX_TEXT_W, UI_BOTTOM, text_width

W, H = 720, 1280
FPS = 30
XF = 0.4  # crossfade between two images
ZOOM = 1.08  # deepest camera zoom; the pans run at this zoom
MIN_ZOOM = 1.01  # NotebookLM frames carry ~2 px of black at the left and right edges: the camera never shows them
EDGE = W * (1 - 1 / MIN_ZOOM) / 2  # px each side that MIN_ZOOM crops away; a pan stays this far from the image edges
EM = 1000 / 1354  # libass sizes fonts by win ascent+descent; Patrick Hand's em is 0.739 of that
LINE_H, CAP_EM, PAD_X, PAD_Y = 62, 50, 22, 12
SUB_BOTTOM = UI_BOTTOM - 11  # every caption box stands on this line, clear of the platforms' description (was centred
# at 1150, half under it); a two-line title grows upwards
INK, BOX = "3A3434", "D6DEE2"  # ASS BGR, sampled from NotebookLM's captions: dark grey ink on a light grey box
WATERMARK = "delogo=x=524:y=1232:w=180:h=32"
LOGO = Path(__file__).resolve().parent.parent / "assets" / "brand" / "anm-logo.png"
SHIELD_W = 185  # the logo's shield ends here; its words start at x 188
OUTRO = LOGO.with_name("anm-outro.mp4")  # appended to every video; `vshort outro` redraws it, or drop in any 720x1280 clip
OUTRO_S = 2.5  # length of the drawn outro


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
    p = kit.ease(t / 0.5)
    if p:
        s = shield.resize((max(1, round(shield.width * (0.7 + 0.3 * p))), max(1, round(shield.height * (0.7 + 0.3 * p)))))
        s.putalpha(s.getchannel("A").point(lambda a: round(a * p)))
        img.paste(s, (round((W - s.width) / 2), round(560 - s.height / 2)), s)
    if q := round(words.width * kit.ease((t - 0.5) / 0.8)):
        w = words.crop((0, 0, q, words.height))
        img.paste(w, ((W - words.width) // 2, 760), w)
    return img


def export_outro(out: Path = OUTRO) -> None:
    """end_card alone as an mp4 with a silent track (vshort's 24 kHz mono), to append to this or any other video."""
    paper = kit._paper().reduce(kit.SS)
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


def clean_video(src: Path, plates: list[Plate], plates_dir: Path, end: float, out: Path) -> None:
    """The source without watermark or old captions, picture only."""
    fps = probe(src).fps
    inputs, chain, last = [], [f"[0:v]{WATERMARK}[v0]"], "v0"
    for i, pl in enumerate(plates, 1):
        inputs += ["-i", str(plates_dir / f"{pl.name}.png")]
        n0, n1 = round(pl.start * fps), round(pl.end * fps)  # frame numbers: rounded seconds can miss a frame
        chain.append(f"[{last}][{i}:v]overlay={pl.x}:{pl.y}:enable='between(n,{n0},{n1 - 1})'[v{i}]")
        last = f"v{i}"
    subprocess.run(
        [FF, "-loglevel", "error", "-y", "-i", str(src), *inputs, "-t", str(end),
         "-filter_complex", ";".join(chain), "-map", f"[{last}]", "-an",
         "-c:v", "libx264", "-crf", "12", "-preset", "medium", "-pix_fmt", "yuv420p", str(out.resolve())],
        check=True,
    )


@dataclass(frozen=True)
class Segment:
    id: int
    start: float
    end: float
    file: Path
    group: str  # consecutive segments with the same group are one camera shot
    scene: int | None = None  # animated: drawn from this motion scene, no camera
    plan: tuple[shots.Beat, ...] | None = field(default=None, compare=False)  # its beats: a Beat holds dicts, so no hashing
    card: Path | None = None  # the svg that writes itself out in place of `file`, only on a line with a plan
    cap: float = shots.MAX_ZOOM_STILL  # the most its planned camera may zoom


def segments(placements: list[Placement], frames: list[dict], run_dir: Path, total: float,
             animated: dict[int, int] | None = None, planned: dict[int, tuple[shots.Beat, ...]] | None = None,
             cards: dict[int, Path] | None = None) -> list[Segment]:
    """One segment per voice; a cut sits in the middle of the gap between two voices.

    `animated` maps a line id to the motion scene that draws it; `planned` a line id to its beats, `cards` the planned
    lines that are a reference card to the svg.
    """
    by_id, animated, planned, cards = {f["id"]: f for f in frames}, animated or {}, planned or {}, cards or {}
    cuts = [0.0] + [(a.start + a.dur + b.start) / 2 for a, b in zip(placements, placements[1:])] + [total]
    out = []
    for p, s, e in zip(placements, cuts, cuts[1:]):
        file, group, scene = run_dir / by_id[p.id]["file"], by_id[p.id]["group"], animated.get(p.id)
        if scene is not None:
            out.append(Segment(p.id, s, e, file, f"m{scene}", scene))
        elif p.id in planned:
            svg = cards.get(p.id)
            out.append(Segment(p.id, s, e, file, f"n{p.id}", None, planned[p.id], svg,
                               card_cap(Card(svg, s, e, XF)) if svg else shots.MAX_ZOOM_STILL))
        else:
            out.append(Segment(p.id, s, e, file, group))
    return out


def _kinds(groups: list[str]) -> list[int]:
    """Camera move of each shot (0 zoom in, 1 zoom out, 2 pan right, 3 pan left, -1 none); no two neighbours alike.

    Stills rotate through the four, skipping the move the shot before them made. References only zoom (a pan at ZOOM
    shows 667 of 720 px and would cut their credit line): opposite to the shot before, or to the last reference
    when that shot panned. Animated shots have no camera and a planned line (n) has its own: both leave the rotation alone.
    """
    kinds, turn, last_ref = [], 0, 1
    for g in groups:
        prev = kinds[-1] if kinds else None
        if g.startswith(("m", "n")):
            k = -1
        elif g.startswith("v"):
            k = last_ref = 1 - (prev if prev in (0, 1) else last_ref)
        else:
            k = turn % 4
            turn += 1
            if k == prev:
                k = turn % 4
                turn += 1
        kinds.append(k)
    return kinds


def _camera(segs: list[Segment], k: int, t: float) -> tuple[float, float, float]:
    """(scale, cx, cy) of the shot segment k belongs to: window centre in frame pixels, linear in time over the shot.

    A shot under 3 s moves proportionally less, so it never rushes. A planned line follows its beats instead.
    """
    if segs[k].plan is not None:
        return shots.camera_at(segs[k].plan, t, segs[k].start - XF / 2, segs[k].cap)
    lo = hi = k
    while lo and segs[lo - 1].group == segs[k].group:
        lo -= 1
    while hi + 1 < len(segs) and segs[hi + 1].group == segs[k].group:
        hi += 1
    shot = sum(a.group != b.group for a, b in zip(segs, segs[1:k + 1]))  # which shot segment k belongs to
    kind = _kinds([g for g, _ in groupby(s.group for s in segs)])[shot]
    if kind < 0:
        return 1.0, W / 2, H / 2
    amp = min(1, (segs[hi].end - segs[lo].start) / 3)
    t0, t1 = segs[lo].start - XF / 2, segs[hi].end + XF / 2
    p = min(max((t - t0) / (t1 - t0), 0), 1)
    if kind < 2:
        return MIN_ZOOM + (ZOOM - MIN_ZOOM) * amp * (p if kind == 0 else 1 - p), W / 2, H / 2
    travel = (W - W / ZOOM - 2 * EDGE) * amp
    return ZOOM, W / 2 + travel * ((p if kind == 2 else 1 - p) - 0.5), H / 2


def _half_fade(segs: list[Segment], k: int) -> float:
    """Half the crossfade at the cut before segment k, at most a third of the shorter neighbour."""
    return min(XF, *((s.end - s.start) / 3 for s in segs[k - 1:k + 1])) / 2


def view(segs: list[Segment], t: float) -> list[tuple[Segment, float, tuple[float, float, float]]]:
    """The 1-2 segments visible at t: (segment, blend weight, camera)."""
    k = next((i for i, s in enumerate(segs) if t < s.end), len(segs) - 1)
    s = segs[k]
    h0 = _half_fade(segs, k) if k else 0
    h1 = _half_fade(segs, k + 1) if k + 1 < len(segs) else 0
    if t < s.start + h0:
        w = (t - s.start + h0) / (2 * h0)
        parts = [(k - 1, 1 - w), (k, w)]
    elif t >= s.end - h1:
        w = (t - s.end + h1) / (2 * h1)
        parts = [(k, 1 - w), (k + 1, w)]
    else:
        parts = [(k, 1.0)]
    return [(segs[i], w, _camera(segs, i, t)) for i, w in parts]


def draw(img: Image.Image, scale: float, cx: float, cy: float) -> Image.Image:
    """The window around (cx, cy) in frame pixels, 1/scale of the frame, resampled to W x H at sub-pixel precision."""
    ww, wh = W / scale, H / scale
    x0 = min(max(cx - ww / 2, 0), W - ww)  # never past the image edge
    y0 = min(max(cy - wh / 2, 0), H - wh)
    sx, sy = img.width / W, img.height / H  # a still of another size is stretched to the frame, not left misaligned
    # float box = sub-pixel window; same result as an affine transform but ~4x faster (26 vs 100 ms per frame)
    box = (x0 * sx, y0 * sy, min((x0 + ww) * sx, img.width), min((y0 + wh) * sy, img.height))
    return img.resize((W, H), Image.BICUBIC, box=box)


class _Planned:
    """The picture of a line with a beat plan, before the camera: its frame (a card writes itself out) with the pencil of
    the beats drawn on. Everything is judged by the finished card, as `vshort shots` judged it. Once nothing on it moves
    any more it is composited one last time and kept: drawing the pencil costs ~20 ms a frame. (ponytail: between two
    beats it is drawn every frame too; keep it across each such pause if renders get slow.)"""

    def __init__(self, seg: Segment, still: Image.Image | None, run_dir: Path | None):
        self.seg, self.run_dir, self.kept = seg, run_dir, None
        self.card = Card(seg.card, seg.start, seg.end, XF) if seg.card else None
        self.still = still if self.card is None else self.card.frame(seg.end)  # a card's finished picture is its still
        self.ref = self.still if self.card else None  # stills and photos judge themselves
        self.done = max(shots.settled(seg.plan), self.card.done if self.card else 0.0)

    def picture(self, t: float) -> Image.Image:
        if self.kept is None:
            base = self.card.frame(t) if self.card and t < self.card.done else self.still
            img = shots.draw_overlays(base, self.seg.plan, t, self.run_dir, ref=self.ref)
            if t < self.done:
                return img
            self.kept = img
        return self.kept


def render_video(segs: list[Segment], ass: Path, narration: Path, total: float, out: Path,
                 scenes: list[Scene] = (), outro: Path | None = None, run_dir: Path | None = None) -> None:
    """`total` s of lines, then the `outro` clip faded in from the last frame, silent. `run_dir`: where the run's own
    shapes are, for the doodles of planned lines."""
    cache: dict[Path, Image.Image] = {}
    planned: dict[int, _Planned] = {}  # the lines on screen that have a plan, by id

    def load(f: Path) -> Image.Image:
        if f not in cache:
            cache[f] = Image.open(f).convert("RGB")
        return cache[f]

    def image(s: Segment, cam, t: float) -> Image.Image:
        if s.scene is not None:
            sc = scenes[s.scene]
            return kit.draw(sc.things, sc.acts, t)
        if s.plan is None:
            return draw(load(s.file), *cam)
        if s.id not in planned:
            planned[s.id] = _Planned(s, None if s.card else load(s.file), run_dir)
        return draw(planned[s.id].picture(t), *cam)

    def frame(t: float) -> Image.Image:
        parts = view(segs, t)
        for gone in planned.keys() - {s.id for s, _, _ in parts}:
            del planned[gone]  # past (the video only goes forward): its pictures are not needed any more
        if len(parts) == 2 and parts[0][0].scene is not None and parts[0][0].scene == parts[1][0].scene:
            parts = parts[1:]  # two lines of one scene: the same picture, drawn once
        imgs = [(image(s, cam, t), w) for s, w, cam in parts]
        img = imgs[0][0] if len(imgs) == 1 else Image.blend(imgs[0][0], imgs[1][0], imgs[1][1])
        return img

    tail = iter_frames(outro, fps=FPS, gray=False) if outro else iter(())
    extra = probe(outro).duration if outro else 0.0
    last = end = None
    tmp = out.resolve().with_name(f"{out.stem}.tmp{out.suffix}")  # a failed render must not replace a good `out`
    cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(narration.resolve()),
           # BT.709 matrix and tags: untagged HD plays as 709 in browsers and phones, swscale's default is 601
           "-vf", f"ass={ass.name}:fontsdir={FONTS},scale=out_color_matrix=bt709:out_range=tv,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv", "-af", "apad",
           "-map", "0:v", "-map", "1:a", "-t", str(total + extra), "-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp)]
    try:
        with subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=ass.parent) as p:
            try:
                for n in range(math.ceil((total + extra) * FPS)):
                    t = n / FPS
                    if t < total:
                        img = last = frame(t)
                    else:
                        if (f := next(tail, None)) is not None:  # one short: hold its last frame
                            end = Image.fromarray(f[1]).resize((W, H), Image.LANCZOS)  # no-op on a 720x1280 clip
                        img = end
                        if last is not None and t - total < XF:
                            img = Image.blend(last, img, (t - total) / XF)
                    p.stdin.write(img.tobytes())
                p.stdin.close()
            except BrokenPipeError:
                pass  # ffmpeg died; its exit code below says why
            except BaseException:
                p.kill()  # closing stdin would let ffmpeg finish a short video with exit 0
                raise
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, cmd)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
