from app.db import db
from app.models import Idea
from pipeline.content.loader import list_series, load_series
from pipeline.content.schema import ContentError

# Nombre de mots consécutifs regroupés dans un seul Short — appliqué
# uniquement aux séries qui n'ont encore AUCUN Short catalogué (cf.
# list_all_short_slots ci-dessous). Les séries déjà entamées sur le modèle
# historique (1 mot = 1 Short, 1618 idées existantes dont certaines déjà
# publiées sur YouTube) continuent sur ce modèle pour ne pas désynchroniser
# la numérotation ni renuméroter des vidéos déjà en ligne.
WORDS_PER_SHORT = 4

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


def _legacy_series_keys() -> set[str]:
    """Séries qui ont déjà au moins un Short catalogué sur le modèle
    historique (1 mot = 1 Short) — on continue ce modèle pour elles plutôt
    que de désynchroniser la numérotation en cours de route."""
    rows = Idea.query.filter_by(video_pipeline="shorts").with_entities(Idea.series_key).distinct().all()
    return {key for (key,) in rows}


def list_all_short_slots() -> list[tuple[str, int, str, int]]:
    """(series_key, item_index, title, group_size) pour tous les Shorts
    possibles des séries alignées avec la mission. Une série déjà entamée
    (cf. _legacy_series_keys) reste sur des slots d'un seul mot
    (group_size=1) ; une série encore jamais catalogée utilise des slots
    groupés de WORDS_PER_SHORT mots pour une durée totale plus substantielle."""
    legacy_series = _legacy_series_keys()
    slots = []
    for series_key in list_series():
        if series_key in NON_MISSION_SERIES:
            continue
        try:
            series = load_series(series_key)
        except ContentError:
            continue

        if series_key in legacy_series:
            for index, item in enumerate(series.items):
                slots.append((series_key, index, item.name, 1))
        else:
            for start in range(0, len(series.items), WORDS_PER_SHORT):
                group = series.items[start : start + WORDS_PER_SHORT]
                title = " / ".join(item.name for item in group)
                slots.append((series_key, start, title, len(group)))
    return slots


def _existing_short_slots() -> set[tuple[str, int]]:
    rows = Idea.query.filter_by(video_pipeline="shorts").with_entities(Idea.series_key, Idea.short_item_index).all()
    return {(key, idx) for key, idx in rows}


def create_missing_shorts(limit: int | None = None) -> list[Idea]:
    """Crée les idées Shorts manquantes (mot(s) de série sans Short existant), au plus `limit`."""
    existing = _existing_short_slots()
    created: list[Idea] = []
    for series_key, index, title, group_size in list_all_short_slots():
        if (series_key, index) in existing:
            continue
        idea = Idea(
            title=f"{title} (Short)",
            series_key=series_key,
            video_pipeline="shorts",
            short_item_index=index,
            short_group_size=group_size,
            status="idea",
        )
        db.session.add(idea)
        created.append(idea)
        if limit is not None and len(created) >= limit:
            break
    if created:
        db.session.commit()
    return created
