from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import urlopen

from app.models import Topic
from .footage_validator import FootageCandidate


def _fetch_json(url: str) -> dict:
    with urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


class SteamTrailerProvider:
    """Best-effort discovery of direct trailer files exposed by a Steam store page."""

    def __init__(self, fetch_json: Callable[[str], dict] = _fetch_json):
        self.fetch_json = fetch_json

    def search(self, app_id: int) -> list[FootageCandidate]:
        url = f"https://store.steampowered.com/api/appdetails?appids={int(app_id)}"
        payload = self.fetch_json(url)
        app = payload.get(str(app_id), {})
        if not app.get("success"):
            return []

        data = app.get("data") or {}
        movies = data.get("movies") or []
        results: list[FootageCandidate] = []

        # Older Steam payloads expose direct MP4 files here.
        for movie in movies:
            mp4 = movie.get("mp4") or {}
            media_url = mp4.get("max") or mp4.get("480")
            if not media_url:
                continue
            results.append(
                FootageCandidate(
                    url=media_url,
                    source_name=f"Steam: {movie.get('name') or 'Official trailer'}",
                    is_official=True,
                )
            )

        # Current Steam payloads may expose only DASH/HLS in movies[] while
        # direct official MP4 gameplay clips remain embedded in the store HTML
        # fragments. Extract those so the Reel downloader still receives a
        # genuine direct media URL that ffmpeg can use.
        html_sources = " ".join(
            str(data.get(key) or "")
            for key in ("about_the_game", "detailed_description")
        )
        direct_mp4_urls = re.findall(
            r'https://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?',
            html_sources,
            flags=re.IGNORECASE,
        )

        for index, media_url in enumerate(direct_mp4_urls, start=1):
            results.append(
                FootageCandidate(
                    url=media_url,
                    source_name=f"Steam official gameplay clip {index}",
                    is_official=True,
                )
            )

        return _dedupe(results)


class YouTubeOfficialSearch:
    """Searches only channel IDs explicitly trusted as publisher/developer channels."""

    def __init__(self, api_key: str, fetch_json: Callable[[str], dict] = _fetch_json):
        self.api_key = api_key
        self.fetch_json = fetch_json

    def search(self, query: str, channel_ids: Iterable[str]) -> list[FootageCandidate]:
        if not self.api_key:
            return []
        results: list[FootageCandidate] = []
        for channel_id in channel_ids:
            channel_id = channel_id.strip()
            if not channel_id:
                continue
            params = urlencode(
                {
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 5,
                    "q": query,
                    "channelId": channel_id,
                    "videoEmbeddable": "true",
                    "key": self.api_key,
                }
            )
            payload = self.fetch_json(f"https://www.googleapis.com/youtube/v3/search?{params}")
            for item in payload.get("items", []):
                video_id = (item.get("id") or {}).get("videoId")
                if not video_id:
                    continue
                channel_title = (item.get("snippet") or {}).get("channelTitle") or channel_id
                results.append(
                    FootageCandidate(
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        source_name=f"YouTube official: {channel_title}",
                        is_official=True,
                    )
                )
        return results


class OfficialFootageDiscovery:
    def __init__(
        self,
        steam: SteamTrailerProvider | None = None,
        youtube: YouTubeOfficialSearch | None = None,
    ):
        self.steam = steam
        self.youtube = youtube

    def discover(self, topic: Topic) -> list[FootageCandidate]:
        results: list[FootageCandidate] = []
        if topic.official_footage_url:
            results.append(
                FootageCandidate(
                    url=topic.official_footage_url,
                    source_name=f"Official source: {topic.publisher or topic.source}",
                    is_official=True,
                )
            )
        if topic.steam_app_id and self.steam:
            results.extend(self.steam.search(topic.steam_app_id))
        if topic.official_channel_ids and self.youtube:
            results.extend(self.youtube.search(f"{topic.title} official trailer", topic.official_channel_ids))
        return _dedupe(results)


def _dedupe(items: list[FootageCandidate]) -> list[FootageCandidate]:
    seen: set[str] = set()
    output: list[FootageCandidate] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        output.append(item)
    return output
