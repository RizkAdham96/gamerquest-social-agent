from pathlib import Path
from media.reel_builder import ReelBuildSpec, ReelBuilder


def test_ffmpeg_command_targets_vertical_h264_aac_mp4(tmp_path: Path):
    spec = ReelBuildSpec(
        footage=tmp_path / "clip.mp4",
        voiceover=tmp_path / "voice.wav",
        subtitles=tmp_path / "subtitles.srt",
        output=tmp_path / "reel.mp4",
        duration_seconds=15.0,
    )
    cmd = ReelBuilder().build_command(spec)
    joined = " ".join(map(str, cmd))
    assert cmd[0].endswith("ffmpeg")
    assert "1080:1920" in joined
    assert "libx264" in cmd
    assert "aac" in cmd
    assert str(spec.output) == cmd[-1]
