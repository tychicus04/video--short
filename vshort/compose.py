"""A HyperFrames composition folder from a resolved neon scene (scene.resolved.json's dict): the browser kit that animates it,
its fonts, icons and logo, and an index.html with the scene embedded. hf.render turns that folder into the video."""
import json
import shutil
from pathlib import Path

from vshort import hf

NEON = hf.NEON
GSAP = NEON / "node_modules" / "gsap" / "dist" / "gsap.min.js"  # the page loads nothing from the network
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FILES = ("BeVietnamPro-Bold.ttf", "BeVietnamPro-ExtraBold.ttf", "IBMPlexMono-SemiBold.ttf")
LOGO = Path(__file__).resolve().parent.parent / "assets" / "brand" / "anm-logo.png"


def write_composition(rt: dict, out_dir: Path) -> Path:
    """Fill out_dir with everything index.html needs, and return it. The scene goes into the page as `window.SCENE`; every `<` in
    it is written \\u003c, so no text of the video can close the script tag or open a comment."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in (*(NEON / n for n in ("kit.js", "kit.css", "icons.json")), GSAP, LOGO, *(FONTS / f for f in FONT_FILES)):
        shutil.copy(src, out_dir / src.name)
    page = (NEON / "index.html").read_text(encoding="utf-8")
    page = page.replace("__DURATION__", str(float(rt["total"])))
    page = page.replace("/*SCENE*/null", json.dumps(rt, ensure_ascii=False).replace("<", "\\u003c"))
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    return out_dir
