import json
from io import BytesIO
from urllib.error import URLError

import numpy as np
import pytest
from PIL import Image

from vshort import cover
from vshort.cli import main
from vshort.run import Run


def _jpg(w, h, color=(90, 90, 90)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


def test_lead_image_reads_og_or_twitter_image_in_any_attribute_order():
    page = "https://example.org/news/a"
    assert cover.lead_image(page, '<meta content="/img/a.jpg" property="og:image">') == "https://example.org/img/a.jpg"
    assert cover.lead_image(page, '<meta name="twitter:image" content="https://cdn.x/b.png">') == "https://cdn.x/b.png"
    assert cover.lead_image(page, '<meta property="og:title" content="t">') is None


def test_source_pages_in_order_once_each():
    md = "| a | https://a.org/1 | x |\n| b | https://b.org/2 | y |\nsee https://a.org/1 again (https://c.org/3)"
    assert cover.source_pages(md) == ["https://a.org/1", "https://b.org/2", "https://c.org/3"]


def test_cut_keeps_the_detailed_middle_and_the_output_size():
    img = Image.new("RGB", (2400, 1200), (60, 60, 60))
    noise = np.random.default_rng(0).integers(0, 255, (1200, 500, 3), np.uint8)
    img.paste(Image.fromarray(noise), (950, 0))  # the subject: x 950-1450
    tall = cover.cut(img, 1080, 1920)
    assert tall.size == (1080, 1920)
    assert np.asarray(tall)[:, 540].std() > 40  # the middle column of the cover is the busy subject
    assert cover.cut(img, 1920, 1080).size == (1920, 1080)


def test_cut_shows_the_whole_picture_rather_than_blow_up_a_sliver():
    img = Image.new("RGB", (1200, 630), (200, 200, 200))
    img.paste((255, 0, 0), (0, 0, 100, 630))
    img.paste((0, 0, 255), (1100, 0, 1200, 630))
    mid = np.asarray(cover.cut(img, 1080, 1920))[960]  # a 9:16 slice would be blown up 3x: fit it instead
    assert (mid[:, 0] > 200).any() and (mid[:, 2] > 200).any()  # both coloured edges are in the cover
    raised = np.asarray(cover.cut(img, 1080, 1920, bottom=1020))[:, 5, 0]  # the red edge's column
    assert (raised[:1021] > 200).sum() > 500 and not (raised[1021:] > 200).any()  # the whole picture ends above the bar


def test_candidates_keep_big_lead_images_and_survive_bad_pages(tmp_path, monkeypatch):
    (tmp_path / "sources.md").write_text("https://a.org/1 https://b.org/2 https://c.org/3 https://d.org/4")
    web = {"https://a.org/1": b'<meta property="og:image" content="https://a.org/big.jpg">',
           "https://a.org/big.jpg": _jpg(1600, 900),
           "https://b.org/2": b'<meta property="og:image" content="https://b.org/icon.jpg">',
           "https://b.org/icon.jpg": _jpg(200, 200),
           "https://d.org/4": b"<p>no lead image</p>"}

    def fetch(url):
        if url not in web:
            raise URLError("down")
        return web[url]

    monkeypatch.setattr(cover, "fetch", fetch)
    rows = cover.candidates(tmp_path)
    assert [(r["n"], r["page"]) for r in rows] == [(1, "https://a.org/1")]
    assert (tmp_path / "cover" / "cand-1.jpg").exists() and (tmp_path / "cover" / "sheet.jpg").exists()
    assert json.loads((tmp_path / "cover" / "candidates.json").read_text()) == rows


def _run(tmp_path):
    """A finished run: first still, opening title, final.mp4."""
    run = tmp_path / "run"
    (run / "cover").mkdir(parents=True)
    (run / "stills").mkdir()
    Image.new("RGB", (720, 1280), (10, 120, 10)).save(run / "stills" / "1.png")
    (run / "script.vi.json").write_text(json.dumps([{"id": 1, "phrases": "Phần mềm *hợp lệ* | vẫn chở mã độc", "note": ""}]))
    (run / "final.mp4").write_bytes(b"video")
    return run


def test_cover_cmd_uses_the_pick_else_the_first_still(tmp_path):
    run = _run(tmp_path)
    (run / "cover" / "cand-1.jpg").write_bytes(_jpg(2400, 1200, (200, 30, 30)))
    (run / "cover" / "candidates.json").write_text(json.dumps(
        [{"n": 1, "page": "https://a.org/1", "image": "https://a.org/big.jpg", "size": [2400, 1200]}]))
    (run / "cover" / "pick.json").write_text(json.dumps({"n": 1, "why": "the report's own picture"}))
    assert main(["cover", str(run)]) == 0
    info = json.loads((run / "cover" / "cover.json").read_text())
    assert info["from"] == "source" and info["page"] == "https://a.org/1"
    for name, size in (("anh-dai-dien-16x9.jpg", (1920, 1080)), ("anh-dai-dien-9x16.jpg", (1080, 1920))):
        im = Image.open(run / "cover" / name)
        assert im.size == size and im.getpixel((size[0] // 2, size[1] // 2))[0] > 150  # the picked picture
    assert Run(run).done("cover")

    (run / "cover" / "pick.json").write_text(json.dumps({"n": None, "why": "only logos"}))
    assert main(["cover", str(run)]) == 0
    assert json.loads((run / "cover" / "cover.json").read_text())["from"] == "video"
    assert Image.open(run / "cover" / "anh-dai-dien-9x16.jpg").getpixel((540, 960))[1] > 80  # the green still


def test_auto_cover_line_falls_back_to_the_video_still_when_the_agent_fails(tmp_path):
    from vshort import auto

    run = _run(tmp_path)
    line = auto._cover(Run(run))  # `claude` is `false` in tests: the agent fails
    assert "Tiêu đề: Phần mềm hợp lệ vẫn chở mã độc" in line and "ảnh từ video, nên thay" in line
    assert "~/Movies/vshort/Phần mềm hợp lệ vẫn chở mã độc/" in line


def test_folder_name_takes_any_title_macos_and_windows_accept():
    assert cover.folder_name("Lỗ hổng CVSS 10: chiếm cụm / không cần khóa?") == "Lỗ hổng CVSS 10 - chiếm cụm không cần khóa"
    long = cover.folder_name("Ổ " * 200)
    assert len(long.encode()) <= cover.MAX_NAME and not long.endswith(" ")
    assert cover.folder_name(" ... ") == "video"


def test_headline_sits_in_the_title_bar_and_falls_back_to_the_spoken_title(tmp_path):
    for shape, (w, h) in cover.SIZES.items():
        (sx0, sy0, sx1, sy1), (x0, y0, x1, y1) = cover.BAR[shape]
        img = cover.headline(Image.new("RGB", (w, h), (0, 0, 255)), "LỖ HỔNG *ẨN* TRONG BỘ ĐIỀU KHIỂN", shape)
        a = np.asarray(img).astype(int)
        assert tuple(a[(sy0 + sy1) // 2, (sx0 + sx1) // 2]) == cover.YELLOW, shape  # the stripe
        assert tuple(a[y0 + 3, x1 - 3]) == cover.TEAL and tuple(a[0, 0]) == (0, 0, 255), shape  # the box; no fade
        ys, xs = np.nonzero(a.min(2) > 200)  # white letters
        assert x0 < xs.min() and xs.max() < x1 and y0 < ys.min() and ys.max() < y1, shape
        yellow = (a[:, :, 0] > 200) & (a[:, :, 1] > 200) & (a[:, :, 2] < 120)
        assert yellow[y0:y1, x0:x1].any(), shape  # the starred word is yellow
    assert cover.headline(Image.new("RGB", (1920, 1080)), "chữ " * 200, "16x9") is None

    run = _run(tmp_path)
    (run / "cover" / "pick.json").write_text(json.dumps({"n": None, "why": "", "title": "T: ổn", "thumb": "chữ " * 200}))
    assert main(["cover", str(run)]) == 0  # too long a headline: the spoken title goes on the picture
    assert json.loads((run / "cover" / "cover.json").read_text())["title"] == "T: ổn"


def test_package_lays_out_one_folder_named_by_the_title(tmp_path):
    run = _run(tmp_path)
    (run / "cover" / "pick.json").write_text(json.dumps({"n": None, "why": "", "title": "Cũ: tên"}))
    assert main(["cover", str(run)]) == 0
    (run / "cover" / "pick.json").write_text(json.dumps({"n": None, "why": "", "title": "Mới: *tên* hay"}))
    assert main(["cover", str(run)]) == 0
    [folder] = (run / "xuat").iterdir()  # the old title's folder is gone
    assert folder.name == "Mới - tên hay"
    assert sorted(f.name for f in folder.iterdir()) == ["Mới - tên hay.mp4", "thumb-doc-9x16.jpg", "thumb-ngang-16x9.jpg",
                                                         "tieu-de.txt"]
    assert (folder / "Mới - tên hay.mp4").read_bytes() == b"video"
    assert (folder / "tieu-de.txt").read_text().startswith("Mới: tên hay\n")
    assert Image.open(folder / "thumb-doc-9x16.jpg").size == (1080, 1920)
    assert not (run / ".xuat").exists()


def test_poster_prompt_goes_with_the_covers_and_the_export(tmp_path):
    run = _run(tmp_path)
    poster = {"scene": "Story: a NAS is held to ransom.", "badge": "CẢNH BÁO KHẨN",
              "lines": ["NAS CHƯA VÁ", "BỊ TỐNG TIỀN!", "Mã độc mã hóa ảnh", "Cập nhật ngay"]}
    (run / "cover" / "pick.json").write_text(json.dumps({"n": None, "why": "", "title": "T", "poster": poster}))
    assert main(["cover", str(run)]) == 0
    prompt = (run / "cover" / "prompt.txt").read_text()
    assert "Story: a NAS is held to ransom." in prompt and '"CẢNH BÁO KHẨN"' in prompt
    assert 'line 1, red, biggest: "NAS CHƯA VÁ"' in prompt and 'line 4, white, smaller: "Cập nhật ngay"' in prompt
    assert cover.WIDE not in prompt  # the 16:9 follow-up is pasted on its own, after the first picture
    saved = (run / "xuat" / "T" / "prompt-anh-bia.txt").read_text()
    assert saved.startswith(prompt) and cover.WIDE in saved

    for bad in ({**poster, "lines": ["một dòng"]}, {**poster, "scene": " "}, {"scene": "x"}, "text"):
        assert cover.poster_prompt({"poster": bad}) is None
    (run / "cover" / "pick.json").write_text(json.dumps({"n": None, "why": "", "title": "T"}))
    assert main(["cover", str(run)]) == 0  # no poster this time: no old prompt left beside the new pick
    assert not (run / "cover" / "prompt.txt").exists() and not (run / "xuat" / "T" / "prompt-anh-bia.txt").exists()


def _png(w, h, color=(200, 0, 0)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def _gif(w, h) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (200, 0, 0)).save(buf, "GIF")
    return buf.getvalue()


def test_save_gemini_converts_and_caps_size(tmp_path):
    p = cover.save_gemini(tmp_path, "9x16", _png(3000, 5333))
    assert p == tmp_path / "cover" / "gemini-9x16.jpg"
    with Image.open(p) as im:
        assert im.format == "JPEG" and max(im.size) == 2048 and abs(im.width / im.height - 3000 / 5333) < 0.01
    assert cover.save_gemini(tmp_path, "16x9", _png(1900, 1080)).name == "gemini-16x9.jpg"  # 1 % off: fine


def test_save_gemini_refuses_wrong_ratio_bad_shape_non_image_and_huge(tmp_path):
    cases = [("4x3", _png(90, 160), "Khổ ảnh phải là 9x16 hoặc 16x9"),
             ("9x16", b"x" * (cover.MAX_UPLOAD + 1), "Ảnh lớn quá 15 MB"),
             ("9x16", b"not an image", "File này không phải ảnh"),
             ("9x16", _png(100, 100), "Ảnh 100×100 không đúng khổ 9x16 \\(lệch quá 5 %\\)"),
             ("16x9", _png(1080, 1920), "không đúng khổ 16x9"),
             ("9x16", _gif(90, 160), "File này không phải ảnh JPEG, PNG hay WebP")]  # only what Gemini gives
    for shape, data, msg in cases:
        with pytest.raises(ValueError, match=msg):
            cover.save_gemini(tmp_path, shape, data)
    assert not list(tmp_path.rglob("*gemini*"))


def test_save_gemini_refuses_too_many_pixels(tmp_path, monkeypatch):
    monkeypatch.setattr(cover, "MAX_PIXELS", 90 * 160 - 1)  # read from the header, before the picture is decoded
    with pytest.raises(ValueError, match="Ảnh lớn quá"):
        cover.save_gemini(tmp_path, "9x16", _png(90, 160))


def test_package_prefers_gemini(tmp_path):
    run = _run(tmp_path)
    assert main(["cover", str(run)]) == 0
    cover.save_gemini(run, "9x16", _png(1080, 1920, (255, 0, 0)))
    cover.package(run)
    [folder] = (run / "xuat").iterdir()
    with Image.open(folder / "thumb-doc-9x16.jpg") as im:
        r, g, b = im.convert("RGB").getpixel((540, 960))
    assert r > 200 and g < 60 and b < 60
    assert (folder / "thumb-ngang-16x9.jpg").read_bytes() == (run / "cover" / "thumb-16x9.jpg").read_bytes()  # no Gemini one
