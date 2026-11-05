import itertools
import subprocess
from pathlib import Path

import numpy as np
import pytest
from conftest import write_silence
from PIL import Image

from vshort import cards, render, shots
from vshort.fit import Placement
from vshort.media import FF, frame_at, probe
from vshort.kit import Act
from vshort.motion import Scene
from vshort.render import FPS, H, OUTRO_S, W, Segment, _kinds, build_ass, draw, export_outro, render_video, segments, view
from vshort.shots import KEEP, Beat


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
    assert f[1058, 360].min() > 200  # the light subtitle box, above the text
    assert np.abs(f[1058, 100].astype(int) - B).max() < 12  # outside the box the frame shows


def test_no_corner_logo_then_the_outro(tmp_path):
    B = (40, 40, 40)
    Image.new("RGB", (720, 1280), B).save(tmp_path / "1.png")
    segs = segments([Placement(1, 0.0, 1.0)], [{"id": 1, "file": "1.png", "group": "a"}], tmp_path, 1.0)
    write_silence(tmp_path / "n.wav", 1.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    out, clip = tmp_path / "o.mp4", tmp_path / "outro.mp4"
    export_outro(clip)
    err = subprocess.run([FF, "-hide_banner", "-i", str(clip)], capture_output=True, text=True).stderr
    assert "Audio:" in err and abs(probe(clip).duration - OUTRO_S) < 0.1  # a silent track: concat-ready on its own
    render_video(segs, ass, tmp_path / "n.wav", 1.0, out, outro=clip)
    assert abs(probe(out).duration - 3.5) < 0.1
    first = frame_at(out, 0.5).astype(int)
    assert np.abs(first[24:80, 481:704] - B).max() < 25  # no logo top right: it is only on the outro
    assert np.abs(first[1214:1270, 483:706] - B).max() < 25  # nothing in the old bottom-right corner
    end = frame_at(out, 3.3)
    assert np.abs(end[300, 360].astype(int) - B).max() > 100  # the outro has replaced the frame
    assert end[480:640, 260:460].std() > 30 and end[780:900, 60:660].std() > 30  # shield and words drawn
    assert np.abs(end[24:80, 481:704].astype(int) - end[300, 360]).max() < 40  # no corner logo on the outro


def test_any_outro_clip_is_appended_scaled_to_the_frame(tmp_path):
    Image.new("RGB", (720, 1280), (40, 40, 40)).save(tmp_path / "1.png")
    segs = segments([Placement(1, 0.0, 1.0)], [{"id": 1, "file": "1.png", "group": "a"}], tmp_path, 1.0)
    write_silence(tmp_path / "n.wav", 1.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    clip, out = tmp_path / "mine.mp4", tmp_path / "o.mp4"  # a hand-made outro: other size, other length
    subprocess.run([FF, "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xC03020:s=1080x1920:r=30:d=4", str(clip)], check=True)
    render_video(segs, ass, tmp_path / "n.wav", 1.0, out, outro=clip)
    assert abs(probe(out).duration - 5.0) < 0.1 and (probe(out).width, probe(out).height) == (W, H)
    assert np.abs(frame_at(out, 4.5)[640, 360].astype(int) - (0xC0, 0x30, 0x20)).max() < 20


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


def test_two_lines_of_the_canvas_never_crossfade_to_their_stills(tmp_path):
    Image.new("RGB", (W, H), "white").save(tmp_path / "w.png")
    Image.new("RGB", (W, H), "black").save(tmp_path / "k.png")
    segs = [Segment(1, 0, 1, tmp_path / "w.png", "s0"), Segment(2, 1, 2.5, tmp_path / "w.png", "m0", 0),
            Segment(3, 2.5, 4, tmp_path / "k.png", "m0", 0)]
    scene = Scene([2, 3], [{"id": "d", "kind": "dot", "xy": [360, 500]}], [Act("draw", "d", 0.8, 1.2)])
    ass = tmp_path / "subs.ass"
    ass.write_text(build_ass([(0, 4, "a")]), encoding="utf-8")
    write_silence(tmp_path / "n.wav", 4)
    render_video(segs, ass, tmp_path / "n.wav", 4, tmp_path / "out.mp4", [scene])
    at_cut = frame_at(tmp_path / "out.mp4", 2.5).astype(int)
    assert abs(at_cut[300, 100] - (238, 234, 226)).max() < 12  # paper, not the black still behind line 3
    assert at_cut[500, 360, 0] > 150 and at_cut[500, 360, 1] < 90  # the dot stays


# ---- lines with a beat plan ----

PAPER = (243, 239, 230)


def _planned_seg(*beats, **kw):
    return Segment(1, 0, 3, Path("f.png"), "n1", None, tuple(beats), **kw)


def test_planned_line_snaps_to_focus():
    focus = (100, 300, 500, 500)
    seg = _planned_seg(Beat(1.0, focus, None, None, None))
    assert view([seg], 1.0 - shots.LEAD + shots.SNAP)[0][2] == pytest.approx(shots.frame_box(focus, 1.5))  # the planned camera, not the rotation's
    assert view([seg], 0.2)[0][2] == pytest.approx((1.01, 360, 640), abs=0.01)  # before the first beat: the wide shot
    near = Segment(1, 0, 3, Path("f.png"), "n1", None, seg.plan, cap=1.2)  # a card's cap, not the stills'
    assert view([near], 1.0 - shots.LEAD + shots.SNAP)[0][2][0] == pytest.approx(1.2)


def test_planned_line_leaves_the_rotation_of_the_others_alone():
    plain = _kinds(["s0", "s1", "s2"])
    assert _kinds(["s0", "n2", "s1", "s2"]) == [plain[0], -1, plain[1], plain[2]]


def test_a_planned_line_is_not_in_the_rotation_at_all():
    # NotebookLM groups are scene ids: lines 4-8 of one scene are one shot, and a planned line in the middle splits it
    k = _kinds(["s2", "v9", "s2"])
    assert _kinds(["s2", "n4", "s2", "v9", "s2"]) == [k[0], -1, k[0], k[1], k[2]]  # the halves are one entry, no turn is spent
    k = _kinds(["s0", "v1", "s2", "s3"])  # s2 skips the move the reference before it made, planned line or not
    assert _kinds(["s0", "v1", "n2", "s2", "s3"]) == k[:2] + [-1] + k[2:]
    assert _kinds(["n0", "s1", "n2", "n3", "s1", "v4"]) == [-1] + _kinds(["s1", "v4"])[:1] + [-1, -1] + _kinds(["s1", "v4"])
    assert _kinds(["s2", "m0", "s2"]) == [0, -1, 1]  # an animated line between is a real cut: two shots


def test_a_planned_line_is_back_on_the_wide_shot_when_the_crossfade_out_starts():
    # the reviewer's probe: one scene, the planned line in the middle ends on a tight focus; its neighbours start at 1.01
    beat = Beat(4.0, (200, 400, 500, 700), None, None, None)
    segs = [Segment(1, 0, 3, Path("f.png"), "s0"), Segment(2, 3, 6, Path("f.png"), "n2", None, (beat,)),
            Segment(3, 6, 9, Path("f.png"), "s0")]
    for t in (5.81, 5.9, 6.0, 6.1, 6.19):  # the whole crossfade 2 -> 3
        (a, _, cam_a), (b, _, cam_b) = view(segs, t)
        assert (a.id, b.id) == (2, 3) and abs(cam_a[0] - cam_b[0]) < 0.06, (t, cam_a, cam_b)
    assert view(segs, 5.0)[0][2][0] > 1.4  # it did zoom in on the focus, mid-line


def test_the_first_focus_of_a_line_waits_for_the_cut_into_it_to_finish_fading_in():
    focus = (100, 300, 500, 500)
    plan = (Beat(3.1, focus, None, None, None),)  # phrase 1: its move would start at 2.9, in the middle of the crossfade 2.8-3.2
    cam = lambda t, bs=plan: render.planned_camera(bs, t, 3.0, 6.0, 1.5)  # noqa: E731
    for t in (2.8, 3.0, 3.0 + render.XF / 2):
        assert cam(t) == pytest.approx(cam(t, ()))  # still the wide shot: the line before it is fading out behind it
    assert cam(3.0 + render.XF / 2 + shots.SNAP / 2)[0] > cam(3.0 + render.XF / 2, ())[0] + 0.01  # on its way
    assert cam(3.0 + render.XF / 2 + shots.SNAP) == pytest.approx(shots.frame_box(focus, 1.5))  # SNAP later it has arrived
    late = (Beat(4.0, focus, None, None, None),)  # a move that starts after the fade is where it always was
    assert cam(4.0 - shots.LEAD + shots.SNAP, late) == pytest.approx(shots.frame_box(focus, 1.5))


def _scene_segments(tmp_path, groups, planned_ids, beat_t=4.0):
    """Lines of 3 s, one per group, the ones in `planned_ids` with a focus beat at beat_t."""
    plan = (Beat(beat_t, (200, 400, 500, 700), None, None, None),)
    ps = [Placement(i, 3.0 * (i - 1), 3.0) for i in range(1, len(groups) + 1)]
    frames = [{"id": i, "file": f"{i}.png", "group": g} for i, g in enumerate(groups, 1)]
    return segments(ps, frames, tmp_path, 3.0 * len(groups), planned={i: plan for i in planned_ids})


def test_unplanned_lines_of_a_planned_scene_stay_wide_so_the_shared_picture_does_not_double(tmp_path):
    # the reviewer's probe: s0 (unplanned) | n (planned, same scene) | s0 (unplanned); the old rotation was at 1.08 / panned
    segs = _scene_segments(tmp_path, ["s0", "s0", "s0"], [2])
    assert [s.group for s in segs] == ["n1", "n2", "n3"] and segs[0].plan == segs[2].plan == () and len(segs[1].plan) == 1
    for cut in (3.0, 6.0):
        for t in [cut - 0.2 + 0.02 * k for k in range(1, 20)]:  # the whole crossfade
            (a, _, ca), (b, _, cb) = view(segs, t)
            assert abs(ca[0] - cb[0]) < 0.06 and abs(ca[1] - cb[1]) < 10 and abs(ca[2] - cb[2]) < 10, (t, a.id, ca, cb)
    for t, k in ((1.5, 0), (8.0, 2)):  # a slow creep from the wide shot, no more: the planned camera with no beats
        assert view(segs, t)[0][2] == pytest.approx(render.planned_camera((), t, segs[k].start, segs[k].end, 1.5))


def test_lines_of_other_scenes_keep_the_camera_rotation(tmp_path):
    plain = _scene_segments(tmp_path, ["s7", "s0", "s0", "s0", "s9"], [])
    segs = _scene_segments(tmp_path, ["s7", "s0", "s0", "s0", "s9"], [3])
    assert [s.group for s in segs] == ["s7", "n2", "n3", "n4", "s9"] and segs[0].plan is None and segs[4].plan is None
    for t in (0.5, 1.5, 2.5):
        assert view(segs, t)[0][2] == pytest.approx(view(plain, t)[0][2])  # s7 before the scene: the camera it always had
    assert max(view(segs, 12.0 + 0.1 * k)[0][2][0] for k in range(30)) > 1.06  # s9 after it: a zoom or a pan of the rotation, not wide
    ref = _scene_segments(tmp_path, ["v1", "s0", "v1"], [2])  # another group of the planned line is not touched
    assert [s.group for s in ref] == ["v1", "n2", "v1"]


def test_without_a_plan_the_groups_are_the_frames_groups(tmp_path):
    segs = _scene_segments(tmp_path, ["s0", "s0", "s0"], [])
    assert [s.group for s in segs] == ["s0", "s0", "s0"] and all(s.plan is None for s in segs)  # sound.cues gets these


def test_a_segment_with_a_plan_can_still_be_hashed_and_compared():
    a, b = _planned_seg(Beat(1.0, KEEP, {"shape": "tick", "box": [1, 2, 3, 4]}, None, None)), _planned_seg()
    assert hash(a) == hash(b) and a == b  # Beat holds dicts: the plan is not part of what a Segment is


def test_segments_give_planned_lines_their_own_group_plan_card_and_cap(tmp_path):
    svg = tmp_path / "c.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280" width="720" height="1280">'
                   '<rect x="60" y="300" width="600" height="400" fill="none" stroke="#4a4a4a" stroke-width="3"/></svg>')
    pl = [Placement(1, 0.2, 1.0), Placement(3, 1.5, 1.0), Placement(4, 2.8, 1.0), Placement(5, 4.0, 1.0)]
    frames = [{"id": i, "file": f"frames/{i}.png", "group": "s1" if i == 1 else "s0"} for i in (1, 3, 4, 5)]  # 1: another scene
    plan = (Beat(1.6, KEEP, None, None, {"text": "a", "box": [1, 2, 3, 4]}),)
    segs = segments(pl, frames, tmp_path, 5.3, {4: 0}, {3: plan, 5: plan}, {3: svg})
    assert [(s.group, s.scene) for s in segs] == [("s1", None), ("n3", None), ("m0", 0), ("n5", None)]
    assert [s.plan for s in segs] == [None, plan, None, plan] and [s.card for s in segs] == [None, svg, None, None]
    assert [s.cap for s in segs] == [1.5, cards.cap(cards.Card(svg, 1.0, 2.0, render.XF)), 1.5, shots.MAX_ZOOM_STILL]


def _line(tmp_path, plan, *, total=3.0, planned=True, **kw):
    """One line of `total` s on a blank paper picture, rendered; the video's path."""
    Image.new("RGB", (W, H), PAPER).save(tmp_path / "1.png")
    segs = segments([Placement(1, 0.0, total)], [{"id": 1, "file": "1.png", "group": "s0"}], tmp_path, total,
                    planned={1: plan} if planned else None, **kw)
    write_silence(tmp_path / "n.wav", total)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    out = tmp_path / ("planned.mp4" if planned else "plain.mp4")
    render_video(segs, ass, tmp_path / "n.wav", total, out, run_dir=tmp_path)
    return out


def _ink(video, t, box=(120, 440, 600, 680)):
    """How many pixels of the frame at t, inside box (x0, y0, x1, y1), are pencil-dark."""
    x0, y0, x1, y1 = box
    return int((frame_at(video, t)[y0:y1, x0:x1].min(axis=2) < 170).sum())


def test_render_with_shots_draws_the_mark(tmp_path):
    plan = (Beat(1.5, KEEP, {"shape": "circle", "box": [200, 500, 520, 600]}, None, None),)  # starts to draw at 1.3 s
    planned, plain = _line(tmp_path, plan), _line(tmp_path, plan, planned=False)
    assert _ink(planned, 1.0) == _ink(plain, 1.0) == 0  # before its time the mark is not there
    assert np.abs(frame_at(planned, 1.0).astype(int) - frame_at(plain, 1.0)).max() < 8  # the frame is the unplanned one
    assert _ink(planned, 2.6) > 200 and _ink(plain, 2.6) == 0  # drawn round the box, and only in the planned video


def test_a_line_that_has_stopped_changing_is_composited_once(tmp_path, monkeypatch):
    plan = (Beat(1.5, KEEP, {"shape": "circle", "box": [200, 500, 520, 600]}, None, None),
            Beat(1.9, KEEP, None, None, {"text": "Hà Nội", "box": [200, 700, 520, 780]}))
    seen, real = [], shots.draw_overlays
    monkeypatch.setattr(shots, "draw_overlays", lambda *a, **k: seen.append(a[2]) or real(*a, **k))
    out = _line(tmp_path, plan, total=4.0)
    done = shots.settled(list(plan))
    assert done == pytest.approx(1.9 - shots.LEAD + shots.POP_T) and max(seen) < done + 2 / FPS  # not asked again once it is whole
    assert len(seen) > 30 and _ink(out, 3.8) > 200 and _ink(out, 3.8, (200, 690, 520, 790)) > 100  # and still there to the end


def test_an_unplanned_line_of_a_planned_scene_renders_beside_its_planned_neighbour(tmp_path):
    for i in (1, 2):
        Image.new("RGB", (W, H), PAPER).save(tmp_path / f"{i}.png")
    plan = (Beat(2.4, KEEP, {"shape": "circle", "box": [200, 500, 520, 600]}, None, None),)
    segs = segments([Placement(1, 0.0, 1.5), Placement(2, 1.5, 1.5)], [{"id": i, "file": f"{i}.png", "group": "s0"} for i in (1, 2)],
                    tmp_path, 3.0, planned={2: plan})
    assert [s.plan for s in segs] == [(), plan]  # the first has no beats and no overlay, but is on the planned camera
    write_silence(tmp_path / "n.wav", 3.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    render_video(segs, ass, tmp_path / "n.wav", 3.0, tmp_path / "o.mp4", run_dir=tmp_path)
    assert _ink(tmp_path / "o.mp4", 0.8) == 0 and _ink(tmp_path / "o.mp4", 2.9) > 200


CARD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280" width="720" height="1280">'
        '<rect x="60" y="300" width="600" height="600" rx="12" fill="none" stroke="#4a4a4a" stroke-width="3"/>'
        '<rect x="100" y="360" width="520" height="70" fill="#444"/><rect x="100" y="700" width="520" height="70" fill="#444"/></svg>')


def test_a_card_line_writes_itself_out_and_is_built_once(tmp_path, monkeypatch):
    svg = tmp_path / "c.svg"
    svg.write_text(CARD)
    plan = (Beat(2.4, KEEP, {"shape": "underline", "box": [100, 780, 620, 830]}, None, None),)
    Image.new("RGB", (W, H), PAPER).save(tmp_path / "1.png")
    segs = segments([Placement(1, 0.0, 3.0)], [{"id": 1, "file": "1.png", "group": "v1"}], tmp_path, 3.0, None, {1: plan}, {1: svg})
    built, real = [], render.Card
    monkeypatch.setattr(render, "Card", lambda *a: built.append(a) or real(*a))
    write_silence(tmp_path / "n.wav", 3.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    render_video(segs, ass, tmp_path / "n.wav", 3.0, tmp_path / "o.mp4", run_dir=tmp_path)
    assert len(built) == 1  # one Card for the whole line, not one a frame
    early, late = frame_at(tmp_path / "o.mp4", 0.3), frame_at(tmp_path / "o.mp4", 2.9)
    top, bottom = (slice(360, 410), slice(140, 580)), (slice(710, 765), slice(140, 580))  # inside the blocks at any zoom
    assert early[top].min() < 120 and early[bottom].min() > 200  # the second block is still to come at 0.3 s
    assert late[top].max() < 120 and late[bottom].max() < 120  # both there by the end
    assert (late[800:900, 100:620].min(axis=2) < 170).sum() > 100  # and the mark is under the second
