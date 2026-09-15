import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from app.models import Topic

class TopicMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_published(self, topic: Topic, published_at: datetime | None = None):
        published_at = published_at or datetime.now(timezone.utc)
        rows = self._load()
        rows.append({"slug": topic.slug, "topic_id": topic.topic_id, "published_at": published_at.isoformat()})
        self._save(rows)

    def is_duplicate(self, topic: Topic, lookback_days: int = 30) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        for row in self._load():
            when = datetime.fromisoformat(row["published_at"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff and row.get("slug") == topic.slug:
                return True
        return False
