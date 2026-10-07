"""French narration with per-word timings, so captions follow the voice."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from content.voice_types import SpokenWord

DEFAULT_VOICE = "fr-FR-VivienneMultilingualNeural"
# The reference Reels speak at about four words a second.
DEFAULT_RATE = "+18%"
MAX_ATTEMPTS = 3


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


def edge_synthesize(text: str, output: Path, voice: str | None = None, rate: str | None = None) -> list[SpokenWord]:
    """Free Microsoft neural voice; reports its own word timings."""
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


FISH_TTS_URL = "https://api.fish.audio/v1/tts"
# Free model by default; set GQ_FISH_MODEL to a paid one (e.g. s2.1-pro).
FISH_DEFAULT_MODEL = "s2.1-pro-free"
FISH_DEFAULT_SPEED = 1.12


def _fish_request(text: str, api_key: str, voice_id: str, model: str, speed: float) -> bytes:
    body = {"text": text, "format": "mp3", "prosody": {"speed": speed}}
    if voice_id:
        body["reference_id"] = voice_id
    request = Request(
        FISH_TTS_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "model": model,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Fish Audio HTTP {exc.code}: {detail}") from exc


def fish_synthesize(
    text: str,
    output: Path,
    *,
    request=_fish_request,
    time_words=None,
) -> list[SpokenWord]:
    """Fish Audio voice. It returns audio only, so word timings are recovered
    by listening to the result (content.align)."""
    api_key = os.getenv("FISH_AUDIO_API_KEY", "").strip()
    voice_id = os.getenv("GQ_FISH_VOICE_ID", "").strip()
    model = os.getenv("GQ_FISH_MODEL", "").strip() or FISH_DEFAULT_MODEL
    speed = float(os.getenv("GQ_FISH_SPEED", "").strip() or FISH_DEFAULT_SPEED)
    output.parent.mkdir(parents=True, exist_ok=True)

    last_error: Exception | None = None
    for _attempt in range(MAX_ATTEMPTS):
        try:
            audio = request(text, api_key, voice_id, model, speed)
        except Exception as exc:
            last_error = exc
            continue
        if len(audio) > 10_000:
            output.write_bytes(audio)
            break
        last_error = RuntimeError("Fish Audio returned no audio")
    else:
        raise RuntimeError(f"narration could not be produced: {last_error}")

    if time_words is None:
        from content.align import time_words
    return time_words(text, output)


def synthesize(text: str, output: Path, voice: str | None = None, rate: str | None = None) -> list[SpokenWord]:
    """Write the narration to `output` and return when each word is spoken.

    Fish Audio is used when its key is configured. If it fails, the Reel still
    gets a narration from the free voice rather than being lost for the day.
    """
    if os.getenv("FISH_AUDIO_API_KEY", "").strip() and voice is None:
        try:
            return fish_synthesize(text, output)
        except Exception as exc:
            print(f"Fish Audio unavailable, using the free voice: {exc}")
    return edge_synthesize(text, output, voice, rate)
