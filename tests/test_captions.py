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
