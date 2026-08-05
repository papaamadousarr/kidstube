import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.assemble.video_builder import assemble_series_video, build_scene_clip
from pipeline.config import MUSIC_DIR, OUTPUT_DIR
from pipeline.content.higgsfield_loader import load_higgsfield_series
from pipeline.render.overlay_builder import build_text_overlay
from pipeline.tts.piper_engine import synth_to_wav
from pipeline.videogen import higgsfield_client

POLL_INTERVAL_SECONDS = 5
MAX_POLL_ATTEMPTS = 180  # ~15 minutes par scène avant d'abandonner


def build_higgsfield_series(
    series_key: str,
    aspect_ratio: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    series = load_higgsfield_series(series_key)
    aspect_ratio = aspect_ratio or series.aspect_ratio

    def report(message: str) -> None:
        if progress_callback:
            progress_callback(message)
        print(message)

    with tempfile.TemporaryDirectory(prefix=f"higgsfield_{series_key}_") as tmp:
        tmp_dir = Path(tmp)
        scene_clips = []

        for i, scene in enumerate(series.scenes):
            report(f"[{i + 1}/{len(series.scenes)}] Voix off...")
            audio_path = tmp_dir / f"scene_{i:02d}.wav"
            duration = synth_to_wav(scene.narration, audio_path, series.voice)

            report(f"[{i + 1}/{len(series.scenes)}] Génération Higgsfield en cours...")
            job_id = higgsfield_client.generate_video(
                scene.prompt, None, aspect_ratio, target_duration=duration
            )

            status = higgsfield_client.poll_job(job_id)
            attempts = 0
            while status["status"] != "done":
                attempts += 1
                if attempts > MAX_POLL_ATTEMPTS:
                    raise higgsfield_client.HiggsfieldError(
                        f"Délai dépassé en attendant la scène {i + 1} (job {job_id}). "
                        f"Dernière réponse brute : {status.get('raw')}"
                    )
                time.sleep(POLL_INTERVAL_SECONDS)
                status = higgsfield_client.poll_job(job_id)

            video_path = tmp_dir / f"scene_{i:02d}.mp4"
            higgsfield_client.download_result(status["video_url"], video_path)

            overlay_path = None
            if scene.text_overlay:
                overlay_path = tmp_dir / f"scene_{i:02d}_overlay.png"
                build_text_overlay(scene.text_overlay).save(overlay_path)

            scene_clips.append(build_scene_clip(video_path, audio_path, duration, overlay_path))
            report(f"[{i + 1}/{len(series.scenes)}] Scène assemblée.")

        report("Assemblage final...")
        out_path = OUTPUT_DIR / f"{series_key}.mp4"

        candidates = sorted(MUSIC_DIR.glob("*.mp3")) + sorted(MUSIC_DIR.glob("*.wav"))
        music_path = candidates[0] if candidates else None

        assemble_series_video(scene_clips, music_path, out_path)

    report(f"Terminé -> {out_path}")
    return out_path
