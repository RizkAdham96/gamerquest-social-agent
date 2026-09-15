from pathlib import Path
from media.reel_pipeline import ReelPipeline


class FakeTTS:
    def synthesize(self, text: str, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-audio")
        return output


class FakeBuilder:
    def build(self, spec):
        spec.output.parent.mkdir(parents=True, exist_ok=True)
        spec.output.write_bytes(b"fake-video")
        return spec.output


def test_pipeline_writes_subtitles_and_returns_output(tmp_path: Path):
    footage = tmp_path / "input.mp4"
    footage.write_bytes(b"clip")
    pipeline = ReelPipeline(tts=FakeTTS(), builder=FakeBuilder())
    output = pipeline.render(
        footage=footage,
        voiceover_text="Une annonce GamerQuest arrive maintenant.",
        output_dir=tmp_path / "out",
        duration_seconds=6.0,
    )
    assert output.exists()
    assert (tmp_path / "out" / "subtitles.srt").exists()
    assert (tmp_path / "out" / "voice.wav").exists()
