from collections import Counter, deque
from datetime import datetime, time as dt_time, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app import higgsfield_jobs, jobs, podcast_jobs, publish_jobs, seo_defaults, shorts_jobs, tiktok_client, tiktok_jobs
from pipeline.videogen import higgsfield_client

TICK_MINUTES = 5
RETRY_COOLDOWN_MINUTES = 30
LOG_MAXLEN = 50

# Politique de publication permanente : toujours garder des vidéos programmées
# pour aujourd'hui et les prochains jours, à heure fixe. Si l'app est arrêtée
# au moment programmé, _tick() traite au redémarrage tout ce qui est en retard
# (scheduled_dt <= now), donc rien n'est perdu.
DAILY_PUBLISH_TIME = dt_time(10, 0)
PLANNING_HORIZON_DAYS = 2
TOPUP_RETRY_COOLDOWN_MINUTES = 60

# YouTube ne publie aucun chiffre officiel de limite quotidienne d'upload, et
# elle évolue avec l'ancienneté/confiance de la chaîne (constaté : 11/jour au
# 8e jour, 12/jour au 14e). Plutôt qu'un chiffre fixe, on vise systématiquement
# "record récent + 1" pour suivre la vraie limite au fur et à mesure qu'elle
# augmente ; DAILY_TARGET_BOOTSTRAP ne sert qu'avant d'avoir un historique.
DAILY_TARGET_BOOTSTRAP = 6
DAILY_TARGET_HISTORY_DAYS = 14
YOUTUBE_DAILY_CAP_ERROR_MARKER = "exceeded the number of videos"

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
# Quota réel constaté bien plus bas que prévu (20 requêtes/jour, cf.
# app/gemini_budget.py) et partagé avec la génération d'idées et les insights
# analytics — on garde ce rythme très bas pour laisser de la place aux autres.
ICON_BACKFILL_PER_TICK = 1

# Rafraîchit automatiquement les insights Gemini (analyse des vraies données
# YouTube Analytics) une fois par jour, pour que la génération de contenu
# reste orientée par les performances réelles sans action manuelle — Gemini
# comme orchestrateur continu de l'automatisation, pas un rapport ponctuel.
INSIGHT_REFRESH_HOURS = 24

_log: deque = deque(maxlen=LOG_MAXLEN)
_last_failure: dict[int, datetime] = {}
_tiktok_last_failure: dict[int, datetime] = {}
_topup_generation_failure_at: datetime | None = None
_youtube_daily_cap_hit_on = None  # date du jour où YouTube a refusé un upload de plus
_higgsfield_broken_token_mtime: float | None = None  # mtime du token au moment où Higgsfield a signalé une session expirée
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


def _handle_higgsfield_session_failure(idea, app) -> None:
    """Higgsfield a signalé une session/autorisation expirée pour cette
    génération : contrairement à un échec ponctuel, retenter toutes les 30 min
    ne sert à rien tant que personne n'a relancé scripts/higgsfield_auth.py —
    ça bloquait juste inutilement les 2 seuls slots de build en même temps
    (cf. app/generation_pool.py) pendant l'appel voué à l'échec.

    On suspend donc les tentatives et on surveille la mtime du fichier de
    token : tant qu'il n'est pas réécrit (= reconnexion manuelle), on reste
    silencieux ; dès qu'il l'est, on retente immédiatement plutôt que
    d'attendre jusqu'à 30 min de plus."""
    global _higgsfield_broken_token_mtime

    current_mtime = higgsfield_client.TOKEN_PATH.stat().st_mtime if higgsfield_client.TOKEN_PATH.exists() else 0.0

    if _higgsfield_broken_token_mtime is not None and current_mtime <= _higgsfield_broken_token_mtime:
        return  # toujours cassé, on attend en silence (pas de log ni de tentative)

    if _higgsfield_broken_token_mtime is None:
        _higgsfield_broken_token_mtime = current_mtime
        _record(
            idea,
            "génération",
            False,
            "Session Higgsfield expirée — tentatives suspendues jusqu'à reconnexion "
            "(python scripts/higgsfield_auth.py).",
        )
        return

    # current_mtime > _higgsfield_broken_token_mtime : le token a été réécrit
    # depuis la dernière panne signalée → reconnexion détectée.
    _higgsfield_broken_token_mtime = None
    _record(idea, "génération", True, "Higgsfield reconnecté — nouvelle tentative de génération.")
    _start_generation_job(idea, app)


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
        shorts_jobs.start_job(idea.id, idea.series_key, idea.short_item_index or 0, app, idea.short_group_size)
    elif idea.video_pipeline == "podcast":
        podcast_jobs.start_job(idea.id, idea.series_key, "9:16", app)
    else:
        jobs.start_job(idea.id, idea.series_key, app)


def _todays_publish_count() -> int:
    from app.models import Idea

    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    return Idea.query.filter(Idea.published_at >= today, Idea.published_at < tomorrow).count()


def _compute_daily_target() -> int:
    """Vise toujours "record récent + 1" pour suivre la vraie limite YouTube au
    fur et à mesure qu'elle augmente, plutôt qu'un chiffre fixe deviné."""
    from app.models import Idea

    since = datetime.now() - timedelta(days=DAILY_TARGET_HISTORY_DAYS)
    rows = Idea.query.filter(Idea.published_at >= since).all()
    if not rows:
        return DAILY_TARGET_BOOTSTRAP
    counts = Counter(r.published_at.date() for r in rows)
    return max(counts.values()) + 1


def _youtube_cap_hit_today() -> bool:
    return _youtube_daily_cap_hit_on == datetime.now().date()


def _process_idea(idea, app) -> None:
    if _in_cooldown(idea.id):
        return

    if idea.status != "assembled":
        gen_job = _get_generation_job(idea)

        if gen_job is not None:
            if gen_job["status"] in ("queued", "running"):
                return
            if gen_job["status"] == "done" and gen_job["success"] is False:
                if idea.video_pipeline in ("higgsfield", "podcast") and higgsfield_client.is_session_error(
                    gen_job.get("message", "")
                ):
                    _handle_higgsfield_session_failure(idea, app)
                    return

                first_failure = idea.id not in _last_failure
                _mark_failure(idea.id)
                if first_failure:
                    _record(idea, "génération", False, "Échec de génération — nouvelle tentative suspendue.")
                    return
                # Le cooldown de 30 min vient d'expirer (sinon _in_cooldown nous
                # aurait arrêtés en tête de fonction) : on retente au lieu de
                # re-logguer indéfiniment le même échec sans jamais relancer.

        if not idea.series_key:
            _record(idea, "génération", False, "Aucune série de contenu associée à cette idée.")
            _mark_failure(idea.id)
            return

        if idea.video_pipeline in ("higgsfield", "podcast") and not higgsfield_client.is_connected():
            _record(idea, "génération", False, "Higgsfield non connecté — génération suspendue.")
            _mark_failure(idea.id)
            return

        _start_generation_job(idea, app)
        _record(idea, "génération", True, "Génération lancée automatiquement.")
        return

    global _youtube_daily_cap_hit_on
    if _youtube_cap_hit_today():
        return

    pub_job = publish_jobs.get_job(idea.id)
    if pub_job is not None:
        if pub_job["status"] in ("queued", "running"):
            return
        if pub_job["status"] == "done" and pub_job["success"] is False:
            error = pub_job.get("error") or ""
            if YOUTUBE_DAILY_CAP_ERROR_MARKER in error.lower():
                _youtube_daily_cap_hit_on = datetime.now().date()
                _record(
                    idea,
                    "publication",
                    False,
                    f"Limite quotidienne YouTube atteinte ({_todays_publish_count()} vidéo(s) "
                    "publiée(s) aujourd'hui) — reprise automatique demain.",
                )
                return
            first_failure = idea.id not in _last_failure
            _mark_failure(idea.id)
            if first_failure:
                _record(idea, "publication", False, f"Échec de publication : {pub_job.get('error')}")
                return
            # Le cooldown de 30 min vient d'expirer (sinon _in_cooldown nous
            # aurait arrêtés en tête de fonction) : on retente au lieu de
            # re-logguer indéfiniment le même échec sans jamais relancer la
            # publication.

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


def _tiktok_in_cooldown(idea_id: int) -> bool:
    last = _tiktok_last_failure.get(idea_id)
    if last is None:
        return False
    return (datetime.now() - last).total_seconds() < RETRY_COOLDOWN_MINUTES * 60


def _process_tiktok_crosspost(idea, app) -> None:
    """Republie sur TikTok les Shorts déjà publiés sur YouTube (format vertical
    adapté), une fois l'app TikTok autorisée. Tant qu'aucun token production
    n'existe (app encore en review), on n'essaie même pas — pas la peine de
    spammer le log avec un échec d'auth garanti à chaque tick."""
    if _tiktok_in_cooldown(idea.id):
        return

    job = tiktok_jobs.get_job(idea.id)
    if job is not None:
        if job["status"] == "running":
            return
        if job["status"] == "done" and job["success"] is False:
            _tiktok_last_failure[idea.id] = datetime.now()
            _record(idea, "TikTok", False, f"Échec de publication TikTok : {job.get('message')}")
            return

    if not tiktok_client.is_connected():
        return

    seo = seo_defaults.build_seo_defaults(idea)
    tiktok_jobs.start_job(idea.id, idea.video_path, seo["title"], app)
    _record(idea, "TikTok", True, "Publication TikTok lancée automatiquement.")


SCHEDULING_PIPELINES = ("flashcards", "shorts", "podcast", "higgsfield")


def _pick_candidates_round_robin(needed: int):
    """Choisit les prochaines idées à programmer, réparties entre pipelines
    (flashcards/shorts/podcast/higgsfield) proportionnellement à la taille de
    l'arriéré de chacun — pas par simple ancienneté globale, sinon un gros lot
    d'idées d'un seul pipeline créées en une fois (ex. 216 flashcards générées
    le même jour) passe indéfiniment devant les autres créés plus tard
    (constaté : 793 Shorts en attente, 0 programmé). Un pipeline avec un
    arriéré 3x plus gros obtient environ 3x plus de créneaux — au moins 1 s'il
    n'est pas vide, pour qu'aucun pipeline ne reste totalement à zéro."""
    from app.models import Idea

    backlogs = {
        pipeline: Idea.query.filter(
            Idea.scheduled_date.is_(None),
            Idea.status != "published",
            Idea.video_pipeline == pipeline,
        ).count()
        for pipeline in SCHEDULING_PIPELINES
    }
    total_backlog = sum(backlogs.values())
    if total_backlog == 0:
        return []

    allocation = {
        pipeline: (max(1, round(needed * count / total_backlog)) if count > 0 else 0)
        for pipeline, count in backlogs.items()
    }
    # Les arrondis peuvent faire déborder le total : on retire l'excédent en
    # priorité aux pipelines les mieux servis (jamais sous 1 tant qu'il en a besoin).
    while sum(allocation.values()) > needed:
        biggest = max((p for p in allocation if allocation[p] > 1), key=lambda p: allocation[p], default=None)
        if biggest is None:
            break
        allocation[biggest] -= 1

    picked = []
    for pipeline, count in allocation.items():
        if count <= 0:
            continue
        picked.extend(
            Idea.query.filter(
                Idea.scheduled_date.is_(None),
                Idea.status != "published",
                Idea.video_pipeline == pipeline,
            )
            .order_by(Idea.created_at)
            .limit(count)
            .all()
        )
    return picked


def _top_up_daily_schedule() -> None:
    global _topup_generation_failure_at
    from app import idea_generator
    from app.db import db
    from app.models import Idea

    today = datetime.now().date()
    daily_target = _compute_daily_target()
    cooldown_active = _topup_generation_failure_at is not None and (
        datetime.now() - _topup_generation_failure_at
    ).total_seconds() < TOPUP_RETRY_COOLDOWN_MINUTES * 60

    # On ne comble jamais rétroactivement aujourd'hui (offset 0) : ça publierait
    # dans la précipitation du contenu déjà en stock dès l'activation de la
    # politique. Elle ne s'applique qu'à partir de demain.
    for offset in range(1, PLANNING_HORIZON_DAYS + 1):
        day = today + timedelta(days=offset)
        scheduled_count = Idea.query.filter(Idea.scheduled_date == day).count()
        needed = daily_target - scheduled_count
        if needed <= 0:
            continue

        available = Idea.query.filter(Idea.scheduled_date.is_(None), Idea.status != "published").count()
        if available < needed and not cooldown_active:
            try:
                idea_generator.generate_new_series_ideas(needed - available)
            except idea_generator.IdeaGenerationError:
                _topup_generation_failure_at = datetime.now()

        candidates = _pick_candidates_round_robin(needed)
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


def _refresh_insight_if_stale() -> None:
    from app import analytics_insights, youtube_analytics
    from app.youtube_client import YouTubeAuthError

    if not youtube_analytics.is_connected():
        return

    latest = analytics_insights.get_latest_insight()
    if latest is not None and (datetime.now() - latest.created_at).total_seconds() < INSIGHT_REFRESH_HOURS * 3600:
        return

    try:
        summary = youtube_analytics.get_channel_summary()
        trend = youtube_analytics.get_daily_trend()
        top_videos = youtube_analytics.get_top_videos()
        traffic_sources = youtube_analytics.get_traffic_sources()
    except (YouTubeAuthError, youtube_analytics.YouTubeAnalyticsError):
        return  # ex. API pas encore activée, ou session expirée : on retentera au prochain tick

    analytics_data = {
        "resume_chaine": summary,
        "tendance_quotidienne": trend,
        "meilleures_videos": top_videos,
        "sources_de_trafic": traffic_sources,
    }
    try:
        analytics_insights.generate_insight(analytics_data, youtube_analytics.DEFAULT_WINDOW_DAYS)
    except analytics_insights.InsightGenerationError:
        pass  # ex. pas de clé Gemini : on retentera au prochain tick


def _tick(app) -> None:
    with app.app_context():
        from app.models import Idea

        _backfill_icons()
        _top_up_shorts_catalog()
        _top_up_podcast_catalog()
        _refresh_insight_if_stale()
        _top_up_daily_schedule()

        now = datetime.now()
        due = Idea.query.filter(Idea.scheduled_date.isnot(None), Idea.status != "published").all()

        for idea in due:
            scheduled_dt = datetime.combine(idea.scheduled_date, idea.scheduled_time or dt_time.min)
            if scheduled_dt <= now:
                _process_idea(idea, app)

        due_tiktok = Idea.query.filter(
            Idea.status == "published",
            Idea.video_pipeline == "shorts",
            Idea.tiktok_publish_id.is_(None),
        ).all()
        for idea in due_tiktok:
            _process_tiktok_crosspost(idea, app)


def init_scheduler(app) -> BackgroundScheduler:
    global _scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(_tick, IntervalTrigger(minutes=TICK_MINUTES), args=[app], id="kidstube_auto_publish")
    scheduler.start()
    _scheduler = scheduler
    return scheduler
