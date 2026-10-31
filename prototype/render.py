"""Re-caption the NotebookLM short: title bar, phrase subs, iOS 17 patch, no watermark/outro.

Usage: python render.py IN.mp4 OUT.mp4 [--preview T ...]
Timings come from detect.py: det/segments.json holds each burned-in caption fragment.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import ImageFont

HERE = Path(__file__).parent
FONTS = HERE / "fonts"
FF = imageio_ffmpeg.get_ffmpeg_exe()
W = 720
SUB_BOTTOM = 1204  # every caption box sits on this line; old low pills span y 1101-1194
EM = 1000 / 1526  # libass sizes fonts by win ascent+descent; this font's em is 0.655 of that
LINE_H, CAP_EM, PAD_X, PAD_Y = 58, 40, 28, 26
MIN_BOX_W = 480  # widest old pill is ~435px: always cover it
MAX_TEXT_W = 620
CUT = 57.30  # Gemini outro starts here; speech ends ~57.0
WATERMARK = "delogo=x=524:y=1232:w=180:h=32"

# old caption fragments as read off det/crops (segment index -> text)
FRAGS = {
    1: "Làm sao iPhone bị chiếm", 2: "quyền hoàn toàn,", 3: "dù bạn không hề", 4: "bấm vào bất kỳ",
    5: "đường link lạ nào?", 6: "Đó là tấn công", 8: "Zero-click.", 9: "Bạn không cần tải",
    10: "app lậu hay sập bẫy", 11: "lừa đảo nào cả.", 12: "Thử tưởng tượng,", 14: "bạn đang lướt Safari",
    15: "đọc báo trên một", 16: "trang web hoàn", 17: "toàn hợp pháp.", 18: "Nhưng thật ra,",
    20: "trang web đó đã bị", 21: "chèn bộ mã độc Coruna", 22: "hoặc DarkSword hoàn", 23: "toàn vô hình.",
    24: "Nó tự động quét", 25: "xem điện thoại", 26: "có đang chạy phiên", 27: "bản iOS cũ chứa lỗ",
    28: "hổng hay không.", 29: "Nếu đúng mục tiêu,", 30: "nó lập tức", 31: "chọc thủng",
    32: "hàng rào bảo vệ của", 33: "trình duyệt Safari.", 34: "Sau đó bẻ khóa,", 35: "tiến thẳng vào lõi",
    36: "hệ điều hành.", 37: "Khi đã nắm", 38: "toàn quyền,", 39: "phần mềm gián điệp", 40: "bắt đầu gom sạch",
    41: "mật khẩu,", 42: "tin nhắn và ví", 43: "tiền mã hóa để", 44: "gửi cho hacker.", 45: "Mọi thứ diễn ra",
    46: "hoàn toàn vô hình.", 47: "Bạn chỉ mở một", 48: "trang web,", 49: "và chiếc iPhone đã",
    50: "thuộc về kẻ khác.", 51: "Mã độc này hiện", 53: "đã lọt lên mạng.", 54: "Hãy nhớ,",
    55: "bản vá của Apple chỉ", 56: "bảo vệ bạn khi bạn", 57: "thực sự cài nó.", 58: "Hãy vào Cài đặt,",
    60: "Cài đặt chung,", 61: "Cập nhật phần mềm", 62: "ngay hôm nay và chia", 63: "sẻ cho người thân.",
}  # missing indices repeat the previous fragment across a scene cut

# phrases split by |; the first sentence stays whole; *word* = highlighted
SENTENCES = [
    "Làm sao iPhone bị chiếm quyền hoàn toàn, dù bạn không hề bấm vào bất kỳ đường link lạ nào?",
    "Đó là tấn công | *Zero-click.*",
    "Bạn không cần tải app lậu | hay sập bẫy lừa đảo nào cả.",
    "Thử tưởng tượng, | bạn đang lướt *Safari* | đọc báo trên một trang web | hoàn toàn hợp pháp.",
    "Nhưng thật ra, | trang web đó đã bị chèn | bộ mã độc *Coruna* | hoặc *DarkSword* | hoàn toàn vô hình.",
    "Nó tự động quét | xem điện thoại | có đang chạy | phiên bản iOS cũ | chứa lỗ hổng hay không.",
    "Nếu đúng mục tiêu, | nó lập tức chọc thủng | hàng rào bảo vệ | của trình duyệt *Safari.*",
    "Sau đó bẻ khóa, | tiến thẳng vào | *lõi hệ điều hành.*",
    "Khi đã nắm toàn quyền, | phần mềm gián điệp | bắt đầu gom sạch | *mật khẩu, tin nhắn* | và *ví tiền mã hóa* | để gửi cho hacker.",
    "Mọi thứ diễn ra | hoàn toàn vô hình.",
    "Bạn chỉ mở một trang web, | và chiếc iPhone | đã thuộc về kẻ khác.",
    "Mã độc này | hiện đã *lọt lên mạng.*",
    "Hãy nhớ, | bản vá của Apple | chỉ bảo vệ bạn | khi bạn thực sự cài nó.",
    "Hãy vào Cài đặt › | Cài đặt chung › | *Cập nhật phần mềm* | ngay hôm nay | và chia sẻ cho người thân.",
]
TITLE_KICKER = "CORUNA & DARKSWORD"
TITLE = "iPhone bị hack chỉ vì mở 1 trang web"

WHITE, YELLOW, INK = "&HFFFFFF&", "&H00D4FF&", "&H141414&"
CARD_BG, ICON_RED = "&HE7EBEC&", "&H595FCE&"  # sampled from the frame (BGR)
UPDATE_SCENE = (52.53, CUT)

cap_font = ImageFont.truetype(str(FONTS / "BeVietnamPro-ExtraBold.ttf"), CAP_EM)


def fs(em):
    return round(em / EM)


def width(s, font=cap_font):
    return font.getlength(s.replace("*", ""))


def wrap(text, max_w):
    lines, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if cur and width(cand) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    return lines + [cur]


def balanced(text):
    n = len(wrap(text, MAX_TEXT_W))
    lo, hi = 200, MAX_TEXT_W  # narrowest width that keeps the same line count
    while lo < hi:
        mid = (lo + hi) // 2
        if len(wrap(text, mid)) <= n:
            hi = mid
        else:
            lo = mid + 1
    return wrap(text, lo)


def colorize(line):
    parts = line.split("*")
    return "".join(
        (f"{{\\1c{YELLOW}}}" if i % 2 else f"{{\\1c{WHITE}}}") + p for i, p in enumerate(parts) if p
    )


def fix_stars(lines):
    # a highlight may span a line break: close it on one line, reopen on the next
    out, open_ = [], False
    for ln in lines:
        s = ("*" if open_ else "") + ln
        open_ = s.count("*") % 2 == 1
        out.append(s + ("*" if open_ else ""))
    return out


def rrect(x0, y0, x1, y1, r):
    return (
        f"m {x0 + r} {y0} l {x1 - r} {y0} b {x1} {y0} {x1} {y0} {x1} {y0 + r} "
        f"l {x1} {y1 - r} b {x1} {y1} {x1} {y1} {x1 - r} {y1} "
        f"l {x0 + r} {y1} b {x0} {y1} {x0} {y1} {x0} {y1 - r} "
        f"l {x0} {y0 + r} b {x0} {y0} {x0} {y0} {x0 + r} {y0}"
    )


def ts(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def shape(start, end, layer, color, path, alpha="&H00&"):
    return f"Dialogue: {layer},{ts(start)},{ts(end)},Cap,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{color}\\1a{alpha}}}{path}{{\\p0}}\n"


def text(start, end, layer, x, y, body, style="Cap"):
    return f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{{\\an5\\pos({x},{y})}}{body}\n"


def norm(tok):
    return re.sub(r"[^\w-]", "", tok.lower())


def phrases():
    """Time each phrase by spreading every old fragment's span evenly over its syllables."""
    segs = json.loads((HERE / "det" / "segments.json").read_text())
    keys = sorted(FRAGS)
    sylls = []
    for k, nxt in zip(keys, keys[1:] + [None]):
        t0, t1 = segs[k]["start"], segs[nxt]["start"] if nxt else segs[k]["end"]
        toks = [norm(x) for x in FRAGS[k].split() if norm(x)]
        d = (t1 - t0) / len(toks)
        sylls += [(tok, t0 + i * d, t0 + (i + 1) * d) for i, tok in enumerate(toks)]
    out, pos = [], 0
    for sent in SENTENCES:
        for ph in (p.strip() for p in sent.split("|")):
            toks = [norm(x) for x in ph.replace("*", "").split() if norm(x)]
            got = [s[0] for s in sylls[pos : pos + len(toks)]]
            assert got == toks, f"phrase {ph!r} does not match the narration: {got}"
            out.append([sylls[pos][1], sylls[pos + len(toks) - 1][2], ph])
            pos += len(toks)
    assert pos == len(sylls), "phrases do not cover the whole narration"
    for a, b in zip(out, out[1:]):  # no gaps, or the old captions peek through
        a[1] = b[0]
    out[0][0] = 0
    return out


def build_ass():
    ev = []
    for start, end, t in phrases():
        lines = fix_stars(balanced(t))
        h = len(lines) * LINE_H + 2 * PAD_Y
        w = max(max(width(ln) for ln in lines) + 2 * PAD_X, MIN_BOX_W)
        x0, y0 = round((W - w) / 2), SUB_BOTTOM - h
        ev.append(shape(start, end, 1, "&H121212&", rrect(x0, y0, x0 + round(w), y0 + h, 18)))
        for i, ln in enumerate(lines):
            ev.append(text(start, end, 2, W // 2, y0 + PAD_Y + LINE_H * i + LINE_H // 2, colorize(ln)))

    # title bar
    ev.append(shape(0, CUT, 1, "&H121212&", rrect(0, -20, W, 104, 0)))
    ev.append(shape(0, CUT, 1, YELLOW, rrect(0, 101, W, 104, 0)))
    ev.append(text(0, CUT, 2, W // 2, 30, f"{{\\1c{YELLOW}\\fsp4}}{TITLE_KICKER}", "Kicker"))
    ev.append(text(0, CUT, 2, W // 2, 70, TITLE, "Title"))

    # "iOS 17" -> "iOS 26" on the update screen
    a, b = UPDATE_SCENE
    ev.append(shape(a, b, 1, CARD_BG, rrect(262, 414, 366, 488, 4)))
    ev.append(shape(a, b, 1, ICON_RED, rrect(191, 419, 258, 485, 13)))
    ev.append(text(a, b, 2, 224, 448, f"{{\\1c&HFFFFFF&\\fs{fs(26)}}}26", "Patch"))
    ev.append(text(a, b, 2, 306, 434, f"{{\\1c{INK}\\fs{fs(20)}}}iOS 26", "Patch"))

    title_em = 38
    while ImageFont.truetype(str(FONTS / "BeVietnamPro-ExtraBold.ttf"), title_em).getlength(TITLE) > W - 48:
        title_em -= 1

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Be Vietnam Pro ExtraBold,{fs(CAP_EM)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Title,Be Vietnam Pro ExtraBold,{fs(title_em)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Kicker,Be Vietnam Pro Bold,{fs(20)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Patch,Be Vietnam Pro Bold,{fs(20)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return head + "".join(ev)


def main(src, dst, *rest):
    ass = HERE / "v3.ass"
    ass.write_text(build_ass(), encoding="utf-8")
    # paste the clean plates (plates.py) over the old mid-frame captions, then draw subs
    plates = json.loads((HERE / "plates" / "plates.json").read_text())
    inputs, chain, last = [], [f"[0:v]{WATERMARK}[v0]"], "v0"
    for i, pl in enumerate(plates, 1):
        inputs += ["-i", f"plates/{pl['name']}.png"]
        chain.append(
            f"[{last}][{i}:v]overlay={pl['x']}:{pl['y']}:enable='between(t,{pl['start']},{pl['end']})'[v{i}]"
        )
        last = f"v{i}"
    chain.append(f"[{last}]ass={ass.name}:fontsdir={FONTS.name}[out]")
    vf = ";".join(chain)
    if rest[:1] == ("--preview",):
        for t in rest[1:]:
            subprocess.run(
                [FF, "-loglevel", "error", "-y", "-i", src, *inputs, "-ss", t, "-filter_complex", vf,
                 "-map", "[out]", "-frames:v", "1",
                 str(Path(dst).with_suffix(f".{t}.png"))],
                cwd=HERE, check=True,
            )
        return
    subprocess.run(
        [FF, "-loglevel", "error", "-y", "-i", src, *inputs, "-t", str(CUT), "-filter_complex", vf,
         "-map", "[out]", "-map", "0:a",
         "-af", f"afade=t=out:st={CUT - 0.25}:d=0.25", "-c:v", "libx264", "-crf", "18",
         "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", dst],
        cwd=HERE, check=True,
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
