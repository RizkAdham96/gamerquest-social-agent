from __future__ import annotations
from pathlib import Path
from typing import Protocol

from content.subtitle_writer import build_subtitle_cues, cues_to_srt
from .reel_builder import ReelBuildSpec, ReelBuilder
from .tts import SmartFrenchTTS

DEFAULT_BRAND_LOGO = Path(__file__).resolve().parents[1] / "brand_assets" / "gamerquest-logo.png"


class TTSProvider(Protocol):
    def synthesize(self, text: str, output: Path) -> Path: ...


class ReelPipeline:
    def __init__(self, tts: TTSProvider | None = None, builder: ReelBuilder | None = None):
        self.tts = tts or SmartFrenchTTS()
        self.builder = builder or ReelBuilder()

    def render(
        self,
        *,
        footage: Path,
        voiceover_text: str,
        output_dir: Path,
        duration_seconds: float,
        background_music: Path | None = None,
        brand_logo: Path = DEFAULT_BRAND_LOGO,
    ) -> Path:
        if not footage.exists():
            raise FileNotFoundError(footage)
        if not voiceover_text.strip():
            raise ValueError("voiceover_text must not be empty")
        if not brand_logo.exists():
            raise FileNotFoundError(brand_logo)
        output_dir.mkdir(parents=True, exist_ok=True)

        voice_path = output_dir / "voice.wav"
        subtitle_path = output_dir / "subtitles.srt"
        reel_path = output_dir / "reel.mp4"

        self.tts.synthesize(voiceover_text, voice_path)
        cues = build_subtitle_cues(voiceover_text, duration_seconds, max_words=4)
        subtitle_path.write_text(cues_to_srt(cues), encoding="utf-8")

        spec = ReelBuildSpec(
            footage=footage,
            voiceover=voice_path,
            subtitles=subtitle_path,
            brand_logo=brand_logo,
            output=reel_path,
            duration_seconds=duration_seconds,
            background_music=background_music,
        )
        return self.builder.build(spec)
