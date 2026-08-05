from PIL import Image, ImageDraw

from pipeline.config import FRAME_SIZE
from pipeline.render.frame_builder import _centered_text, _fit_font

OVERLAY_FONT_SIZE = 54
BAND_PADDING_Y = 30
BAND_MARGIN_X = 60
BAND_OPACITY = 190


def build_text_overlay(text: str, size: tuple[int, int] = FRAME_SIZE) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    max_text_width = size[0] - 2 * BAND_MARGIN_X - 40
    font = _fit_font(draw, text, "body", OVERLAY_FONT_SIZE, max_text_width)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]

    band_h = text_h + 2 * BAND_PADDING_Y
    band_y0 = size[1] - int(size[1] * 0.16) - band_h
    band_y1 = band_y0 + band_h

    draw.rounded_rectangle(
        [(BAND_MARGIN_X, band_y0), (size[0] - BAND_MARGIN_X, band_y1)],
        radius=24,
        fill=(20, 20, 20, BAND_OPACITY),
    )

    text_y = band_y0 + BAND_PADDING_Y
    _centered_text(draw, text, font, text_y, size, fill="#FFFFFF")

    return img
