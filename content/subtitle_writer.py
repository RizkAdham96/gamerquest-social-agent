from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


def build_subtitle_cues(text: str, duration_seconds: float, max_words: int = 5) -> list[SubtitleCue]:
    words = text.split()
    if not words:
        return []
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if max_words <= 0:
        raise ValueError("max_words must be positive")

    chunks = [words[i:i + max_words] for i in range(0, len(words), max_words)]
    chunk_durations = [duration_seconds * (len(chunk) / len(words)) for chunk in chunks]
    cues: list[SubtitleCue] = []
    cursor = 0.0
    for idx, (chunk, span) in enumerate(zip(chunks, chunk_durations)):
        end = duration_seconds if idx == len(chunks) - 1 else cursor + span
        cues.append(SubtitleCue(round(cursor, 3), round(end, 3), " ".join(chunk)))
        cursor = end
    return cues


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def cues_to_srt(cues: list[SubtitleCue]) -> str:
    blocks = []
    for idx, cue in enumerate(cues, 1):
        blocks.append(
            f"{idx}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{cue.text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")
