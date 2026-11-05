"""Spike #2: shot lists for window A (lines 1-2) and window B (lines 9-12), render, compare. Usage:
  build2.py prev A|B t1 t2 ...   -> out2/prev_<w>.png montage with UI-zone guides
  build2.py render A|B           -> out2/<w>_after.mp4 (+ compare)
"""
import json, re, subprocess, sys, time
from pathlib import Path
from engine2 import *
from vshort.media import FF

O = Path(S) / "out2"
XFD = 0.2  # crossfade length at a cut


def build(win):
    if win == "A":
        w1, w2 = StillWorld(f"{S}/frames/1.png"), StillWorld(f"{S}/frames/2.png")
        s1 = Seg(0, 3.21, w1,
                 [Key(0.0, 360, 640, 1.02, 360, 640, 0.02),
                  Key(0.8, 250, 745, 1.5, 330, 600),
                  Key(1.7, 250, 740, 1.15, 345, 600),
                  Key(2.45, 250, 650, 1.3, 345, 560)],
                 [arrow(bez((350, 470), (340, 520), (300, 555), (262, 598)), 11, 0.05, 0.55, out=1.65),
                  one(circle(409, 708, 30), 12, 1.2, 0.4, 5, out=1.65),
                  one(ellipse(250, 745, 205, 185, tilt=-0.02), 13, 1.7, 0.5, out=2.55),
                  one(ellipse(250, 745, 115, 98, tilt=0.03, start=-30), 14, 1.95, 0.35, out=2.55),
                  one(circle(250, 745, 9), 15, 2.2, 0.2, 5, out=2.55)],
                 [Pop("$", (150, 470), 200, 2.45)])
        s2 = Seg(3.21, 8.96, w2,
                 [Key(3.21, 360, 600, 1.02, 360, 600, 0.02),
                  Key(3.5, 360, 590, 1.22, 360, 590),
                  Key(3.95, 270, 545, 1.6, 345, 560),
                  Key(4.85, 480, 575, 1.5, 330, 570),
                  Key(5.55, 470, 500, 1.35, 340, 620),
                  Key(6.15, 360, 600, 1.02, 360, 600, 0.02),
                  Key(7.58, 480, 705, 1.6, 330, 580)],
                 [one(ellipse(268, 560, 125, 95, tilt=-0.05), 21, 3.95, 0.7, out=4.9),
                  one(ellipse(480, 562, 112, 98), 22, 4.95, 0.6, out=5.9),
                  one(star(585, 345, 36), 23, 5.5, 0.45, out=6.2),
                  one(ellipse(360, 615, 262, 165), 24, 6.5, 0.55, out=7.5),
                  one(ellipse(360, 615, 215, 125, start=-20), 25, 6.9, 0.45, out=7.5),
                  one(ellipse(480, 706, 108, 40, tilt=-0.02), 26, 7.6, 0.55)])
        return [s1, s2], [3.21], (0.0, 8.96)
    # ---- window B
    sch9 = [("<bar>", 38.95, 39.25), ("“", 38.9, 39.1), ("Nguồn", 38.7, 39.1), ("Cut off", 39.0, 39.6),
            ("to the Internet", 39.55, 40.0), ("(unless", 40.0, 40.5), ("what you", 40.45, 40.9),
            ("remove port", 40.9, 41.35), ("to the DSM", 41.05, 41.5), ("and use", 41.8, 42.3)]
    c9 = CardWorld(f"{S}/visuals/khong-lo-giao-dien.svg", sch9)
    l1, l2, l6 = c9.find("Cut off"), c9.find("to the Internet"), c9.find("to the DSM")
    xa, xb = l6.span(2, 4)
    s9 = Seg(38.3, 45.97, c9,
             [Key(38.3, 360, 590, 1.02, 360, 600, 0.02),
              Key(39.0, 360, 495, 1.5, 360, 520),
              Key(40.15, 360, 600, 1.12, 360, 600),
              Key(41.0, 360, 640, 1.25, 330, 520),
              Key(42.1, 360, 505, 1.45, 360, 470),
              Key(43.3, 360, 640, 1.05, 360, 640),
              Key(44.7, 505, 900, 1.4, 340, 560)],
             [one(rrect(60, 330, 660, 850, 18), 5, 38.55, 0.7, 4),
              one(ellipse((xa + xb) / 2, 711, (xb - xa) / 2 + 20, 25, tilt=-0.02), 31, 41.3, 0.5, 5, out=42.1),
              one([(l1.box()[0], 491), (l1.box()[2] * .5 + l1.box()[0] * .5, 493), (l1.box()[2], 490)], 32, 42.1, 0.35, 5, out=43.3),
              one([(l2.box()[0], 539), (l2.box()[2], 538)], 33, 42.45, 0.3, 5, out=43.3),
              one([(455, 892), (482, 932), (555, 874)], 34, 43.4, 0.45, 7),
              one(ellipse(505, 905, 82, 64), 35, 44.75, 0.5)])
    sch10 = [("<bar>", 46.1, 46.4), ("“", 46.05, 46.25), ("Nguồn", 45.95, 46.3), ("Synology strongly", 46.4, 47.0),
             ("running", 47.0, 47.5), ("update DSM", 47.5, 48.2), ("their systems", 48.2, 48.55)]
    c10 = CardWorld(f"{S}/visuals/cap-nhat-ngay.svg", sch10)
    u = c10.find("update DSM")
    ua, ub = u.span(0, 3)
    ia, ib = u.span(2, 3)
    s10 = Seg(45.97, 50.33, c10,
              [Key(45.97, 360, 590, 1.02, 360, 600, 0.02),
               Key(46.3, 360, 583, 1.18, 360, 500),
               Key(47.2, 360, 655, 1.18, 360, 500),
               Key(48.55, 360, 610, 1.2, 360, 590),
               Key(49.3, 360, 645, 1.15, 360, 520)],
              [one(rrect(60, 400, 660, 780, 18), 6, 45.97, 0.6, 4),
               one(ellipse((ua + ub) / 2, 643, (ub - ua) / 2 + 14, 27, tilt=-0.02, n=2.4), 41, 48.7, 0.55, 5),
               one([(ia, 664), (ib, 662)], 42, 49.4, 0.35, 5),
               one([(ia, 671), (ib, 670)], 43, 49.75, 0.3, 5)])
    sch11 = [("<bar>", 50.4, 50.65), ("“", 50.35, 50.5), ("Nguồn", 50.35, 50.6), ("Synology also", 50.45, 50.95),
             ("automatic updates", 50.9, 51.35), ("up to date", 51.35, 51.8)]
    c11 = CardWorld(f"{S}/visuals/bat-tu-dong.svg", sch11)
    e1, e2 = c11.find("Synology also"), c11.find("automatic updates")
    ea, eb = e1.span(3, 4)
    fa, fb = e2.span(0, 2)
    person = lambda cx: [(cx - 18, 948), (cx - 14, 925), (cx, 918), (cx + 14, 925), (cx + 18, 948)]
    c11.dim = (53.7, 54.0, 0.55)
    s11 = Seg(50.33, 57.39, c11,
              [Key(50.33, 360, 590, 1.02, 360, 600, 0.02),
               Key(50.5, 360, 585, 1.18, 360, 500),
               Key(51.45, 360, 760, 1.15, 350, 600),
               Key(52.75, 150, 900, 1.6, 330, 560),
               Key(53.8, 360, 800, 1.1, 360, 600),
               Key(55.0, 450, 905, 1.5, 340, 560),
               Key(56.3, 560, 905, 1.5, 330, 560)],
              [one(rrect(60, 400, 660, 780, 18), 7, 50.33, 0.55, 4),
               one([(ea, 570), (eb, 569)], 51, 50.75, 0.25, 5, out=53.7),
               one([(fa, 616), (fb, 615)], 52, 51.0, 0.4, 5, out=53.7),
               multi([circle(150, 900, 52), ellipse(150, 900, 52, 16, start=180, sweep=360, grow=0),
                      ellipse(150, 900, 20, 52, start=-90, sweep=360, grow=0)], 53, 51.45, 0.6, 5),
               multi([[(105, 855), (195, 945)], [(195, 855), (105, 945)]], 54, 52.1, 0.35, 7),
               multi([[(285, 905), (275, 905), (275, 955), (335, 955), (335, 935)],
                      bez((300, 935), (310, 900), (330, 880), (357, 858), 20)], 55, 53.85, 0.6, 5),
               Mark([(h, 56 + j, 0, 1) for j, h in enumerate(head(bez((300, 935), (310, 900), (330, 880), (357, 858), 20)))],
                    54.4, 0.2, 5),
               multi([[(415, 915), (415, 960), (485, 960), (485, 915)], [(405, 918), (450, 875), (495, 918)],
                      [(440, 960), (440, 935), (460, 935), (460, 960)]], 60, 55.0, 0.6, 5),
               multi([circle(535, 893, 13), circle(570, 885, 13), circle(605, 893, 13), person(535), person(570), person(605)],
                     70, 56.3, 0.6, 5)])
    sch12 = [("<dot1>", 57.39, 57.6), ("<dot2>", 60.85, 61.05), ("October", 57.45, 57.85), ("Synology has", 57.8, 58.15),
             ("exploiting", 58.1, 58.4), ("December", 58.35, 58.6), ("Synology-SA", 60.95, 61.4),
             ("Publish Time", 61.35, 61.6), ("2024-11-05", 61.55, 61.95), ("Nguồn", 57.4, 57.7)]
    c12 = CardWorld(f"{S}/visuals/moc-va.svg", sch12)
    d, sa = c12.find("December"), c12.find("Synology-SA")
    da, _, db, _ = d.box()
    sa0, _, sa1, _ = sa.box()
    pw = pfont(200).getlength("2024")
    s12 = Seg(57.39, 62.74, c12,
              [Key(57.39, 392, 540, 1.2, 335, 470, 0.02),
               Key(58.4, (da + db) / 2, 575, 1.8, 330, 520),
               Key(59.2, 360, 600, 1.02, 360, 600, 0.02),
               Key(60.0, 300, 640, 1.15, 340, 600),
               Key(60.95, 320, 800, 1.3, 340, 540),
               Key(61.9, 360, 640, 1.02, 360, 640, 0.02)],
              [one([(140, 494), (140, 776)], 81, 59.95, 0.9, 4),
               one(ellipse((da + db) / 2, 577, (db - da) / 2 + 22, 14, tilt=-0.02, n=2.4), 82, 58.6, 0.6, 5),
               one([(sa0, 802), (sa1, 800)], 83, 61.3, 0.4, 5),
               one([(sa0, 809), (sa1 * .7 + sa0 * .3, 808)], 84, 61.55, 0.25, 5),
               one([(385 - pw / 2, 392), (385 + pw / 2, 388)], 85, 59.85, 0.4, 6)],
              [Pop("2024", (385, 290), 200, 59.3)])
    return [s9, s10, s11, s12], [45.97, 50.33, 57.39], (38.3, 62.74)


def frame_at(segs, cuts, t):
    k = sum(t >= c for c in cuts)
    for i, c in enumerate(cuts):
        if abs(t - c) < XFD / 2:
            w = (t - c + XFD / 2) / XFD
            return Image.blend(segs[i].render(t), segs[i + 1].render(t), w)
    return segs[k].render(t)


def check_rule(segs, w0, w1):
    iv = sorted(x for s in segs for x in s.activity())
    edges = [(w0, w0)] + [(a, b) for a, b in iv if b > w0 and a < w1]
    worst, t = [], w0
    for a, b in edges:
        if a - t > 1.0:
            worst.append((round(t, 2), round(a, 2), round(a - t, 2)))
        t = max(t, b)
    if w1 - t > 1.0:
        worst.append((round(t, 2), round(w1, 2), round(w1 - t, 2)))
    return worst


def guides(img):
    d = ImageDraw.Draw(img, "RGBA")
    d.line([(0, 141), (W, 141)], fill=(255, 0, 0, 120), width=1)
    d.line([(618, 535), (618, H)], fill=(255, 0, 0, 120), width=1)
    d.rectangle([0, 1076, W, 1224], fill=(0, 100, 255, 60))
    return img


def preview(win, times):
    segs, cuts, (w0, w1) = build(win)
    tiles = [guides(frame_at(segs, cuts, t)).resize((360, 640)) for t in times]
    cols = 6
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (360 * cols, 640 * rows), (255, 255, 255))
    for i, im in enumerate(tiles):
        sheet.paste(im, (360 * (i % cols), 640 * (i // cols)))
        ImageDraw.Draw(sheet).text((360 * (i % cols) + 6, 640 * (i // cols) + 4), f"{times[i]:.2f}", fill=(255, 0, 0))
    sheet.save(O / f"prev_{win}.png")
    print("gaps>1s:", check_rule(segs, w0, w1))


def shift_ass(src, dst, w0, dur):
    def ts(s):
        h, m, x = s.split(":")
        return int(h) * 3600 + int(m) * 60 + float(x)

    def fmt(v):
        return f"{int(v // 3600)}:{int(v % 3600 // 60):02d}:{v % 60:05.2f}"

    out = []
    for line in open(src).read().splitlines():
        if line.startswith("Dialogue:"):
            head_, a, b, rest = re.match(r"(Dialogue: \d+),([\d:.]+),([\d:.]+),(.*)", line).groups()
            a, b = ts(a) - w0, ts(b) - w0
            if b <= 0 or a >= dur:
                continue
            line = f"{head_},{fmt(max(a, 0))},{fmt(min(b, dur))},{rest}"
        out.append(line)
    Path(dst).write_text("\n".join(out) + "\n")


def render(win):
    segs, cuts, (w0, w1) = build(win)
    dur = round(w1 - w0, 3)
    n = round(dur * FPS)
    name = win.lower()
    shift_ass(f"{S}/subs.ass", O / f"{name}.ass", w0, dur)
    out = O / f"{name}_after.mp4"
    cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-ss", str(w0), "-t", str(dur), "-i", f"{S}/narration.wav",
           "-vf", f"ass={name}.ass:fontsdir={FONTS},scale=out_color_matrix=bt709:out_range=tv,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-map", "0:v", "-map", "1:a", "-t", str(dur), "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    t0 = time.time()
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=O) as p:
        for i in range(n):
            p.stdin.write(frame_at(segs, cuts, w0 + i / FPS).tobytes())
        p.stdin.close()
    el = time.time() - t0
    print(f"{win}: {dur}s video rendered+encoded in {el:.0f}s = {el / dur:.1f}s per video second", flush=True)
    # compare: before (cut from final.mp4) | after
    lab = lambda txt: (f"drawtext=fontfile={FONTS}/PatrickHand-Regular.ttf:text='{txt}':fontsize=44:fontcolor=0x2b2b2b:"
                       "box=1:boxcolor=0xEEEAE2@0.85:boxborderw=10:x=(w-text_w)/2:y=24")
    fc = f"[0:v]scale=720:1280,{lab('Hiện tại')}[l];[1:v]{lab('Mới')}[r];[l][r]hstack=inputs=2[v]"
    subprocess.run([FF, "-loglevel", "error", "-y", "-ss", str(w0), "-t", str(dur), "-i", f"{S}/final.mp4", "-i", str(out),
                    "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-t", str(dur), "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    str(O / f"{name}_compare.mp4")], check=True)


if __name__ == "__main__":
    if sys.argv[1] == "prev":
        preview(sys.argv[2], [float(x) for x in sys.argv[3:]])
    elif sys.argv[1] == "render":
        for w in sys.argv[2:]:
            render(w)
