import itertools
import subprocess
from pathlib import Path

import numpy as np
import pytest
from conftest import write_silence
from PIL import Image

from vshort.fit import Placement
from vshort.media import FF, frame_at, probe
from vshort.kit import Act
from vshort.motion import Scene
from vshort.render import FPS, H, W, Segment, _kinds, build_ass, draw, render_video, segments, view


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


def _line_steps(segs, ts, x):
    """Frame-to-frame steps of the centroid of a 2 px black vertical line at x, drawn through the camera at each t."""
    img = Image.new("RGB", (720, 1280), "white")
    img.paste((0, 0, 0), (x, 0, x + 2, 1280))
    xs = []
    for t in ts:
        (_, _, cam), = view(segs, t)  # outside a crossfade: one image
        ink = 255 - np.asarray(draw(img, *cam))[640, :, 0].astype(float)
        xs.append((np.arange(720) * ink).sum() / ink.sum())
    return np.diff(xs)


def test_motion_is_subpixel_smooth():
    # x=360 would sit on the first shot's zoom centre and never move
    d = _line_steps(_segs((0, 4, "s0")), [n / FPS for n in range(4 * FPS)], 200)
    assert np.abs(d).max() < 1.5 and np.abs(d[5:-5]).min() > 0.05  # moves every frame, never jumps a pixel step


def test_pan_is_subpixel_smooth():
    segs = _segs((0, 4, "s0"), (4, 8, "s1"), (8, 12, "s2"))  # third shot pans right: the line drifts left
    d = _line_steps(segs, [8.25 + n / FPS for n in range(3 * FPS)], 360)
    assert np.abs(d).max() < 1.5 and np.abs(d[5:-5]).min() > 0.05 and (d < 0).all()


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
    assert (f0, f1) == (segs[0], segs[1]) and w0 == w1 == 0.5 and c0 == c1


def test_shots_cycle_zoom_in_zoom_out_pan_right_pan_left():
    segs = _segs(*[(i * 4, i * 4 + 4, f"g{i}") for i in range(4)])
    cams = [(view(segs, i * 4 + 1)[0][2], view(segs, i * 4 + 3)[0][2]) for i in range(4)]
    assert cams[0][1][0] > cams[0][0][0] > 1 and cams[1][1][0] < cams[1][0][0] < 1.08
    assert cams[2][0][0] == cams[2][1][0] == cams[3][0][0] == 1.08 and cams[2][1][1] > cams[2][0][1]
    assert cams[3][1][1] < cams[3][0][1]


def test_short_segment_clamps_crossfade():
    segs = _segs((0, 3, "a"), (3, 3.8, "b"), (3.8, 7, "c"))
    assert [(f, w) for f, w, _ in view(segs, 3.4)] == [(segs[1], 1.0)]
    assert [(f, w) for f, w, _ in view(segs, 3.15)] == [(segs[1], 1.0)]  # a full 0.4 s fade would still be running
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
    f = frame_at(out, 3.2)
    assert f[1112, 360].min() > 200  # the light subtitle box, above the text
    assert np.abs(f[1112, 100].astype(int) - B).max() < 12  # outside the box the frame shows


def test_reference_shots_only_zoom_and_keep_the_credit_line_in_view():
    # credit lines run to x 30..690; a pan at ZOOM shows only 667 px
    segs = _segs(*[(i * 4, i * 4 + 4, f"v{i}") for i in range(5)])
    scales = []
    for n in range(20 * FPS):
        for f, _, (s, cx, _) in view(segs, n / FPS):
            assert cx - 360 / s <= 30 and cx + 360 / s >= 690 and cx == 360
        scales.append(view(segs, n / FPS)[-1][2][0])
    ins = [view(segs, i * 4 + 3.5)[0][2][0] > view(segs, i * 4 + 0.5)[0][2][0] for i in range(5)]
    assert ins == [True, False, True, False, True]  # alternate zoom in / zoom out


def _kind(segs, k):
    """What the camera of shot k does between 1 s after its start and 1 s before its end."""
    (_, _, a), (_, _, b) = (view(segs, t)[0] for t in (segs[k].start + 1, segs[k].end - 1))
    return "in" if b[0] > a[0] else "out" if b[0] < a[0] else "right" if b[1] > a[1] else "left"


def test_stills_rotate_among_stills_and_skip_what_the_previous_shot_did():
    segs = _segs((0, 4, "s0"), (4, 8, "v1"), (8, 12, "s2"), (12, 16, "v3"), (16, 20, "s4"))
    # s0 zooms in, v1 zooms out, so s2 skips its turn (zoom out) and pans right; v3 follows a pan and alternates
    # from v1 (in); s4 takes the next turn in the rotation (pan left)
    assert [_kind(segs, k) for k in range(5)] == ["in", "out", "right", "in", "left"]


def test_reference_zooms_the_other_way_from_the_shot_before_it():
    segs = _segs((0, 4, "s0"), (4, 8, "v4"), (8, 12, "v5"), (12, 16, "s1"), (16, 20, "s2"), (20, 24, "v6"))
    assert [_kind(segs, k) for k in range(6)] == ["in", "out", "in", "out", "right", "out"]


def test_no_two_adjacent_shots_move_alike():
    for sorts in itertools.product("sv", repeat=7):
        segs = _segs(*[(i * 4, i * 4 + 4, f"{c}{i}") for i, c in enumerate(sorts)])
        kinds = [_kind(segs, k) for k in range(len(sorts))]
        assert all(a != b for a, b in zip(kinds, kinds[1:])), (sorts, kinds)
        assert all(k in ("in", "out") for k, c in zip(kinds, sorts) if c == "v"), (sorts, kinds)


def test_shots_of_several_lines_count_once():
    segs = _segs((0, 3, "s0"), (3, 6, "s0"), (6, 10, "v2"), (10, 13, "s3"), (13, 16, "s3"), (16, 20, "v5"))
    assert [_kind(segs, k) for k in (0, 2, 3, 5)] == ["in", "out", "right", "in"]


def test_short_shot_moves_gently():
    for group in ("s", "v"):
        segs = _segs((0, 4, group + "0"), (4, 4.6, group + "1"), (4.6, 9, group + "2"))
        d = _line_steps(segs, [4.2 + n / FPS for n in range(8)], 100)
        assert np.abs(d).max() < 1.0
    # the pan kind too: third shot of stills, 0.6 s long
    segs = _segs((0, 4, "s0"), (4, 8, "s1"), (8, 8.6, "s2"), (8.6, 12, "s3"))
    assert np.abs(_line_steps(segs, [8.2 + n / FPS for n in range(6)], 360)).max() < 1.0


def test_draw_always_returns_a_full_frame():
    for size in ((360, 640), (720, 1280), (1080, 1920)):
        out = draw(Image.new("RGB", size, "white"), 1.05, 400, 600)
        assert out.size == (W, H) and np.asarray(out).min() > 250


def test_failed_render_keeps_the_previous_video(tmp_path):
    Image.new("RGB", (720, 1280), "white").save(tmp_path / "1.png")  # 2.png is missing: fails when its crossfade starts
    ps = [Placement(1, 0.2, 1.0), Placement(2, 1.5, 1.0)]
    frames = [{"id": 1, "file": "1.png", "group": "a"}, {"id": 2, "file": "2.png", "group": "b"}]
    wav = tmp_path / "n.wav"
    write_silence(wav, 3.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([(0, 3.0, "Xin chào")]), encoding="utf-8")
    out = tmp_path / "final.mp4"
    out.write_bytes(b"previous good video")
    with pytest.raises(FileNotFoundError):
        render_video(segments(ps, frames, tmp_path, 3.0), ass, wav, 3.0, out)
    assert out.read_bytes() == b"previous good video" and not (tmp_path / "final.tmp.mp4").exists()
    with pytest.raises(subprocess.CalledProcessError):  # ffmpeg itself fails: no narration to read
        render_video(segments(ps, frames, tmp_path, 3.0), ass, tmp_path / "nope.wav", 3.0, out)
    assert out.read_bytes() == b"previous good video" and not (tmp_path / "final.tmp.mp4").exists()


def test_the_black_edge_columns_of_a_frame_never_show():
    # NotebookLM frames carry a few px of black at the left and right edges
    img = Image.new("RGB", (720, 1280), "white")
    for x0 in (0, 717):
        img.paste((0, 0, 0), (x0, 0, x0 + 3, 1280))
    # zoom in, zoom out, pan right, pan left, then a short shot of each sort and reference shots
    segs = _segs((0, 4, "s0"), (4, 8, "s1"), (8, 12, "s2"), (12, 16, "s3"), (16, 16.8, "s4"), (16.8, 20, "v5"),
                 (20, 20.6, "v6"), (20.6, 25, "s7"))
    for n in range(0, 25 * FPS, 4):
        for _, _, cam in view(segs, n / FPS):
            edges = np.asarray(draw(img, *cam))
            assert edges[:, :4].min() > 200 and edges[:, -4:].min() > 200, (n / FPS, cam)


def test_animated_shots_leave_the_camera_rotation_alone():
    assert _kinds(["s0", "m0", "s1", "s2"]) == [0, -1, 1, 2]
    assert _kinds(["s0", "m0", "m1", "v4", "s1"]) == [0, -1, -1, 0, 1]  # the reference zooms against the last reference


def test_segments_mark_animated_lines(tmp_path):
    pl = [Placement(1, 0.2, 1.0), Placement(3, 1.5, 1.0), Placement(4, 2.8, 1.0)]
    frames = [{"id": i, "file": f"frames/{i}.png", "group": "s0"} for i in (1, 3, 4)]
    segs = segments(pl, frames, tmp_path, 4.3, {3: 0, 4: 0})
    assert [(s.group, s.scene) for s in segs] == [("s0", None), ("m0", 0), ("m0", 0)]


def test_render_video_draws_the_scene_on_animated_lines(tmp_path):
    Image.new("RGB", (W, H), "white").save(tmp_path / "w.png")
    segs = [Segment(1, 0, 1, tmp_path / "w.png", "s0"), Segment(2, 1, 2.5, tmp_path / "w.png", "m0", 0)]
    scene = Scene([2], [{"id": "d", "kind": "dot", "xy": [360, 500]}], [Act("draw", "d", 1.2, 1.6)])
    ass = tmp_path / "subs.ass"
    ass.write_text(build_ass([(0, 2.5, "a")]), encoding="utf-8")
    write_silence(tmp_path / "n.wav", 2.5)
    render_video(segs, ass, tmp_path / "n.wav", 2.5, tmp_path / "out.mp4", [scene])
    early, late = frame_at(tmp_path / "out.mp4", 0.5), frame_at(tmp_path / "out.mp4", 2.2)
    assert early[490:510, 350:370].min() > 200  # white still, no dot
    r, g, b = late[500, 360].astype(int)
    assert r > 150 and g < 90 and b < 90  # the red dot on paper
