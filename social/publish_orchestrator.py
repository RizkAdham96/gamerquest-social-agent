from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OrchestratedPublishResult:
    media_id: str
    container_id: str
    drive_file_id: str|None


class PublishOrchestrator:
    def __init__(self, *, stage, instagram_pipeline, drive_store=None, drive_published_folder_id: str|None=None):
        self.stage=stage; self.instagram_pipeline=instagram_pipeline; self.drive_store=drive_store; self.drive_published_folder_id=drive_published_folder_id
    def publish_reel(self, *, topic_id: str, reel_path: str|Path, caption: str) -> OrchestratedPublishResult:
        reel_path=Path(reel_path)
        staged=self.stage.stage(reel_path)
        try:
            published=self.instagram_pipeline.publish(topic_id=topic_id,media_url=staged.public_url,caption=caption)
            drive_file_id=None
            if self.drive_store:
                uploaded=self.drive_store.upload_file(reel_path,parent_id=self.drive_published_folder_id,mime_type='video/mp4')
                drive_file_id=uploaded.get('id')
            return OrchestratedPublishResult(published.media_id,published.container_id,drive_file_id)
        finally:
            self.stage.cleanup(staged.asset_id)
