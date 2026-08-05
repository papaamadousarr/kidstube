from collections import deque
from datetime import datetime, time as dt_time, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app import higgsfield_jobs, jobs, podcast_jobs, publish_jobs, seo_defaults, shorts_jobs

TICK_MINUTES = 5
RETRY_COOLDOWN_MINUTES = 30
LOG_MAXLEN = 50

# Politique de publication permanente : toujours garder ce nombre de vidéos
# programmées pour aujourd'hui et les prochains jours, à heure fixe. Si l'app
# est arrêtée au moment programmé, _tick() traite au redémarrage tout ce qui
# est en retard (scheduled_dt <= now), donc rien n'est perdu.
DAILY_PUBLISH_COUNT = 6
DAILY_PUBLISH_TIME = dt_time(10, 0)
PLANNING_HORIZON_DAYS = 2
TOPUP_RETRY_COOLDOWN_MINUTES = 60

# Crée automatiquement les Shorts manquants (un mot de série sans Short
# existant) par petits lots à chaque tick, plutôt que tout d'un coup — le
# catalogue peut compter des centaines de mots, pas besoin de tout créer
# avant d'en avoir besoin pour la programmation quotidienne.
SHORTS_TOPUP_PER_TICK = 10

# Idem pour les podcasts teasers : un par série flashcards alignée mission qui
# n'en a pas encore (dérivé automatiquement de son intro + ses mots, cf.
# app/podcast_catalog.py). Créer l'idée est gratuit ; seule la génération
# réelle (déclenchée plus tard par la programmation quotidienne) consomme des
# crédits Higgsfield.
PODCAST_TOPUP_PER_TICK = 5

# Rattrapage des icônes manquantes sur les séries flashcards déjà générées
# (1 appel Gemini par série, cf. app/idea_generator.py::backfill_missing_icons).
# Gratuit sur le tier gratuit de l'API Gemini tant qu'on reste sous ses quotas
# journaliers — on étale volontairement pour ne jamais s'en approcher.
ICON_BACKFILL_PER_TICK = 5

_log: deque = deque(maxlen=LOG_MAXLEN)
_last_failure: dict[int, datetime] = {}
_topup_generation_failure_at: datetime | None = None
_scheduler: BackgroundScheduler | None = None


def _record(idea, action: str, success: bool, message: str) -> None:
    _log.appendleft(
        {
            "idea_id": idea.id,
            "title": idea.title,
            "action": action,
            "success": success,
            "message": message,
            "timestamp": datetime.now(),
        }
    )


def get_recent_log() -> list[dict]:
    return list(_log)


def _in_cooldown(idea_id: int) -> bool:
    last = _last_failure.get(idea_id)
    if last is None:
        return False
    return (datetime.now() - last).total_seconds() < RETRY_COOLDOWN_MINUTES * 60


def _mark_failure(idea_id: int) -> None:
    _last_failure[idea_id] = datetime.now()


def _get_generation_job(idea):
    if idea.video_pipeline == "higgsfield":
        return higgsfield_jobs.get_job(idea.id)
    if idea.video_pipeline == "shorts":
        return shorts_jobs.get_job(idea.id)
    if idea.video_pipeline == "podcast":
        return podcast_jobs.get_job(idea.id)
    return jobs.get_job(idea.id)


def _start_generation_job(idea, app) -> None:
    if idea.video_pipeline == "higgsfield":
        higgsfield_jobs.start_job(idea.id, idea.series_key, None, app)
    elif idea.video_pipeline == "shorts":
        shorts_jobs.start_job(idea.id, idea.series_key, idea.short_item_index or 0, app)
    elif idea.video_pipeline == "podcast":
        podcast_jobs.start_job(idea.id, idea.series_key, "9:16", app)
    else:
        jobs.start_job(idea.id, idea.series_key, app)


def _process_idea(idea, app) -> None:
    if _in_cooldown(idea.id):
        return

    if idea.status != "assembled":
        gen_job = _get_generation_job(idea)

        if gen_job is not None:
            if gen_job["status"] in ("queued", "running"):
                return
            if gen_job["status"] == "done" and gen_job["success"] is False:
                _record(idea, "génération", False, "Échec de génération — nouvelle tentative suspendue.")
                _mark_failure(idea.id)
                return

        if not idea.series_key:
            _record(idea, "génération", False, "Aucune série de contenu associée à cette idée.")
            _mark_failure(idea.id)
            return

        _start_generation_job(idea, app)
        _record(idea, "génération", True, "Génération lancée automatiquement.")
        return

    pub_job = publish_jobs.get_job(idea.id)
    if pub_job is not None:
        if pub_job["status"] == "running":
            return
        if pub_job["status"] == "done" and pub_job["success"] is False:
            _record(idea, "publication", False, f"Échec de publication : {pub_job.get('error')}")
            _mark_failure(idea.id)
            return

    seo = seo_defaults.build_seo_defaults(idea)
    publish_jobs.start_job(
        idea.id,
        idea.video_path,
        seo["title"],
        seo["description"],
        seo["tags"],
        "public",
        False,
        app,
    )
    _record(idea, "publication", True, "Publication YouTube lancée automatiquement.")


def _top_up_daily_schedule() -> None:
    global _topup_generation_failure_at
    from app import idea_generator
    from app.db import db
    from app.models import Idea

    today = datetime.now().date()
    cooldown_active = _topup_generation_failure_at is not None and (
        datetime.now() - _topup_generation_failure_at
    ).total_seconds() < TOPUP_RETRY_COOLDOWN_MINUTES * 60

    # On ne comble jamais rétroactivement aujourd'hui (offset 0) : ça publierait
    # dans la précipitation du contenu déjà en stock dès l'activation de la
    # politique. Elle ne s'applique qu'à partir de demain.
    for offset in range(1, PLANNING_HORIZON_DAYS + 1):
        day = today + timedelta(days=offset)
        scheduled_count = Idea.query.filter(Idea.scheduled_date == day).count()
        needed = DAILY_PUBLISH_COUNT - scheduled_count
        if needed <= 0:
            continue

        available = Idea.query.filter(Idea.scheduled_date.is_(None), Idea.status != "published").count()
        if available < needed and not cooldown_active:
            try:
                idea_generator.generate_new_series_ideas(needed - available)
            except idea_generator.IdeaGenerationError:
                _topup_generation_failure_at = datetime.now()

        candidates = (
            Idea.query.filter(Idea.scheduled_date.is_(None), Idea.status != "published")
            .order_by(Idea.created_at)
            .limit(needed)
            .all()
        )
        for idea in candidates:
            idea.scheduled_date = day
            idea.scheduled_time = DAILY_PUBLISH_TIME
        if candidates:
            db.session.commit()


def _top_up_shorts_catalog() -> None:
    from app import shorts_catalog

    shorts_catalog.create_missing_shorts(limit=SHORTS_TOPUP_PER_TICK)


def _top_up_podcast_catalog() -> None:
    from app import podcast_catalog

    podcast_catalog.create_missing_podcast_teasers(limit=PODCAST_TOPUP_PER_TICK)


def _backfill_icons() -> None:
    from app import idea_generator

    idea_generator.backfill_missing_icons(limit=ICON_BACKFILL_PER_TICK)


def _tick(app) -> None:
    with app.app_context():
        from app.models import Idea

        _backfill_icons()
        _top_up_shorts_catalog()
        _top_up_podcast_catalog()
        _top_up_daily_schedule()

        now = datetime.now()
        due = Idea.query.filter(Idea.scheduled_date.isnot(None), Idea.status != "published").all()

        for idea in due:
            scheduled_dt = datetime.combine(idea.scheduled_date, idea.scheduled_time or dt_time.min)
            if scheduled_dt <= now:
                _process_idea(idea, app)


def init_scheduler(app) -> BackgroundScheduler:
    global _scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(_tick, IntervalTrigger(minutes=TICK_MINUTES), args=[app], id="kidstube_auto_publish")
    scheduler.start()
    _scheduler = scheduler
    return scheduler
