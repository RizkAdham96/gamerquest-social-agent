from app.models import Topic
from content.script_writer import build_reel_script
from content.caption_writer import build_caption

def test_script_is_short_french_and_has_cta():
    topic = Topic(title='Hades est gratuit pendant 48 heures', url='https://example.com', source='epic', tags=['free-game'])
    script = build_reel_script(topic)
    assert script.language == 'fr'
    assert 3 <= len(script.beats) <= 5
    assert script.hook
    assert script.cta.endswith('?')
    assert len(script.voiceover) <= 420

def test_caption_has_single_clear_cta():
    topic = Topic(title='Hades est gratuit pendant 48 heures', url='https://example.com', source='epic', tags=['free-game'])
    caption = build_caption(topic)
    assert 'GamerQuestFR' in caption
    assert '?' in caption
    assert len(caption) < 500
