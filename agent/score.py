from datetime import datetime, timezone
from app.models import Topic, TopicScore

HIGH_INTEREST = {"gta", "gta-vi", "rockstar", "ps5", "xbox", "nintendo", "steam", "free-game", "deal", "fortnite", "call-of-duty"}


def score_topic(topic: Topic, now: datetime | None = None) -> TopicScore:
    now = now or datetime.now(timezone.utc)
    freshness = 5
    if topic.published_at:
        age_hours = max(0, (now - topic.published_at).total_seconds() / 3600)
        if age_hours <= 6:
            freshness = 20
        elif age_hours <= 24:
            freshness = 16
        elif age_hours <= 72:
            freshness = 10
        else:
            freshness = 4

    official = 20 if topic.official_footage_url else 0
    tagset = {t.lower() for t in topic.tags}
    relevance = min(20, 6 + 5 * len(tagset & HIGH_INTEREST))

    lowered = topic.title.lower()
    engagement = 10
    if any(k in lowered for k in ("gratuit", "free", "trailer", "annonce", "sortie", "nouveau", "mise à jour")):
        engagement += 8
    if any(t in tagset for t in ("free-game", "deal")):
        engagement += 4
    engagement = min(20, engagement)

    clarity = 10 if len(topic.title) <= 90 else 6
    novelty = 10
    breakdown = {
        "freshness": freshness,
        "official_footage": official,
        "relevance": relevance,
        "engagement": engagement,
        "clarity": clarity,
        "novelty": novelty,
    }
    return TopicScore(total=sum(breakdown.values()), breakdown=breakdown)
