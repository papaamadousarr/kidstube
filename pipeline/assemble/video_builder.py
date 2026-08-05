from pathlib import Path
from typing import Optional

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.audio.fx.AudioFadeIn import AudioFadeIn
from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
from moviepy.audio.fx.AudioLoop import AudioLoop
from moviepy.audio.fx.MultiplyVolume import MultiplyVolume
from moviepy.video.fx.Loop import Loop
from moviepy.video.fx.Resize import Resize
from PIL import Image, ImageDraw

from pipeline.assemble.transitions import with_crossfade
from pipeline.config import FPS, FRAME_SIZE, ICONS_DIR
from pipeline.content.schema import SeriesConfig
from pipeline.render.fonts import get_font
from pipeline.tts.piper_engine import synth_to_wav

PADDING = 0.6
ZOOM_AMOUNT = 0.08
MUSIC_VOLUME = 0.12
OUTRO_TEXT = (
    "Merci d'avoir regardé ! Abonne-toi et active la cloche "
    "pour ne rater aucune nouvelle vidéo !"
)
OUTRO_TITLE = "Merci d'avoir regardé !"
SUBSCRIBE_BUTTON_TEXT = "ABONNE-TOI"
BELL_CTA_TEXT = "+ active la cloche !"
SUBSCRIBE_BUTTON_COLOR = "#FF3B30"
BELL_ICON_PATH = ICONS_DIR / "bell.png"


def build_item_clip(
    frame_path: Path,
    audio_path: Path,
    duration: float,
    ken_burns: bool = True,
    size: tuple[int, int] = FRAME_SIZE,
) -> CompositeVideoClip:
    total_duration = duration + PADDING

    img_clip = ImageClip(str(frame_path)).with_duration(total_duration)
    if ken_burns:
        img_clip = img_clip.with_effects([Resize(lambda t: 1 + ZOOM_AMOUNT * (t / total_duration))])
    video = CompositeVideoClip([img_clip.with_position("center")], size=size).with_duration(total_duration)
    video = with_crossfade(video)

    audio = AudioFileClip(str(audio_path)).with_effects([AudioFadeIn(0.15), AudioFadeOut(0.15)])
    audio = audio.with_start(PADDING / 2)
    full_audio = CompositeAudioClip([audio]).with_duration(total_duration)

    return video.with_audio(full_audio)


def build_scene_clip(
    video_path: Path,
    audio_path: Path,
    narration_duration: float,
    text_overlay_path: Optional[Path] = None,
) -> CompositeVideoClip:
    total_duration = narration_duration + PADDING

    raw_clip = VideoFileClip(str(video_path)).without_audio().resized(FRAME_SIZE)
    if raw_clip.duration < total_duration:
        video_clip = raw_clip.with_effects([Loop(duration=total_duration)])
    else:
        video_clip = raw_clip.subclipped(0, total_duration)

    layers = [video_clip.with_position("center")]
    if text_overlay_path is not None:
        overlay_clip = ImageClip(str(text_overlay_path)).with_duration(total_duration).with_position("center")
        layers.append(overlay_clip)

    video = CompositeVideoClip(layers, size=FRAME_SIZE).with_duration(total_duration)
    video = with_crossfade(video)

    audio = AudioFileClip(str(audio_path)).with_effects([AudioFadeIn(0.15), AudioFadeOut(0.15)])
    audio = audio.with_start(PADDING / 2)
    full_audio = CompositeAudioClip([audio]).with_duration(total_duration)

    return video.with_audio(full_audio)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _title_card(text: str, background_color: str, size: tuple[int, int] = FRAME_SIZE) -> Image.Image:
    img = Image.new("RGB", size, background_color)
    draw = ImageDraw.Draw(img)
    font = get_font("display", 90)
    lines = _wrap_text(draw, text, font, size[0] - 160)

    line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
    total_h = sum(line_heights) + 20 * (len(lines) - 1)
    y = (size[1] - total_h) / 2

    for line, h in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (size[0] - w) / 2 - bbox[0]
        draw.text((x, y - bbox[1]), line, font=font, fill="#2B2B2B")
        y += h + 20

    return img


def build_intro_clip(series: SeriesConfig, tmp_dir: Path) -> CompositeVideoClip:
    audio_path = tmp_dir / "intro.wav"
    duration = synth_to_wav(series.intro_text, audio_path, series.voice)
    frame_path = tmp_dir / "intro.png"
    _title_card(series.title, series.background_color).save(frame_path)
    return build_item_clip(frame_path, audio_path, duration, ken_burns=False)


def _subscribe_cta_card(background_color: str, size: tuple[int, int] = FRAME_SIZE) -> Image.Image:
    img = Image.new("RGB", size, background_color)
    draw = ImageDraw.Draw(img)

    title_font = get_font("display", 72)
    lines = _wrap_text(draw, OUTRO_TITLE, title_font, size[0] - 160)
    line_heights = [draw.textbbox((0, 0), line, font=title_font)[3] - draw.textbbox((0, 0), line, font=title_font)[1] for line in lines]
    y = size[1] * 0.1
    for line, h in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        x = (size[0] - w) / 2 - bbox[0]
        draw.text((x, y - bbox[1]), line, font=title_font, fill="#2B2B2B")
        y += h + 16

    button_font = get_font("display", 54)
    btn_w, btn_h = 480, 120
    btn_x = (size[0] - btn_w) / 2
    btn_y = size[1] * 0.42
    draw.rounded_rectangle(
        [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], radius=btn_h / 2, fill=SUBSCRIBE_BUTTON_COLOR
    )
    bbox = draw.textbbox((0, 0), SUBSCRIBE_BUTTON_TEXT, font=button_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (btn_x + (btn_w - tw) / 2 - bbox[0], btn_y + (btn_h - th) / 2 - bbox[1]),
        SUBSCRIBE_BUTTON_TEXT,
        font=button_font,
        fill="white",
    )

    bell_size = 100
    bell = None
    if BELL_ICON_PATH.exists():
        bell = Image.open(BELL_ICON_PATH).convert("RGBA").resize((bell_size, bell_size), Image.LANCZOS)

    bell_font = get_font("body", 46)
    bbox = draw.textbbox((0, 0), BELL_CTA_TEXT, font=bell_font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    row_y = btn_y + btn_h + 55
    gap = 18
    content_w = (bell_size + gap + text_w) if bell is not None else text_w
    start_x = (size[0] - content_w) / 2

    if bell is not None:
        img.paste(bell, (int(start_x), int(row_y)), bell)
        text_x = start_x + bell_size + gap
        text_y = row_y + (bell_size - text_h) / 2
    else:
        text_x = start_x
        text_y = row_y

    draw.text((text_x - bbox[0], text_y - bbox[1]), BELL_CTA_TEXT, font=bell_font, fill="#2B2B2B")

    return img


def build_outro_clip(series: SeriesConfig, tmp_dir: Path) -> CompositeVideoClip:
    audio_path = tmp_dir / "outro.wav"
    duration = synth_to_wav(OUTRO_TEXT, audio_path, series.voice)
    frame_path = tmp_dir / "outro.png"
    _subscribe_cta_card(series.background_color).save(frame_path)
    return build_item_clip(frame_path, audio_path, duration, ken_burns=False)


def assemble_series_video(
    item_clips: list,
    music_path: Optional[Path],
    out_path: Path,
) -> Path:
    final = concatenate_videoclips(item_clips, method="compose")

    if music_path is not None and Path(music_path).exists():
        music = AudioFileClip(str(music_path)).with_effects(
            [AudioLoop(duration=final.duration), MultiplyVolume(MUSIC_VOLUME)]
        )
        final = final.with_audio(CompositeAudioClip([music, final.audio]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(str(out_path), fps=FPS, codec="libx264", audio_codec="aac", logger="bar")
    return out_path
