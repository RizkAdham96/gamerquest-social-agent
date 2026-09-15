from __future__ import annotations

import re

from app.models import EditorialBeat, Topic


_ROLES = ("hook", "context", "impact", "close")
_RATIOS = (0.15, 0.30, 0.35, 0.20)


def _sentences(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", value.strip())
        if part.strip()
    ]


def plan_beats(topic: Topic, duration_seconds: float) -> list[EditorialBeat]:
    """Create four factual beats without inventing information."""
    if duration_seconds < 15:
        raise ValueError("Reel duration must be at least 15 seconds")
    if not topic.summary.strip():
        raise ValueError("A verified summary is required")

    facts = _sentences(topic.summary)
    context = facts[0]
    impact = facts[1] if len(facts) > 1 else facts[0]
    narrations = (
        topic.title.rstrip(".") + ".",
        context,
        impact,
        "Retrouve l'article complet sur GamerQuest FR.",
    )

    beats: list[EditorialBeat] = []
    cursor = 0.0
    for index, (role, ratio, narration) in enumerate(
        zip(_ROLES, _RATIOS, narrations)
    ):
        end = (
            duration_seconds
            if index == len(_ROLES) - 1
            else round(cursor + duration_seconds * ratio, 3)
        )
        beats.append(
            EditorialBeat(
                index=index,
                role=role,
                start=cursor,
                end=end,
                narration=narration,
                visual_query=(
                    ""
                    if role == "close"
                    else f"{topic.title} {narration}".strip()
                ),
            )
        )
        cursor = end
    return beats
