import re
import unicodedata
from pathlib import Path

import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from app import gemini_budget
from app.db import db
from app.models import Idea
from pipeline.config import DATA_DIR
from pipeline.content.loader import ContentError, list_series, load_series
from pipeline.render.icons import ensure_icon_from_emoji

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / "secrets" / ".env")

MODEL = "gemini-2.5-flash"


class VocabItem(BaseModel):
    name: str
    script: str
    accent_color: str
    emoji: str = Field(
        description=(
            "Un seul caractère emoji Unicode représentant visuellement ce concept "
            "(ex. 🤖 pour robot, 🔁 pour boucle, 💡 pour idée/algorithme, 🖱️ pour souris). "
            "Choisis l'emoji standard le plus proche visuellement, même approximatif."
        )
    )


class SeriesIdea(BaseModel):
    key: str
    title: str
    intro_text: str
    background_color: str
    items: list[VocabItem]


class SeriesIdeaBatch(BaseModel):
    series: list[SeriesIdea]


class IdeaGenerationError(Exception):
    pass


def _sanitize_key(raw_key: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw_key).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return key or "serie"


def _unique_key(base_key: str, taken: set[str]) -> str:
    key = base_key
    suffix = 2
    while key in taken:
        key = f"{base_key}_{suffix}"
        suffix += 1
    return key


def _insight_guidance() -> str:
    """Consulte le dernier insight généré par Gemini à partir des vraies
    données YouTube Analytics (cf. app/analytics_insights.py) pour orienter la
    génération de nouvelles idées vers ce qui performe réellement — Gemini
    devient ainsi orchestrateur de sa propre automatisation, pas juste un
    générateur de contenu à l'aveugle."""
    from app.analytics_insights import get_latest_insight, priority_themes_list

    insight = get_latest_insight()
    if insight is None:
        return ""

    themes = priority_themes_list(insight)
    if not themes:
        return ""

    return (
        "\n\nD'après l'analyse des vraies performances de la chaîne (YouTube "
        f"Analytics), privilégie en priorité ces thèmes qui fonctionnent bien : "
        f"{', '.join(themes)}. Contexte : {insight.summary}"
    )


def _build_prompt(n: int, existing_titles: list[str]) -> str:
    existing = ", ".join(existing_titles) if existing_titles else "(aucune)"
    return (
        f"Propose {n} nouveaux concepts de séries de vidéos éducatives pour enfants "
        "en français, sur le modèle de flashcards de vocabulaire (comme déjà "
        "utilisées sur la chaîne). La chaîne a pour mission d'initier les jeunes "
        "enfants au code et à l'intelligence artificielle : chaque série doit couvrir "
        "un thème lié à la programmation ou à l'IA, vulgarisé pour un enfant de 4 à 7 "
        "ans (ex. le robot, la commande, la boucle qui répète, le bouton, l'écran, le "
        "code, l'algorithme/la recette à suivre, le capteur, le circuit, l'ordinateur, "
        "le cerveau artificiel, la souris, le clavier, internet...), en évitant le "
        "jargon technique et les thèmes déjà utilisés listés ci-dessous. Chaque série "
        "doit avoir : un titre accrocheur, un texte d'introduction court, une couleur "
        "de fond pastel claire (hex), et entre 5 et 6 items de vocabulaire. Chaque "
        "item a un nom court, une phrase exclamative courte adaptée aux jeunes "
        "enfants qui explique simplement le concept, une couleur d'accent (hex) "
        "cohérente avec le thème, et un émoji représentatif du concept (pour "
        "illustrer la flashcard).\n\n"
        f"Thèmes déjà utilisés (à éviter) : {existing}."
        f"{_insight_guidance()}"
    )


def generate_new_series_ideas(n: int) -> list[Idea]:
    if n <= 0:
        return []

    if gemini_budget.is_exhausted_today():
        raise IdeaGenerationError(
            f"Quota gratuit Gemini déjà atteint. {gemini_budget.reset_message()}"
        )

    existing_titles = [load_series(key).title for key in list_series()]

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_prompt(n, existing_titles),
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SeriesIdeaBatch,
            ),
        )
    except genai_errors.ClientError as exc:
        if gemini_budget.is_quota_error(exc):
            gemini_budget.mark_exhausted()
            raise IdeaGenerationError(
                f"Quota gratuit Gemini atteint. {gemini_budget.reset_message()}"
            ) from exc
        if exc.code == 401 or exc.code == 403:
            raise IdeaGenerationError(
                "Clé API Gemini absente ou invalide. "
                "Configure la variable d'environnement GEMINI_API_KEY."
            ) from exc
        raise IdeaGenerationError(f"Échec de l'appel à l'API Gemini : {exc}") from exc
    except genai_errors.APIError as exc:
        if gemini_budget.is_quota_error(exc):
            gemini_budget.mark_exhausted()
            raise IdeaGenerationError(
                f"Quota gratuit Gemini atteint. {gemini_budget.reset_message()}"
            ) from exc
        raise IdeaGenerationError(f"Échec de l'appel à l'API Gemini : {exc}") from exc

    batch = response.parsed
    if batch is None:
        raise IdeaGenerationError("Réponse de Gemini vide ou invalide.")

    taken_keys = set(list_series())
    created: list[Idea] = []

    for series in batch.series:
        key = _unique_key(_sanitize_key(series.key), taken_keys)
        taken_keys.add(key)

        yaml_path = DATA_DIR / f"{key}.yaml"
        yaml_path.write_text(_to_yaml(key, series), encoding="utf-8")

        try:
            load_series(key)
        except ContentError:
            yaml_path.unlink(missing_ok=True)
            continue

        idea = Idea(
            title=series.title,
            series_key=key,
            notes=f"Générée automatiquement par Gemini ({MODEL}).",
            status="idea",
        )
        db.session.add(idea)
        created.append(idea)

    db.session.commit()
    return created


def _item_to_dict(item: VocabItem) -> dict:
    item_dict = {"name": item.name, "script": item.script, "accent_color": item.accent_color}
    icon_key = ensure_icon_from_emoji(item.emoji)
    if icon_key:
        item_dict["icon"] = icon_key
    return item_dict


def _to_yaml(key: str, series: SeriesIdea) -> str:
    data = {
        "series": {
            "key": key,
            "title": series.title,
            "voice": "fr_FR-siwis-medium",
            "background_color": series.background_color,
            "intro_text": series.intro_text,
        },
        "items": [_item_to_dict(item) for item in series.items],
    }
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


class ItemEmojiMapping(BaseModel):
    name: str
    emoji: str = Field(description="Un seul caractère emoji Unicode représentant ce mot.")


class ItemEmojiBatch(BaseModel):
    items: list[ItemEmojiMapping]


def backfill_icons_for_series(series_key: str) -> int:
    """Rattrape les icônes manquantes sur une série flashcards déjà existante
    (1 appel Gemini regroupant tous ses mots sans icône). Retourne le nombre
    d'items mis à jour. Lève IdeaGenerationError si le quota Gemini est atteint,
    pour que l'appelant arrête le lot en cours plutôt que de gaspiller le reste
    de ses tentatives sur des appels qui échoueront de toute façon."""
    path = DATA_DIR / f"{series_key}.yaml"
    if not path.exists():
        return 0

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items_raw = raw.get("items", [])
    missing = [item for item in items_raw if not item.get("icon")]
    if not missing:
        return 0

    if gemini_budget.is_exhausted_today():
        raise IdeaGenerationError(f"Quota gratuit Gemini déjà atteint. {gemini_budget.reset_message()}")

    prompt = (
        "Pour chaque mot suivant (destiné à une flashcard éducative pour jeunes "
        "enfants), donne un seul emoji Unicode représentant visuellement ce "
        "concept, même approximatif si le concept est abstrait :\n\n"
        + "\n".join(f"- {item['name']}" for item in missing)
    )

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ItemEmojiBatch,
            ),
        )
    except genai_errors.APIError as exc:
        if gemini_budget.is_quota_error(exc):
            gemini_budget.mark_exhausted()
            raise IdeaGenerationError(f"Quota gratuit Gemini atteint. {gemini_budget.reset_message()}") from exc
        return 0

    batch = response.parsed
    if batch is None:
        return 0

    emoji_by_name = {mapping.name.strip().lower(): mapping.emoji for mapping in batch.items}

    updated = 0
    for item in items_raw:
        if item.get("icon"):
            continue
        emoji_char = emoji_by_name.get(str(item["name"]).strip().lower())
        if not emoji_char:
            continue
        icon_key = ensure_icon_from_emoji(emoji_char)
        if icon_key:
            item["icon"] = icon_key
            updated += 1

    if updated:
        raw["items"] = items_raw
        path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return updated


def backfill_missing_icons(limit: int | None = None) -> int:
    """Traite au plus `limit` séries ayant des items sans icône (pour étaler les
    appels Gemini dans le temps plutôt que tout faire d'un coup). Retourne le
    nombre total d'items mis à jour."""
    processed = 0
    total_updated = 0
    for series_key in list_series():
        path = DATA_DIR / f"{series_key}.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if all(item.get("icon") for item in raw.get("items", [])):
            continue

        try:
            total_updated += backfill_icons_for_series(series_key)
        except IdeaGenerationError:
            break  # quota atteint : inutile de tenter les séries suivantes ce tour-ci
        processed += 1
        if limit is not None and processed >= limit:
            break

    return total_updated
