"""Caption fragments -> English sentences with time windows; checks on the Vietnamese script."""
import math
import re
import unicodedata
from dataclasses import dataclass, replace

from vshort.captions import Fragment
from vshort.textfit import MAX_TEXT_W, NEON_EM, NEON_FONT, text_width


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


PACE = 4.3  # syllables a second: the voice Tai settled on (02/11/2026)
# a line said this much longer than its English stretch (s) holds the picture that long: past runs padded 8–13 s only
# where the translator re-appended the brief's call to action (Rails 16, linux-tcp 12); every other line ≤ 2.1 s
LONGER = 4.0


def check_script(sentences: list[Sentence], script: list[dict]) -> list[str]:
    probs = []
    by_id = {row["id"]: row for row in script}
    want = {s.id for s in sentences}
    probs += [f"Thiếu câu {i}" for i in sorted(want - by_id.keys())]
    probs += [f"Thừa câu {i} (không có trong bản tiếng Anh)" for i in sorted(by_id.keys() - want)]
    first = by_id.get(sentences[0].id) if sentences else None
    if first and not first["phrases"].strip():
        probs.append(f"Câu đầu (câu {sentences[0].id}) là tiêu đề, không được để trống")
    lines = merged(sentences, script)
    for n, s in enumerate(lines):
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
            span = (lines[n + 1].start if n + 1 < len(lines) else s.end) - s.start  # the English stretch it is shown over
            said = syllables(text) / PACE
            if said - span > LONGER:
                probs.append(f"Câu {s.id}: lời Việt ~{said:.0f} giây ({syllables(text)} âm tiết), dài hơn đoạn tiếng Anh "
                             f"({span:.1f} giây) {said - span:.0f} giây — hình sẽ đứng yên chừng ấy: đừng nối ý mà video "
                             "tiếng Anh đã nói ở câu khác (lời kêu gọi, câu chốt)")
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


NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Digits of each number, separators dropped: "2.7" and "2,7", "9,402" and "9.402" are the same number."""
    return {re.sub(r"[.,]", "", m) for m in NUMBER.findall(text)}


def check_numbers(sentences: list[Sentence], script: list[dict]) -> list[str]:
    """Every number the English says is said in Vietnamese too: a figure dropped or changed in translation.

    The opening line is the brief's title, not a translation, and is left out. The other way round is not checked: a
    Vietnamese number the English lacks was mostly "October" → "tháng 10" or "ten" → "10" (5 runs, 03–05/11/2026).
    """
    spoken = {row["id"] for row in script if row["phrases"].strip()}
    said: dict[int, str] = {}  # a line left empty hands its English to the spoken line before it, as its time
    for s in sentences:
        if s.id in spoken or not said:
            said[s.id] = ""
        said[next(reversed(said))] += " " + s.en
    title = next(iter(said), None)
    return [f"Câu {row['id']}: câu tiếng Anh có số {n} mà lời Việt không có; giữ đúng số, hoặc ghi note nhắc số đó "
            "và vì sao bỏ"
            for row in script if row["id"] in said and row["id"] in spoken and row["id"] != title
            for n in sorted(_numbers(said[row["id"]]) - _numbers(row["phrases"]) - _numbers(row.get("note", "")))]


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


# Neon style: Claude writes the Vietnamese narration from the approved brief, so it is checked against the brief
SYL_MIN, SYL_MAX = 260, 390  # 60–90 s of narration at PACE


def _after(brief: str, heading: str) -> list[str]:
    """The stripped lines after the first heading that starts with `heading` ('#', '**' and ':' around it are fine)."""
    lines = [ln.strip() for ln in brief.splitlines()]
    head = next((i for i, ln in enumerate(lines) if ln.strip("#*: ").startswith(heading)), None)
    return [] if head is None else lines[head + 1:]


def brief_title(brief: str) -> str | None:
    """The opening line the brief proposes: the first non-empty line under "Tiêu đề"."""
    return next((ln.strip('#*:"“”') for ln in _after(brief, "Tiêu đề") if ln), None)


def mechanism_steps(brief: str) -> list[str]:
    """The numbered lines under "Cơ chế từng bước", numbers kept ("0. Bình thường: …")."""
    steps = []
    for ln in (ln for ln in _after(brief, "Cơ chế từng bước") if ln):
        if not re.match(r"\d+\.", ln):
            break
        steps.append(ln)
    return steps


def ints(text: str) -> set[int]:
    """Each run of digits is a number, '.', ',', '/' and '-' all break it: "05.11.2026" = "5/11/2026", "9,8" = "9.8"."""
    return {int(d) for d in re.findall(r"\d+", text)}


DECIMAL = re.compile(r"(?<![\d.,])\d+[.,]\d{1,2}(?![\d.,])")  # "2,7", "9.8"; not "05.11.2026" or "9,402"
LIST_NUMBER = re.compile(r"(?m)^\s*\d+\.\s")  # a brief's own "1. …" numbering says nothing about a figure


def unknown_numbers(text: str, ref: str) -> list[str]:
    """The numbers in `text` that `ref` lacks. A decimal is one number, compared whole with , = . ("7,2" is not "2,7");
    any other number is a run of digits (`ints`), counted apart from decimals and from the list numbering of `ref`."""
    have = {d.replace(",", ".") for d in DECIMAL.findall(ref)}
    out = list(dict.fromkeys(d for d in DECIMAL.findall(text) if d.replace(",", ".") not in have))
    known = ints(LIST_NUMBER.sub(" ", DECIMAL.sub(" ", ref)))
    return out + [str(i) for i in sorted(ints(DECIMAL.sub(" ", text)) - known)]


def names(text: str) -> set[str]:
    """Words that look like names: a capital after the first letter ("OpenMatter", "CVE", "iPhone", "5G"), or a
    capitalised word that does not start a sentence (the start of the text, or after . ! ? or :; a | does not)."""
    out = set()
    for m in re.finditer(r"\w+", text):
        w, before = m.group(), text[:m.start()].rstrip()
        if w.isdigit():
            continue
        if any(c.isupper() for c in w[1:]) or (w[0].isupper() and before and before[-1] not in ".!?:"):
            out.add(w)
    return out  # ponytail: a name at the very start of a sentence slips through; add a word list if Tai sees one


def check_neon(script: list[dict], brief: str) -> list[str]:
    """The narration against the brief: first line the brief's title, only the brief's numbers and names, captions that
    fit, the right length. A note on a line explains a number or name the brief writes otherwise."""
    probs = []
    title = brief_title(brief)
    if title is None:
        probs.append("Brief không có mục 'Tiêu đề (câu mở đầu)' để đối chiếu câu đầu")
    for n, row in enumerate(script):
        text = row["phrases"]
        if n == 0:
            if title is not None and _plain(text) != _plain(title):
                probs.append(f"Câu {row['id']}: câu đầu phải là tiêu đề của brief ({title!r}), đang là {text!r}")
            if "|" in text:
                probs.append(f"Câu đầu (câu {row['id']}) phải hiện trọn câu, không được chia bằng '|'")
        else:
            for ph in (p.strip() for p in text.split("|")):
                if (w := text_width(ph, NEON_EM, NEON_FONT)) > MAX_TEXT_W:
                    probs.append(f"Câu {row['id']}: cụm '{ph}' rộng {w:.0f}px, vượt {MAX_TEXT_W}px")
        ref = brief + "\n" + row.get("note", "")
        probs += [f"Câu {row['id']}: lời có số {i} mà brief không có; giữ đúng số trong brief, hoặc ghi note nhắc "
                  "số đó và vì sao khác" for i in unknown_numbers(text, ref)]
        probs += [f"Câu {row['id']}: có tên '{w}' mà brief không có; dùng đúng tên trong brief, hoặc ghi note nhắc "
                  f"'{w}' và vì sao"
                  for w in sorted(names(text)) if not re.search(rf"(?<!\w){re.escape(w)}(?!\w)", ref, re.I)]
    total = sum(syllables(row["phrases"]) for row in script)
    if not SYL_MIN <= total <= SYL_MAX:
        probs.append(f"Lời có {total} âm tiết (~{total / PACE:.0f} giây); cần {SYL_MIN}–{SYL_MAX} âm tiết (60–90 giây)")
    return probs
