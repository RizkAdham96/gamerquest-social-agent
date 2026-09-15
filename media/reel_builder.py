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
    """Render a branded, mobile-safe GamerQuest vertical Reel."""

    BRAND_LABEL = "GAMERQUEST FR"

    def build_command(self, spec: ReelBuildSpec) -> list[str]:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subtitle_path = str(spec.subtitles).replace("\\", "/").replace(":", "\\:")
        caption_style = (
            "FontName=DejaVu Sans,"
            "FontSize=14,"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"
            "BackColour=&H60000000,"
            "BorderStyle=3,"
            "Outline=0,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginL=24,"
            "MarginR=24,"
            "MarginV=48,"
            "Spacing=0.5"
        )
        video_filter = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1,"
            "eq=contrast=1.04:saturation=1.08,"
            "drawbox=x=54:y=90:w=500:h=96:color=black@0.72:t=fill,"
            "drawbox=x=54:y=90:w=14:h=96:color=0x7C4DFF@1:t=fill,"
            "drawtext=font='DejaVu Sans':"
            f"text='{self.BRAND_LABEL}':"
            "fontcolor=white:fontsize=38:x=88:y=116,"
            f"subtitles='{subtitle_path}':force_style='{caption_style}'"
        )
        cmd = [ffmpeg, "-y", "-i", str(spec.footage), "-i", str(spec.voiceover)]
        if spec.background_music:
            cmd += ["-i", str(spec.background_music)]
            audio_filter = (
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.10[music];"
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
            "-profile:v", "high",
            "-level", "4.1",
            "-pix_fmt", "yuv420p",
            "-r", "30",
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
