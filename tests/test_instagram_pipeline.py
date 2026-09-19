from datetime import datetime, timezone
import pytest

from social.instagram_pipeline import InstagramPublishPipeline, DuplicatePublishError, WeeklyLimitError
from storage.publish_log import PublishLog


class FakePublisher:
    def __init__(self): self.calls=[]
    def create_reel_container(self, media_url, caption, share_to_feed=True):
        self.calls.append(('create',media_url,caption,share_to_feed)); return 'c123'
    def wait_until_ready(self, container_id, **kwargs):
        self.calls.append(('wait',container_id)); return {'status_code':'FINISHED'}
    def publish_container(self, container_id):
        self.calls.append(('publish',container_id)); return 'm123'


def test_pipeline_publishes_and_records_result(tmp_path):
    publisher=FakePublisher(); log=PublishLog(tmp_path/'log.json')
    pipeline=InstagramPublishPipeline(publisher=publisher,publish_log=log,max_reels_per_week=3)
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    result=pipeline.publish(topic_id='topic-1',media_url='https://cdn/reel.mp4',caption='Salut',now=now)
    assert result.media_id=='m123'
    assert result.container_id=='c123'
    assert log.has_topic('topic-1')
    assert [x[0] for x in publisher.calls]==['create','wait','publish']


def test_pipeline_blocks_duplicate_before_api_calls(tmp_path):
    publisher=FakePublisher(); log=PublishLog(tmp_path/'log.json')
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    log.record(topic_id='topic-1',container_id='c',media_id='m',media_url='u',published_at=now)
    pipeline=InstagramPublishPipeline(publisher=publisher,publish_log=log,max_reels_per_week=3)
    with pytest.raises(DuplicatePublishError):
        pipeline.publish(topic_id='topic-1',media_url='https://cdn/new.mp4',caption='Salut',now=now)
    assert publisher.calls==[]


def test_pipeline_enforces_weekly_cap_before_api_calls(tmp_path):
    publisher=FakePublisher(); log=PublishLog(tmp_path/'log.json')
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    for i in range(3):
        log.record(topic_id=f't{i}',container_id=f'c{i}',media_id=f'm{i}',media_url=f'u{i}',published_at=now)
    pipeline=InstagramPublishPipeline(publisher=publisher,publish_log=log,max_reels_per_week=3)
    with pytest.raises(WeeklyLimitError):
        pipeline.publish(topic_id='fresh',media_url='https://cdn/new.mp4',caption='Salut',now=now)
    assert publisher.calls==[]


def test_pipeline_can_bypass_weekly_cap_for_manual_test(tmp_path):
    publisher=FakePublisher(); log=PublishLog(tmp_path/'log.json')
    now=datetime(2026,9,14,12,0,tzinfo=timezone.utc)
    for i in range(3):
        log.record(topic_id=f't{i}',container_id=f'c{i}',media_id=f'm{i}',media_url=f'u{i}',published_at=now)
    pipeline=InstagramPublishPipeline(
        publisher=publisher,
        publish_log=log,
        max_reels_per_week=3,
        bypass_weekly_limit=True,
    )
    result=pipeline.publish(topic_id='fresh',media_url='https://cdn/new.mp4',caption='Salut',now=now)
    assert result.media_id=='m123'
    assert [x[0] for x in publisher.calls]==['create','wait','publish']
