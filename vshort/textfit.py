"""Measure subtitle text the way the renderer draws it."""
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MAX_TEXT_W = 620  # widest one-line phrase, px at em 50


@lru_cache
def _font(em: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), em)


def text_width(text: str, em: int = 50) -> float:
    return _font(em).getlength(text.replace("*", "").replace("|", ""))
