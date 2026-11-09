"""Spike of 09/11/2026 (throwaway, kept as the look reference): fills template.html into one page.

Inputs next to this file, made from run openmatter-network-giai-phap-dien-toan-phi-tap-trung-thay (pve2):
script.vi.json, timeline.json, caps.json ([start, end, phrase] parsed from subs.ass), and
  ffmpeg -i narration.wav -t 34.6 -af afade=t=out:st=34.2:d=0.4 -ac 1 -c:a libmp3lame -b:a 80k seg.mp3; base64 seg.mp3 > seg.b64
  env.json: narration RMS per 1/30 s over the same 34.6 s, scaled to its 98th percentile
  logo.b64: base64 of assets/brand/anm-logo.png resized to 480 px wide
Usage: python3 inject.py OUT.html
"""
import json, sys
from pathlib import Path
here = Path(__file__).parent
env30 = json.loads((here / "env.json").read_text())
env15 = [max(env30[i:i + 2]) for i in range(0, len(env30), 2)]
caps = [c for c in json.loads((here / "caps.json").read_text()) if c[0] < 34.5]
s = json.loads((here / "script.vi.json").read_text()); s = s if isinstance(s, list) else s.get("lines", s)
pl = {p["id"]: p for p in json.loads((here / "timeline.json").read_text())["placements"]}
text = {x["id"]: " ".join(p.strip() for p in x["phrases"].split("|")) for x in s}
lines = [{"start": round(pl[i]["start"], 2), "end": round(pl[i + 1]["start"], 2) if i < 6 else 34.6, "text": text[i]} for i in range(2, 7)]
html = (here / "template.html").read_text()
for k, v in {"__ENV__": json.dumps(env15), "__CAPS__": json.dumps(caps, ensure_ascii=False), "__LINES__": json.dumps(lines, ensure_ascii=False),
             "__TITLE__": json.dumps(text[1], ensure_ascii=False), "__AUDIO_B64__": (here / "seg.b64").read_text().strip(),
             "__LOGO_B64__": (here / "logo.b64").read_text().strip()}.items():
    assert k in html, k
    html = html.replace(k, v)
Path(sys.argv[1]).write_text(html)
print("ok", len(html), "bytes;", len(caps), "caps;", lines[0]["text"][:40], "; title:", text[1])
