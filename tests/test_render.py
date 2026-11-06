import subprocess

import numpy as np
import pytest
from conftest import write_silence
from PIL import Image

from vshort.media import FF, frame_at, probe
from vshort.render import H, OUTRO_S, W, build_ass, export_outro, render_pieces
from vshort.retime import Piece


def test_build_ass_layout():
    a = build_ass([(0, 2, "Câu mở đầu dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài"),
                   (2, 3, "*Zero-click.*")])
    assert "Style: Cap,Patrick Hand,68," in a  # fs(50)
    assert a.endswith("}Zero-click.\n")  # old * highlights are dropped, not drawn
    assert a.count("Dialogue: 2,0:00:00.00,0:00:02.00,Cap") >= 2  # first sentence wraps to ≥2 lines
    assert "Title" not in a and "Kicker" not in a


def test_no_corner_logo_then_the_drawn_outro(make_video, tmp_path):
    B = (40, 40, 40)
    clean = make_video(tmp_path, scenes=[(0, 1, "#282828")], captions=[])
    clip = tmp_path / "outro.mp4"
    export_outro(clip)
    err = subprocess.run([FF, "-hide_banner", "-i", str(clip)], capture_output=True, text=True).stderr
    assert "Audio:" in err and abs(probe(clip).duration - OUTRO_S) < 0.1  # a silent track: concat-ready on its own
    write_silence(tmp_path / "n.wav", 1.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    out = tmp_path / "o.mp4"
    render_pieces([Piece(1, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0)], clean, [], ass, tmp_path / "n.wav", 1.0, out, outro=clip)
    assert abs(probe(out).duration - 3.5) < 0.1
    first = frame_at(out, 0.5).astype(int)
    assert np.abs(first[24:80, 481:704] - B).max() < 25  # no logo top right: it is only on the outro
    assert np.abs(first[1214:1270, 483:706] - B).max() < 25  # nothing in the old bottom-right corner
    end = frame_at(out, 3.3)
    assert np.abs(end[300, 360].astype(int) - B).max() > 100  # the outro has replaced the frame
    assert end[480:640, 260:460].std() > 30 and end[780:900, 60:660].std() > 30  # shield and words drawn
    assert np.abs(end[24:80, 481:704].astype(int) - end[300, 360]).max() < 40  # no corner logo on the outro


# ---- render_pieces: NotebookLM's own video, retimed ----

def _level(k: int) -> int:
    return 10 + 20 * k


@pytest.fixture
def seconds_video(make_video, tmp_path):
    """10 s of video whose grey level says which source second it is: 10 + 20·floor(t)."""
    return make_video(tmp_path, scenes=[(k, k + 1, "#" + f"{_level(k):02x}" * 3) for k in range(10)], captions=[])


def _render(tmp_path, clean, ps, total, stills=(), outro=None, subs=()):
    write_silence(tmp_path / "n.wav", total)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass(list(subs)), encoding="utf-8")
    out = tmp_path / "o.mp4"
    render_pieces(ps, clean, list(stills), ass, tmp_path / "n.wav", total, out, outro=outro)
    return out


def _grey(out, t):
    return int(frame_at(out, t)[300, 360].astype(int).mean())


def test_render_pieces_shows_the_right_source_second(seconds_video, tmp_path):
    ps = [Piece(1, 0.0, 3.0, 0.0, 2.0, 1.5, 0.0, 0.0), Piece(2, 3.0, 6.0, 2.0, 5.0, 1.0, 0.0, 0.0)]
    out = _render(tmp_path, seconds_video, ps, 5.0)
    assert abs(_grey(out, 1.0) - _level(1)) < 5  # 1.0 s out = 1.5 s in, at 1.5x
    assert abs(_grey(out, 3.5) - _level(4)) < 5  # line 2 starts at source 3.0: 1.5 s later is source 4.5


def test_render_pieces_holds_the_last_played_frame(seconds_video, tmp_path):
    ps = [Piece(1, 0.0, 2.5, 0.0, 3.5, 1.0, 1.0, 0.0)]
    out = _render(tmp_path, seconds_video, ps, 3.5)
    assert abs(_grey(out, 3.2) - _level(2)) < 5  # held on source 2.5 s, not run on to second 3


def test_render_pieces_overlays_a_patched_still_only_in_its_window(seconds_video, tmp_path):
    Image.new("RGB", (720, 1280), (220, 30, 30)).save(tmp_path / "patched.png")
    ps = [Piece(1, 0.0, 3.0, 0.0, 3.0, 1.0, 0.0, 0.0)]
    out = _render(tmp_path, seconds_video, ps, 3.0, stills=[(tmp_path / "patched.png", 1.0, 3.0)])
    assert abs(_grey(out, 0.5) - _level(0)) < 5
    assert np.abs(frame_at(out, 1.5)[300, 360].astype(int) - (220, 30, 30)).max() < 15


def test_render_pieces_length_subtitles_bt709_and_the_outro(seconds_video, tmp_path):
    clip = tmp_path / "mine.mp4"  # any outro: other size, its own length
    subprocess.run([FF, "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xC03020:s=1080x1920:r=30:d=1", str(clip)],
                   check=True)
    ps = [Piece(1, 0.0, 2.0, 0.0, 2.0, 1.0, 0.0, 0.0)]
    out = _render(tmp_path, seconds_video, ps, 2.0, outro=clip, subs=[(0, 2.0, "Xin chào")])
    assert abs(probe(out).duration - 3.0) < 0.1 and (probe(out).width, probe(out).height) == (W, H)
    err = subprocess.run([FF, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    assert "Audio:" in err and "bt709" in err
    assert frame_at(out, 1.0)[1058, 360].min() > 200  # the light subtitle box
    assert np.abs(frame_at(out, 2.8)[640, 360].astype(int) - (0xC0, 0x30, 0x20)).max() < 20  # the outro, after XF


def test_render_pieces_failure_keeps_the_previous_video(seconds_video, tmp_path):
    out = tmp_path / "o.mp4"
    out.write_bytes(b"previous good video")
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):  # no narration to read
        render_pieces([Piece(1, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0)], seconds_video, [], ass, tmp_path / "nope.wav", 1.0, out,
                      outro=None)
    assert out.read_bytes() == b"previous good video" and not (tmp_path / "o.tmp.mp4").exists()
