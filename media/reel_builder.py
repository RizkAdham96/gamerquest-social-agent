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
    """Render a branded, subject-safe GamerQuest vertical Reel."""

    BRAND_LABEL = "GAMERQUEST FR"

    def build_command(self, spec: ReelBuildSpec) -> list[str]:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subtitle_path = str(spec.subtitles).replace("\\", "/").replace(":", "\\:")
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

        # Preserve the complete source frame in the sharp foreground. A separate
        # blurred background fills 9:16, so landscape gameplay is never stretched
        # or destructively center-cropped.
        video_filter = (
            "[0:v]split=2[vbg][vfg];"
            "[vbg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=28[bg];"
            "[vfg]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,"
            "drawbox=x=54:y=90:w=430:h=86:color=black@0.70:t=fill,"
            "drawtext=font='DejaVu Sans':"
            f"text='{self.BRAND_LABEL}':"
            "fontcolor=white:fontsize=34:x=82:y=113,"
            f"subtitles='{subtitle_path}':force_style='{caption_style}'[vout]"
        )

        cmd = [ffmpeg, "-y", "-ss", str(self.TRAILER_INTRO_SKIP_SECONDS), "-i", str(spec.footage), "-i", str(spec.voiceover)]
        if spec.background_music:
            cmd += ["-i", str(spec.background_music)]
            audio_filter = (
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.10[music];"
                "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            filter_complex = video_filter + ";" + audio_filter
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
        else:
            cmd += ["-filter_complex", video_filter, "-map", "[vout]", "-map", "1:a:0"]

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
