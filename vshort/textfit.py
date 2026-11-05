"""Measure subtitle text the way the renderer draws it."""
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# What TikTok, Reels and YouTube Shorts draw over a 720x1280 frame, strictest of each (shorts-kit's iOS measurements,
# scaled from 1080x1920): the button column from x 618 (at y ≥ 535), the name and description from y 1151, the top bar
# down to y 141. Tai posts to all three and to the CMS.
UI_TOP, UI_RIGHT, UI_RIGHT_FROM, UI_BOTTOM = 141, 618, 535, 1151
MAX_TEXT_W = 2 * UI_RIGHT - 720  # widest one-line phrase, px at em 50: centred, it ends left of the buttons (was 620)


@lru_cache
def _font(em: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), em)


def text_width(text: str, em: int = 50) -> float:
    return _font(em).getlength(text.replace("*", "").replace("|", ""))
