from pathlib import Path
from media.tts import EspeakTTS


def test_espeak_tts_builds_command_for_french_voice(tmp_path: Path):
    output = tmp_path / "voice.wav"
    cmd = EspeakTTS().build_command("Bonjour GamerQuest", output)
    assert cmd[0].endswith("espeak")
    assert "-v" in cmd
    assert "fr" in cmd
    assert str(output) in cmd
