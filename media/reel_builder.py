from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class ReelBuildSpec:
    footage: Path
    subtitles: Path
    output: Path
    duration_seconds: float
    background_music: Path | None = None


class ReelBuilder:
    """Render a branded, subject-safe GamerQuest vertical Reel."""

    BRAND_LABEL = "GAMERQUEST FR"
    TRAILER_INTRO_SKIP_SECONDS = 7.0

    def build_command(self, spec: ReelBuildSpec) -> list[str]:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subtitle_path = str(spec.subtitles).replace("\\", "/").replace(":", "\\:")
        end_start = max(0.0, spec.duration_seconds - 2.2)

        caption_style = (
            "FontName=DejaVu Sans,"
            "FontSize=20,"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"
            "BackColour=&H78000000,"
            "BorderStyle=3,"
            "Outline=0,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginL=52,"
            "MarginR=52,"
            "MarginV=118,"
            "Spacing=0.4"
        )

        # Force a true full-screen 9:16 Reel. The source keeps its aspect ratio,
        # then center-crops to 1080x1920 so Instagram receives a genuine vertical video.
        video_filter = (
            "[0:v]"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1,"
            "drawbox=x=54:y=90:w=430:h=86:color=black@0.70:t=fill,"
            "drawtext=font='DejaVu Sans':"
            f"text='{self.BRAND_LABEL}':"
            "fontcolor=white:fontsize=34:x=82:y=113,"
            f"subtitles='{subtitle_path}':force_style='{caption_style}',"
            f"drawbox=x=0:y=0:w=1080:h=1920:color=black@0.78:t=fill:enable='gte(t,{end_start:.2f})',"
            f"drawtext=font='DejaVu Sans':text='GAMERQUEST FR':fontcolor=white:fontsize=72:"
            f"x=(w-text_w)/2:y=760:enable='gte(t,{end_start:.2f})',"
            f"drawtext=font='DejaVu Sans':text='L essentiel du gaming, sans perdre ton temps.':"
            f"fontcolor=white:fontsize=34:x=(w-text_w)/2:y=870:enable='gte(t,{end_start:.2f})',"
            f"fade=t=out:st={max(0.0, spec.duration_seconds - 0.35):.2f}:d=0.35[vout]"
        )

        cmd = [ffmpeg, "-y", "-ss", str(self.TRAILER_INTRO_SKIP_SECONDS), "-i", str(spec.footage)]
        if spec.background_music:
            cmd += ["-stream_loop", "-1", "-i", str(spec.background_music)]
            cmd += ["-filter_complex", video_filter, "-map", "[vout]", "-map", "1:a:0"]
        else:
            # No AI narration: keep the official trailer/game audio.
            # The optional map avoids failing on rare silent trailers.
            cmd += ["-filter_complex", video_filter, "-map", "[vout]", "-map", "0:a?"]

        cmd += [
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
