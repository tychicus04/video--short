import json
from io import BytesIO
from urllib.error import URLError

import numpy as np
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


def test_headline_stays_in_its_box_and_falls_back_to_the_spoken_title(tmp_path):
    for shape, (w, h) in cover.SIZES.items():
        x0, y0, x1, y1 = cover.TEXT_BOX[shape]
        img = cover.headline(Image.new("RGB", (w, h), (0, 0, 255)), "LỖ HỔNG *ẨN* TRONG BỘ ĐIỀU KHIỂN", shape)
        a = np.asarray(img).astype(int)
        ink = (a[:, :, 0] > 200) & (a[:, :, 2] < 120) | (a.min(2) > 200)  # yellow or white letters
        ys, xs = np.nonzero(ink)
        assert x0 <= xs.min() and xs.max() <= x1 and y0 <= ys.min() and ys.max() <= y1, shape
        assert (a[:, :, 0] > 200)[ink & (a[:, :, 2] < 120)].any()  # the starred word is yellow
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
