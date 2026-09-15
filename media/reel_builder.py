from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class ReelBuildSpec:
    footage: Path
    voiceover: Path
    subtitles: Path
    output: Path
    duration_seconds: float
    background_music: Path | None = None


class ReelBuilder:
    def build_command(self, spec: ReelBuildSpec) -> list[str]:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subtitle_path = str(spec.subtitles).replace("\\", "/").replace(":", "\\:")
        video_filter = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"subtitles='{subtitle_path}':force_style='Alignment=2,MarginV=180,FontSize=18'"
        )
        cmd = [ffmpeg, "-y", "-i", str(spec.footage), "-i", str(spec.voiceover)]
        if spec.background_music:
            cmd += ["-i", str(spec.background_music)]
            audio_filter = (
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.12[music];"
                "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            cmd += ["-filter_complex", audio_filter, "-map", "0:v:0", "-map", "[aout]"]
        else:
            cmd += ["-map", "0:v:0", "-map", "1:a:0"]
        cmd += [
            "-vf", video_filter,
            "-t", str(spec.duration_seconds),
            "-c:v", "libx264",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(spec.output),
        ]
        return cmd

    def build(self, spec: ReelBuildSpec) -> Path:
        spec.output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self.build_command(spec), check=True, capture_output=True)
        if not spec.output.exists() or spec.output.stat().st_size == 0:
            raise RuntimeError("FFmpeg did not produce a Reel")
        return spec.output
