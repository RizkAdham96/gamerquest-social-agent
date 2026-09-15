from pathlib import Path

from app.models import Topic
from media.footage_validator import FootageCandidate
from media.production_pipeline import ReelProductionPipeline


def test_production_pipeline_downloads_renders_and_archives(tmp_path):
    topic = Topic(title="Example", url="https://gq.test/x", source="GQ")

    class Discovery:
        def discover(self, topic):
            return [
                FootageCandidate("https://www.youtube.com/watch?v=abc", "YouTube official", True),
                FootageCandidate("https://cdn.example.com/trailer.mp4", "Official CDN", True),
            ]

    class Downloader:
        def download(self, candidate, output_dir):
            if "youtube.com" in candidate.url:
                raise ValueError("not direct")
            path = output_dir / "footage.mp4"
            path.write_bytes(b"video")
            return path

    class Renderer:
        def render(self, **kwargs):
            path = kwargs["output_dir"] / "reel.mp4"
            path.write_bytes(b"reel")
            return path

    class Drive:
        def create_folder(self, name, parent_id=None):
            return "published-folder"
        def upload_file(self, file_path, parent_id=None, mime_type=None):
            return {"id": "drive-file", "name": file_path.name}

    pipeline = ReelProductionPipeline(
        discovery=Discovery(), downloader=Downloader(), renderer=Renderer(), drive_store=Drive(), drive_root_folder_id="root"
    )
    result = pipeline.produce(
        topic=topic,
        voiceover_text="Une nouvelle mise à jour arrive.",
        output_dir=tmp_path,
        duration_seconds=12,
    )

    assert result.source_name == "Official CDN"
    assert result.reel_path.name == "reel.mp4"
    assert result.drive_file_id == "drive-file"


def test_production_pipeline_can_run_without_drive(tmp_path):
    topic = Topic(title="Example", url="https://gq.test/x", source="GQ", official_footage_url="https://cdn.example.com/a.mp4")

    class Discovery:
        def discover(self, topic):
            return [FootageCandidate(topic.official_footage_url, "Official", True)]

    class Downloader:
        def download(self, candidate, output_dir):
            p = output_dir / "footage.mp4"
            p.write_bytes(b"video")
            return p

    class Renderer:
        def render(self, **kwargs):
            p = kwargs["output_dir"] / "reel.mp4"
            p.write_bytes(b"reel")
            return p

    pipeline = ReelProductionPipeline(discovery=Discovery(), downloader=Downloader(), renderer=Renderer())
    result = pipeline.produce(topic=topic, voiceover_text="bonjour", output_dir=tmp_path, duration_seconds=10)
    assert result.drive_file_id is None
