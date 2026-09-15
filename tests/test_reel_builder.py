from pathlib import Path
from media.reel_builder import ReelBuildSpec, ReelBuilder


def _spec(tmp_path: Path) -> ReelBuildSpec:
    return ReelBuildSpec(
        footage=tmp_path / "clip.mp4",
        voiceover=tmp_path / "voice.wav",
        subtitles=tmp_path / "subtitles.srt",
        output=tmp_path / "reel.mp4",
        duration_seconds=15.0,
    )


def test_ffmpeg_command_targets_vertical_h264_aac_mp4(tmp_path: Path):
    spec = _spec(tmp_path)
    cmd = ReelBuilder().build_command(spec)
    joined = " ".join(map(str, cmd))
    assert cmd[0].endswith("ffmpeg")
    assert "1080:1920" in joined
    assert "libx264" in cmd
    assert "aac" in cmd
    assert str(spec.output) == cmd[-1]


def test_ffmpeg_command_uses_clean_newsroom_caption_treatment(tmp_path: Path):
    joined = " ".join(map(str, ReelBuilder().build_command(_spec(tmp_path))))
    assert "BorderStyle=3" in joined
    assert "Bold=1" in joined
    assert "FontSize=14" in joined
    assert "MarginL=24" in joined
    assert "MarginR=24" in joined
    assert "MarginV=48" in joined
    assert "drawtext" not in joined
    assert "0x7C4DFF" not in joined
    assert "eq=" not in joined
