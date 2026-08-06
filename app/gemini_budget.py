"""Suivi partagé du quota gratuit Gemini entre tous les appelants (génération
d'idées, rattrapage d'icônes, insights analytics, chat). Le vrai quota
journalier observé (429 RESOURCE_EXHAUSTED) est bien plus bas que la
documentation générale ne le laisse penser (20 requêtes/jour constaté sur ce
compte) — donc plutôt que deviner un chiffre, on détecte le vrai blocage et on
met en pause tous les appelants jusqu'à la remise à zéro réelle.

Google réinitialise ces quotas à minuit heure du Pacifique (America/Los_Angeles),
pas à minuit UTC ni minuit serveur — un simple test "même date que le serveur"
se trompait de 7-8h selon l'heure d'été. On stocke donc l'instant exact
(timestamp UTC) de la prochaine remise à zéro, pas une date.

Persisté sur disque (pas seulement en mémoire) : l'app est redémarrée souvent
pendant le développement, et un simple redémarrage ne doit pas faire oublier
qu'on a déjà tapé le mur aujourd'hui — sinon l'automatisation retente
immédiatement et regaspille les quelques requêtes restantes."""

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from google.genai import errors as genai_errors

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "secrets" / "gemini_quota_state.txt"

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")

_lock = threading.Lock()


def next_reset_at() -> datetime:
    """Prochain minuit heure du Pacifique (Google y réinitialise les quotas
    API), en UTC — gère automatiquement le passage heure d'été/hiver."""
    now_pacific = datetime.now(PACIFIC_TZ)
    next_midnight_pacific = (now_pacific + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_midnight_pacific.astimezone(timezone.utc)


def _read_reset_at() -> datetime | None:
    if not STATE_PATH.exists():
        return None
    raw = STATE_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def is_exhausted_today() -> bool:
    with _lock:
        reset_at = _read_reset_at()
        return reset_at is not None and datetime.now(timezone.utc) < reset_at


def mark_exhausted() -> None:
    with _lock:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(next_reset_at().isoformat(), encoding="utf-8")


def reset_message() -> str:
    """Message lisible indiquant l'heure exacte de la prochaine remise à zéro,
    dans le fuseau du Pacifique (source) et en UTC (repère serveur)."""
    reset_at = _read_reset_at() or next_reset_at()
    pacific = reset_at.astimezone(PACIFIC_TZ)
    return (
        f"Remise à zéro à minuit heure du Pacifique, soit {reset_at.strftime('%H:%M')} UTC "
        f"le {reset_at.strftime('%d/%m/%Y')} ({pacific.strftime('%Z')})."
    )


def is_quota_error(exc: Exception) -> bool:
    if not isinstance(exc, genai_errors.APIError):
        return False
    return exc.code == 429 or (exc.status or "").upper() == "RESOURCE_EXHAUSTED"
