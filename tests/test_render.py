from conftest import write_silence
from PIL import Image

from vshort.captions import Fragment
from vshort.media import frame_at, probe
from vshort.plates import Plate
from vshort.render import build_ass, compose, outro_cut


def test_build_ass_layout():
    a = build_ass([(0, 2, "Câu mở đầu dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài dài"),
                   (2, 3, "*Zero-click.*")])
    assert "Style: Cap,Patrick Hand,68," in a  # fs(50)
    assert a.endswith("}Zero-click.\n")  # old * highlights are dropped, not drawn
    assert a.count("Dialogue: 2,0:00:00.00,0:00:02.00,Cap") >= 2  # first sentence wraps to ≥2 lines
    assert "Title" not in a and "Kicker" not in a


def test_outro_cut():
    assert outro_cut([Fragment(0, 0, 57.13, 0, 0, "x")], [10.2, 57.3], 60.35) == 57.3
    assert outro_cut([Fragment(0, 0, 50.0, 0, 0, "x")], [10.2], 60.0) == 60.0


def test_compose_output(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 3, "#000000")], captions=[])
    wav = tmp_path / "n.wav"
    write_silence(wav, 3.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([(0, 2.5, "Xin chào")]), encoding="utf-8")
    out = tmp_path / "o.mp4"
    compose(v, wav, ass, [], tmp_path, cut=2.5, out=out)
    f = frame_at(out, 1.0)
    assert abs(probe(out).duration - 2.5) < 0.1
    assert f[1112, 360].min() > 200 and f[1112, 100].max() < 40  # light box around y 1150, above the text; page outside


def test_outro_cut_takes_a_blank_frame_when_there_is_no_hard_cut():
    assert outro_cut([Fragment(0, 0, 85.13, 0, 0, "x")], [], 88.49, blank=85.4) == 85.4
    assert outro_cut([Fragment(0, 0, 57.13, 0, 0, "x")], [57.3], 60.35, blank=57.5) == 57.3


def test_plate_applies_from_its_first_frame(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000")], captions=[])
    Image.new("RGB", (50, 50), "white").save(tmp_path / "p00.png")
    plates = [Plate("p00", 100, 100, 0.0667, 0.5, "clean", False)]  # as build_plates rounds frame 2 (2/30 s)
    wav = tmp_path / "n.wav"
    write_silence(wav, 1.0)
    ass = tmp_path / "s.ass"
    ass.write_text(build_ass([(0, 1.0, "x")]), encoding="utf-8")
    out = tmp_path / "o.mp4"
    compose(v, wav, ass, plates, tmp_path, cut=1.0, out=out)
    assert frame_at(out, 2 / 30)[125, 125].min() > 200 and frame_at(out, 1 / 30)[125, 125].max() < 60
