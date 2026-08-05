import yaml

from app.db import db
from app.models import Idea
from app.shorts_catalog import NON_MISSION_SERIES
from pipeline.config import PODCAST_DATA_DIR
from pipeline.content.loader import list_series, load_series
from pipeline.content.podcast_loader import list_podcast_series
from pipeline.content.schema import ContentError

INTRO_IMAGE_PROMPT_TEMPLATE = (
    "Colorful glowing 3D illustration representing the theme '{title}', vibrant "
    "playful colors, Pixar-style children's animation, warm inviting composition, "
    "no text, no logos"
)
ITEM_IMAGE_PROMPT_TEMPLATE = (
    "Colorful vibrant 3D cartoon illustration for children showing {name} ({script}), "
    "joyful bright saturated colors, Pixar-style render, no text, no logos"
)
CTA_NARRATION = (
    "Pour découvrir tout ça en vrai, regarde la vidéo complète juste ici, "
    "et abonne-toi pour ne rater aucun épisode !"
)
CTA_IMAGE_PROMPT = (
    "Giant glowing colorful arrow pointing right toward a YouTube play button, "
    "surrounded by bright stars and sparkles, dynamic inviting composition, "
    "Pixar-style children's animation, no text, no logos"
)


def _find_main_idea(series_key: str) -> Idea | None:
    candidates = Idea.query.filter_by(series_key=series_key, video_pipeline="flashcards").all()
    if not candidates:
        return None
    for idea in candidates:
        if idea.status in ("assembled", "published"):
            return idea
    return candidates[0]


def _podcast_key_for(series_key: str) -> str:
    return f"podcast_{series_key}"


def create_podcast_teaser(series_key: str) -> Idea | None:
    """Dérive un podcast teaser (1 segment d'intro + 1 par mot + 1 CTA) à partir
    d'une série flashcards existante, et crée l'Idée correspondante."""
    try:
        series = load_series(series_key)
    except ContentError:
        return None

    podcast_key = _podcast_key_for(series_key)
    PODCAST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    segments = [{"narration": series.intro_text, "image_prompt": INTRO_IMAGE_PROMPT_TEMPLATE.format(title=series.title)}]
    for item in series.items:
        segments.append(
            {
                "narration": item.script,
                "image_prompt": ITEM_IMAGE_PROMPT_TEMPLATE.format(name=item.name, script=item.script),
            }
        )
    segments.append({"narration": CTA_NARRATION, "image_prompt": CTA_IMAGE_PROMPT})

    data = {
        "podcast_series": {
            "key": podcast_key,
            "title": series.title,
            "voice": series.voice,
            "linked_series_key": series_key,
        },
        "segments": segments,
    }
    (PODCAST_DATA_DIR / f"{podcast_key}.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    main_idea = _find_main_idea(series_key)
    idea = Idea(
        title=f"{series.title} (Podcast)",
        series_key=podcast_key,
        video_pipeline="podcast",
        linked_idea_id=main_idea.id if main_idea else None,
        status="idea",
    )
    db.session.add(idea)
    db.session.commit()
    return idea


def create_missing_podcast_teasers(limit: int | None = None) -> list[Idea]:
    """Crée les podcasts teasers manquants pour les séries flashcards alignées
    avec la mission code/IA, au plus `limit`."""
    existing_podcast_series = set(list_podcast_series())
    created: list[Idea] = []
    for series_key in list_series():
        if series_key in NON_MISSION_SERIES:
            continue
        if _podcast_key_for(series_key) in existing_podcast_series:
            continue
        idea = create_podcast_teaser(series_key)
        if idea is not None:
            created.append(idea)
        if limit is not None and len(created) >= limit:
            break
    return created
