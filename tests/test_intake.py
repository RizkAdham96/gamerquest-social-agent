import json
from agent.discover import load_topics_from_json

def test_load_topics_from_json(tmp_path):
    p = tmp_path / 'topics.json'
    p.write_text(json.dumps([{'title':'Test news','url':'https://example.com','source':'publisher'}]), encoding='utf-8')
    topics = load_topics_from_json(p)
    assert len(topics) == 1
    assert topics[0].slug == 'test-news'


def test_load_topics_preserves_footage_discovery_fields(tmp_path):
    p = tmp_path / 'topics-rich.json'
    p.write_text(json.dumps([{
        'title': 'Rich topic',
        'url': 'https://example.com/rich',
        'source': 'publisher',
        'publisher': 'Studio X',
        'steam_app_id': 123,
        'official_channel_ids': ['UC123'],
        'official_footage_url': None,
        'tags': ['news'],
        'summary': 'A useful summary.'
    }]), encoding='utf-8')
    topic = load_topics_from_json(p)[0]
    assert topic.publisher == 'Studio X'
    assert topic.steam_app_id == 123
    assert topic.official_channel_ids == ['UC123']
