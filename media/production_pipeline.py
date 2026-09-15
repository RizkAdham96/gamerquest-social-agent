from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models import Topic
from .footage_downloader import FootageDownloader
from .official_footage import OfficialFootageDiscovery
from .reel_pipeline import ReelPipeline


class DriveLike(Protocol):
    def create_folder(self, name: str, parent_id: str | None = None) -> str: ...
    def upload_file(self, file_path: Path, parent_id: str | None = None, mime_type: str | None = None) -> dict: ...


@dataclass(frozen=True)
class ProductionResult:
    source_name: str
    reel_path: Path
    drive_file_id: str | None = None


class ReelProductionPipeline:
    def __init__(
        self,
        *,
        discovery: OfficialFootageDiscovery,
        downloader: FootageDownloader | None = None,
        renderer: ReelPipeline | None = None,
        drive_store: DriveLike | None = None,
        drive_root_folder_id: str | None = None,
    ):
        self.discovery = discovery
        self.downloader = downloader or FootageDownloader()
        self.renderer = renderer or ReelPipeline()
        self.drive_store = drive_store
        self.drive_root_folder_id = drive_root_folder_id

    def produce(
        self,
        *,
        topic: Topic,
        voiceover_text: str,
        output_dir: Path,
        duration_seconds: float,
        background_music: Path | None = None,
    ) -> ProductionResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        candidates = self.discovery.discover(topic)
        if not candidates:
            raise RuntimeError("no official footage candidates found")

        footage_path = None
        selected_source = None
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                footage_path = self.downloader.download(candidate, output_dir)
                selected_source = candidate.source_name
                break
            except (ValueError, RuntimeError, OSError) as exc:
                last_error = exc
                continue
        if footage_path is None or selected_source is None:
            raise RuntimeError("no downloadable official footage found") from last_error

        reel_path = self.renderer.render(
            footage=footage_path,
            voiceover_text=voiceover_text,
            output_dir=output_dir,
            duration_seconds=duration_seconds,
            background_music=background_music,
        )

        drive_file_id: str | None = None
        if self.drive_store:
            parent_id = self.drive_store.create_folder("Published", parent_id=self.drive_root_folder_id)
            upload = self.drive_store.upload_file(reel_path, parent_id=parent_id, mime_type="video/mp4")
            drive_file_id = upload.get("id")

        return ProductionResult(source_name=selected_source, reel_path=reel_path, drive_file_id=drive_file_id)
