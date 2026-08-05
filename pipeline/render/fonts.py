from functools import lru_cache

from PIL import ImageFont

from pipeline.config import FONTS_DIR

DISPLAY_FONT = FONTS_DIR / "Baloo2.ttf"
BODY_FONT = FONTS_DIR / "Fredoka.ttf"


@lru_cache(maxsize=32)
def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = DISPLAY_FONT if name == "display" else BODY_FONT
    return ImageFont.truetype(str(path), size)
