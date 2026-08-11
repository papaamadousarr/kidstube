from app import youtube_client
from app.db import db
from app.models import Playlist
from pipeline.content.higgsfield_loader import load_higgsfield_series
from pipeline.content.loader import load_series
from pipeline.content.podcast_loader import load_podcast_series
from pipeline.content.schema import ContentError

TYPE_PLAYLIST_TITLES = {
    "flashcards": "Flashcards",
    "shorts": "Shorts",
    "podcast": "Podcasts",
    "higgsfield": "Réalisme",
}

_SERIES_LOADERS = {
    "podcast": load_podcast_series,
    "higgsfield": load_higgsfield_series,
}


def _series_title(idea) -> str:
    loader = _SERIES_LOADERS.get(idea.video_pipeline, load_series)
    try:
        return loader(idea.series_key).title
    except ContentError:
        return idea.series_key


def _get_or_create_playlist(kind: str, key: str, title: str) -> str:
    row = Playlist.query.filter_by(kind=kind, key=key).first()
    if row is not None:
        return row.youtube_playlist_id

    playlist_id = youtube_client.create_playlist(title)
    db.session.add(Playlist(kind=kind, key=key, youtube_playlist_id=playlist_id))
    db.session.commit()
    return playlist_id


def sync_playlists_for_idea(idea) -> None:
    """Ajoute la vidéo YouTube d'une idée fraîchement publiée aux playlists
    'type' (globale par pipeline) et 'série' correspondantes, en les créant
    à la volée si elles n'existent pas encore."""
    if not idea.youtube_video_id:
        return

    type_title = TYPE_PLAYLIST_TITLES.get(idea.video_pipeline)
    if type_title:
        playlist_id = _get_or_create_playlist("type", idea.video_pipeline, type_title)
        youtube_client.add_video_to_playlist(playlist_id, idea.youtube_video_id)

    if idea.series_key:
        playlist_id = _get_or_create_playlist("series", idea.series_key, _series_title(idea))
        youtube_client.add_video_to_playlist(playlist_id, idea.youtube_video_id)
