from datetime import datetime
from pathlib import Path

from app.db import db
from pipeline.config import OUTPUT_DIR

STATUSES = ["idea", "script", "recorded", "assembled", "published"]


class Idea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    series_key = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="idea")
    scheduled_date = db.Column(db.Date, nullable=True)
    scheduled_time = db.Column(db.Time, nullable=True)
    video_pipeline = db.Column(db.String(20), nullable=False, default="flashcards")
    short_item_index = db.Column(db.Integer, nullable=True)
    linked_idea_id = db.Column(db.Integer, db.ForeignKey("idea.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    youtube_video_id = db.Column(db.String(64), nullable=True)

    linked_idea = db.relationship("Idea", remote_side=[id])

    @property
    def youtube_url(self) -> str | None:
        return f"https://youtu.be/{self.youtube_video_id}" if self.youtube_video_id else None

    @property
    def video_path(self) -> Path:
        if self.video_pipeline == "shorts" and self.short_item_index is not None:
            return OUTPUT_DIR / f"{self.series_key}_short_{self.short_item_index:02d}.mp4"
        if self.video_pipeline == "podcast":
            return OUTPUT_DIR / f"podcast_{self.series_key}.mp4"
        return OUTPUT_DIR / f"{self.series_key}.mp4"
