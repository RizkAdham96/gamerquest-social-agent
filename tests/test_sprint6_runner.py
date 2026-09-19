import json
from pathlib import Path
import pytest

from automation.runner import prepare_content, run_once


class FakeProducer:
    def __init__(self, reel_path: Path):
        self.reel_path = reel_path
        self.calls = []

    def produce(self, **kwargs):
        self.calls.append(kwargs)
        return type('ProductionResult', (), {
            'source_name': 'Official source',
            'reel_path': self.reel_path,
            'drive_file_id': None,
        })()


class FakePublisher:
    def __init__(self):
        self.calls = []

    def publish_reel(self, **kwargs):
        self.calls.append(kwargs)
        return type('PublishResult', (), {
            'media_id': 'media-1',
            'container_id': 'container-1',
            'drive_file_id': 'drive-1',
        })()


def _topics_file(tmp_path: Path) -> Path:
    p = tmp_path / 'topics.json'
    p.write_text(json.dumps([
        {
            'title': 'Free game official',
            'url': 'https://example.com/free-game',
            'source': 'publisher',
            'official_footage_url': 'https://cdn.example.com/trailer.mp4',
            'tags': ['free-game'],
            'publisher': 'Example Studio'
        }
    ]), encoding='utf-8')
    return p


def test_prepare_content_builds_selected_topic_script_and_caption(tmp_path):
    prepared = prepare_content(_topics_file(tmp_path), min_score=0)
    assert prepared.topic.title == 'Free game official'
    assert prepared.script.voiceover
    assert 'Free game official' in prepared.caption


def test_prepare_content_refuses_already_published_topic(tmp_path):
    first = prepare_content(_topics_file(tmp_path), min_score=0)
    with pytest.raises(ValueError, match='no eligible topics'):
        prepare_content(
            _topics_file(tmp_path),
            min_score=0,
            published_topic_ids={first.topic.topic_id},
        )


def test_run_once_dry_run_produces_reel_without_publishing(tmp_path):
    reel = tmp_path / 'reel.mp4'
    reel.write_bytes(b'video')
    producer = FakeProducer(reel)
    publisher = FakePublisher()

    result = run_once(
        topics_path=_topics_file(tmp_path),
        output_dir=tmp_path / 'out',
        production_pipeline=producer,
        publish_orchestrator=publisher,
        live_publish=False,
        min_score=0,
    )

    assert result.status == 'dry-run'
    assert result.reel_path == reel
    assert publisher.calls == []


def test_run_once_live_publish_calls_orchestrator(tmp_path):
    reel = tmp_path / 'reel.mp4'
    reel.write_bytes(b'video')
    producer = FakeProducer(reel)
    publisher = FakePublisher()

    result = run_once(
        topics_path=_topics_file(tmp_path),
        output_dir=tmp_path / 'out',
        production_pipeline=producer,
        publish_orchestrator=publisher,
        live_publish=True,
        min_score=0,
    )

    assert result.status == 'published'
    assert result.media_id == 'media-1'
    assert publisher.calls[0]['topic_id']
    assert publisher.calls[0]['reel_path'] == reel
