import subprocess
from pathlib import Path

import numpy as np
from conftest import write_silence
from PIL import Image

from vshort.fit import Placement
from vshort.media import FF, frame_at, probe
from vshort.render import FPS, Segment, build_ass, draw, render_video, segments, view


def test_build_ass_layout():
    a = build_ass([(0, 2, "Câu mở đầu dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài"),
                   (2, 3, "*Zero-click.*")])
    assert "Style: Cap,Patrick Hand,68," in a  # fs(50)
    assert a.endswith("}Zero-click.\n")  # old * highlights are dropped, not drawn
    assert a.count("Dialogue: 2,0:00:00.00,0:00:02.00,Cap") >= 2  # first sentence wraps to ≥2 lines
    assert "Title" not in a and "Kicker" not in a


def _segs(*spans):
    """(start, end, group) -> segments with distinct files."""
    return [Segment(i, a, b, Path(f"f{i}.png"), g) for i, (a, b, g) in enumerate(spans)]


def _win(cam):
    """Source window edges (x0, x1, y0, y1) of a camera on a 720x1280 frame."""
    s, cx, cy = cam
    return cx - 360 / s, cx + 360 / s, cy - 640 / s, cy + 640 / s


def test_motion_is_subpixel_smooth():
    img = Image.new("RGB", (720, 1280), "white")
    img.paste((0, 0, 0), (200, 0, 202, 1280))  # 2 px line; x=360 would sit on the first shot's zoom centre and never move
    segs = _segs((0, 4, "s0"))
    xs = []
    for n in range(4 * FPS):
        row = np.asarray(draw(img, *view(segs, n / FPS)[0][2]))[640, :, 0].astype(float)
        ink = 255 - row
        xs.append((np.arange(720) * ink).sum() / ink.sum())
    d = np.diff(xs)
    assert np.abs(d).max() < 1.5 and np.abs(d[5:-5]).min() > 0.05  # moves every frame, never jumps a pixel step


def test_every_shot_kind_keeps_the_window_inside_the_image():
    segs = _segs(*[(i * 2, i * 2 + 2, f"g{i}") for i in range(4)])  # zoom in, zoom out, pan right, pan left
    white = Image.new("RGB", (720, 1280), "white")
    for n in range(8 * FPS):
        for _, _, cam in view(segs, n / FPS):
            x0, x1, y0, y1 = _win(cam)
            assert x0 >= -1e-9 and y0 >= -1e-9 and x1 <= 720 + 1e-9 and y1 <= 1280 + 1e-9
            if n % 7 == 0:
                assert np.asarray(draw(white, *cam)).min() > 250  # no black border


def test_camera_continues_across_lines_of_one_scene():
    segs = _segs((0, 3, "s0"), (3, 6, "s0"))
    (_, _, a), (_, _, b) = view(segs, 3 - 1 / FPS)[0], view(segs, 3 + 1 / FPS)[-1]
    assert max(abs(p - q) for p, q in zip(_win(a), _win(b))) < 0.5


def test_one_scene_crossfades_the_image_but_not_the_camera():
    segs = _segs((0, 3, "s0"), (3, 6, "s0"))
    (f0, w0, c0), (f1, w1, c1) = view(segs, 3.0)
    assert (f0, f1) == (segs[0].file, segs[1].file) and w0 == w1 == 0.5 and c0 == c1


def test_shots_cycle_zoom_in_zoom_out_pan_right_pan_left():
    segs = _segs(*[(i * 4, i * 4 + 4, f"g{i}") for i in range(4)])
    cams = [(view(segs, i * 4 + 1)[0][2], view(segs, i * 4 + 3)[0][2]) for i in range(4)]
    assert cams[0][1][0] > cams[0][0][0] > 1 and cams[1][1][0] < cams[1][0][0] < 1.08
    assert cams[2][0][0] == cams[2][1][0] == cams[3][0][0] == 1.08 and cams[2][1][1] > cams[2][0][1]
    assert cams[3][1][1] < cams[3][0][1]


def test_short_segment_clamps_crossfade():
    segs = _segs((0, 3, "a"), (3, 3.8, "b"), (3.8, 7, "c"))
    assert [(f, w) for f, w, _ in view(segs, 3.4)] == [(segs[1].file, 1.0)]
    assert [(f, w) for f, w, _ in view(segs, 3.15)] == [(segs[1].file, 1.0)]  # a full 0.4 s fade would still be running
    assert abs(sum(w for _, w, _ in view(segs, 3.05)) - 1) < 1e-9


def test_segments_split_in_the_middle_of_the_gap():
    ps = [Placement(1, 0.2, 1.0), Placement(2, 1.5, 1.0), Placement(3, 2.8, 1.0)]
    fr = [{"id": i, "file": f"frames/{i}.png", "group": "s0"} for i in (1, 2, 3)]
    ss = segments(ps, fr, Path("/r"), 4.3)
    assert [(s.start, s.end) for s in ss] == [(0.0, 1.35), (1.35, 2.65), (2.65, 4.3)]
    assert ss[1].file == Path("/r/frames/2.png") and ss[1].group == "s0"


def test_render_video_duration_audio_and_subs(tmp_path):
    A, B = (200, 30, 30), (30, 30, 200)
    for name, c in (("1", A), ("2", B)):
        Image.new("RGB", (720, 1280), c).save(tmp_path / f"{name}.png")
    ps = [Placement(1, 0.2, 1.5), Placement(2, 2.0, 1.5)]
    total = 4.0
    segs = segments(ps, [{"id": 1, "file": "1.png", "group": "a"}, {"id": 2, "file": "2.png", "group": "b"}],
                    tmp_path, total)
    wav = tmp_path / "n.wav"
    write_silence(wav, total)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([(0, total, "Xin chào")]), encoding="utf-8")
    out = tmp_path / "o.mp4"
    render_video(segs, ass, wav, total, out)
    assert abs(probe(out).duration - total) < 0.1
    assert "Audio:" in subprocess.run([FF, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr

    def is_(t, c):
        return np.abs(frame_at(out, t)[300, 360].astype(int) - c).max() < 12

    assert is_(0.9, A) and is_(3.2, B)
    assert frame_at(out, 3.2)[1112, 360].min() > 200  # the light subtitle box, above the text
