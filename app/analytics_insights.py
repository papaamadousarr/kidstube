import json
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from app import gemini_budget
from app.db import db
from app.models import Insight

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / "secrets" / ".env")

MODEL = "gemini-2.5-flash"


class ContentRecommendation(BaseModel):
    summary: str = Field(description="Résumé en 2-3 phrases de ce que montrent les données et pourquoi.")
    priority_themes: list[str] = Field(
        description=(
            "3 à 5 thèmes ou concepts code/IA à privilégier pour les prochaines vidéos, "
            "déduits des vraies performances observées (pas des généralités)."
        )
    )
    format_advice: str = Field(description="Conseil concret sur le format (durée, Shorts vs vidéos classiques, structure) basé sur les données.")
    timing_advice: str = Field(description="Conseil concret sur le rythme/horaire de publication basé sur les données.")


class InsightGenerationError(Exception):
    pass


def _build_prompt(analytics_data: dict) -> str:
    return (
        "Tu es un stratège de croissance YouTube pour une chaîne éducative "
        "destinée aux jeunes enfants (4-7 ans) dont la mission est de leur "
        "apprendre le code et l'intelligence artificielle de façon ludique "
        "(flashcards, Shorts, podcasts).\n\n"
        "Voici les vraies données de performance de la chaîne :\n"
        f"{json.dumps(analytics_data, ensure_ascii=False, indent=2)}\n\n"
        "Analyse ces données et donne des recommandations concrètes et "
        "actionnables pour accélérer la croissance de la chaîne — basées sur "
        "ce que les chiffres montrent réellement (pas des conseils génériques "
        "de type 'poste régulièrement'). Si les données sont trop limitées "
        "pour conclure quelque chose de précis, dis-le clairement dans le "
        "résumé plutôt que d'inventer."
    )


def generate_insight(analytics_data: dict, period_days: int) -> Insight:
    if gemini_budget.is_exhausted_today():
        raise InsightGenerationError(
            f"Quota gratuit Gemini déjà atteint. {gemini_budget.reset_message()}"
        )

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_prompt(analytics_data),
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ContentRecommendation,
            ),
        )
    except genai_errors.ClientError as exc:
        if gemini_budget.is_quota_error(exc):
            gemini_budget.mark_exhausted()
            raise InsightGenerationError(
                f"Quota gratuit Gemini atteint. {gemini_budget.reset_message()}"
            ) from exc
        if exc.code in (401, 403):
            raise InsightGenerationError(
                "Clé API Gemini absente ou invalide. Configure GEMINI_API_KEY."
            ) from exc
        raise InsightGenerationError(f"Échec de l'appel à l'API Gemini : {exc}") from exc
    except genai_errors.APIError as exc:
        if gemini_budget.is_quota_error(exc):
            gemini_budget.mark_exhausted()
            raise InsightGenerationError(
                f"Quota gratuit Gemini atteint. {gemini_budget.reset_message()}"
            ) from exc
        raise InsightGenerationError(f"Échec de l'appel à l'API Gemini : {exc}") from exc

    rec = response.parsed
    if rec is None:
        raise InsightGenerationError("Réponse de Gemini vide ou invalide.")

    insight = Insight(
        period_days=period_days,
        summary=rec.summary,
        priority_themes=json.dumps(rec.priority_themes, ensure_ascii=False),
        format_advice=rec.format_advice,
        timing_advice=rec.timing_advice,
    )
    db.session.add(insight)
    db.session.commit()
    return insight


def get_latest_insight() -> Insight | None:
    return Insight.query.order_by(Insight.created_at.desc()).first()


def priority_themes_list(insight: Insight) -> list[str]:
    try:
        return json.loads(insight.priority_themes)
    except (json.JSONDecodeError, TypeError):
        return []
