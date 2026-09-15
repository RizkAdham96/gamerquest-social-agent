from datetime import datetime, timezone, timedelta
from pathlib import Path

from storage.publish_log import PublishLog


def test_publish_log_records_and_blocks_duplicate_topic(tmp_path):
    path=tmp_path/'publish-log.json'
    log=PublishLog(path)
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    log.record(topic_id='topic-1', container_id='c1', media_id='m1', media_url='https://cdn/reel.mp4', published_at=now)
    assert log.has_topic('topic-1') is True
    assert log.has_topic('topic-2') is False
    fresh=PublishLog(path)
    assert fresh.has_topic('topic-1') is True


def test_publish_log_counts_posts_within_last_seven_days(tmp_path):
    path=tmp_path/'publish-log.json'
    log=PublishLog(path)
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    log.record(topic_id='new',container_id='c1',media_id='m1',media_url='u1',published_at=now-timedelta(days=2))
    log.record(topic_id='old',container_id='c2',media_id='m2',media_url='u2',published_at=now-timedelta(days=8))
    assert log.count_since(now-timedelta(days=7)) == 1
