import pytest

from pipeline.tts.piper_engine import VoiceNotFoundError, synth_to_wav


def test_synth_to_wav_creates_file_with_duration(tmp_path):
    out_path = tmp_path / "a.wav"
    duration = synth_to_wav("A, comme Avion !", out_path, "fr_FR-siwis-medium")
    assert out_path.exists()
    assert out_path.stat().st_size > 0
    assert duration > 0.2


def test_synth_to_wav_unknown_voice_raises(tmp_path):
    with pytest.raises(VoiceNotFoundError):
        synth_to_wav("test", tmp_path / "b.wav", "fr_FR-does-not-exist")
