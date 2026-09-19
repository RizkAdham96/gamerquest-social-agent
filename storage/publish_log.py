from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class PublishLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("publish log must contain a JSON list")
        return raw

    def _save(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def has_topic(self, topic_id: str) -> bool:
        return any(record.get("topic_id") == topic_id for record in self._load())

    def topic_ids(self) -> set[str]:
        return {
            str(record["topic_id"])
            for record in self._load()
            if record.get("topic_id")
        }

    def count_since(self, since: datetime) -> int:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        count = 0
        for record in self._load():
            value = record.get("published_at")
            if not value:
                continue
            published = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if published >= since:
                count += 1
        return count

    def record(
        self,
        *,
        topic_id: str,
        container_id: str,
        media_id: str,
        media_url: str,
        published_at: datetime,
    ) -> dict:
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        record = {
            "topic_id": topic_id,
            "container_id": container_id,
            "media_id": media_id,
            "media_url": media_url,
            "published_at": published_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records = self._load()
        records.append(record)
        self._save(records)
        return record
