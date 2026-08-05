import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.assemble.video_builder import assemble_series_video, build_item_clip
from pipeline.config import FRAME_SIZE, MUSIC_DIR, OUTPUT_DIR, SHORT_FRAME_SIZE
from pipeline.content.podcast_loader import load_podcast_series
from pipeline.tts.piper_engine import synth_to_wav
from pipeline.videogen import higgsfield_client

POLL_INTERVAL_SECONDS = 5
MAX_POLL_ATTEMPTS = 60  # ~5 minutes par image avant d'abandonner


def podcast_output_path(series_key: str) -> Path:
    return OUTPUT_DIR / f"podcast_{series_key}.mp4"


def build_podcast_series(
    series_key: str,
    aspect_ratio: str = "9:16",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Assemble un podcast teaser : chaque segment = une phrase narrée (Piper) +
    une image illustrative générée par Higgsfield, affichée pendant exactement la
    durée de la phrase. Pas de calage mot-à-mot : nos voix Piper gratuites
    n'exportent aucun timing par phonème, donc on cale par phrase, ce qui reste
    honnête et visuellement proche de l'effet recherché."""
    series = load_podcast_series(series_key)
    size = SHORT_FRAME_SIZE if aspect_ratio == "9:16" else FRAME_SIZE

    def report(message: str) -> None:
        if progress_callback:
            progress_callback(message)
        print(message)

    with tempfile.TemporaryDirectory(prefix=f"podcast_{series_key}_") as tmp:
        tmp_dir = Path(tmp)
        clips = []

        for i, segment in enumerate(series.segments):
            report(f"[{i + 1}/{len(series.segments)}] Voix off...")
            audio_path = tmp_dir / f"segment_{i:02d}.wav"
            duration = synth_to_wav(segment.narration, audio_path, series.voice)

            report(f"[{i + 1}/{len(series.segments)}] Génération de l'image Higgsfield...")
            job_id = higgsfield_client.generate_image(segment.image_prompt, aspect_ratio)

            status = higgsfield_client.poll_job(job_id)
            attempts = 0
            while status["status"] != "done":
                attempts += 1
                if attempts > MAX_POLL_ATTEMPTS:
                    raise higgsfield_client.HiggsfieldError(
                        f"Délai dépassé en attendant l'image du segment {i + 1} (job {job_id})."
                    )
                time.sleep(POLL_INTERVAL_SECONDS)
                status = higgsfield_client.poll_job(job_id)

            image_path = tmp_dir / f"segment_{i:02d}.jpg"
            higgsfield_client.download_result(status["video_url"], image_path)

            clips.append(build_item_clip(image_path, audio_path, duration, ken_burns=True, size=size))
            report(f"[{i + 1}/{len(series.segments)}] Segment assemblé.")

        report("Assemblage final...")
        out_path = podcast_output_path(series_key)

        candidates = sorted(MUSIC_DIR.glob("*.mp3")) + sorted(MUSIC_DIR.glob("*.wav"))
        music_path = candidates[0] if candidates else None

        assemble_series_video(clips, music_path, out_path)

    report(f"Terminé -> {out_path}")
    return out_path
