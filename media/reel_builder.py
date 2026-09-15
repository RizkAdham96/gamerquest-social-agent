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
    brand_logo: Path
    output: Path
    duration_seconds: float
    background_music: Path | None = None


class ReelBuilder:
    """Render a color-faithful Clean Newsroom vertical Reel."""

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
            "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,"
            f"subtitles='{subtitle_path}':force_style='{caption_style}'"
        )
        video_filter = (
            f"[0:v]{video_filter}[base];"
            "[2:v]scale=150:-1[logo];"
            "[base][logo]overlay=W-w-48:48:format=auto[vout]"
        )
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(spec.footage),
            "-i",
            str(spec.voiceover),
            "-i",
            str(spec.brand_logo),
        ]
        if spec.background_music:
            cmd += ["-i", str(spec.background_music)]
            audio_filter = (
                "[1:a]volume=1.0[voice];"
                "[3:a]volume=0.10[music];"
                "[voice][music]amix=inputs=2:duration=first:dropout_transition=2,"
                "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
            )
            filter_complex = f"{video_filter};{audio_filter}"
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
        else:
            audio_filter = "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
            filter_complex = f"{video_filter};{audio_filter}"
            cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
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
