import pytest

from vshort.captions import detect_fragments, find_bands, write_sheets

CAPS = [(0.0, 0.5, 930, "How can an iPhone"), (0.5, 1.0, 930, "be taken over"),
        (1.0, 1.5, 1147, "without a single"), (1.5, 2.0, 1147, "click?")]


def test_find_bands(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=CAPS)
    bands = find_bands(v)
    assert len(bands) == 2
    assert bands[0][0] < 930 < bands[0][1] and bands[1][0] < 1147 < bands[1][1]


def test_detect_fragments_times_and_bands(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "#EDEDED")], captions=CAPS)
    fr = detect_fragments(v)
    assert len(fr) == 4
    assert [round(f.start, 2) for f in fr] == [0.0, 0.5, 1.0, 1.5]
    assert fr[2].y0 < 1147 < fr[2].y1


def test_write_sheets(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=CAPS)
    sheets = write_sheets(v, detect_fragments(v), tmp_path / "sheets", per_sheet=3)
    assert len(sheets) == 2 and all(s.exists() for s in sheets)


def test_low_captions_found_while_a_dark_label_fills_the_upper_band(make_video, tmp_path):
    caps = [(0.0, 0.5, 930, "Top one"), (0.5, 1.0, 930, "Top two"),
            (1.0, 1.5, 1147, "Low one"), (1.5, 2.0, 1147, "Low two")]
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "label")], captions=caps)
    fr = detect_fragments(v)
    assert [round(f.start, 2) for f in fr if f.y0 > 1000] == [1.0, 1.5]
    assert [f.i for f in fr] == list(range(len(fr)))


def test_write_sheets_keeps_simultaneous_captions_in_two_bands(make_video, tmp_path):
    caps = [(0.0, 1.0, 930, "Upper"), (0.0, 1.0, 1147, "Lower"), (1.0, 2.0, 930, "Upper two")]
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=caps)
    fr = detect_fragments(v)
    sheets = write_sheets(v, fr, tmp_path / "sheets", per_sheet=22)
    assert len(fr) == 3 and len(sheets) == 1


@pytest.mark.xfail(strict=True, reason="known limit: a caption height used by <5 % of samples is not a band; "
                   "a lower toggle count merges nearby animated art into the caption band (seen on the English run)")
def test_band_used_by_one_short_scene_is_found(make_video, tmp_path):
    caps = [(k * 0.5, k * 0.5 + 0.5, 930, f"Main caption {k}") for k in range(40) if not 10 <= k < 13]
    caps += [(5.0, 5.5, 1147, "Rare one"), (5.5, 6.0, 1147, "Rare two"), (6.0, 6.5, 1147, "Rare three")]
    v = make_video(tmp_path, scenes=[(0, 20, "#F3EFE6")], captions=caps, fps=10)
    assert len(find_bands(v)) == 2
