from app.models import Topic, SelectedTopic
from agent.score import score_topic


def select_best_topic(topics: list[Topic], recent_slugs: set[str], min_score: int = 0) -> SelectedTopic:
    eligible = []
    for topic in topics:
        has_official_footage_signal = bool(topic.official_footage_url or topic.steam_app_id or topic.official_channel_ids)
        if not has_official_footage_signal:
            continue
        if topic.slug in recent_slugs:
            continue
        score = score_topic(topic)
        if score.total >= min_score:
            eligible.append((score.total, topic, score))
    if not eligible:
        raise ValueError("no eligible topics")
    eligible.sort(key=lambda item: item[0], reverse=True)
    _, topic, score = eligible[0]
    return SelectedTopic(topic=topic, score=score)
