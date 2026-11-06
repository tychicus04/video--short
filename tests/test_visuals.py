import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from vshort.textfit import FONTS
from vshort.visuals import (PAPER, REF_RIGHT, REF_RIGHT_FROM, SUBTITLE, patch_text, pencil, svg_frame, ui_problems,
                            validate)

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


def test_pencil_fits_any_photo_clear_of_the_platforms():
    for size, wide in [((1600, 900), True), ((200, 300), False)]:
        f = np.asarray(pencil(Image.new("RGB", size, "gray"), "Nguồn: Google")).astype(int)
        bare = np.asarray(pencil(Image.new("RGB", size, "gray"), "")).astype(int)  # flat gray turns to paper: the frame
        assert f.shape == (1280, 720, 3)
        ink = np.abs(bare - PAPER).max(2) > 40
        rows, cols = np.nonzero(ink.any(1))[0], np.nonzero(ink.any(0))[0]
        assert (cols[-1] - cols[0] > 600) == wide  # a wide photo keeps the full width, above the button column
        bottom = rows[-1]
        assert np.abs(f[bottom + 6:bottom + 60] - bare[bottom + 6:bottom + 60]).max() > 40  # credit just under it
        assert np.array_equal(f[bottom + 60:], bare[bottom + 60:])  # and nowhere else
        assert ui_problems(Image.fromarray(f.astype(np.uint8))) == []  # pushed in, nothing under the platforms
        assert np.abs(f[SUBTITLE[1]:] - PAPER).max() <= 6


def test_reference_ink_where_the_platforms_draw_is_flagged():
    img = Image.new("RGB", (720, 1280), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle((60, 300, 680, 520), outline=(74, 74, 74), width=2)  # full width, above the button column: fine
    assert ui_problems(img) == []
    d.rectangle((60, 560, 610, 900), outline=(74, 74, 74), width=2)  # beside the buttons but 12 px too far right
    assert [p.split(" (")[0] for p in ui_problems(img)] == [f"có nét vẽ ở x > {REF_RIGHT} từ y {REF_RIGHT_FROM} trở xuống"]


def test_pencil_keeps_the_edges_of_a_photo():
    photo = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(photo).rectangle((100, 100, 300, 300), fill=(20, 20, 20))
    f = np.asarray(pencil(photo, "")).astype(int)  # no credit: its ink is dark too
    ys, xs = np.nonzero(f.min(2) < 90)  # dark strokes survive: the square's outline
    cy, cx = (ys.min() + ys.max()) // 2, (xs.min() + xs.max()) // 2
    assert ys.max() - ys.min() > 200 and xs.max() - xs.min() > 200
    assert np.abs(f[cy - 60:cy + 60, cx - 60:cx + 60] - PAPER).max() <= 6  # the flat interior dodges to paper


def test_pencil_shrinks_a_long_credit_to_the_frame():
    img = pencil(Image.new("RGB", (400, 400), "gray"), "Nguồn: " + "rất dài " * 12)
    f, bare = (np.asarray(i).astype(int) for i in (img, pencil(Image.new("RGB", (400, 400), "gray"), "")))
    cols = (np.abs(f - bare).max(2) > 40).any(0).nonzero()[0]
    assert len(cols) and cols.max() - cols.min() > 400 and ui_problems(img) == []  # wide, still left of the buttons


def _svg(tmp_path, family):
    p = tmp_path / f"{family.replace(' ', '')}.svg"
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 1280"><text x="20" y="400" '
                 f'font-size="64" font-family="{family}">Cập nhật phần mềm</text></svg>', encoding="utf-8")
    return p


def test_svg_frame_resolves_patrick_hand(tmp_path):
    widths = []
    for family in ("Patrick Hand", "DejaVu Sans"):
        img = svg_frame(_svg(tmp_path, family))
        f = np.asarray(img).astype(int)
        assert img.size == (720, 1280) and tuple(f[0, 0]) == PAPER
        cols = (np.abs(f - PAPER).max(2) > 40).any(0).nonzero()[0]
        assert len(cols)
        widths.append(cols.max() - cols.min())
    assert abs(widths[0] - widths[1]) > 20  # the same fallback font twice would give equal widths


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
