from app.models import Topic

def test_topic_normalizes_slug_and_text():
    topic = Topic(title='  GTA VI : Nouveau trailer !  ', url='https://example.com/x', source='rockstar')
    assert topic.title == 'GTA VI : Nouveau trailer !'
    assert topic.slug == 'gta-vi-nouveau-trailer'
    assert topic.topic_id
