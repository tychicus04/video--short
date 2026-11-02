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
    sents, words, start = [], [], None
    for f in frags:
        start = f.start if start is None else start
        words.append(f.text)
        if f.text.rstrip().rstrip("\"”’)").endswith((".", "?", "!", "…")):  # '…needed."' ends a sentence too
            sents.append(Sentence(len(sents) + 1, start, f.end, " ".join(words)))
            words, start = [], None
    if words:
        sents.append(Sentence(len(sents) + 1, start, frags[-1].end, " ".join(words)))
    for a, b in zip(sents, sents[1:]):
        a.end = b.start
    return sents


def syllables(text: str) -> int:
    """Spoken syllables: a Vietnamese word is one vowel cluster, but "Anthropic" is three, "CVE" three, "2026" about eight."""
    n = 0
    for part in re.findall(r"\d+|[^\W\d_]+", text):
        if part.isdigit():
            n += 2 * len(part)  # ponytail: ~2 per digit ("hai nghìn không trăm hai mươi sáu"), not a number reader
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
