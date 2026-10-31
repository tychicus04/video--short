from pathlib import Path

from PIL import Image

from vshort.captions import Fragment, detect_fragments
from vshort.plates import build_plates, scene_cuts


def test_scene_cuts(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    assert [round(t, 2) for t in scene_cuts(v)] == [1.0]


def test_clean_frame_preferred_and_cover_band_skipped(make_video, tmp_path):
    caps = [(0.0, 1.5, 930, "Top caption"), (1.5, 2.0, 1150, "Low caption")]  # 1.5-2.0: band 930 clean
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda *a: 1 / 0)
    assert len(plates) == 1 and plates[0].method == "clean" and plates[0].start == 0.0


def test_lama_used_and_moving_flagged(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "moving")], captions=[(0, 1, 930, "Always on"), (1, 2, 930, "Still here")])
    calls = []
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"),
                          inpaint=lambda img, mask: calls.append(1) or img)
    assert calls and plates[0].method == "lama" and plates[0].moving


def test_clean_frame_found_when_non_caption_art_was_blanked(make_video, tmp_path):
    caps = [(0.0, 1.5, 930, "Top caption"), (1.5, 2.0, 930, "Button")]
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    real = [f for f in detect_fragments(v) if f.start < 1.4]  # the transcriber blanked "Button"
    plates = build_plates(v, real, tmp_path / "p", Path("unused"), inpaint=lambda *a: 1 / 0)
    assert plates[0].method == "clean"


def test_moving_measured_on_plate_window_only(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1.5, "moving"), (1.5, 2, "#A0A0A0")],
                   captions=[(1.6, 2.0, 930, "Late caption")])
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda *a: 1 / 0)
    assert plates[0].method == "clean" and not plates[0].moving


def test_caption_spanning_scene_cut_is_covered_in_both_scenes(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "#C8C8C8")],
                   captions=[(0.5, 1.5, 930, "Across the cut")])
    fr = detect_fragments(v)
    merged = [Fragment(0, fr[0].start, fr[-1].end, fr[0].y0, fr[0].y1, "Across the cut")]  # as merge_text does
    plates = sorted(build_plates(v, merged, tmp_path / "p", Path("unused"), inpaint=lambda img, mask: img),
                    key=lambda p: p.start)
    assert [(round(p.start, 2), round(p.end, 2)) for p in plates] == [(0.5, 1.0), (1.0, 1.5)]


def test_flickering_art_line_not_taken_for_caption_text(make_video, tmp_path):
    caps = [(0.0, 0.7, 930, "Short"), (0.7, 1.4, 930, "A somewhat longer one"), (1.4, 2.0, 930, "Mid size")]
    v = make_video(tmp_path, scenes=[(0, 2, "jitter")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda img, mask: img)
    width = Image.open(tmp_path / "p" / f"{plates[0].name}.png").width
    assert plates[0].x + width < 630  # stops short of the line at x 640


def test_caption_over_static_art_keeps_full_text_width(make_video, tmp_path):
    caps = [(0.0, 0.7, 930, "Short"), (0.7, 1.4, 930, "A somewhat longer one"), (1.4, 2.0, 930, "Mid size")]
    v = make_video(tmp_path, scenes=[(0, 2, "artbar")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda img, mask: img)
    width = Image.open(tmp_path / "p" / f"{plates[0].name}.png").width
    assert plates[0].x < 170 and plates[0].x + width > 550  # spans the widest caption, art or not
