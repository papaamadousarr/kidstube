from app.models import Idea
from pipeline.content.loader import load_series
from pipeline.content.podcast_loader import load_podcast_series
from pipeline.content.schema import ContentError

PODCAST_TAGS = [
    "KidsTube",
    "PodcastEnfant",
    "IA",
    "ApprendreEnSAmusant",
    "STEM",
    "CodingPourEnfants",
    "EducationNumerique",
]

GENERIC_TAGS = [
    "comptine",
    "apprendre le français",
    "éducatif",
    "maternelle",
    "vocabulaire français",
    "dessin animé enfant",
    "chansons pour enfants",
]

TITLE_MAX_LEN = 100
MAX_TAGS = 20


def _build_short_seo_defaults(idea: Idea, series) -> dict:
    index = idea.short_item_index or 0
    if not (0 <= index < len(series.items)):
        return {"title": idea.title, "description": idea.notes or "", "tags": ["#Shorts"]}

    item = series.items[index]
    title = f"{item.name} en français #Shorts"
    if len(title) > TITLE_MAX_LEN:
        title = title[: TITLE_MAX_LEN - 1].rstrip() + "…"

    description = (
        f"{item.name} — {item.script}\n\n"
        "Abonne-toi pour plus de vidéos éducatives pour enfants !\n\n"
        "#Shorts #comptine #apprendrelefrançais #maternelle"
    )

    tags = list(dict.fromkeys([item.name, "Shorts"] + GENERIC_TAGS))[:MAX_TAGS]

    return {"title": title, "description": description, "tags": tags}


def _build_podcast_seo_defaults(idea: Idea, series) -> dict:
    episode_number = (
        Idea.query.filter(Idea.video_pipeline == "podcast", Idea.status == "published").count() + 1
    )

    title = f"{series.title} | KidsTube Podcast Ép. {episode_number:02d} (Code & IA pour les petits)"
    if len(title) > TITLE_MAX_LEN:
        title = title[: TITLE_MAX_LEN - 1].rstrip() + "…"

    learning_points = "\n".join(f"- {seg.narration}" for seg in series.segments[:-1])

    linked_line = ""
    if series.linked_series_key:
        try:
            linked_title = load_series(series.linked_series_key).title
            linked_line = (
                f"\n🎬 Regarde la vidéo complète juste ici pour tout comprendre en détail : "
                f"« {linked_title} » (lien en premier commentaire) !\n"
            )
        except ContentError:
            pass

    description = (
        f"{title}\n\n"
        "👋 Bienvenue dans ce nouvel épisode du podcast KidsTube !\n\n"
        f"🎯 Ce que ton enfant va apprendre :\n{learning_points}\n"
        f"{linked_line}\n"
        "🔔 Abonne-toi et active la cloche pour ne rater aucun épisode !\n\n"
        "#" + " #".join(PODCAST_TAGS)
    )

    tags = list(dict.fromkeys([series.title] + PODCAST_TAGS + GENERIC_TAGS))[:MAX_TAGS]

    return {"title": title, "description": description, "tags": tags}


def build_seo_defaults(idea: Idea) -> dict:
    if not idea.series_key:
        return {"title": idea.title, "description": idea.notes or "", "tags": []}

    if idea.video_pipeline == "podcast":
        try:
            podcast_series = load_podcast_series(idea.series_key)
        except ContentError:
            return {"title": idea.title, "description": idea.notes or "", "tags": []}
        return _build_podcast_seo_defaults(idea, podcast_series)

    try:
        series = load_series(idea.series_key)
    except ContentError:
        return {"title": idea.title, "description": idea.notes or "", "tags": []}

    if idea.video_pipeline == "shorts":
        return _build_short_seo_defaults(idea, series)

    item_names = [item.name for item in series.items]

    title_base = series.title if "français" in series.title.lower() else f"{series.title} en français"
    title = f"{title_base} | Apprendre {', '.join(item_names[:3])}"
    if len(title) > TITLE_MAX_LEN:
        title = title[: TITLE_MAX_LEN - 1].rstrip() + "…"

    description = (
        f"{series.intro_text}\n\n"
        f"Dans cette vidéo, on découvre : {', '.join(item_names)}.\n\n"
        "Abonne-toi pour plus de vidéos éducatives pour enfants !\n\n"
        "#comptine #apprendrelefrançais #maternelle"
    )

    tags = list(dict.fromkeys(item_names + GENERIC_TAGS))[:MAX_TAGS]

    return {"title": title, "description": description, "tags": tags}
