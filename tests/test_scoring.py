from datetime import datetime, timedelta, timezone
from app.models import Topic
from agent.score import score_topic

def test_score_topic_rewards_fresh_official_relevant_topic():
    topic = Topic(
        title='GTA VI nouveau trailer officiel',
        url='https://www.rockstargames.com/gta6',
        source='rockstar',
        published_at=datetime.now(timezone.utc) - timedelta(hours=2),
        official_footage_url='https://www.youtube.com/watch?v=official',
        tags=['gta', 'rockstar', 'ps5'],
    )
    result = score_topic(topic)
    assert result.total >= 70
    assert result.breakdown['freshness'] >= 15
    assert result.breakdown['official_footage'] == 20
