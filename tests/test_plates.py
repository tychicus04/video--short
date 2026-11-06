from pathlib import Path

import numpy as np

from vshort.captions import Fragment
from vshort.media import frame_at
from vshort.plates import scene_cuts


def test_scene_cuts(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    assert [round(t, 2) for t in scene_cuts(v)] == [1.0]


def test_scene_cuts_between_two_dark_scenes(make_video, tmp_path):
    # a dark theme's cut changed the mean grey by only 24.9 (NetamLoader): here 23, but over the whole frame
    v = make_video(tmp_path, scenes=[(0, 1, "#505050"), (1, 2, "#676767")], captions=[])
    assert [round(t, 2) for t in scene_cuts(v)] == [1.0]


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
