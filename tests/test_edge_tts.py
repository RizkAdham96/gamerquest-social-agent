from pathlib import Path

from media.tts import EdgeTTS, SmartFrenchTTS


def test_edge_tts_builds_french_neural_voice_command(tmp_path):
    tts = EdgeTTS(voice="fr-FR-DeniseNeural", rate="+5%")
    command = tts.build_command("Bonjour GamerQuest", tmp_path / "voice.mp3")
    assert command[0].endswith("edge-tts")
    assert "--voice" in command
    assert "fr-FR-DeniseNeural" in command
    assert "--rate=+5%" in command
    assert "--write-media" in command


def test_smart_tts_falls_back_when_primary_fails(tmp_path):
    class Broken:
        def synthesize(self, text, output):
            raise RuntimeError("offline")

    class Backup:
        def synthesize(self, text, output):
            output.write_bytes(b"audio")
            return output

    output = tmp_path / "voice.wav"
    result = SmartFrenchTTS(primary=Broken(), fallback=Backup()).synthesize("bonjour", output)
    assert result == output
    assert output.read_bytes() == b"audio"
