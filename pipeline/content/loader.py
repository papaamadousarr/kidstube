from pathlib import Path

import yaml

from pipeline.config import DATA_DIR
from pipeline.content.schema import ContentError, Item, SeriesConfig

REQUIRED_SERIES_KEYS = ("key", "title", "voice", "background_color", "intro_text")
REQUIRED_ITEM_KEYS = ("name", "script")


def list_series(data_dir: Path = DATA_DIR) -> list[str]:
    return sorted(p.stem for p in data_dir.glob("*.yaml"))


def load_series(name: str, data_dir: Path = DATA_DIR) -> SeriesConfig:
    path = data_dir / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(list_series(data_dir)) or "(aucune)"
        raise ContentError(f"Série inconnue '{name}'. Séries disponibles : {available}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"YAML invalide dans {path}: {exc}") from exc

    if not isinstance(raw, dict) or "series" not in raw or "items" not in raw:
        raise ContentError(f"{path} doit contenir les clés 'series' et 'items'")

    series_raw = raw["series"]
    missing = [k for k in REQUIRED_SERIES_KEYS if k not in series_raw]
    if missing:
        raise ContentError(f"{path}: clés manquantes dans 'series': {missing}")

    items_raw = raw["items"]
    if not isinstance(items_raw, list) or not items_raw:
        raise ContentError(f"{path}: 'items' doit être une liste non vide")

    items: list[Item] = []
    for i, item_raw in enumerate(items_raw):
        missing_item = [k for k in REQUIRED_ITEM_KEYS if k not in item_raw]
        if missing_item:
            raise ContentError(f"{path}: item #{i} manque les clés {missing_item}")
        items.append(
            Item(
                name=str(item_raw["name"]),
                script=str(item_raw["script"]),
                icon=item_raw.get("icon"),
                accent_color=item_raw.get("accent_color"),
            )
        )

    return SeriesConfig(
        key=series_raw["key"],
        title=series_raw["title"],
        voice=series_raw["voice"],
        background_color=series_raw["background_color"],
        intro_text=series_raw["intro_text"],
        items=items,
    )
