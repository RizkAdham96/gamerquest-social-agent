"""One-word-at-a-time captions, the reading rhythm of the reference Reel."""

from __future__ import annotations

from dataclasses import dataclass

# Comfortable silent-reading pace for single flashed words.
BASE_WORD_SECONDS = 0.26
PER_CHARACTER_SECONDS = 0.028
SENTENCE_PAUSE_SECONDS = 0.30
CLAUSE_PAUSE_SECONDS = 0.12

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,DejaVu Sans,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,2,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass(frozen=True)
class WordCue:
    start: float
    end: float
    text: str


def build_word_cues(text: str, lead_in: float = 0.35) -> list[WordCue]:
    """Time each word by its length, with a breath after punctuation."""
    cues: list[WordCue] = []
    cursor = lead_in
    for word in str(text or "").split():
        duration = BASE_WORD_SECONDS + PER_CHARACTER_SECONDS * len(word.strip(".,;:!?…«»\"'"))
        end = cursor + duration
        cues.append(WordCue(round(cursor, 3), round(end, 3), word))
        cursor = end
        if word.endswith((".", "!", "?", "…")):
            cursor += SENTENCE_PAUSE_SECONDS
        elif word.endswith((",", ";", ":")):
            cursor += CLAUSE_PAUSE_SECONDS
    return cues


def total_duration(cues: list[WordCue], tail: float = 0.9) -> float:
    return round(cues[-1].end + tail, 3) if cues else 0.0


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, rest = divmod(centiseconds, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def cues_to_ass(cues: list[WordCue]) -> str:
    lines = [
        f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Word,,0,0,0,,{_escape(cue.text)}"
        for cue in cues
    ]
    return ASS_HEADER + "\n".join(lines) + ("\n" if lines else "")
