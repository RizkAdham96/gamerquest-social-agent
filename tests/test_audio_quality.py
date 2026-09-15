from pathlib import Path

import pytest

from media.audio_quality import AudioQualityError, validate_narration


def test_robotic_fallback_is_not_publishable(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"fixture")

    with pytest.raises(AudioQualityError, match="neural"):
        validate_narration(
            audio,
            provider_name="espeak",
            probe=lambda _: {"duration": 5.0, "mean_volume": -20.0},
        )


def test_silent_narration_is_rejected(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"fixture")

    with pytest.raises(AudioQualityError, match="silent"):
        validate_narration(
            audio,
            provider_name="edge-tts",
            probe=lambda _: {"duration": 5.0, "mean_volume": -50.0},
        )


def test_natural_non_silent_narration_passes(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"fixture")

    report = validate_narration(
        audio,
        provider_name="edge-tts",
        probe=lambda _: {"duration": 5.0, "mean_volume": -20.0},
    )

    assert report.publishable
    assert report.provider_name == "edge-tts"
