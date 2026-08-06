from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app import gemini_budget
from app.db import db
from app.models import ChatMessage, Idea, Insight

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / "secrets" / ".env")

MODEL = "gemini-2.5-flash"
HISTORY_TURNS = 10  # nombre de messages passés inclus comme contexte (paires user+model)

SYSTEM_PREAMBLE = (
    "Tu es l'assistant stratégique de KidsTube, une chaîne YouTube éducative "
    "pour jeunes enfants (4-7 ans) dont la mission est de leur apprendre le "
    "code et l'intelligence artificielle de façon ludique (vidéos flashcards, "
    "Shorts, podcasts). Tu réponds en français, de façon concise et concrète, "
    "à toutes les questions sur la chaîne : performance, stratégie de "
    "contenu, croissance, YouTube en général. Base-toi sur le contexte réel "
    "fourni ci-dessous plutôt que sur des généralités si les données sont "
    "disponibles."
)


class ChatError(Exception):
    pass


def _build_channel_context() -> str:
    lines = []

    counts_by_status = {
        status: Idea.query.filter_by(status=status).count()
        for status in ("idea", "script", "recorded", "assembled", "published")
    }
    lines.append("Contenu en base : " + ", ".join(f"{k}={v}" for k, v in counts_by_status.items()))

    for pipeline in ("flashcards", "shorts", "podcast", "higgsfield"):
        count = Idea.query.filter_by(video_pipeline=pipeline).count()
        if count:
            lines.append(f"  - {pipeline} : {count}")

    insight = Insight.query.order_by(Insight.created_at.desc()).first()
    if insight:
        lines.append(f"Dernier insight Gemini ({insight.created_at.strftime('%d/%m/%Y')}) : {insight.summary}")

    try:
        from app import youtube_analytics

        if youtube_analytics.is_connected():
            summary = youtube_analytics.get_channel_summary(days=28)
            lines.append(
                "Analytics YouTube (28 derniers jours) : "
                f"{summary.get('views', 0)} vues, "
                f"{summary.get('subscribersGained', 0)} abonnés gagnés, "
                f"{summary.get('subscribersLost', 0)} perdus."
            )
    except Exception:
        pass  # contexte optionnel : on continue sans si l'API n'est pas dispo

    return "\n".join(lines)


def get_history(limit: int = 50) -> list[ChatMessage]:
    return ChatMessage.query.order_by(ChatMessage.created_at).limit(limit).all()


def send_message(user_text: str) -> ChatMessage:
    if not user_text.strip():
        raise ChatError("Message vide.")

    if gemini_budget.is_exhausted_today():
        raise ChatError(f"Quota gratuit Gemini déjà atteint. {gemini_budget.reset_message()}")

    user_message = ChatMessage(role="user", content=user_text)
    db.session.add(user_message)
    db.session.commit()

    history = ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(HISTORY_TURNS * 2).all()
    history.reverse()

    contents = [
        genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=f"{SYSTEM_PREAMBLE}\n\nContexte actuel de la chaîne :\n{_build_channel_context()}")],
        ),
        genai_types.Content(role="model", parts=[genai_types.Part(text="Compris, je suis prêt à t'aider.")]),
    ]
    for msg in history:
        contents.append(genai_types.Content(role=msg.role, parts=[genai_types.Part(text=msg.content)]))

    try:
        client = genai.Client()
        response = client.models.generate_content(model=MODEL, contents=contents)
    except genai_errors.APIError as exc:
        if gemini_budget.is_quota_error(exc):
            gemini_budget.mark_exhausted()
            raise ChatError(f"Quota gratuit Gemini atteint. {gemini_budget.reset_message()}") from exc
        if isinstance(exc, genai_errors.ClientError) and exc.code in (401, 403):
            raise ChatError("Clé API Gemini absente ou invalide. Configure GEMINI_API_KEY.") from exc
        raise ChatError(f"Échec de l'appel à l'API Gemini : {exc}") from exc

    reply_text = response.text or "(réponse vide)"
    reply = ChatMessage(role="model", content=reply_text)
    db.session.add(reply)
    db.session.commit()
    return reply
