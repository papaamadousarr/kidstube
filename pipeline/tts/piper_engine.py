import wave
from functools import lru_cache
from pathlib import Path

from piper.config import SynthesisConfig
from piper.voice import PiperVoice

from pipeline.config import VOICES_DIR


class VoiceNotFoundError(FileNotFoundError):
    pass


@lru_cache(maxsize=4)
def _load_voice(voice_name: str) -> PiperVoice:
    model_path = VOICES_DIR / f"{voice_name}.onnx"
    config_path = VOICES_DIR / f"{voice_name}.onnx.json"
    if not model_path.exists() or not config_path.exists():
        raise VoiceNotFoundError(
            f"Voix Piper introuvable : {model_path}. "
            "Lance scripts/setup_voices.sh pour la télécharger."
        )
    return PiperVoice.load(model_path, config_path=config_path)


def synth_to_wav(
    text: str,
    out_path: Path,
    voice_name: str,
    length_scale: float = 1.0,
) -> float:
    """Synthétise `text` avec la voix Piper `voice_name` dans `out_path` (WAV).

    Retourne la durée du clip audio généré, en secondes.
    """
    voice = _load_voice(voice_name)
    syn_config = SynthesisConfig(length_scale=length_scale)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)

    with wave.open(str(out_path), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
    return frames / float(rate)
