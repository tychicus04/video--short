from conftest import write_silence

from vshort.captions import Fragment
from vshort.media import frame_at, probe
from vshort.render import build_ass, compose, outro_cut


def test_build_ass_layout():
    a = build_ass([(0, 2, "Câu mở đầu dài dài dài dài dài dài dài dài dài dài dài dài dài dài"), (2, 3, "*Zero-click.*")],
                  "CORUNA & DARKSWORD", "iPhone bị hack chỉ vì mở 1 trang web", cut=3.0)
    assert "Style: Cap,Be Vietnam Pro ExtraBold,61," in a  # fs(40)
    assert "{\\1c&H00D4FF&}Zero-click." in a
    assert a.count("Dialogue: 2,0:00:00.00,0:00:02.00,Cap") >= 2  # first sentence wraps to ≥2 lines


def test_outro_cut():
    assert outro_cut([Fragment(0, 0, 57.13, 0, 0, "x")], [10.2, 57.3], 60.35) == 57.3
    assert outro_cut([Fragment(0, 0, 50.0, 0, 0, "x")], [10.2], 60.0) == 60.0


def test_compose_output(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 3, "#F3EFE6")], captions=[])
    wav = tmp_path / "n.wav"
    write_silence(wav, 3.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([(0, 2.5, "Xin chào")], "K", "Tiêu đề", 2.5), encoding="utf-8")
    out = tmp_path / "o.mp4"
    compose(v, wav, ass, [], tmp_path, cut=2.5, out=out)
    p = probe(out)
    assert abs(p.duration - 2.5) < 0.1 and frame_at(out, 1.0)[1150, 150].max() < 40  # dark sub box (x 120-600), clear of the text


def test_outro_cut_takes_a_blank_frame_when_there_is_no_hard_cut():
    assert outro_cut([Fragment(0, 0, 85.13, 0, 0, "x")], [], 88.49, blank=85.4) == 85.4
    assert outro_cut([Fragment(0, 0, 57.13, 0, 0, "x")], [57.3], 60.35, blank=57.5) == 57.3
