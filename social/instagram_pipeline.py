from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from storage.publish_log import PublishLog


class DuplicatePublishError(RuntimeError):
    pass


class WeeklyLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishResult:
    topic_id: str
    container_id: str
    media_id: str
    media_url: str
    published_at: datetime


class InstagramPublishPipeline:
    def __init__(
        self,
        *,
        publisher,
        publish_log: PublishLog,
        max_reels_per_week: int = 3,
        bypass_weekly_limit: bool = False,
    ):
        if max_reels_per_week < 1:
            raise ValueError("max_reels_per_week must be >= 1")
        self.publisher = publisher
        self.publish_log = publish_log
        self.max_reels_per_week = max_reels_per_week
        self.bypass_weekly_limit = bypass_weekly_limit

    def publish(
        self,
        *,
        topic_id: str,
        media_url: str,
        caption: str,
        now: datetime | None = None,
        share_to_feed: bool = True,
    ) -> PublishResult:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if self.publish_log.has_topic(topic_id):
            raise DuplicatePublishError(f"topic {topic_id} has already been published")

        if (
            not self.bypass_weekly_limit
            and self.publish_log.count_since(now - timedelta(days=7)) >= self.max_reels_per_week
        ):
            raise WeeklyLimitError(f"weekly Reel limit of {self.max_reels_per_week} reached")

        container_id = self.publisher.create_reel_container(
            media_url,
            caption,
            share_to_feed=share_to_feed,
        )
        self.publisher.wait_until_ready(container_id)
        media_id = self.publisher.publish_container(container_id)
        self.publish_log.record(
            topic_id=topic_id,
            container_id=container_id,
            media_id=media_id,
            media_url=media_url,
            published_at=now,
        )
        return PublishResult(
            topic_id=topic_id,
            container_id=container_id,
            media_id=media_id,
            media_url=media_url,
            published_at=now,
        )
