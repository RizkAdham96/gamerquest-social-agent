from pathlib import Path
from media.tts import EdgeTTS, EspeakTTS


def test_espeak_tts_builds_command_for_french_voice(tmp_path: Path):
    output = tmp_path / "voice.wav"
    cmd = EspeakTTS().build_command("Bonjour GamerQuest", output)
    assert cmd[0].endswith("espeak")
    assert "-v" in cmd
    assert "fr" in cmd
    assert str(output) in cmd


def test_edge_tts_has_module_fallback_when_script_is_not_on_path(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("media.tts.shutil.which", lambda _: None)
    command = EdgeTTS().build_command("Bonjour", tmp_path / "voice.mp3")
    assert command[1:3] == ["-m", "edge_tts"]
