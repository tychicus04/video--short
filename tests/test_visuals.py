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
    from vshort.scene import MAX_GAP, MAX_TONES
    scene = (agents / "vs-scene.md").read_text(encoding="utf-8")
    assert f"`MAX_GAP` ({MAX_GAP:g} giây)" in scene and f"`MAX_TONES` ({MAX_TONES} màu)" in scene


def _agent_md(name: str) -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")


def test_vs_scene_names_the_whole_vocabulary_the_code_loads():
    from vshort import layout
    from vshort.scene import (BEAT_KEYS, LAYOUTS, LINK_KEYS, LINK_STYLES, NODE_KEYS, OPTIONAL, SECTION_KEYS, TONES, VERBS,
                              icons)
    md = _agent_md("vs-scene")
    assert md.startswith("---\nname: vs-scene\n") and "tools: Read, Write, Bash\n" in md and "model: sonnet\n" in md
    keys = set().union(*VERBS.values(), *OPTIONAL.values(), SECTION_KEYS, NODE_KEYS, LINK_KEYS, BEAT_KEYS)
    slots = {slot for table in layout.SLOTS.values() for slot in table}
    for word in (*VERBS, *icons(), *LAYOUTS, *LINK_STYLES, *TONES, *slots, *keys):
        assert f"`{word}`" in md, word


def test_vs_scene_examples_pass_the_code_checks():
    import json
    import re

    from vshort.scene import Phrase, check, load_scene, resolve
    blocks = re.findall(r"```json\n(.*?)\n```", _agent_md("vs-scene"), re.S)
    assert len(blocks) == 4  # SharePoint, Synology, VPN, and what is said outside the mechanism
    for raw in blocks:
        data = json.loads(raw)
        last = max(b["at"] for sec in data["sections"] for b in sec["beats"])
        table = [Phrase(0, 0.2, 2.7, "Tiêu đề")] + [Phrase(i, 3.0 + 2 * (i - 1), 3.0 + 2 * i, f"cụm {i}") for i in range(1, last + 1)]
        rt = resolve(load_scene(data), table, "Tiêu đề", 4.0 + 2 * last, (0.2, 2.7))  # a voice 2 s a phrase, a beat in each
        assert check(rt, raw) == []  # the words of the example are its own brief: the geometry, colours and gaps are what is tested


def test_vs_reviewer_neon_writes_the_review_vshort_auto_reads():
    md = _agent_md("vs-reviewer-neon")
    assert md.startswith("---\nname: vs-reviewer-neon\n") and "tools: Read, Bash, Write\n" in md and "model: opus\n" in md
    assert all(f'`"{kind}"`' in md for kind in ("scene", "writer", "none"))  # what read_review(kinds=…) takes, and nothing else
    assert all(word in md for word in ('"fix"', "Soát lại", "scene.resolved.json", "script.vi.json", "review.json", "review.md", "final.mp4"))
    assert "visuals" not in md and "translator" not in md  # the old reviewer's agents do not exist here


def _contact_sheets(tmp_path, action_times, total=12.0):
    """Run the contact-sheet code of vs-reviewer-neon.md on a generated 14 s video with actions at `action_times`: the frame times
    on each sheet it makes (it prints them), and the sheets' files."""
    import contextlib
    import io
    import json
    import re
    import subprocess

    from vshort.media import FF
    run, sheets = tmp_path / "run", tmp_path / "sheets"
    run.mkdir()
    sheets.mkdir()
    subprocess.run([FF, "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=720x1280:rate=30:duration=14", "-pix_fmt", "yuv420p",
                    str(run / "final.mp4")], check=True)
    acts = [{"t": t, "do": "on", "ids": ["a"]} for t in action_times]
    (run / "scene.resolved.json").write_text(json.dumps({"total": total, "title": {"t0": 0.5, "t1": 3.4, "out": 3.9}, "actions": acts}))
    [code] = re.findall(r"<<'EOF'\n(.*?)\nEOF", _agent_md("vs-reviewer-neon"), re.S)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(code.replace('Path("RUN")', f"Path({str(run)!r})").replace("/tmp/vs_review/", f"{sheets}/"), {})
    return [json.loads(line.split(" ", 1)[1]) for line in out.getvalue().splitlines()], sorted(sheets.glob("sheet*.png"))


def test_vs_reviewer_neon_contact_sheet_code_runs(tmp_path):
    from PIL import Image
    times, made = _contact_sheets(tmp_path, (4.0, 4.3, 6.0, 7.5, 8.0, 9.0, 10.0, 11.0, 12.0))
    assert len(made) == 2 and Image.open(made[0]).size == (4 * 360, 2 * 664)
    # 4.0 and 4.3 are one frame (4.7), 7.5 and 8.0 one (8.4), the others stand alone (6.4, 9.4, 10.4, 11.4, 12.4); then the title bar
    # typed (3.4) and gone (4.9), the end of the diagram (11.7), the outro (13.0)
    assert times == [[3.4, 4.7, 4.9, 6.4, 8.4, 9.4, 10.4, 11.4], [11.7, 12.4, 13.0]]


def test_vs_reviewer_neon_contact_sheet_keeps_a_frame_for_every_half_second_of_beats(tmp_path):
    # two beats a phrase, 0.5 s apart, a new phrase every 1 s: a cluster must not grow while each gap is under 0.8 s
    times, _ = _contact_sheets(tmp_path, [4.0 + 0.5 * k for k in range(9)])
    frames = [t for sheet in times for t in sheet]
    assert len([t for t in frames if 4.4 <= t <= 8.4]) >= 4
