from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.discover import load_topics_from_json
from agent.select import select_best_topic
from content.caption_writer import build_caption
from content.script_writer import build_reel_script
from app.models import Topic, ReelScript


@dataclass(frozen=True)
class PreparedContent:
    topic: Topic
    script: ReelScript
    caption: str
    score: int


@dataclass(frozen=True)
class RunResult:
    status: str
    topic_id: str
    reel_path: Path
    media_id: str | None = None
    container_id: str | None = None
    drive_file_id: str | None = None


def prepare_content(topics_path: str | Path, *, min_score: int = 0, recent_slugs: set[str] | None = None) -> PreparedContent:
    selected = select_best_topic(
        load_topics_from_json(topics_path),
        recent_slugs=recent_slugs or set(),
        min_score=min_score,
    )
    script = build_reel_script(selected.topic)
    return PreparedContent(
        topic=selected.topic,
        script=script,
        caption=build_caption(selected.topic),
        score=selected.score.total,
    )


def run_once(
    *,
    topics_path: str | Path,
    output_dir: str | Path,
    production_pipeline,
    publish_orchestrator,
    live_publish: bool,
    min_score: int = 0,
    duration_seconds: float = 16.0,
    background_music: str | Path | None = None,
) -> RunResult:
    prepared = prepare_content(topics_path, min_score=min_score)
    produced = production_pipeline.produce(
        topic=prepared.topic,
        voiceover_text=prepared.script.voiceover,
        output_dir=Path(output_dir),
        duration_seconds=duration_seconds,
        background_music=Path(background_music) if background_music else None,
    )

    if not live_publish:
        return RunResult(
            status="dry-run",
            topic_id=prepared.topic.topic_id,
            reel_path=Path(produced.reel_path),
            drive_file_id=getattr(produced, "drive_file_id", None),
        )

    published = publish_orchestrator.publish_reel(
        topic_id=prepared.topic.topic_id,
        reel_path=produced.reel_path,
        caption=prepared.caption,
    )
    return RunResult(
        status="published",
        topic_id=prepared.topic.topic_id,
        reel_path=Path(produced.reel_path),
        media_id=published.media_id,
        container_id=published.container_id,
        drive_file_id=published.drive_file_id,
    )
