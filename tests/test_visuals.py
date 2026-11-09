import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from vshort.textfit import FONTS
from vshort.visuals import patch_text, validate

PAGE = (243, 239, 230)


def _label_image(text="untrusted-site.com") -> Image.Image:
    img = Image.new("RGB", (720, 1280), PAGE)
    ImageDraw.Draw(img).text((104, 100), text, fill=(40, 40, 40),
                             font=ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), 36))
    return img


def _ink(img, box):
    x0, y0, x1, y1 = box
    return np.asarray(img).astype(int)[y0:y1, x0:x1].sum(2) < 400


def _height(mask) -> int:
    rows = mask.any(1).nonzero()[0]
    return rows[-1] - rows[0] + 1


def test_patch_text_replaces_the_label():
    img, box = _label_image(), (96, 96, 404, 144)
    out = patch_text(img, box, "tin-tuc.example")
    before, after = np.asarray(img).astype(int), np.asarray(out).astype(int)
    x0, y0, x1, y1 = box
    old, new = _ink(img, box), _ink(out, box)
    assert old.any() and new.any()
    assert (old ^ new).sum() > old.sum() // 2  # the old strokes are gone, others drawn
    mid = np.median(after[y0:y1, x0:x1].reshape(-1, 3), axis=0)
    assert np.abs(mid - PAGE).max() <= 6
    before[y0:y1, x0:x1] = after[y0:y1, x0:x1] = 0
    assert np.array_equal(before, after)  # nothing outside the box moved
    assert _ink(img, box).any()  # the caller's image is untouched


def _band(mask) -> tuple[int, float]:
    """Height and centre row of the x-height band: rows with at least half the ink of the busiest row."""
    n = mask.sum(1)
    rows = np.flatnonzero(n >= 0.5 * n.max())
    return rows[-1] - rows[0] + 1, (rows[0] + rows[-1]) / 2


@pytest.mark.parametrize("old, new", [
    ("untrusted-site.com", "tin-tuc.example"),  # the new text has a descender (p), the old one has none
    ("copying.page", "tin-tuc.test"),  # the old text has descenders (p, y, g), the new one has none
])
def test_patch_text_matches_the_old_x_height_in_a_loose_or_tight_box(old, new):
    img = _label_image(old)
    old_h, old_mid = _band(_ink(img, (0, 0, 720, 300)))
    bands = []
    for box in [(96, 96, 404, 144), (20, 60, 700, 200)]:  # tight, loose
        out = patch_text(img, box, new)
        bands.append(_band(_ink(out, box)))
        bands[-1] = (bands[-1][0], bands[-1][1] + box[1])
        ink = np.asarray(out).astype(int)[box[1]:box[3], box[0]:box[2]][_ink(out, box)]
        assert ink.sum(1).min() < 150  # the old dark ink colour, not a lightened mix with paper
    assert abs(bands[0][0] - bands[1][0]) <= 1
    assert all(abs(h - old_h) <= 2 and abs(mid - old_mid) <= 3 for h, mid in bands)  # same size, same baseline


def _full_height(text: str, width: int) -> int:
    """Ink height of `text` in Be Vietnam Pro Regular at the size where it is `width` px wide (nothing cut off)."""
    def bbox(em):
        return ImageFont.truetype(str(FONTS / "BeVietnamPro-Regular.ttf"), em).getbbox(text)
    em = min(range(8, 120), key=lambda e: abs(bbox(e)[2] - bbox(e)[0] - width))
    return bbox(em)[3] - bbox(em)[1]


@pytest.mark.parametrize("old, new", [
    ("SOFTWARE UPDATE", "CẬP NHẬT"),  # caps only: stacked marks need more room than the old ink has
    ("secure.com", "Ứng dụng Ếch"),  # x-height only
])
def test_patch_text_never_clips_stacked_diacritics_in_a_tight_box(old, new):
    img = _label_image(old)
    old = _ink(img, (0, 0, 720, 300))
    rows, cols = old.any(1).nonzero()[0], old.any(0).nonzero()[0]
    box = (cols[0] - 6, rows[0] - 6, cols[-1] + 7, rows[-1] + 7)  # a 6 px margin around the old ink
    ink = _ink(patch_text(img, box, new), box)
    cut = ink.any(0).nonzero()[0]
    assert not ink[0].any() and not ink[-1].any()  # nothing touches the top or the bottom edge
    assert _height(ink) >= _full_height(new, cut[-1] - cut[0] + 1) - 2  # all of the glyphs are there


def test_patch_text_ignores_a_hairline_as_old_text():
    img = Image.new("RGB", (720, 1280), PAGE)
    ImageDraw.Draw(img).line((110, 120, 390, 120), fill=(40, 40, 40), width=1)
    for text in ("Cập nhật", "Ế"):  # used to ask for a font of size 0
        ink = _ink(patch_text(img, (96, 96, 404, 144), text), (96, 96, 404, 144))
        assert 12 <= _height(ink) <= 29  # 60 % of the box, readable


def test_patch_text_bold_flag_changes_the_weight():
    img, box = _label_image(), (96, 96, 404, 144)
    regular, bold = (_ink(patch_text(img, box, "tin-tuc.test", bold=b), box).sum() for b in (False, True))
    assert bold > regular * 1.1


def test_patch_text_ink_matches_the_old_ink_on_a_dark_button():
    img = Image.new("RGB", (720, 1280), (30, 60, 120))
    ImageDraw.Draw(img).text((110, 104), "iOS 18.7.6+", fill=(250, 250, 250),
                             font=ImageFont.truetype(str(FONTS / "BeVietnamPro-Bold.ttf"), 30))
    out = np.asarray(patch_text(img, (96, 96, 404, 144), "iOS 26.3.1")).astype(int)
    assert (out[96:144, 96:404].sum(2) > 600).any()  # light text on the dark fill


def _item(**kw):
    return {"kind": "photo", "id": 1, "file": "visuals/1.jpg", "source": "https://a.example/x",
            "accessed": "2026-10-31", "credit": "Nguồn: A", "note": "ảnh minh họa của báo cáo", **kw}


@pytest.mark.parametrize("item, needle", [
    ("not an object", "object"),
    ({"kind": "gif"}, "gif"),
    (_item(), "không còn dùng"),  # reference cards and pencil photos are gone: only patches are left
    ({**_item(), "kind": "svg"}, "không còn dùng"),
    ({"kind": "patch", "ids": [], "box": [0, 0, 10, 10], "text": "x"}, "ids"),
    ({"kind": "patch", "ids": [True], "box": [0, 0, 10, 10], "text": "x"}, "ids"),
    ({"kind": "patch", "ids": [7], "box": [0, 0, 300, 50], "text": "x"}, "[7]"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 10], "text": "x"}, "box"),
    ({"kind": "patch", "ids": [1], "box": [50, 0, 40, 10], "text": "x"}, "box"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 10, 1281], "text": "x"}, "1281"),
    ({"kind": "patch", "ids": [1], "box": [10, 1100, 400, 1150], "text": "x"}, "phụ đề"),
    ({"kind": "patch", "ids": [1], "box": [530, 1235, 700, 1262], "text": "x"}, "watermark"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": " "}, "text"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "a\nb"}, "text"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 40, 20], "text": "một dòng chữ rất dài không vừa"}, "vừa"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "x", "bold": "yes"}, "bold"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "tin-tuc.com"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "https://cai-dat.vn/tin"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "x", "note": ""}, "note"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "x", "note": 5}, "note"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "Tải tại apple.com"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "user@evil.com"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "evil.com."}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "Cài đặt.app mới"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "Tải tại “apple.com”"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "«apple.com»"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "apple.com…"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "<apple.com>"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "Link:apple.com"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "Nguồn/apple.com"}, ".example"),
    ({"kind": "patch", "ids": [1], "box": [0, 0, 300, 50], "text": "apple.com:8080"}, ".example"),
])
def test_validate_reports(item, needle, tmp_path):
    (tmp_path / "visuals").mkdir()
    (tmp_path / "x.jpg").write_bytes(b"x")  # exists, but outside visuals/
    (tmp_path / "visuals" / "1.jpg").write_bytes(b"x")
    probs = validate([item], {1, 2}, tmp_path)
    assert probs and needle in " ".join(probs), probs


def test_validate_accepts_good_patches(tmp_path):
    patch = {"kind": "patch", "ids": [1, 2], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": "địa chỉ sai"}
    assert validate([patch], {1, 2}, tmp_path) == []
    for text in ("tin-tuc.test", "mạng.invalid", "tin-tuc.example.", "Tải tại tin-tuc.example", "iOS 26.3.1", "26.3.1+",
                 "OS Kernel", "payload.dylib", "WebKit.framework", "update.zip", "“tin-tuc.example”",
                 "Link:tin-tuc.test"):
        assert validate([{**patch, "text": text, "bold": True}], {1, 2}, tmp_path) == []


def test_validate_prints_the_box_and_the_text_problem_together(tmp_path):
    probs = validate([{"kind": "patch", "ids": [1], "box": [0, 0, 900, 50], "text": "tin-tuc.com"}], {1}, tmp_path)
    assert any("900" in p for p in probs) and any(".example" in p for p in probs)


def test_appear_time_when_text_is_drawn_mid_line(make_video, tmp_path):
    from vshort.media import frame_at
    from vshort.visuals import appear_time
    v = make_video(tmp_path, scenes=[(0, 2, "drawn")], captions=[])  # cream page; the dark bar (the wrong text) from 1 s
    still = frame_at(v, 1.5, gray=True)
    assert appear_time(v, 0.0, 1.8, (200, 300, 520, 700), still) == pytest.approx(0.9, abs=0.1)


def test_appear_time_when_text_is_there_from_the_start(make_video, tmp_path):
    from vshort.media import frame_at
    from vshort.visuals import appear_time
    v = make_video(tmp_path, scenes=[(0, 2, "drawn")], captions=[])
    assert appear_time(v, 1.2, 1.8, (200, 300, 520, 700), frame_at(v, 1.5, gray=True)) == 1.2


def test_vs_visuals_quotes_the_subtitle_band_the_code_checks():
    from pathlib import Path

    from vshort.visuals import SUBTITLE
    md = (Path(__file__).resolve().parent.parent / "claude" / "agents" / "vs-visuals.md").read_text(encoding="utf-8")
    assert f"vùng phụ đề y {SUBTITLE[1]}–{SUBTITLE[3]}" in md and '"kind": "patch"' in md and "svg" not in md


def test_agents_quote_neon_limits():
    from pathlib import Path

    from vshort.script import SYL_MAX, SYL_MIN
    agents = Path(__file__).resolve().parent.parent / "claude" / "agents"
    writer = (agents / "vs-writer.md").read_text(encoding="utf-8")
    assert all(name in writer for name in ("MAX_TEXT_W", "SYL_MIN", "SYL_MAX")) and f"{SYL_MIN}–{SYL_MAX}" in writer
    # vs-scene.md (MAX_GAP, MAX_TONES) joins with Task 9, which writes the agent
