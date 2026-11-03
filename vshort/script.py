"""Caption fragments -> English sentences with time windows; checks on the Vietnamese script."""
import math
import re
import unicodedata
from dataclasses import dataclass, replace

from vshort.captions import Fragment
from vshort.textfit import MAX_TEXT_W, text_width


@dataclass
class Sentence:
    id: int
    start: float
    end: float
    en: str


def merge_text(frags: list[Fragment], texts: dict[int, str]) -> list[Fragment]:
    """Attach read text; drop non-captions (empty text); fuse a caption repeated across a scene cut."""
    out: list[Fragment] = []
    for f in frags:
        text = (texts.get(f.i) or "").strip()
        if not text:
            continue
        if out and out[-1].text == text and math.isclose(out[-1].end, f.start, abs_tol=0.05):
            out[-1].end = f.end
        else:
            out.append(replace(f, text=text))
    return out


def group_sentences(frags: list[Fragment]) -> list[Sentence]:
    sents, words, start, glue = [], [], None, False
    for f, nxt in zip(frags, [*frags[1:], None]):
        start = f.start if start is None else start
        if glue:
            words[-1] = words[-1].rstrip() + f.text
        else:
            words.append(f.text)
        # "draining 2." + "7 million": one number cut across two captions, not a sentence end
        # ponytail: short number + "." + caption opening on a digit; "in 2026." + "3 firms" still splits
        glue = bool(nxt and re.search(r"(?<!\d)\d{1,3}\.$", f.text.rstrip()) and nxt.text[:1].isdigit())
        if not glue and f.text.rstrip().rstrip("\"”’)").endswith((".", "?", "!", "…")):  # '…needed."' ends a sentence too
            sents.append(Sentence(len(sents) + 1, start, f.end, " ".join(words)))
            words, start = [], None
    if words:
        sents.append(Sentence(len(sents) + 1, start, frags[-1].end, " ".join(words)))
    for a, b in zip(sents, sents[1:]):
        a.end = b.start
    return sents


def _number(digits: str) -> int:
    """Syllables of an integer read aloud: 700 "bảy trăm" is 2, 2026 "hai nghìn không trăm hai mươi sáu" is 7."""
    groups = [int(g) for g in f"{int(digits):,}".split(",")]
    if groups == [0]:
        return 1  # "không"
    n = 0
    for i, g in enumerate(groups):
        if not g:
            continue
        hundreds, tens, ones = g // 100, g // 10 % 10, g % 10
        inner = hundreds or i > 0  # "không trăm" inside a number
        if inner:
            n += 2  # "bảy trăm"
        if tens > 1:
            n += 2  # "hai mươi"
        elif tens == 1:
            n += 1  # "mười"
        elif ones and inner:
            n += 1  # "linh"
        n += ones > 0
        n += i < len(groups) - 1  # "nghìn", "triệu", "tỷ"
    return n


def syllables(text: str) -> int:
    """Spoken syllables: a Vietnamese word is one vowel cluster, but "Anthropic" is three, "CVE" three, "2026" seven."""
    n = 0
    for part in re.findall(r"\d+(?:\.\d{3})*(?:,\d+)?|[^\W\d_]+", text):
        if part[0].isdigit():
            whole, _, frac = part.replace(".", "").partition(",")  # "5.500" thousands, "2,7" decimal
            n += _number(whole) + (1 + _number(frac) if frac else 0)  # "phẩy"
        elif part.isascii() and part.isupper():
            n += len(part)  # spelled out
        else:
            bare = "".join(c for c in unicodedata.normalize("NFD", part.lower()) if not unicodedata.combining(c))
            n += max(len(re.findall(r"[aeiouy]+", bare)), 1)
    return n


def merged(sentences: list[Sentence], script: list[dict]) -> list[Sentence]:
    """Sentences that get a Vietnamese line; a line left empty hands its time to the line before it."""
    said = {row["id"] for row in script if row["phrases"].strip()}
    out: list[Sentence] = []
    for s in sentences:
        if s.id in said or not out:
            out.append(s)
        else:
            out[-1] = replace(out[-1], end=s.end)
    return out


def check_script(sentences: list[Sentence], script: list[dict]) -> list[str]:
    probs = []
    by_id = {row["id"]: row for row in script}
    want = {s.id for s in sentences}
    probs += [f"Thiếu câu {i}" for i in sorted(want - by_id.keys())]
    probs += [f"Thừa câu {i} (không có trong bản tiếng Anh)" for i in sorted(by_id.keys() - want)]
    first = by_id.get(sentences[0].id) if sentences else None
    if first and not first["phrases"].strip():
        probs.append(f"Câu đầu (câu {sentences[0].id}) là tiêu đề, không được để trống")
    for n, s in enumerate(merged(sentences, script)):
        row = by_id.get(s.id)
        if not row:
            continue
        text = row["phrases"]
        if n == 0 and "|" in text:
            probs.append(f"Câu đầu (câu {s.id}) phải hiện trọn câu, không được chia bằng '|'")
        if n > 0:
            for ph in (p.strip() for p in text.split("|")):
                if text_width(ph) > MAX_TEXT_W:
                    probs.append(f"Câu {s.id}: cụm '{ph}' rộng {text_width(ph):.0f}px, vượt {MAX_TEXT_W}px")
    return probs


# ponytail: fixed word list; read the brief's own "Không nói …" phrases if one slips through
ABSOLUTE = ("hoàn toàn", "tuyệt đối", "không gián đoạn", "không ngắt", "100%")


def _plain(text: str) -> str:
    return " ".join(text.replace("|", " ").split()).lower()


# ponytail: patterns seen in the first two runs; add one when Tai flags another
STIFF = {
    r"\bmột cách\b(?! (?:khác|để|nào|mà)\b)": "bỏ 'một cách', dùng thẳng tính từ ('cứ thế nhận', 'chạy nhanh')",
    r"\b(?:bị|được)\b[^,.;:?!]{0,40}?\bbởi\b(?! vì)": "bị động kiểu Anh: đưa người làm lên trước ('kẻ tấn công gửi tới…')",
    r"\bhãy xét\b": "'Take a…' không phải 'hãy xét': 'Thử hình dung…', 'Ví dụ…'",
    r"\blấy\b[^,.;:?!]{0,30}?\blàm ví dụ\b": "'Take X' không phải 'lấy X làm ví dụ': 'Bắt đầu với X.'",
    r"\bdễ tổn thương\b": "'vulnerable' của máy/phần mềm là 'có lỗ hổng', 'chưa vá'",
}


def check_style(script: list[dict]) -> list[str]:
    """Translationese a Vietnamese narrator would never say aloud; a note naming the words keeps them."""
    probs = []
    for row in script:
        note = _plain(row.get("note", ""))
        for pat, fix in STIFF.items():
            m = re.search(pat, _plain(row["phrases"]))
            if m and m.group(0) not in note:
                probs.append(f"Câu {row['id']}: '{m.group(0)}' là văn dịch — {fix}; "
                             f"hoặc ghi note nhắc '{m.group(0)}' và vì sao giữ")
    return probs


def check_brief(script: list[dict], brief: str) -> list[str]:
    """What only the brief can catch: absolute claims left unexplained, and an ending that is not the approved call to action."""
    probs = []
    for row in script:
        note = _plain(row.get("note", ""))
        probs += [f"Câu {row['id']}: có '{w}' — brief thường cấm khẳng định tuyệt đối; "
                  f"bỏ, viết lại theo mục Lưu ý của brief, hoặc ghi note nhắc '{w}' và vì sao giữ"
                  for w in ABSOLUTE if w in _plain(row["phrases"]) and w not in note]
    lines = [ln.strip() for ln in brief.splitlines()]
    head = next((i for i, ln in enumerate(lines) if ln.strip("#*: ") == "Lời kêu gọi"), None)
    cta = next((ln.strip('"“”') for ln in lines[head + 1:] if ln), "") if head is not None else ""
    said = [row for row in script if row["phrases"].strip()]
    if cta and said and not _plain(said[-1]["phrases"]).endswith(_plain(cta)) and not said[-1].get("note", "").strip():
        probs.append(f"Câu {said[-1]['id']} là câu cuối nhưng không kết bằng nguyên văn lời kêu gọi trong brief "
                     f"({cta!r}); nếu câu tiếng Anh là câu chốt thì giữ nó và nối lời kêu gọi sau, hoặc ghi note vì sao khác")
    return probs
