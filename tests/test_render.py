import copy
import subprocess

import numpy as np
import pytest
from conftest import write_silence
from PIL import Image, ImageFont

from vshort import hf
from vshort.compose import write_composition
from vshort.media import FF, frame_at, probe
from vshort.textfit import FONTS
from vshort.render import (BAR, H, OUTRO, OUTRO_S, STRIPE, TEAL, TEXT_L, TEXT_R, TITLE_XY, W, YELLOW, build_ass,
                           export_outro, export_title, render_neon, render_pieces, title_card, title_fit, title_times)
from vshort.retime import Piece
from vshort.scene import load_scene, resolve


def test_build_ass_layout():
    a = build_ass([(0, 2, "Câu mở đầu dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài"),
                   (2, 3, "*Zero-click.*")])
    assert "Style: Cap,Patrick Hand,68," in a  # fs(50)
    assert a.endswith("}Zero-click.\n")  # old * highlights are dropped, not drawn
    assert a.count("Dialogue: 2,0:00:00.00,0:00:02.00,Cap") >= 2  # first sentence wraps to ≥2 lines
    assert "Title" not in a and "Kicker" not in a


def test_corner_logo_then_the_drawn_outro(make_video, tmp_path):
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
    assert np.abs(first[24:82, 470:700] - B).max() > 100  # the magazine's logo top right, in its own colours (07/11)
    assert np.abs(first[1214:1270, 483:706] - B).max() < 25  # nothing in the old bottom-right corner
    end = frame_at(out, 3.3)
    assert np.abs(end[300, 360].astype(int) - B).max() > 100  # the outro has replaced the frame
    assert end[480:640, 260:460].std() > 30 and end[780:900, 60:660].std() > 30  # shield and words drawn
    assert np.abs(end[24:80, 481:704].astype(int) - end[300, 360]).max() < 40  # no corner logo on the outro


# ---- the title bar: the spoken title typed into the magazine's bar, then rolled back ----

def _local(box):
    """A rectangle of the frame in title_card's own coordinates (it is drawn at TITLE_XY)."""
    x, y = TITLE_XY
    return box[0] - x, box[1] - y, box[2] - x, box[3] - y


def _count(img, rgb, box, tol=40):
    a = np.array(img).astype(int)
    x0, y0, x1, y1 = _local(box)
    part = a[y0:y1, x0:x1]
    return int(((np.abs(part[..., :3] - rgb[:3]).sum(-1) < tol) & (part[..., 3] > 200)).sum())


INSIDE = (BAR[0] + 4, BAR[1] + 4, BAR[2] - 4, BAR[3] - 4)


def test_title_fit_two_lines_left_of_the_buttons():
    size, lines = title_fit("Ảnh độc upload, Rails ghi file tùy ý")
    assert lines == ["ẢNH ĐỘC UPLOAD,", "RAILS GHI FILE TÙY Ý"] and size >= 40
    size, lines = title_fit("Siemens IoT2050 lỗi CVE-2026-58115 - một request chiếm máy, không cần mật khẩu")
    font = ImageFont.truetype(str(FONTS / "BeVietnamPro-ExtraBold.ttf"), size)
    assert len(lines) <= 3 and max(font.getlength(ln) for ln in lines) <= TEXT_R - TEXT_L
    assert title_fit("rất dài " * 40) is None  # no bar: the subtitle keeps the line


def test_title_times_type_while_it_is_said_and_leave_after():
    t0, t1, out = title_times(0.2, 2.7)
    assert (t0, round(t1, 2), round(out, 2)) == (0.5, 2.6, 3.0)  # box open first; gone 0.3 s after the title is said
    t0, t1, out = title_times(0.0, 0.6)  # a very short title still types for 0.5 s, then leaves
    assert t1 == t0 + 0.5 and out == t1 + 0.3


def test_title_card_opens_types_and_rolls_back():
    fit = title_fit("Ảnh độc upload, Rails ghi file tùy ý")
    t0, t1, out = title_times(0.2, 2.7)
    assert np.array(title_card(0.0, fit, t0, t1, out))[..., 3].max() == 0  # nothing yet
    full = title_card(t1 + 0.1, fit, t0, t1, out)
    assert _count(full, TEAL, (BAR[2] - 30, BAR[1] + 4, BAR[2] - 2, BAR[1] + 20)) > 300  # box open to its right end
    assert _count(full, YELLOW, STRIPE) > 1500  # the stripe
    lines_y = (BAR[1] + BAR[3]) // 2
    top, bottom = (BAR[0], BAR[1], BAR[2], lines_y), (BAR[0], lines_y, BAR[2], BAR[3])
    assert _count(full, (255, 255, 255), top) > 500 and _count(full, (255, 255, 255), bottom) > 500  # both lines typed
    half = title_card((t0 + t1) / 2, fit, t0, t1, out)
    assert _count(half, (255, 255, 255), bottom) < _count(full, (255, 255, 255), bottom) / 2  # still typing
    leaving = title_card(out + 0.3, fit, t0, t1, out)
    assert _count(leaving, TEAL, (BAR[2] - 60, BAR[1] + 4, BAR[2] - 2, BAR[3] - 4)) == 0  # rolled back from the right…
    assert _count(leaving, TEAL, (BAR[0], BAR[1] + 4, BAR[0] + 60, BAR[1] + 20)) > 300  # …not yet from the left
    assert np.array(title_card(out + 0.7, fit, t0, t1, out))[..., 3].max() == 0  # gone


def test_title_cursor_only_while_typing():
    """Tai, 07/11: the cursor left blinking after the last letter read as a glitch next to the "Ý"."""
    fit = title_fit("Ảnh độc upload, Rails ghi file tùy ý")
    t0, t1, out = title_times(0.2, 2.7)
    assert _count(title_card((t0 + t1) / 2, fit, t0, t1, out), YELLOW, INSIDE) > 50
    for t in (t1 + 0.05, t1 + 0.25, t1 + 0.45, out - 0.05):
        assert _count(title_card(t, fit, t0, t1, out), YELLOW, INSIDE) == 0


def test_render_pieces_lays_the_title_bar_over_the_start(seconds_video, tmp_path):
    clip = tmp_path / "title.mov"
    assert export_title("Ảnh độc upload, Rails ghi file tùy ý", 0.2, 1.5, clip)
    write_silence(tmp_path / "n.wav", 3.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([]), encoding="utf-8")
    out = tmp_path / "o.mp4"
    render_pieces([Piece(1, 0.0, 3.0, 0.0, 3.0, 1.0, 0.0, 0.0)], seconds_video, [], ass, tmp_path / "n.wav", 3.0, out,
                  outro=None, title=clip)
    probe_at = (BAR[2] - 15, BAR[1] + 8)  # right of the text, inside the box
    assert np.abs(frame_at(out, 1.5)[probe_at[1], probe_at[0]].astype(int) - TEAL[:3]).max() < 25
    assert abs(int(frame_at(out, 2.8)[probe_at[1], probe_at[0]].astype(int).mean()) - _level(2)) < 6  # gone again
    assert frame_at(out, 1.5)[761, 69].min() < 60 and frame_at(out, 1.5)[761, 69][:2].min() > 200  # the yellow stripe


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


def test_the_reviewer_quotes_the_subtitle_place_the_render_uses():
    from pathlib import Path

    from vshort import render, textfit
    md = (Path(__file__).resolve().parent.parent / "claude" / "agents" / "vs-reviewer.md").read_text(encoding="utf-8")
    assert f"đáy hộp y≈{render.SUB_BOTTOM}" in md and f"y {textfit.UI_BOTTOM}" in md and f"x {textfit.UI_RIGHT}" in md
    for agent in ('"visuals"', '"translator"', '"none"'):  # the agents auto.read_review accepts, and no other
        assert agent in md
    assert '"motion"' not in md and '"shots"' not in md


# ---- the neon style: the rendered diagram, the voice and the outro in one pass ----

def _visuals(tmp_path, rgb="2BE3FF", seconds=4):
    """A flat silent clip tagged the way HyperFrames tags what it renders: BT.709, limited range."""
    out = tmp_path / "visuals.mp4"
    subprocess.run([FF, "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x{rgb}:s={W}x{H}:r=30:d={seconds}", "-vf",
                    "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
                    "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv", "-c:v", "libx264", str(out)], check=True)
    return out


def test_render_neon_lengths(tmp_path):
    visuals = _visuals(tmp_path)
    write_silence(tmp_path / "mix.wav", 4.0)
    out = tmp_path / "final.mp4"
    render_neon(visuals, tmp_path / "mix.wav", 4.0, out)
    info = probe(out)
    assert abs(info.duration - (4.0 + probe(OUTRO).duration)) < 0.05 and (info.width, info.height) == (W, H)
    err = subprocess.run([FF, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    assert "Audio:" in err and "bt709" in err


def test_render_neon_keeps_the_colours_and_ends_on_the_outro(tmp_path):
    visuals = _visuals(tmp_path)
    write_silence(tmp_path / "mix.wav", 4.0)
    out = tmp_path / "final.mp4"
    render_neon(visuals, tmp_path / "mix.wav", 4.0, out, outro=None)
    assert abs(probe(out).duration - 4.0) < 0.05
    assert np.abs(frame_at(out, 2.0)[640, 360].astype(int) - (0x2B, 0xE3, 0xFF)).max() < 8  # no 601/709 shift of the neon hues
    render_neon(visuals, tmp_path / "mix.wav", 4.0, out)
    assert np.abs(frame_at(out, 2.0)[640, 360].astype(int) - frame_at(visuals, 2.0)[640, 360].astype(int)).max() < 4  # the diagram
    assert np.abs(frame_at(out, probe(out).duration - 0.1)[640, 360].astype(int) - frame_at(OUTRO, 2.4)[640, 360].astype(int)).max() < 30


def test_render_neon_failure_keeps_the_previous_video(tmp_path):
    out = tmp_path / "final.mp4"
    out.write_bytes(b"previous good video")
    with pytest.raises(subprocess.CalledProcessError):  # no voice to read
        render_neon(_visuals(tmp_path), tmp_path / "nope.wav", 4.0, out)
    assert out.read_bytes() == b"previous good video" and not (tmp_path / "final.tmp.mp4").exists()


@pytest.mark.skipif(not hf.available(), reason="chưa cài vshort/neon (npm ci)")
def test_a_resolved_scene_loads_in_the_kit_without_an_error(tmp_path):
    """scene.resolve and the kit were written against the runtime contract at the same time: here they meet. Every verb and
    kind of element in one scene (a quote in a third section), through the real composition, loaded in headless Chrome."""
    from test_scene import ALL, TWO

    data = copy.deepcopy(TWO)
    data["sections"].append({"id": "s3", "label": "", "tone": "claim", "layout": "none", "keep": [], "nodes": [], "links": [],
                             "beats": [{"at": 14, "do": "quote", "text": "Mỗi máy chỉ thấy một phần", "who": "kỹ sư", "tone": "claim"}]})
    rt = resolve(load_scene(data), ALL, "Tiêu đề của video", 46.0, (0.2, 2.8))
    assert {"hero", "quote", "tile", "chip", "statement", "badge", "link", "icon"} <= {e["kind"] for e in rt["elements"]}
    assert {"on", "draw", "type", "off", "tone", "flow", "move", "swap"} <= {a["do"] for a in rt["actions"]}
    assert hf.validate(write_composition(rt, tmp_path / "neon")) == []
