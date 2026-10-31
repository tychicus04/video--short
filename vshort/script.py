"""Caption fragments -> English sentences with time windows; checks on the Vietnamese script."""
import math
import re
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
        if f.text.rstrip().endswith((".", "?", "!", "…")):
            sents.append(Sentence(len(sents) + 1, start, f.end, " ".join(words)))
            words, start = [], None
    if words:
        sents.append(Sentence(len(sents) + 1, start, frags[-1].end, " ".join(words)))
    for a, b in zip(sents, sents[1:]):
        a.end = b.start
    return sents


def syllables(text: str) -> int:
    return sum(1 for tok in text.replace("|", " ").replace("*", "").split() if re.search(r"\w", tok))


def budget(s: Sentence, rate: float) -> int:
    return math.floor((s.end - s.start) * rate * 0.95)


def check_script(sentences: list[Sentence], script: list[dict], rate: float) -> list[str]:
    probs = []
    by_id = {row["id"]: row for row in script}
    want = {s.id for s in sentences}
    probs += [f"Thiếu câu {i}" for i in sorted(want - by_id.keys())]
    probs += [f"Thừa câu {i} (không có trong bản tiếng Anh)" for i in sorted(by_id.keys() - want)]
    for n, s in enumerate(sentences):
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
        if syllables(text) > budget(s, rate):
            probs.append(f"Câu {s.id}: quá dài ({syllables(text)} âm tiết, tối đa {budget(s, rate)})")
        if text.count("*") % 2:
            probs.append(f"Câu {s.id}: dấu * tô màu không đóng mở đủ cặp")
    return probs
