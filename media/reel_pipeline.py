from __future__ import annotations
from pathlib import Path
from typing import Protocol

from content.subtitle_writer import build_subtitle_cues, cues_to_srt
from .reel_builder import ReelBuildSpec, ReelBuilder


class ReelPipeline:
    def __init__(self, builder: ReelBuilder | None = None):
        self.builder = builder or ReelBuilder()

    def render(
        self,
        *,
        footage: Path,
        voiceover_text: str,
        output_dir: Path,
        duration_seconds: float,
        background_music: Path | None = None,
    ) -> Path:
        if not footage.exists():
            raise FileNotFoundError(footage)
        if not voiceover_text.strip():
            raise ValueError("voiceover_text must not be empty")
        output_dir.mkdir(parents=True, exist_ok=True)

        subtitle_path = output_dir / "subtitles.srt"
        reel_path = output_dir / "reel.mp4"

        cues = build_subtitle_cues(voiceover_text, duration_seconds, max_words=4)
        subtitle_path.write_text(cues_to_srt(cues), encoding="utf-8")

        spec = ReelBuildSpec(
            footage=footage,
            subtitles=subtitle_path,
            output=reel_path,
            duration_seconds=duration_seconds,
            background_music=background_music,
        )
        return self.builder.build(spec)
