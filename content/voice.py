"""French narration with per-word timings, so captions follow the voice."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICE = "fr-FR-VivienneMultilingualNeural"
# The reference Reels speak at about four words a second.
DEFAULT_RATE = "+18%"
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class SpokenWord:
    start: float
    end: float
    text: str


async def _stream(text: str, output: Path, voice: str, rate: str) -> list[SpokenWord]:
    import edge_tts

    words: list[SpokenWord] = []
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(output, "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append(
                    SpokenWord(start, start + chunk["duration"] / 10_000_000, chunk["text"])
                )
    return words


def synthesize(text: str, output: Path, voice: str | None = None, rate: str | None = None) -> list[SpokenWord]:
    """Write the narration to `output` and return when each word is spoken."""
    voice = voice or os.getenv("GQ_REEL_VOICE", "").strip() or DEFAULT_VOICE
    rate = rate or os.getenv("GQ_REEL_VOICE_RATE", "").strip() or DEFAULT_RATE
    output.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for _attempt in range(MAX_ATTEMPTS):
        try:
            words = asyncio.run(_stream(text, output, voice, rate))
        except Exception as exc:  # the service is remote and occasionally drops
            last_error = exc
            continue
        if words and output.exists() and output.stat().st_size > 10_000:
            return words
        last_error = RuntimeError("the voice service returned no audio")
    raise RuntimeError(f"narration could not be produced: {last_error}")
