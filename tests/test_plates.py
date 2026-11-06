from pathlib import Path

import numpy as np
from PIL import Image

from vshort.captions import Fragment, detect_fragments
from vshort.media import frame_at
from vshort.plates import build_plates, scene_cuts


def test_scene_cuts(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    assert [round(t, 2) for t in scene_cuts(v)] == [1.0]


def test_scene_cuts_between_two_dark_scenes(make_video, tmp_path):
    # a dark theme's cut changed the mean grey by only 24.9 (NetamLoader): here 23, but over the whole frame
    v = make_video(tmp_path, scenes=[(0, 1, "#505050"), (1, 2, "#676767")], captions=[])
    assert [round(t, 2) for t in scene_cuts(v)] == [1.0]


def test_clean_frame_preferred_and_every_band_plated(make_video, tmp_path):
    caps = [(0.0, 1.5, 930, "Top caption"), (1.5, 2.0, 1150, "Low caption")]  # each band is clean while the other shows
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda *a: 1 / 0)
    assert [p.method for p in plates] == ["clean", "clean"] and plates[0].start == 0.0


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


def test_wide_low_caption_beyond_the_sub_box_gets_a_plate(make_video, tmp_path):
    caps = [(0, 1, 1150, "A very wide low caption that sticks out"), (1, 2, 1150, "Another wide low caption sticking out")]
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda img, mask: img)
    assert plates and plates[0].y > 1050


def test_plate_rows_cover_the_whole_old_caption_box(make_video, tmp_path):
    caps = [(0, 1, 930, "mmmm nnnn"), (1, 2, 930, "uuuu wwww")]  # no ascenders: short text band, full-height box
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda img, mask: img)
    f = frame_at(v, 0.5, gray=True)[:, 300:420]
    box = np.where(((f > 220) & (f < 236)).sum(1) > 60)[0]  # rows of the light-grey caption box
    height = Image.open(tmp_path / "p" / f"{plates[0].name}.png").height
    assert plates[0].y <= box.min() and plates[0].y + height >= box.max() + 1


def test_plates_sit_on_even_pixels(make_video, tmp_path):
    # yuv420 overlay rounds odd x/y down to even, shifting a patch by 1 px and leaving a sliver of the old box
    caps = [(0, 0.7, 931, "mmmm nnnn"), (0.7, 1.4, 931, "uuuu wwww xx"), (1.4, 2, 931, "ab")]
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    plates = build_plates(v, detect_fragments(v), tmp_path / "p", Path("unused"), inpaint=lambda img, mask: img)
    w, h = Image.open(tmp_path / "p" / f"{plates[0].name}.png").size
    assert plates[0].x % 2 == plates[0].y % 2 == w % 2 == h % 2 == 0


# ---- vshort clean: old captions removed frame by frame ----

from vshort import plates  # noqa: E402
from vshort.media import iter_frames, probe  # noqa: E402

DISSOLVE = [(0, 0.8, "artbar"), (0.8, 1.4, "fade:artbar:#A0A0A0"), (1.4, 2.0, "#A0A0A0")]


def _oracle(truth: Path):
    """An inpainter that knows the answer: the caption-free frame whose picture outside the mask matches."""
    frames = [f.astype(np.int16) for _, f in iter_frames(truth, gray=False)]

    def run(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        keep = ~mask
        best = min(frames, key=lambda f: np.abs(f[keep] - img[keep]).mean())
        out = img.copy()
        out[mask] = best[mask]
        return out

    return run


def _frags(caps) -> list[Fragment]:
    """The captions as `vshort text` leaves them (a dissolving art bar would merge with the caption's ink band in detect)."""
    return [Fragment(i, a, b, y - 25, y + 25, text) for i, (a, b, y, text) in enumerate(caps)]


def _caption_pair(make_video, tmp_path, scenes, caps):
    truth = make_video(tmp_path, scenes=scenes, captions=[])
    src = make_video(tmp_path, scenes=scenes, captions=caps)
    return src, truth


def test_clean_removes_a_caption_across_a_dissolve(make_video, tmp_path):
    caps = [(0.3, 1.0, 930, "to process it,"), (1.0, 1.7, 930, "and the server")]
    src, truth = _caption_pair(make_video, tmp_path, DISSOLVE, caps)
    plates.clean(src, _frags(caps), tmp_path / "clean.mp4", Path("unused"), inpaint=_oracle(truth))
    for t in (0.5, 0.9, 1.1, 1.25, 1.6):
        out, ok = frame_at(tmp_path / "clean.mp4", t, gray=True), frame_at(truth, t, gray=True)
        assert np.abs(out[870:990].astype(int) - ok[870:990]).mean() < 3, t  # no box, no seam, the bar still there
        was = frame_at(src, t, gray=True)
        assert np.abs(out[:800].astype(int) - was[:800]).mean() < 2.5, t  # the rest as it came (one more encode: ±2 on mixed colours)


def test_clean_leaves_frames_without_captions_alone(make_video, tmp_path):
    caps = [(1.5, 1.9, 930, "late words")]
    src, truth = _caption_pair(make_video, tmp_path, DISSOLVE, caps)
    plates.clean(src, _frags(caps), tmp_path / "clean.mp4", Path("unused"), inpaint=_oracle(truth))
    out, ok = frame_at(tmp_path / "clean.mp4", 0.5, gray=True), frame_at(src, 0.5, gray=True)
    assert np.abs(out[:1200].astype(int) - ok[:1200]).mean() < 1


def test_clean_inpaints_once_per_still_scene(make_video, tmp_path):
    caps = [(0.1, 0.6, 930, "one"), (0.6, 1.2, 930, "two"), (1.2, 1.9, 930, "three")]
    src, truth = _caption_pair(make_video, tmp_path, [(0, 2, "artbar")], caps)
    calls = []
    oracle = _oracle(truth)
    plates.clean(src, _frags(caps), tmp_path / "clean.mp4", Path("unused"),
                 inpaint=lambda img, mask: calls.append(1) or oracle(img, mask))
    assert len(calls) == 1


def test_clean_erases_the_watermark_and_keeps_length(make_video, tmp_path):
    src = make_video(tmp_path, scenes=[(0, 1, "mark")], captions=[])
    info = plates.clean(src, [], tmp_path / "clean.mp4", Path("unused"), inpaint=lambda *a: 1 / 0)
    out = frame_at(tmp_path / "clean.mp4", 0.5, gray=True)
    assert out[1240:1256, 570:670].mean() > 200  # the dark mark is gone: cream again
    assert abs(probe(tmp_path / "clean.mp4").duration - probe(src).duration) < 1 / 30 + 1e-6
    assert info["boxes"] == [] and info["seconds"] >= 0


def test_scene_changes_sees_a_dissolve_not_a_small_pop(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#3C3C3C"), (1, 1.5, "fade:#3C3C3C:#B4B4B4"), (1.5, 2.2, "#B4B4B4"),
                                     (2.2, 3.0, "label")], captions=[])
    got = [t for t, _ in plates.scene_changes(v)]
    assert len(got) == 2 and 1.0 <= got[0] <= 1.7 and 2.1 <= got[1] <= 2.8  # the cut to a new page counts, not a fade's every frame


def test_scene_changes_ignores_a_shape_popping_in(make_video, tmp_path):
    # a 320x50 label (2 % of the frame) pops in at 1 s; Rails' softest real change, pencil page to pencil page, moved 15 %
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "label")], captions=[])
    assert plates.scene_changes(v) == []
