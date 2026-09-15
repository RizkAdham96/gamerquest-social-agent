from app.models import Topic
from agent.select import select_best_topic

def test_select_best_topic_requires_official_footage():
    topics = [
        Topic(title='Huge rumor', url='https://rumor.test', source='blog'),
        Topic(title='Free game official', url='https://store.test', source='epic', official_footage_url='https://official.test/video.mp4', tags=['free-game']),
    ]
    selected = select_best_topic(topics, recent_slugs=set())
    assert selected.topic.title == 'Free game official'


def test_select_best_topic_accepts_steam_as_official_footage_signal():
    topics = [
        Topic(title='Steam official', url='https://store.steampowered.com/app/123', source='steam', steam_app_id=123),
    ]
    selected = select_best_topic(topics, recent_slugs=set(), min_score=0)
    assert selected.topic.title == 'Steam official'
