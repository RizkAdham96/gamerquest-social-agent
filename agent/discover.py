import json
from pathlib import Path
from datetime import datetime
from app.models import Topic


def _parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_topics_from_json(path: str | Path) -> list[Topic]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("topics JSON must be a list")
    return [Topic(
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
    ) for item in payload]
