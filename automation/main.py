from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.config import Settings
from media.official_footage import OfficialFootageDiscovery, SteamTrailerProvider, YouTubeOfficialSearch
from media.production_pipeline import ReelProductionPipeline
from media.reel_pipeline import ReelPipeline
from social.instagram_pipeline import InstagramPublishPipeline
from social.instagram_publish import InstagramPublisher
from social.publish_orchestrator import PublishOrchestrator
from storage.drive_store import DriveStore, EnvAccessTokenProvider, ServiceAccountTokenProvider
from storage.github_release_stage import GitHubReleaseStage
from storage.publish_log import PublishLog

from .runner import run_once


TRUE_VALUES = {"1", "true", "yes", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def require_preview_mode() -> bool:
    """Keep external publishing disabled during the quality rebuild."""
    if env_flag("GQ_LIVE_PUBLISH", False):
        raise RuntimeError(
            "Instagram publishing is disabled during Clean Newsroom quality work"
        )
    return False


def build_drive_store() -> DriveStore | None:
    service_account_file = os.getenv("GQ_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if service_account_file:
        return DriveStore(ServiceAccountTokenProvider(service_account_file))
    if os.getenv("GQ_GOOGLE_DRIVE_ACCESS_TOKEN", "").strip():
        return DriveStore(EnvAccessTokenProvider())
    return None


def build_production_pipeline() -> ReelProductionPipeline:
    youtube_key = os.getenv("GQ_YOUTUBE_API_KEY", "").strip()
    discovery = OfficialFootageDiscovery(
        steam=SteamTrailerProvider(),
        youtube=YouTubeOfficialSearch(youtube_key) if youtube_key else None,
    )
    return ReelProductionPipeline(
        discovery=discovery,
        renderer=ReelPipeline(),
    )


def build_publish_orchestrator(settings: Settings, publish_log_path: Path) -> PublishOrchestrator:
    github_repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if not github_repository:
        raise RuntimeError("Missing GITHUB_REPOSITORY")
    if not github_token:
        raise RuntimeError("Missing GITHUB_TOKEN")

    publisher = InstagramPublisher(
        ig_user_id=settings.instagram_user_id,
        access_token=settings.instagram_access_token,
        api_version=settings.meta_api_version,
    )
    instagram_pipeline = InstagramPublishPipeline(
        publisher=publisher,
        publish_log=PublishLog(publish_log_path),
        max_reels_per_week=settings.max_reels_per_week,
    )
    return PublishOrchestrator(
        stage=GitHubReleaseStage(repository=github_repository, token=github_token),
        instagram_pipeline=instagram_pipeline,
        drive_store=build_drive_store(),
        drive_published_folder_id=os.getenv("GQ_DRIVE_PUBLISHED_FOLDER_ID", "").strip() or None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GamerQuest Social Agent once")
    parser.add_argument("--topics", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--publish-log", type=Path, default=Path("state/publish_log.json"))
    parser.add_argument("--duration", type=float, default=16.0)
    args = parser.parse_args()

    settings = Settings.from_env()
    live_publish = require_preview_mode()
    orchestrator = None

    result = run_once(
        topics_path=args.topics,
        output_dir=args.output_dir,
        production_pipeline=build_production_pipeline(),
        publish_orchestrator=orchestrator,
        live_publish=live_publish,
        min_score=settings.min_topic_score,
        duration_seconds=args.duration,
        background_music=os.getenv("GQ_BACKGROUND_MUSIC", "").strip() or None,
    )
    print(json.dumps({
        "status": result.status,
        "topic_id": result.topic_id,
        "reel_path": str(result.reel_path),
        "media_id": result.media_id,
        "container_id": result.container_id,
        "drive_file_id": result.drive_file_id,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
