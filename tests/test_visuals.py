import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from vshort.textfit import FONTS
from vshort.visuals import PAPER, patch_text, pencil, svg_frame, validate

PAGE = (243, 239, 230)


def _label_image() -> Image.Image:
    img = Image.new("RGB", (720, 1280), PAGE)
    ImageDraw.Draw(img).text((104, 100), "untrusted-site.com", fill=(40, 40, 40),
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


def test_patch_text_matches_the_old_text_size_in_a_loose_or_tight_box():
    img = _label_image()
    old_h = _height(_ink(img, (0, 0, 720, 300)))
    heights = []
    for box in [(96, 96, 404, 144), (20, 60, 700, 200)]:  # tight, loose
        out = patch_text(img, box, "tin-tuc.test")  # no descender, like the old label
        heights.append(_height(_ink(out, box)))
        ink = np.asarray(out).astype(int)[box[1]:box[3], box[0]:box[2]][_ink(out, box)]
        assert ink.sum(1).min() < 150  # the old dark ink colour, not a lightened mix with paper
    assert abs(heights[0] - heights[1]) <= 1 and abs(heights[0] - old_h) <= 0.2 * old_h


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


def test_pencil_fits_any_photo():
    for size, bottom in [((1600, 900), 700), ((200, 300), 980)]:  # y where the fitted photo ends
        f = np.asarray(pencil(Image.new("RGB", size, "gray"), "Nguồn: Google")).astype(int)
        bare = np.asarray(pencil(Image.new("RGB", size, "gray"), "")).astype(int)
        assert f.shape == (1280, 720, 3)
        assert np.abs(f[bottom + 6:bottom + 60] - bare[bottom + 6:bottom + 60]).max() > 40  # credit just under it
        assert np.array_equal(f[bottom + 60:], bare[bottom + 60:])  # and nowhere else
        assert np.abs(f[1094:] - PAPER).max() <= 6  # subtitle band and below stay clear


def test_pencil_keeps_the_edges_of_a_photo():
    photo = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(photo).rectangle((100, 100, 300, 300), fill=(20, 20, 20))
    f = np.asarray(pencil(photo, "x")).astype(int)
    assert f[100:940, 40:680].min() < 90  # dark strokes survive
    assert np.abs(f[420:620, 260:460] - PAPER).max() <= 6  # the flat interior dodges to paper


def test_pencil_shrinks_a_long_credit_to_the_frame():
    f = np.asarray(pencil(Image.new("RGB", (400, 400), "gray"), "Nguồn: " + "rất dài " * 12)).astype(int)
    cols = (np.abs(f[846:900] - PAPER).max(2) > 40).any(0).nonzero()[0]
    assert len(cols) and cols.min() >= 16 and cols.max() <= 704


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
    return {"kind": "photo", "id": 1, "file": "visuals/1.jpg", "source": "https://a.example/x", "accessed": "2026-10-31",
            "credit": "Nguồn: A", **kw}


@pytest.mark.parametrize("item, needle", [
    ("not an object", "object"),
    ({"kind": "gif"}, "gif"),
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
    (_item(file="../x.jpg"), "visuals/"),
    (_item(file="visuals/missing.jpg"), "visuals/missing.jpg"),
    (_item(file="/etc/passwd"), "visuals/"),
    (_item(file="visuals/a\0.jpg"), "không hợp lệ"),
    (_item(source="file:///etc/passwd"), "source"),
    (_item(accessed="yesterday"), "accessed"),
    (_item(credit=" "), "credit"),
    (_item(credit="Nguồn:\nA"), "credit"),
    (_item(credit="Nguồn: " + "rất dài " * 20), "credit"),
    (_item(id=7), "7"),
])
def test_validate_reports(item, needle, tmp_path):
    (tmp_path / "visuals").mkdir()
    (tmp_path / "x.jpg").write_bytes(b"x")  # exists, but outside visuals/
    (tmp_path / "visuals" / "1.jpg").write_bytes(b"x")
    probs = validate([item], {1, 2}, tmp_path)
    assert probs and needle in " ".join(probs), probs


def test_validate_accepts_good_items_and_flags_duplicate_references(tmp_path):
    (tmp_path / "visuals").mkdir()
    (tmp_path / "visuals" / "1.jpg").write_bytes(b"x")
    patch = {"kind": "patch", "ids": [1, 2], "box": [96, 96, 404, 144], "text": "tin-tuc.example", "note": ""}
    assert validate([patch, _item()], {1, 2}, tmp_path) == []  # a patch plus a reference on one line is fine
    for text in ("tin-tuc.test", "mạng.invalid", "iOS 26.3.1", "26.3.1+", "Cài đặt.app mới", "OS Kernel"):
        assert validate([{**patch, "text": text, "bold": True}], {1, 2}, tmp_path) == []
    assert any("1" in p for p in validate([_item(), _item()], {1}, tmp_path))


def test_validate_prints_the_box_and_the_text_problem_together(tmp_path):
    probs = validate([{"kind": "patch", "ids": [1], "box": [0, 0, 900, 50], "text": "tin-tuc.com"}], {1}, tmp_path)
    assert any("900" in p for p in probs) and any(".example" in p for p in probs)
