"""Find when each script word is spoken in a narration file.

Edge's voices report word timings themselves. Other voice services return
audio only, so the captions' timing is recovered by listening to the audio
with a small speech recogniser and matching what it heard to the script.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import unicodedata
from pathlib import Path

from content.voice_types import SpokenWord

WHISPER_MODEL = "base"
SAMPLE_RATE = 16_000


def _key(word: str) -> str:
    text = unicodedata.normalize("NFKD", word.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text)


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def hear_words(path: Path, language: str = "fr") -> list[SpokenWord]:
    """Recognised words with their timings."""
    import numpy as np
    from faster_whisper import WhisperModel

    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(audio, language=language, word_timestamps=True)
    return [
        SpokenWord(float(word.start), float(word.end), word.word.strip())
        for segment in segments
        for word in segment.words
    ]


def spread_evenly(script_words: list[str], duration: float) -> list[SpokenWord]:
    """Timing by word length alone: the fallback when nothing can be heard."""
    weights = [len(word) + 2 for word in script_words]
    total = float(sum(weights)) or 1.0
    cursor = 0.0
    spoken = []
    for word, weight in zip(script_words, weights):
        span = duration * weight / total
        spoken.append(SpokenWord(round(cursor, 3), round(cursor + span, 3), word))
        cursor += span
    return spoken


def align_script(script: str, heard: list[SpokenWord], duration: float) -> list[SpokenWord]:
    """Give every script word a time, anchored on the words that were recognised."""
    script_words = script.split()
    if not script_words:
        return []
    if not heard:
        return spread_evenly(script_words, duration)

    # The recogniser splits "c'est" or "abonne-toi" differently from the
    # script, so both sides are compared as runs of bare letters.
    script_keys = [_key(word) for word in script_words]
    heard_keys = [_key(word.text) for word in heard]
    matcher = difflib.SequenceMatcher(a=script_keys, b=heard_keys, autojunk=False)
    starts: list[float | None] = [None] * len(script_words)
    ends: list[float | None] = [None] * len(script_words)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            starts[block.a + offset] = heard[block.b + offset].start
            ends[block.a + offset] = heard[block.b + offset].end

    # Unrecognised words share the gap between their recognised neighbours.
    index = 0
    while index < len(script_words):
        if starts[index] is not None:
            index += 1
            continue
        run_end = index
        while run_end < len(script_words) and starts[run_end] is None:
            run_end += 1
        left = ends[index - 1] if index > 0 else 0.0
        right = starts[run_end] if run_end < len(script_words) else duration
        right = max(right, left)
        step = (right - left) / (run_end - index)
        for position in range(index, run_end):
            starts[position] = left + step * (position - index)
            ends[position] = left + step * (position - index + 1)
        index = run_end

    spoken = []
    previous_end = 0.0
    for word, start, end in zip(script_words, starts, ends):
        start = max(float(start), previous_end)
        end = max(float(end), start + 0.04)
        spoken.append(SpokenWord(round(start, 3), round(end, 3), word))
        previous_end = start
    return spoken


ENDING_WORDS = 6
ENDING_WINDOW = 10


def ending_was_spoken(script: str, heard: list[SpokenWord]) -> bool:
    """True when the script's closing words are among the last things heard.

    A published Reel stopped at "Ce jeu, c'est…": the voice service had cut
    the sentence that names the game. With nothing heard there is nothing to
    judge, so the narration is given the benefit of the doubt.
    """
    if not heard:
        return True
    closing = [key for key in (_key(word) for word in script.split()[-ENDING_WORDS:]) if len(key) >= 2]
    if not closing:
        return True
    last_heard = {_key(word.text) for word in heard[-ENDING_WINDOW:]}
    return sum(key in last_heard for key in closing) >= max(2, len(closing) // 2)


def listen(script: str, audio: Path, hear=hear_words) -> tuple[list[SpokenWord], bool]:
    """Word timings for the captions, and whether the narration reached its end."""
    duration = audio_duration(audio)
    try:
        heard = hear(audio)
    except Exception as exc:  # recogniser missing or failing must not stop the Reel
        print(f"Caption timing: recogniser unavailable ({exc}); spacing words by length.")
        heard = []
    return align_script(script, heard, duration), ending_was_spoken(script, heard)


def time_words(script: str, audio: Path, hear=hear_words) -> list[SpokenWord]:
    return listen(script, audio, hear)[0]
