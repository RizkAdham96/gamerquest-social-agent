import os
from app.config import Settings

def test_settings_load_defaults(monkeypatch):
    monkeypatch.delenv('GQ_MAX_REELS_PER_WEEK', raising=False)
    s = Settings.from_env()
    assert s.max_reels_per_week == 3
    assert s.dedupe_days == 30
    assert s.language == 'fr'

def test_settings_loads_meta_publishing_configuration(monkeypatch):
    monkeypatch.setenv('GQ_META_API_VERSION','v26.0')
    monkeypatch.setenv('GQ_INSTAGRAM_USER_ID','17841400000000000')
    monkeypatch.setenv('GQ_INSTAGRAM_ACCESS_TOKEN','token-value')
    s=Settings.from_env()
    assert s.meta_api_version=='v26.0'
    assert s.instagram_user_id=='17841400000000000'
    assert s.instagram_access_token=='token-value'
