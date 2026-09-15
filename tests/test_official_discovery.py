from app.models import Topic
from media.official_footage import OfficialFootageDiscovery, SteamTrailerProvider, YouTubeOfficialSearch


def test_steam_provider_extracts_direct_official_trailer_urls():
    payload = {
        "123": {
            "success": True,
            "data": {
                "movies": [
                    {"name": "Launch Trailer", "mp4": {"max": "https://cdn.akamai.steamstatic.com/trailer.mp4"}}
                ]
            },
        }
    }
    provider = SteamTrailerProvider(fetch_json=lambda url: payload)
    results = provider.search(123)
    assert results[0].url == "https://cdn.akamai.steamstatic.com/trailer.mp4"
    assert results[0].is_official is True
    assert results[0].source_name == "Steam: Launch Trailer"


def test_youtube_search_only_queries_configured_official_channel():
    captured = {}
    def fake_fetch(url):
        captured["url"] = url
        return {"items": [{"id": {"videoId": "abc"}, "snippet": {"channelTitle": "Official Studio"}}]}

    provider = YouTubeOfficialSearch(api_key="key", fetch_json=fake_fetch)
    results = provider.search("Example Game trailer", ["UC-official"])
    assert "channelId=UC-official" in captured["url"]
    assert results[0].is_official is True
    assert results[0].url == "https://www.youtube.com/watch?v=abc"


def test_discovery_prefers_explicit_then_steam_then_youtube():
    topic = Topic(
        title="Example Game",
        url="https://example.com/news",
        source="GQ",
        official_footage_url="https://publisher.example/trailer.mp4",
        steam_app_id=123,
        official_channel_ids=["UC1"],
    )
    discovery = OfficialFootageDiscovery()
    result = discovery.discover(topic)
    assert result[0].url == "https://publisher.example/trailer.mp4"
