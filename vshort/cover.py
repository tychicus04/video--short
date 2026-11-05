"""Cover images for every video, one 16:9 and one 9:16, from a source's own lead image (og:image), clean and with the
headline on it, and the export folder named by the publish title.

`candidates` gathers the sources' lead images onto a numbered sheet; an agent looks at it and writes cover/pick.json
({"n": k | null, "why": ..., "title": publish title, "thumb": headline, "poster": prompt parts}); `make` cuts the pick
(or, failing that, the video's first still) to both shapes, writes the headline on them and writes cover/prompt.txt, the
prompt Tai pastes into the Gemini app for a poster cover; `package` lays out xuat/<title>/ for the Mac to pull.
"""
import json
import os
import re
import shutil
import unicodedata
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from vshort.textfit import FONTS

SIZES = {"16x9": (1920, 1080), "9x16": (1080, 1920)}
MIN_W, MIN_H = 800, 400  # smaller lead images are icons
MAX_UP = 2.0  # a window blown up more than this goes soft: the whole picture over a blur of itself instead
MAX_PAGES, MAX_BYTES = 10, 20_000_000
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TILE = (480, 270)
THUMB_FONT = FONTS / "BeVietnamPro-ExtraBold.ttf"
HIGHLIGHT = (255, 214, 0)  # *starred* words of the headline
# where the headline sits, px: 16:9 bottom left, clear of the duration badge (bottom right); 9:16 under the middle,
# inside the 3:4 band profile grids show (y 240–1680) and over the blur when a wide picture is fitted
TEXT_BOX = {"16x9": (90, 560, 1480, 1000), "9x16": (70, 1190, 1010, 1640)}
EM = (150, 64)  # largest and smallest headline size, px
MAX_NAME = 200  # bytes of the folder/file name: APFS allows 255, Vietnamese takes 2–3 bytes a letter
# The prompt Tai pastes into the Gemini app to draw a poster cover by hand (an API key that draws costs money: Tai said
# no, 05/11). The agent writes only what changes per video (pick.json "poster"); the frame stays the same every time.
POSTER = """Create a vertical 9:16 cover image for a Vietnamese cybersecurity news short video (TikTok/Reels thumbnail).

Style: dramatic, cinematic, photorealistic digital poster. Dark navy/black background with red danger glow, sparks, \
smoke and fire, high contrast, layered composition filling the whole frame, like a breaking-news alert poster.

{scene}

Top-right corner: a red badge with the bold text "{badge}".

Lower third: a huge bold condensed Vietnamese headline, stacked and centered, with a thick black outline and drop shadow:
{lines}

Spell every Vietnamese text exactly as given, with correct diacritics. No other text, no real company or agency \
logos, no watermark."""
# pasted in the same Gemini chat once the 9:16 one is drawn: the article's lead image
WIDE = """Now make the same poster as a horizontal 16:9 image: same scene and the same headline text, rearranged for the wide \
frame, with the headline on the left half."""
LINE_LOOK = ["red, biggest", "white with the last word in red, big", "yellow, smaller", "white, smaller"]


class _Lead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and self.url is None and a.get("content") \
                and (a.get("property") or a.get("name") or "").lower() in ("og:image", "twitter:image"):
            self.url = a["content"]


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": UA}), timeout=20) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"lớn hơn {MAX_BYTES} byte")
    return data


def lead_image(page: str, html: str) -> str | None:
    p = _Lead()
    p.feed(html)
    return urljoin(page, p.url) if p.url else None


def source_pages(sources_md: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s)>\]|`]+", sources_md)))[:MAX_PAGES]


def candidates(run_dir: Path) -> list[dict]:
    """The sources' lead images big enough to use: cover/cand-N.jpg, cover/candidates.json and a numbered sheet.jpg."""
    out = run_dir / "cover"
    out.mkdir(exist_ok=True)
    rows = []
    for page in source_pages((run_dir / "sources.md").read_text(encoding="utf-8")):
        try:
            src = lead_image(page, fetch(page).decode("utf-8", "replace"))
            img = Image.open(BytesIO(fetch(src))).convert("RGB") if src else None
        except (OSError, ValueError, Image.DecompressionBombError) as e:  # one bad page never stops the others
            print(f"bỏ {page}: {type(e).__name__}: {e}")
            continue
        if img is None or img.width < MIN_W or img.height < MIN_H:
            continue
        rows.append({"n": len(rows) + 1, "page": page, "image": src, "size": list(img.size)})
        img.save(out / f"cand-{len(rows)}.jpg", quality=92)
    (out / "candidates.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    if rows:
        _sheet(out, rows)
    return rows


def _sheet(out: Path, rows: list[dict]) -> None:
    cols = 2
    sheet = Image.new("RGB", (TILE[0] * cols, TILE[1] * -(-len(rows) // cols)), "white")
    font = ImageFont.truetype(FONTS / "BeVietnamPro-ExtraBold.ttf", 44)
    for k, r in enumerate(rows):
        tile = Image.open(out / f"cand-{r['n']}.jpg")
        tile.thumbnail(TILE)
        x, y = k % cols * TILE[0], k // cols * TILE[1]
        sheet.paste(tile, (x + (TILE[0] - tile.width) // 2, y + (TILE[1] - tile.height) // 2))
        ImageDraw.Draw(sheet).text((x + 10, y + 6), str(r["n"]), font=font, fill=(230, 30, 30), stroke_width=3,
                                   stroke_fill="white")
    sheet.save(out / "sheet.jpg", quality=88)


def cut(img: Image.Image, w: int, h: int) -> Image.Image:
    """w×h from img: the window of that shape with the most detail, leaning to the middle (subjects sit there)."""
    W, H = img.size
    cw, ch = (round(H * w / h), H) if W / H > w / h else (W, round(W * h / w))
    if w / cw > MAX_UP:
        return _fit(img, w, h)
    g = np.asarray(img.convert("L"), float)
    detail = np.abs(np.diff(g, axis=0))[:, :-1] + np.abs(np.diff(g, axis=1))[:-1]
    across = cw < W
    prof, span = (detail.sum(0), cw) if across else (detail.sum(1), ch)
    n = len(prof)
    prof = prof * np.exp(-(((np.arange(n) - n / 2) / (n / 2)) ** 2))
    c = np.concatenate([[0.0], np.cumsum(prof)])
    span = min(span, n)
    off = int(np.argmax(c[span:] - c[:-span]))
    box = (off, 0, off + cw, H) if across else (0, off, W, off + ch)
    return img.crop(box).resize((w, h), Image.LANCZOS)


def _fit(img: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / img.width, h / img.height)
    back = img.resize((round(img.width * s), round(img.height * s)))
    back = back.crop(((back.width - w) // 2, (back.height - h) // 2, (back.width - w) // 2 + w, (back.height - h) // 2 + h))
    back = Image.eval(back.filter(ImageFilter.GaussianBlur(30)), lambda v: v * 0.55)
    s = min(w / img.width, h / img.height)
    front = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    back.paste(front, ((w - front.width) // 2, (h - front.height) // 2))
    return back


def _words(text: str) -> list[list[tuple[str, bool]]]:
    """The headline in capitals, word by word, each word as (piece, highlighted) pieces: `*` toggles the highlight."""
    words, hi = [], False
    for tok in unicodedata.normalize("NFC", text).replace("|", " ").upper().split():
        pieces = []
        for k, piece in enumerate(tok.split("*")):
            hi = hi != (k > 0)
            if piece:
                pieces.append((piece, hi))
        if pieces:
            words.append(pieces)
    return words


def _pitch(font) -> tuple[int, int]:
    """(line pitch, ink above the ascender): capitals with stacked marks (Ẩ, Ỗ) rise over the font's ascent."""
    asc, desc = font.getmetrics()
    over = max(0, -font.getbbox("ẨỖẪỂ")[1])
    return asc + desc + over, over


def _layout(words, w: int, h: int):
    """(font, [(line words, line width)]) at the biggest size the words fit w×h in; None when even the smallest does not."""
    for em in range(EM[0], EM[1] - 1, -4):
        font = ImageFont.truetype(str(THUMB_FONT), em)
        space = font.getlength(" ")
        lines: list[tuple[list, float]] = []
        for word in words:
            ww = sum(font.getlength(p) for p, _ in word)
            if lines and lines[-1][1] + space + ww <= w:
                lines[-1] = (lines[-1][0] + [word], lines[-1][1] + space + ww)
            else:
                lines.append(([word], ww))
        if lines and max(lw for _, lw in lines) <= w and len(lines) * _pitch(font)[0] <= h:
            return font, lines
    return None


def headline(img: Image.Image, text: str, shape: str) -> Image.Image | None:
    """img with the headline in TEXT_BOX[shape] over a dark fade; None when it does not fit."""
    x0, y0, x1, y1 = TEXT_BOX[shape]
    fit = _layout(_words(text), x1 - x0, y1 - y0)
    if not fit:
        return None
    font, lines = fit
    pitch, over = _pitch(font)
    top = y1 - len(lines) * pitch
    a = np.asarray(img.convert("RGB"), float)
    fade = np.clip((np.arange(a.shape[0]) - (top - 260)) / 300, 0, 1) * 0.72  # dark under the words, fading out above
    img = Image.fromarray((a * (1 - fade)[:, None, None]).astype(np.uint8))
    d, space, y = ImageDraw.Draw(img), font.getlength(" "), top + over
    for words, lw in lines:
        x = x0 if shape == "16x9" else (x0 + x1 - lw) / 2
        for word in words:
            for piece, hi in word:
                d.text((x, y), piece, font=font, fill=HIGHLIGHT if hi else "white", stroke_width=max(2, font.size // 18),
                       stroke_fill="black")
                x += font.getlength(piece)
            x += space
        y += pitch
    return img


def spoken_title(run_dir: Path) -> str:
    """The video's first sentence, the title it opens with (approved with the brief)."""
    first = json.loads((run_dir / "script.vi.json").read_text(encoding="utf-8"))[0]["phrases"]
    return " ".join(first.replace("|", " ").split())


def folder_name(title: str) -> str:
    """title as a folder/file name that macOS and Windows both take."""
    name = re.sub(r"\s*:\s*", " - ", unicodedata.normalize("NFC", title))
    name = re.sub(r'[\x00-\x1f\\/*?"<>|]+', " ", name)
    name = " ".join(name.split()).strip(" .")
    while len(name.encode()) > MAX_NAME:
        name = name[:-1].rstrip(" .")
    return name or "video"


def poster_prompt(pick: dict) -> str | None:
    """The Gemini prompt from pick.json's "poster" ({"scene", "badge", "lines": 2–4 headline lines}); None when the
    agent wrote none or wrote it in another shape, so a bad prompt never stops the covers."""
    p = pick.get("poster")
    try:
        scene, badge, lines = p["scene"].strip(), p.get("badge", "CẢNH BÁO KHẨN").strip(), [x.strip() for x in p["lines"]]
    except (TypeError, KeyError, AttributeError):
        return None
    if not scene or not badge or not 2 <= len(lines) <= len(LINE_LOOK) or not all(lines):
        return None
    head = "\n".join(f'  line {k + 1}, {look}: "{x}"' for k, (x, look) in enumerate(zip(lines, LINE_LOOK)))
    return POSTER.format(scene=scene, badge=badge, lines=head)


def make(run_dir: Path) -> dict:
    """cover/anh-dai-dien-{16x9,9x16}.jpg from the pick (the video's first still when there is none) and
    cover/thumb-{16x9,9x16}.jpg with the headline on them: the agent's, else the spoken title when it does not fit."""
    out = run_dir / "cover"
    out.mkdir(exist_ok=True)
    pick = json.loads((out / "pick.json").read_text(encoding="utf-8")) if (out / "pick.json").exists() else {}
    rows = {r["n"]: r for r in json.loads((out / "candidates.json").read_text(encoding="utf-8"))} \
        if (out / "candidates.json").exists() else {}
    row = rows.get(pick.get("n"))
    if row:
        img, info = Image.open(out / f"cand-{row['n']}.jpg"), {"from": "source", "page": row["page"], "image": row["image"]}
    else:
        img, info = Image.open(run_dir / "stills" / "1.png"), {"from": "video", "why": pick.get("why", "")}
    img, spoken = img.convert("RGB"), spoken_title(run_dir)
    info["title"] = " ".join((pick.get("title") or spoken).replace("*", "").split())
    for name, (w, h) in SIZES.items():
        clean = cut(img, w, h)
        clean.save(out / f"anh-dai-dien-{name}.jpg", quality=92)
        thumb = (pick.get("thumb") and headline(clean, pick["thumb"], name)) or headline(clean, spoken, name)
        if thumb is None:
            raise ValueError(f"tiêu đề không vừa ảnh {name}: {spoken!r}")
        thumb.save(out / f"thumb-{name}.jpg", quality=92)
    if prompt := poster_prompt(pick):
        (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    else:
        (out / "prompt.txt").unlink(missing_ok=True)  # never an old video's prompt next to a new pick
    (out / "cover.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def package(run_dir: Path) -> Path:
    """xuat/<title>/: <title>.mp4, both headline covers, tieu-de.txt (title, picture credit) and the Gemini prompt, built aside and
    swapped in whole, so the Mac's pull (rsync of */xuat/) never takes half a video or an old title's folder."""
    info = json.loads((run_dir / "cover" / "cover.json").read_text(encoding="utf-8"))
    name, tmp = folder_name(info["title"]), run_dir / ".xuat"
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / name).mkdir(parents=True)
    shutil.copy2(run_dir / "final.mp4", tmp / name / f"{name}.mp4")
    for shape, word in (("16x9", "ngang"), ("9x16", "doc")):
        shutil.copy2(run_dir / "cover" / f"thumb-{shape}.jpg", tmp / name / f"thumb-{word}-{shape}.jpg")
    if (run_dir / "cover" / "prompt.txt").exists():
        (tmp / name / "prompt-anh-bia.txt").write_text(
            (run_dir / "cover" / "prompt.txt").read_text(encoding="utf-8") + "\n\n----- Có ảnh dọc rồi thì dán tiếp câu "
            "này vào cùng cuộc trò chuyện Gemini để có ảnh ngang 16:9 cho bài báo:\n\n" + WIDE + "\n", encoding="utf-8")
    credit = f"\nẢnh bìa: {info['page']}" if info["from"] == "source" else ""
    (tmp / name / "tieu-de.txt").write_text(f"{info['title']}\n{credit}", encoding="utf-8")
    shutil.rmtree(run_dir / "xuat", ignore_errors=True)
    os.replace(tmp, run_dir / "xuat")
    return run_dir / "xuat" / name
