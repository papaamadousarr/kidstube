import math
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from pipeline.config import ICONS_DIR
from pipeline.render.fonts import get_font

SHAPE_KEYS = {"shape_circle", "shape_square", "shape_triangle", "shape_rectangle", "shape_star"}

TWEMOJI_CDN_TEMPLATE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/{codepoint}.png"


def resolve_icon(icon_key: str) -> Path | None:
    path = ICONS_DIR / f"{icon_key}.png"
    return path if path.exists() else None


def _emoji_codepoint(emoji_char: str) -> str:
    # U+FE0F (variation selector) n'apparaît pas dans les noms de fichiers Twemoji.
    return "-".join(f"{ord(c):x}" for c in emoji_char if ord(c) != 0xFE0F)


def ensure_icon_from_emoji(emoji_char: str) -> str | None:
    """Résout un caractère emoji vers une icône Twemoji locale (CC BY 4.0, même
    licence que les icônes déjà utilisées), téléchargée à la demande si absente.
    Retourne l'icon_key à stocker dans le YAML, ou None si le caractère est vide
    ou le téléchargement échoue (pas de connexion, emoji inconnu de Twemoji...) —
    dans ce cas l'appelant doit simplement omettre le champ 'icon' (repli texte
    déjà géré par build_flashcard)."""
    if not emoji_char:
        return None
    codepoint = _emoji_codepoint(emoji_char)
    if not codepoint:
        return None

    path = ICONS_DIR / f"{codepoint}.png"
    if path.exists():
        return codepoint

    try:
        response = httpx.get(
            TWEMOJI_CDN_TEMPLATE.format(codepoint=codepoint), timeout=10, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return codepoint


def load_icon(icon_key: str, size: tuple[int, int], fallback_label: str = "?", accent_color: str = "#FF6B6B") -> Image.Image:
    if icon_key == "swatch":
        return _draw_swatch(size, accent_color)
    if icon_key in SHAPE_KEYS:
        return _draw_shape(icon_key, size, accent_color)

    path = resolve_icon(icon_key)
    if path is not None:
        icon = Image.open(path).convert("RGBA")
        return icon.resize(size, Image.LANCZOS)
    return _draw_fallback(size, fallback_label, accent_color)


def _draw_fallback(size: tuple[int, int], label: str, accent_color: str) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([(0, 0), (size[0] - 1, size[1] - 1)], fill=accent_color)
    font = get_font("display", int(size[1] * 0.55))
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((size[0] - text_w) / 2 - bbox[0], (size[1] - text_h) / 2 - bbox[1])
    draw.text(pos, label, font=font, fill="white")
    return img


def _draw_swatch(size: tuple[int, int], color: str) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([(0, 0), (size[0] - 1, size[1] - 1)], fill=color)
    return img


def _draw_shape(shape_key: str, size: tuple[int, int], color: str) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size
    margin = int(min(w, h) * 0.1)

    if shape_key == "shape_circle":
        draw.ellipse([margin, margin, w - margin, h - margin], fill=color)
    elif shape_key == "shape_square":
        side = min(w, h) - 2 * margin
        x0, y0 = (w - side) / 2, (h - side) / 2
        draw.rectangle([x0, y0, x0 + side, y0 + side], fill=color)
    elif shape_key == "shape_rectangle":
        rw, rh = w - 2 * margin, (h - 2 * margin) * 0.6
        x0, y0 = margin, (h - rh) / 2
        draw.rectangle([x0, y0, x0 + rw, y0 + rh], fill=color)
    elif shape_key == "shape_triangle":
        draw.polygon([(w / 2, margin), (margin, h - margin), (w - margin, h - margin)], fill=color)
    elif shape_key == "shape_star":
        draw.polygon(_star_points(w / 2, h / 2, min(w, h) / 2 - margin), fill=color)

    return img


def _star_points(cx: float, cy: float, radius: float, points: int = 5) -> list[tuple[float, float]]:
    coords = []
    for i in range(points * 2):
        angle = math.pi / points * i - math.pi / 2
        r = radius if i % 2 == 0 else radius * 0.45
        coords.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return coords
