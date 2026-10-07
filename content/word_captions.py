"""Captions for Reels: short phrases that follow the narration."""

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
Style: Phrase,DejaVu Sans,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,2,2,60,60,400,1
Style: Karaoke,Montserrat ExtraBold,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,1,0,0,0,100,100,0,0,1,7,3,8,50,50,1430,1

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


MAX_PHRASE_WORDS = 4
MAX_PHRASE_CHARS = 24
# A caption that vanishes the instant the last word ends is hard to read.
PHRASE_HOLD_SECONDS = 0.25


def attach_punctuation(spoken_texts: list[str], script: str) -> list[str]:
    """Give each spoken word the punctuation it has in the script.

    The voice service reports bare words ("jeu"), while phrase breaks need the
    script's punctuation ("jeu,"). Words are matched in order; when the two
    sequences disagree the spoken text is kept as it is.
    """
    script_words = script.split()
    if len(script_words) != len(spoken_texts):
        return list(spoken_texts)
    return script_words


def build_phrase_cues(spoken, script: str = "") -> list[WordCue]:
    """Group timed words into short phrases, breaking at punctuation."""
    texts = attach_punctuation([word.text for word in spoken], script) if script else [
        word.text for word in spoken
    ]
    cues: list[WordCue] = []
    current: list[int] = []

    def flush(next_start: float | None) -> None:
        if not current:
            return
        start = spoken[current[0]].start
        end = spoken[current[-1]].end + PHRASE_HOLD_SECONDS
        if next_start is not None:
            end = min(end, next_start)
        cues.append(WordCue(round(start, 3), round(end, 3), " ".join(texts[i] for i in current)))
        current.clear()

    for index, text in enumerate(texts):
        length = sum(len(texts[i]) + 1 for i in current) + len(text)
        if current and (len(current) >= MAX_PHRASE_WORDS or length > MAX_PHRASE_CHARS):
            flush(spoken[index].start)
        current.append(index)
        if text.endswith((".", "!", "?", "…", ",", ";", ":")):
            flush(spoken[index + 1].start if index + 1 < len(spoken) else None)
    flush(None)
    return cues


def cues_to_ass(cues: list[WordCue], style: str = "Word") -> str:
    lines = [
        f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},{style},,0,0,0,,{_escape(cue.text)}"
        for cue in cues
    ]
    return ASS_HEADER + "\n".join(lines) + ("\n" if lines else "")



# Captions in the style of the reference Reels: two or three bold words at a
# time under the footage, the word being spoken picked out in yellow.
KARAOKE_MAX_WORDS = 3
KARAOKE_MAX_CHARS = 20
HIGHLIGHT = r"{\c&H00E5FF&}"
PLAIN = r"{\c&HFFFFFF&}"
POP = r"{\fscx112\fscy112\t(0,110,\fscx100\fscy100)}"


def build_karaoke_ass(spoken, script: str = "") -> str:
    """One caption line per spoken word, with that word highlighted."""
    texts = attach_punctuation([word.text for word in spoken], script) if script else [
        word.text for word in spoken
    ]
    groups: list[list[int]] = []
    current: list[int] = []
    for index, text in enumerate(texts):
        length = sum(len(texts[i]) + 1 for i in current) + len(text)
        if current and (len(current) >= KARAOKE_MAX_WORDS or length > KARAOKE_MAX_CHARS):
            groups.append(current)
            current = []
        current.append(index)
        if text.endswith((".", "!", "?", "…", ",", ";", ":")):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    lines = []
    for group_number, group in enumerate(groups):
        next_group_start = (
            spoken[groups[group_number + 1][0]].start if group_number + 1 < len(groups) else None
        )
        for position, index in enumerate(group):
            start = spoken[index].start
            if position + 1 < len(group):
                end = spoken[group[position + 1]].start
            else:
                end = spoken[index].end + PHRASE_HOLD_SECONDS
                if next_group_start is not None:
                    end = min(end, next_group_start)
            parts = [
                (HIGHLIGHT + _escape(texts[i]) + PLAIN) if i == index else _escape(texts[i])
                for i in group
            ]
            text = (POP if position == 0 else "") + " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(end, start + 0.05))},Karaoke,,0,0,0,,{text}"
            )
    return ASS_HEADER + "\n".join(lines) + ("\n" if lines else "")
