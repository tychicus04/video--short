"""THROWAWAY SPIKE v2: same lines 7-13, one idea per scene, few big elements, only the red dot moves."""
import math

from PIL import Image, ImageDraw

import anim as A
from anim import INK, RED, SS, clamp, dot, ease, font, rrect, stroke

BLUE, GREEN = (70, 110, 160), (60, 140, 80)
SCENES = [(0.0, 9.15), (9.15, 21.73), (21.73, 99)]  # lines 7-9 | 10-12 | 13
XF = 0.45


def write(img, xy, text, em, p, color=INK, anchor="mm"):
    """Handwriting reveal on a small layer (the full-frame layer of v1 was the slow part)."""
    if p <= 0:
        return
    f = font(em)
    l, t, r, b = ImageDraw.Draw(img).textbbox((xy[0] * SS, xy[1] * SS), text, font=f, anchor=anchor)
    l, t, r, b = int(l) - 4, int(t) - 4, int(r) + 4, int(b) + 4
    layer = Image.new("RGBA", (r - l, b - t), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] * SS - l, xy[1] * SS - t), text, font=f, fill=color, anchor=anchor)
    layer = layer.crop((0, 0, max(1, int((r - l) * clamp(p))), b - t))
    img.paste(layer, (l, t), layer)


def scene_web(img, d, t):
    """Lines 7-9: a phone opens a legitimate page; a red dot hidden in it wakes up."""
    write(img, (360, 110), "trang web hợp pháp", 44, (t - 1.4) / 0.8, GREEN)
    stroke(d, rrect(180, 170, 540, 1010, 50), ease(t / 1.2), seed=1)
    stroke(d, rrect(210, 235, 510, 295, 16), ease((t - 0.6) / 0.6), seed=2)
    write(img, (360, 265), "tin-tuc.example", 32, (t - 1.0) / 0.6)
    for k, y in enumerate((350, 400, 450, 500, 600, 650, 700)):
        stroke(d, [(230, y), (490 - 50 * (k % 3), y)], ease((t - 1.2 - 0.08 * k) / 0.4), (150, 150, 155), 3, seed=10 + k)
    stroke(d, [(215, 305), (505, 305)], ease((t - 2.9) / 1.0), (120, 120, 125), 5, seed=5)
    r = 11 * ease((t - 2.2) / 0.3) + (5 * ease((t - 3.8) / 0.6))
    if r > 0.5:
        dot(d, (400, 550), r, RED, 0.5 + 0.5 * math.sin(t * 5) if t > 3.8 else 0)
    write(img, (400, 620), "mã độc", 44, (t - 4.0) / 0.7, RED)


LAYERS = [(160, 350, "Safari"), (430, 620, "Hệ thống"), (700, 890, "Lõi (kernel)")]


def scene_layers(img, d, t):
    """Lines 10-12: three layers; the dot bounces off the sandbox, breaks through, takes each layer."""
    t -= 9.15
    for k, (y0, y1, label) in enumerate(LAYERS):
        stroke(d, rrect(120, y0, 600, y1, 22), ease((t - 0.2 - 0.9 * k) / 0.8), seed=20 + k)
        write(img, (300, (y0 + y1) / 2), label, 46, (t - 0.6 - 0.9 * k) / 0.6)
    stroke(d, rrect(95, 135, 625, 375, 30), ease((t - 1.2) / 1.2), BLUE, 4, seed=30, dash=18)
    write(img, (360, 108), "sandbox", 40, (t - 2.0) / 0.6, BLUE)
    taken = [ease((t - 7.4) / 0.8), ease((t - 11.0) / 0.8)]  # Hệ thống, then Lõi turn red
    for k, p in enumerate(taken, 1):
        y0, y1, label = LAYERS[k]
        stroke(d, rrect(120, y0, 600, y1, 22), p, RED, 6, seed=40 + k)
        write(img, (300, (y0 + y1) / 2), label, 46, p * 2, RED)
    write(img, (300, 860), "đã bị chiếm", 36, (t - 11.5) / 0.6, RED)
    crack = [(470, 375), (482, 364), (494, 386), (506, 364), (518, 386), (530, 375)]
    stroke(d, crack, ease((t - 5.6) / 0.5), RED, 5, seed=50)
    crack2 = [(x, y + 330) for x, y in crack]
    stroke(d, crack2, ease((t - 9.6) / 0.5), RED, 5, seed=51)
    # the dot: sits in Safari, bumps the wall and bounces (line 10), breaks through (11), goes down (12)
    x, y = 500, 255
    if 2.8 < t < 4.0:
        y = 255 + 95 * math.sin(math.pi * (t - 2.8) / 1.2)
    elif t >= 6.2:
        y = 255 + (525 - 255) * ease((t - 6.2) / 1.2)
    if t >= 9.8:
        y = 525 + (795 - 525) * ease((t - 9.8) / 1.2)
    dot(d, (x, y), 13 * ease((t - 1.0) / 0.4), RED, 0.5 + 0.5 * math.sin(t * 5))


def key(d, x, y, p, c, s):
    stroke(d, rrect(x - 40, y - 40, x, y, 18), p, c, 5, seed=s)
    stroke(d, [(x - 6, y - 10), (x + 40, y + 36), (x + 26, y + 48), (x + 14, y + 36)], p, c, 5, seed=s + 1)


def bubble(d, x, y, p, c, s):
    stroke(d, rrect(x - 48, y - 40, x + 48, y + 22, 14) + [(x - 18, y + 22), (x - 34, y + 48), (x - 4, y + 22)], p, c, 5, seed=s)


def wallet(d, x, y, p, c, s):
    stroke(d, rrect(x - 48, y - 34, x + 48, y + 36, 10), p, c, 5, seed=s)
    stroke(d, [(x + 10, y - 8), (x + 48, y - 8), (x + 48, y + 14), (x + 10, y + 14), (x + 10, y - 8)], p, c, 5, seed=s + 1)


ITEMS = [(key, "mật khẩu"), (bubble, "tin nhắn"), (wallet, "ví tiền")]


def scene_steal(img, d, t):
    """Line 13: passwords, messages and the wallet leave the phone for the attacker, one after another."""
    t -= 21.73
    stroke(d, rrect(60, 260, 300, 960, 40), ease(t / 0.8), RED, 5, seed=60)
    write(img, (180, 225), "điện thoại", 38, (t - 0.4) / 0.6, RED)
    stroke(d, rrect(440, 500, 660, 680, 20), ease((t - 0.8) / 0.7), seed=61)
    write(img, (550, 590), "hacker", 46, (t - 1.2) / 0.6)
    for k, (draw, label) in enumerate(ITEMS):
        x0, y0 = 180, 400 + 200 * k
        go = ease((t - 2.0 - 1.2 * k) / 1.1)
        x, y = x0 + (550 - x0) * go, y0 + (590 - y0) * go - 120 * math.sin(math.pi * go)
        if go < 1:
            c = RED if go > 0 else INK
            draw(d, x, y - 15, ease((t - 0.6 - 0.2 * k) / 0.6), c, 70 + 3 * k)
            write(img, (x, y + 55), label, 32, (t - 0.9 - 0.2 * k) / 0.5, c)


def frame(t):
    def render(k):
        img = A.grain.copy()
        [scene_web, scene_layers, scene_steal][k](img, ImageDraw.Draw(img), t)
        return img

    k = next(i for i, (a, b) in enumerate(SCENES) if t < b)
    img = render(k)
    a = SCENES[k][0]
    if k and t < a + XF:  # crossfade from the previous scene
        img = Image.blend(render(k - 1), img, (t - a) / XF)
    return img.resize((A.W, A.H), Image.LANCZOS)


A.write = write
A.frame = frame
if __name__ == "__main__":
    A.main()
