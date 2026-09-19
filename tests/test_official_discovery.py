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


def test_steam_provider_accepts_current_hls_manifest():
    payload = {
        "2909400": {
            "success": True,
            "data": {
                "movies": [{
                    "name": "Launch",
                    "hls_h264": "https://video.akamai.steamstatic.com/trailer/master.m3u8",
                    "dash_h264": "https://video.akamai.steamstatic.com/trailer/manifest.mpd",
                }]
            },
        }
    }
    provider = SteamTrailerProvider(fetch_json=lambda url: payload)
    urls = [item.url for item in provider.search(2909400)]
    assert "https://video.akamai.steamstatic.com/trailer/master.m3u8" in urls
    assert "https://video.akamai.steamstatic.com/trailer/manifest.mpd" in urls


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


def test_steam_provider_keeps_hls_and_embedded_mp4_candidates():
    payload = {
        "2369390": {
            "success": True,
            "data": {
                "movies": [
                    {
                        "name": "Launch Trailer",
                        "hls_h264": "https://video.akamai.steamstatic.com/master.m3u8",
                    }
                ],
                "about_the_game": (
                    '<video><source src="https://shared.akamai.steamstatic.com/'
                    'store_item_assets/steam/apps/2369390/extras/gameplay.mp4?t=123" '
                    'type="video/mp4"></video>'
                ),
            },
        }
    }

    provider = SteamTrailerProvider(fetch_json=lambda url: payload)
    results = provider.search(2369390)
    urls = [item.url for item in results]

    assert "https://video.akamai.steamstatic.com/master.m3u8" in urls
    assert "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2369390/extras/gameplay.mp4?t=123" in urls
    assert all(item.is_official for item in results)


def test_steam_provider_finds_nested_direct_video_urls_anywhere_in_payload():
    payload = {
        "2369390": {
            "success": True,
            "data": {
                "movies": [{"name": "Trailer", "hls_h264": "https://video.example/master.m3u8"}],
                "nested": {
                    "blocks": [
                        '<video><source src="https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2369390/extras/a.webm?t=1"></video>',
                        '<source src="https:\\/\\/shared.akamai.steamstatic.com\\/store_item_assets\\/steam\\/apps\\/2369390\\/extras\\/b.mp4?t=2">',
                    ]
                },
            },
        }
    }
    provider = SteamTrailerProvider(fetch_json=lambda url: payload)
    results = provider.search(2369390)
    urls = [item.url for item in results]
    assert "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2369390/extras/a.webm?t=1" in urls
    assert "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2369390/extras/b.mp4?t=2" in urls
