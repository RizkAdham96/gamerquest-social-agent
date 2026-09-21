from pathlib import Path
from media.reel_builder import ReelBuildSpec, ReelBuilder


def _spec(tmp_path: Path) -> ReelBuildSpec:
    return ReelBuildSpec(
        footage=tmp_path / "clip.mp4",
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
    assert "-ss" in cmd
    assert str(ReelBuilder.TRAILER_INTRO_SKIP_SECONDS) in cmd
    assert "aac" in cmd
    assert str(spec.output) == cmd[-1]


def test_ffmpeg_command_forces_true_vertical_fill(tmp_path: Path):
    joined = " ".join(map(str, ReelBuilder().build_command(_spec(tmp_path))))
    assert "force_original_aspect_ratio=increase" in joined
    assert "crop=1080:1920" in joined
    assert "setsar=1" in joined
    assert "eq=" not in joined


def test_ffmpeg_command_uses_professional_gamerquest_caption_treatment(tmp_path: Path):
    joined = " ".join(map(str, ReelBuilder().build_command(_spec(tmp_path))))
    assert "GAMERQUEST FR" in joined
    assert "BorderStyle=3" in joined
    assert "Bold=1" in joined
    assert "FontSize=20" in joined
    assert "MarginL=52" in joined
    assert "MarginR=52" in joined
    assert "MarginV=118" in joined
    assert "drawbox" in joined
    assert "drawtext" in joined


def test_ffmpeg_command_uses_official_trailer_audio_by_default(tmp_path: Path):
    cmd = ReelBuilder().build_command(_spec(tmp_path))
    joined = " ".join(map(str, cmd))
    assert "0:a?" in joined
    assert "voice.wav" not in joined


def test_ffmpeg_command_can_override_with_background_music(tmp_path: Path):
    spec = ReelBuildSpec(
        footage=tmp_path / "clip.mp4",
        subtitles=tmp_path / "subtitles.srt",
        output=tmp_path / "reel.mp4",
        duration_seconds=15.0,
        background_music=tmp_path / "music.mp3",
    )
    cmd = ReelBuilder().build_command(spec)
    joined = " ".join(map(str, cmd))
    assert str(spec.background_music) in joined
    assert "1:a:0" in joined
