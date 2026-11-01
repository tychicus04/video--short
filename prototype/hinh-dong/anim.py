"""THROWAWAY SPIKE: hand-drawn explainer animation for Coruna lines 7-13."""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vshort.fit import Placement, phrase_times
from vshort.media import FF
from vshort.render import build_ass
from vshort.textfit import FONTS

RUN = Path.home() / "notebooklm-videos/coruna-darksword-en"
OUT = Path(sys.argv[1])
SS, W, H, FPS = 2, 720, 1280, 30
PAPER, INK, RED, GREEN, CYAN = (238, 234, 226), (62, 62, 68), (196, 48, 40), (60, 140, 80), (150, 205, 215)
T0, T1 = 15.55, 43.6
rng = np.random.default_rng(7)
grain = Image.fromarray((np.array(PAPER) + rng.normal(0, 2.2, (H * SS, W * SS, 1))).clip(0, 255).astype(np.uint8))


def font(em):
    return ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), em * SS)


def clamp(x):
    return max(0.0, min(1.0, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def wobble(pts, seed, amp=1.3):
    """Densify a polyline and push it sideways a little, like a hand-drawn pencil line."""
    pts = np.asarray(pts, float)
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(2, int(np.hypot(*(b - a)) / 4))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    out = np.array(out)
    d = np.gradient(out, axis=0)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1) / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9)
    s = np.arange(len(out))
    r = np.random.default_rng(seed)
    f1, f2, p1, p2 = r.uniform(0.02, 0.05), r.uniform(0.1, 0.2), r.uniform(0, 6), r.uniform(0, 6)
    off = amp * (np.sin(s * f1 + p1) + 0.4 * np.sin(s * f2 + p2))
    return out + nrm * off[:, None]


def stroke(d, pts, p, color=INK, width=3, seed=0, dash=None):
    if p <= 0:
        return
    q = wobble(pts, seed)
    seg = np.hypot(*np.diff(q, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    keep = cum <= cum[-1] * p
    q, cum = q[keep] * SS, cum[keep]
    if len(q) < 2:
        return
    for k in range(len(q) - 1):
        if dash and int(cum[k] // dash) % 2:
            continue
        d.line([tuple(q[k]), tuple(q[k + 1])], fill=color, width=width * SS)


def rrect(x0, y0, x1, y1, r):
    pts = []
    for cx, cy, a0 in [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]:
        for a in range(a0, a0 + 91, 10):
            pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
    return pts + [pts[0]]


def write(img, xy, text, em, p, color=INK, anchor="mm"):
    """Handwriting reveal: wipe the text in from left to right."""
    if p <= 0:
        return
    f = font(em)
    l, t, r, b = ImageDraw.Draw(img).textbbox((xy[0] * SS, xy[1] * SS), text, font=f, anchor=anchor)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] * SS, xy[1] * SS), text, font=f, fill=color, anchor=anchor)
    cut = int(l + (r - l + 4) * clamp(p))
    layer = layer.crop((0, 0, cut, img.size[1]))
    img.paste(layer, (0, 0), layer)


def dot(d, xy, r=9, color=RED, glow=0.0):
    x, y = xy[0] * SS, xy[1] * SS
    if glow:
        g = (r + 8 + 6 * glow) * SS
        d.ellipse((x - g, y - g, x + g, y + g), outline=color, width=2 * SS)
    d.ellipse((x - r * SS, y - r * SS, x + r * SS, y + r * SS), fill=color)


def along(pts, p):
    pts = np.asarray(pts, float)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = cum[-1] * clamp(p)
    k = min(np.searchsorted(cum, s, side="right") - 1, len(seg) - 1)
    return pts[k] + (pts[k + 1] - pts[k]) * ((s - cum[k]) / seg[k])


def bezier(a, c, b, n=24):
    return [tuple((1 - u) ** 2 * np.array(a) + 2 * (1 - u) * u * np.array(c) + u * u * np.array(b)) for u in np.linspace(0, 1, n)]


ICONS = [(185, 645, "mật khẩu"), (270, 645, "tin nhắn"), (355, 645, "ví tiền")]
PATH = [(300, 395), (420, 430), (420, 486), (420, 575), (420, 795), (420, 930), (405, 935)]


def icon(d, img, i, p, color):
    x, y, label = ICONS[i]
    if i == 0:  # key
        stroke(d, rrect(x - 22, y - 22, x - 2, y - 2, 10), p, color, seed=40)
        stroke(d, [(x - 4, y - 6), (x + 22, y + 20), (x + 14, y + 26), (x + 8, y + 20)], p, color, seed=41)
    elif i == 1:  # speech bubble
        stroke(d, rrect(x - 26, y - 22, x + 26, y + 12, 8) + [(x - 10, y + 12), (x - 18, y + 26), (x - 2, y + 12)], p, color, seed=42)
    else:  # wallet
        stroke(d, rrect(x - 26, y - 18, x + 26, y + 20, 5), p, color, seed=43)
        stroke(d, [(x + 6, y - 4), (x + 26, y - 4), (x + 26, y + 8), (x + 6, y + 8), (x + 6, y - 4)], p, color, seed=44)
    write(img, (x, y + 56), label, 24, p * 1.5 - 0.5, color)


def frame(t):
    img = grain.copy()
    d = ImageDraw.Draw(img)
    # line 7: the phone, a legitimate page, a hidden red dot
    stroke(d, rrect(110, 110, 470, 1060, 48), ease(t / 1.2), seed=1)
    stroke(d, rrect(135, 172, 445, 222, 14), ease((t - 0.6) / 0.6), seed=2)
    write(img, (290, 197), "tin-tuc.example", 27, (t - 1.0) / 0.6)
    for k, y in enumerate((260, 295, 330, 365, 430, 455)):
        stroke(d, [(155, y), (425 - 40 * (k % 3), y)], ease((t - 1.2 - 0.1 * k) / 0.4), (150, 150, 155), 2, seed=10 + k)
    stroke(d, [(560, 197), (452, 197)], ease((t - 1.5) / 0.4), GREEN, seed=3)
    stroke(d, [(452, 197), (468, 187)], ease((t - 1.8) / 0.2), GREEN, seed=4)
    write(img, (600, 165), "trang hợp pháp", 30, (t - 1.6) / 0.6, GREEN)
    # line 8: page finishes loading, the dot wakes up inside Safari
    stroke(d, [(140, 228), (440, 228)], ease((t - 2.9) / 0.9), (120, 120, 125), 4, seed=5)
    write(img, (165, 150), "Safari", 27, (t - 3.0) / 0.5, anchor="lm")
    pos, show_dot = PATH[0], t > 2.2
    # line 9: zero-click — no tap needed
    stroke(d, rrect(565, 560, 625, 640, 26), ease((t - 6.1) / 0.7), seed=6)
    stroke(d, [(552, 548), (640, 652)], ease((t - 6.9) / 0.4), RED, 4, seed=7)
    stroke(d, [(640, 548), (552, 652)], ease((t - 7.2) / 0.4), RED, 4, seed=8)
    write(img, (596, 690), "0 lần chạm", 32, (t - 7.3) / 0.7)
    # line 10: the sandbox, the system and its data, the kernel
    stroke(d, rrect(122, 152, 458, 488, 20), ease((t - 9.2) / 1.4), (70, 110, 160), 3, seed=9, dash=14)
    write(img, (175, 512), "sandbox", 31, (t - 10.4) / 0.7, (70, 110, 160))
    stroke(d, rrect(135, 560, 445, 795, 16), ease((t - 11.0) / 0.8), seed=20)
    write(img, (150, 580), "hệ thống", 27, (t - 11.4) / 0.5, anchor="lm")
    stroke(d, rrect(135, 860, 445, 1005, 16), ease((t - 12.0) / 0.7), seed=21)
    write(img, (250, 925), "lõi hệ điều hành", 30, (t - 12.4) / 0.6)
    owned = ease((t - 24.0) / 0.8)
    for i in range(3):
        icon(d, img, i, ease((t - 11.6 - 0.25 * i) / 0.6), INK)
    if 12.2 < t < 13.2:  # the dot bumps into the sandbox wall and bounces back
        u = (t - 12.2) / 1.0
        pos = (300 + 110 * math.sin(math.pi * u), 395 + 80 * math.sin(math.pi * u))
    # line 11: a chain of bugs breaks through the wall
    for k, y in enumerate((462, 492, 522)):
        stroke(d, rrect(408, y - 16, 432, y + 16, 11), ease((t - 13.5 - 0.35 * k) / 0.45), RED, 3, seed=30 + k)
    write(img, (525, 492), "chuỗi lỗ hổng", 29, (t - 14.2) / 0.7, RED)
    stroke(d, [(395, 488), (405, 480), (412, 492), (428, 482), (436, 494), (446, 486)], ease((t - 15.0) / 0.4), RED, 3, seed=35)
    if t > 15.4:
        pos = along(PATH[:4], ease((t - 15.4) / 1.2) * 1.0)
    # line 12: escalate step by step to the kernel
    if t > 17.15:
        u = clamp((t - 17.15) / 4.0)
        pos = along(PATH[3:], ease(u))
    stroke(d, [(395, 797), (405, 789), (414, 801), (428, 790), (437, 802), (446, 794)], ease((t - 18.6) / 0.4), RED, 3, seed=36)
    write(img, (470, 700), "bước 1", 28, (t - 17.6) / 0.5, RED, anchor="lm")
    write(img, (470, 840), "bước 2", 28, (t - 18.8) / 0.5, RED, anchor="lm")
    stroke(d, rrect(135, 860, 445, 1005, 16), ease((t - 20.4) / 0.9), RED, 5, seed=22)
    write(img, (290, 975), "đã bị chiếm", 29, (t - 20.8) / 0.6, RED)
    # line 13: the data leaves the phone for the attacker's server
    for i, (x, y, _) in enumerate(ICONS):
        stroke(d, [(405, 925), (x, y + 30)], ease((t - 21.8 - 0.3 * i) / 0.6), RED, 2, seed=50 + i, dash=10)
    if owned:
        for i in range(3):
            icon(d, img, i, owned, RED)
    stroke(d, rrect(520, 270, 690, 330, 8), ease((t - 22.8) / 0.5), seed=60)
    stroke(d, rrect(520, 335, 690, 395, 8), ease((t - 23.1) / 0.5), seed=61)
    for k, y in enumerate((300, 365)):
        if t > 23.6:
            dot(d, (545, y), 5, GREEN if (int(t * 4) + k) % 2 else (120, 120, 125))
    write(img, (605, 430), "máy chủ hacker", 30, (t - 23.4) / 0.7, RED)
    if t > 24.6:
        for i, (x, y, _) in enumerate(ICONS):
            path = bezier((x, y - 20), (470, 420 - 60 * i), (520, 330))
            for j in range(4):
                u = ((t - 24.6) * 0.7 + j * 0.25 + i * 0.08) % 1.0
                dot(d, along(path, u), 5)
    if show_dot:
        glow = 0.5 + 0.5 * math.sin(t * 6) if t > 3.8 else 0.0
        r = 9 * ease((t - 2.2) / 0.3)
        if r > 0.5:
            dot(d, pos, r, RED, glow)
    write(img, (300, 360) if t < 15.4 else (0, -100), "mã độc", 30, (t - 3.9) / 0.6, RED)
    return img.resize((W, H), Image.LANCZOS)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tl = json.loads((RUN / "timeline.json").read_text())
    pl = [Placement(p["id"], p["start"] - T0, p["dur"]) for p in tl["placements"] if 7 <= p["id"] <= 13]
    phrases = phrase_times(pl, json.loads((RUN / "script.vi.json").read_text()))
    ass = OUT.with_suffix(".ass")
    ass.write_text(build_ass(phrases), encoding="utf-8")
    with wave.open(str(RUN / "narration.wav")) as w:
        rate = w.getframerate()
        w.setpos(round(T0 * rate))
        audio = w.readframes(round((T1 - T0) * rate))
        params = w.getparams()
    wav = OUT.with_suffix(".wav")
    with wave.open(str(wav), "wb") as o:
        o.setparams(params)
        o.writeframes(audio)
    p = subprocess.Popen([FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", str(wav), "-vf", f"ass={ass.name}:fontsdir={FONTS}",
                          "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                          OUT.name], stdin=subprocess.PIPE, cwd=OUT.parent)
    for n in range(round((T1 - T0) * FPS)):
        p.stdin.write(frame(n / FPS).convert("RGB").tobytes())
    p.stdin.close()
    sys.exit(p.wait())


if __name__ == "__main__":
    main()
