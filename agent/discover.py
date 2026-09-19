import json
import re
from pathlib import Path
from datetime import datetime
from app.models import Topic


def _parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _steam_app_id_from_url(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"store\.steampowered\.com/app/(\d+)", value)
    return int(match.group(1)) if match else None


def _normalize_feed_item(item: dict, generated_at: str | None = None) -> dict:
    """Normalize both native social-agent topics and GamerQuest feed articles."""
    source_value = item.get("source")
    source_url = item.get("source_url")

    if isinstance(source_value, dict):
        source_url = source_url or source_value.get("url")
        source_name = source_value.get("domain") or "GamerQuest FR"
    else:
        source_name = source_value or "GamerQuest FR"

    deal = item.get("deal") or {}
    tags = list(item.get("tags", []))
    if deal:
        tags.append("deal")
        store = str(deal.get("store") or "").strip().lower()
        if store:
            tags.append(store)
        if deal.get("current_price") == 0:
            tags.append("free-game")

    url = (
        item.get("url")
        or item.get("link")
        or source_url
        or (item.get("official_source") or {}).get("url")
    )
    if not url:
        raise ValueError(f"topic is missing a URL: {item.get('title', '<untitled>')}")

    steam_app_id = item.get("steam_app_id")
    if steam_app_id is None:
        steam_app_id = _steam_app_id_from_url(source_url or url)

    return {
        "title": item["title"],
        "url": url,
        "source": source_name,
        "published_at": item.get("published_at") or item.get("created_at") or generated_at,
        "official_footage_url": item.get("official_footage_url"),
        "publisher": item.get("publisher", ""),
        "steam_app_id": steam_app_id,
        "official_channel_ids": list(item.get("official_channel_ids", [])),
        "tags": list(dict.fromkeys(tags)),
        "summary": item.get("summary") or item.get("excerpt") or "",
    }


def load_topics_from_json(path: str | Path) -> list[Topic]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    generated_at = None
    if isinstance(payload, dict) and isinstance(payload.get("articles"), list):
        generated_at = payload.get("generated_at")
        items = payload["articles"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("topics JSON must be a list or a GamerQuest feed with an articles list")

    normalized = [_normalize_feed_item(item, generated_at) for item in items]
    return [
        Topic(
            title=item["title"],
            url=item["url"],
            source=item.get("source", "unknown"),
            published_at=_parse_dt(item.get("published_at")),
            official_footage_url=item.get("official_footage_url"),
            publisher=item.get("publisher", ""),
            steam_app_id=item.get("steam_app_id"),
            official_channel_ids=list(item.get("official_channel_ids", [])),
            tags=list(item.get("tags", [])),
            summary=item.get("summary", ""),
        )
        for item in normalized
    ]
