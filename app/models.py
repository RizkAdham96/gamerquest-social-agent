from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
import re
import unicodedata
from typing import Optional


def _slugify(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value

@dataclass
class Topic:
    title: str
    url: str
    source: str
    published_at: Optional[datetime] = None
    official_footage_url: Optional[str] = None
    publisher: str = ""
    steam_app_id: Optional[int] = None
    official_channel_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    slug: str = field(init=False)
    topic_id: str = field(init=False)

    def __post_init__(self):
        self.title = self.title.strip()
        self.slug = _slugify(self.title)
        self.topic_id = sha1(f"{self.slug}|{self.source}".encode("utf-8")).hexdigest()[:16]
        if self.published_at and self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)

@dataclass(frozen=True)
class TopicScore:
    total: int
    breakdown: dict[str, int]

@dataclass(frozen=True)
class SelectedTopic:
    topic: Topic
    score: TopicScore

@dataclass(frozen=True)
class ReelScript:
    language: str
    hook: str
    beats: list[str]
    cta: str
    voiceover: str
