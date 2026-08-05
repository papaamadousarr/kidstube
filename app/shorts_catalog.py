from app.db import db
from app.models import Idea
from pipeline.content.loader import list_series, load_series
from pipeline.content.schema import ContentError

# Séries de vocabulaire générique créées avant que la mission de la chaîne
# (initier au code et à l'IA, cf. README) ne soit clarifiée. On les garde pour
# les vidéos flashcards déjà en place, mais on n'en tire plus de nouveaux
# Shorts : les Shorts doivent rester alignés avec la mission code/IA.
NON_MISSION_SERIES = frozenset(
    {
        "alphabet_fr",
        "numbers_1_10_fr",
        "colors_fr",
        "shapes_fr",
        "animals_fr",
        "weekdays_fr",
        "fruits_veggies_fr",
        "body_parts_fr",
        "vehicles_fr",
        "family_fr",
        "emotions_fr",
        "halloween_fr",
        "christmas_fr",
    }
)


def list_all_short_slots() -> list[tuple[str, int, str]]:
    """(series_key, item_index, item_name) pour tous les mots des séries alignées avec la mission."""
    slots = []
    for series_key in list_series():
        if series_key in NON_MISSION_SERIES:
            continue
        try:
            series = load_series(series_key)
        except ContentError:
            continue
        for index, item in enumerate(series.items):
            slots.append((series_key, index, item.name))
    return slots


def _existing_short_slots() -> set[tuple[str, int]]:
    rows = Idea.query.filter_by(video_pipeline="shorts").with_entities(Idea.series_key, Idea.short_item_index).all()
    return {(key, idx) for key, idx in rows}


def create_missing_shorts(limit: int | None = None) -> list[Idea]:
    """Crée les idées Shorts manquantes (un mot de série sans Short existant), au plus `limit`."""
    existing = _existing_short_slots()
    created: list[Idea] = []
    for series_key, index, name in list_all_short_slots():
        if (series_key, index) in existing:
            continue
        idea = Idea(
            title=f"{name} (Short)",
            series_key=series_key,
            video_pipeline="shorts",
            short_item_index=index,
            status="idea",
        )
        db.session.add(idea)
        created.append(idea)
        if limit is not None and len(created) >= limit:
            break
    if created:
        db.session.commit()
    return created
