from pathlib import Path

from PIL import Image, ImageDraw

from pipeline.config import FRAME_SIZE
from pipeline.content.schema import Item, SeriesConfig
from pipeline.render.fonts import get_font
from pipeline.render.icons import load_icon

ICON_SIZE = (300, 300)
NAME_FONT_SIZE = 150
SCRIPT_FONT_SIZE = 48
TEXT_MARGIN = 100


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_name: str, base_size: int, max_width: int, min_size: int = 36):
    size = base_size
    while size > min_size:
        font = get_font(font_name, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 8
    return get_font(font_name, min_size)


def _centered_text(draw: ImageDraw.ImageDraw, text: str, font, y: float, size: tuple[int, int], fill: str = "#2B2B2B") -> float:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size[0] - text_w) / 2 - bbox[0]
    draw.text((x, y - bbox[1]), text, font=font, fill=fill)
    return text_h


def build_flashcard(item: Item, series: SeriesConfig, size: tuple[int, int] = FRAME_SIZE) -> Image.Image:
    img = Image.new("RGB", size, series.background_color)
    draw = ImageDraw.Draw(img)

    if item.icon:
        icon = load_icon(item.icon, ICON_SIZE, fallback_label=item.name, accent_color=item.accent_color or "#FF6B6B")
        icon_x = (size[0] - ICON_SIZE[0]) // 2
        icon_y = int(size[1] * 0.06)
        img.paste(icon, (icon_x, icon_y), icon)
        name_y = icon_y + ICON_SIZE[1] + 20
    else:
        name_y = int(size[1] * 0.28)

    max_text_width = size[0] - TEXT_MARGIN
    name_font = _fit_font(draw, item.name, "display", NAME_FONT_SIZE, max_text_width)
    name_h = _centered_text(draw, item.name, name_font, name_y, size, fill=item.accent_color or "#2B2B2B")

    script_font = _fit_font(draw, item.script, "body", SCRIPT_FONT_SIZE, max_text_width)
    script_y = name_y + name_h + 40
    _centered_text(draw, item.script, script_font, script_y, size)

    return img


def render_series_frames(series: SeriesConfig, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, item in enumerate(series.items):
        frame = build_flashcard(item, series)
        path = out_dir / f"{series.key}_{i:02d}_{item.name}.png"
        frame.save(path)
        paths.append(path)
    return paths
