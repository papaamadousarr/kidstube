import random
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

DECORATION_BLOB_COUNT = 6
DECORATION_MIN_ALPHA = 16
DECORATION_MAX_ALPHA = 32


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def _draw_background(size: tuple[int, int], background_color: str, accent_color: str, seed_text: str) -> Image.Image:
    """Fond avec quelques taches douces et translucides dans la couleur d'accent,
    pour une carte moins plate qu'un aplat uni — sans dépendre d'images externes.
    `seed_text` rend la décoration stable (même rendu si on régénère la même carte)
    tout en variant d'un item/série à l'autre."""
    img = Image.new("RGBA", size, (*_hex_to_rgb(background_color), 255))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(seed_text)
    accent_rgb = _hex_to_rgb(accent_color)

    for _ in range(DECORATION_BLOB_COUNT):
        radius = rng.randint(int(min(size) * 0.12), int(min(size) * 0.32))
        cx = rng.randint(0, size[0])
        cy = rng.randint(0, size[1])
        alpha = rng.randint(DECORATION_MIN_ALPHA, DECORATION_MAX_ALPHA)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(*accent_rgb, alpha))

    return Image.alpha_composite(img, overlay).convert("RGB")


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


def build_flashcard_layers(item: Item, series: SeriesConfig, size: tuple[int, int] = FRAME_SIZE) -> dict:
    """Retourne les couches d'une flashcard séparément (fond, icône, nom, phrase)
    afin de pouvoir les animer indépendamment (cf. build_animated_item_clip).
    Le fond est une image RGB opaque ; les autres couches sont RGBA transparentes
    de la taille du cadre entier, avec leur contenu déjà positionné dedans."""
    background = _draw_background(
        size, series.background_color, item.accent_color or "#FF6B6B", seed_text=f"{series.key}:{item.name}"
    )

    icon_layer = None
    if item.icon:
        icon_layer = Image.new("RGBA", size, (0, 0, 0, 0))
        icon = load_icon(item.icon, ICON_SIZE, fallback_label=item.name, accent_color=item.accent_color or "#FF6B6B")
        icon_x = (size[0] - ICON_SIZE[0]) // 2
        icon_y = int(size[1] * 0.06)
        icon_layer.paste(icon, (icon_x, icon_y), icon)
        name_y = icon_y + ICON_SIZE[1] + 20
    else:
        name_y = int(size[1] * 0.28)

    max_text_width = size[0] - TEXT_MARGIN

    name_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    name_draw = ImageDraw.Draw(name_layer)
    name_font = _fit_font(name_draw, item.name, "display", NAME_FONT_SIZE, max_text_width)
    name_h = _centered_text(name_draw, item.name, name_font, name_y, size, fill=item.accent_color or "#2B2B2B")

    script_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    script_draw = ImageDraw.Draw(script_layer)
    script_font = _fit_font(script_draw, item.script, "body", SCRIPT_FONT_SIZE, max_text_width)
    script_y = name_y + name_h + 40
    _centered_text(script_draw, item.script, script_font, script_y, size)

    return {"background": background, "icon": icon_layer, "name": name_layer, "script": script_layer}


def build_flashcard(item: Item, series: SeriesConfig, size: tuple[int, int] = FRAME_SIZE) -> Image.Image:
    layers = build_flashcard_layers(item, series, size)
    img = layers["background"].convert("RGBA")
    if layers["icon"] is not None:
        img = Image.alpha_composite(img, layers["icon"])
    img = Image.alpha_composite(img, layers["name"])
    img = Image.alpha_composite(img, layers["script"])
    return img.convert("RGB")


def render_series_frames(series: SeriesConfig, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, item in enumerate(series.items):
        frame = build_flashcard(item, series)
        path = out_dir / f"{series.key}_{i:02d}_{item.name}.png"
        frame.save(path)
        paths.append(path)
    return paths
