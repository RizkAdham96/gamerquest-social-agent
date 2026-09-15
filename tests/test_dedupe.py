from datetime import datetime, timezone
from app.models import Topic
from agent.dedupe import TopicMemory

def test_memory_detects_same_slug(tmp_path):
    path = tmp_path / 'memory.json'
    memory = TopicMemory(path)
    first = Topic(title='Steam rend Hades gratuit', url='https://a.test/1', source='steam')
    memory.mark_published(first, published_at=datetime.now(timezone.utc))
    second = Topic(title='Steam rend Hades gratuit!', url='https://b.test/2', source='steam')
    assert memory.is_duplicate(second, lookback_days=30)

def test_memory_allows_unrelated_topic(tmp_path):
    path = tmp_path / 'memory.json'
    memory = TopicMemory(path)
    memory.mark_published(Topic(title='Hades gratuit', url='https://a.test', source='steam'))
    assert not memory.is_duplicate(Topic(title='Nouvelle mise à jour PS5', url='https://b.test', source='sony'), lookback_days=30)
