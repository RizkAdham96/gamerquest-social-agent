import pytest

from app.models import Topic
from content.beat_planner import plan_beats


def test_plan_has_hook_context_impact_and_close():
    topic = Topic(
        title="Le mode Horde arrive vendredi",
        url="https://gamerquestfr.com/horde",
        source="gamerquest",
        summary=(
            "Le studio confirme le mode Horde vendredi. "
            "Il sera jouable en coopération."
        ),
    )

    beats = plan_beats(topic, 20.0)

    assert [beat.role for beat in beats] == [
        "hook",
        "context",
        "impact",
        "close",
    ]
    assert beats[0].start == 0.0
    assert beats[-1].end == 20.0
    assert all(a.end == b.start for a, b in zip(beats, beats[1:]))
    assert all(beat.visual_query.strip() for beat in beats[:-1])


def test_plan_rejects_missing_verified_summary():
    topic = Topic(
        title="Une rumeur",
        url="https://gamerquestfr.com/rumeur",
        source="gamerquest",
    )

    with pytest.raises(ValueError, match="verified summary"):
        plan_beats(topic, 20.0)


def test_plan_rejects_too_short_duration():
    topic = Topic(
        title="Une annonce",
        url="https://gamerquestfr.com/annonce",
        source="gamerquest",
        summary="Le studio confirme une nouvelle annonce.",
    )

    with pytest.raises(ValueError, match="15"):
        plan_beats(topic, 10.0)
