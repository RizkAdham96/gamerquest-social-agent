import json
from pathlib import Path

from media.asset_manifest import VisualAsset
from quality.preview_package import PreviewFixture, create_preview_package
from quality.reel_validator import QualityReport


def test_package_contains_review_materials(tmp_path: Path):
    source_reel = tmp_path / "source.mp4"
    source_reel.write_bytes(b"video")
    subtitles = tmp_path / "source.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:02,000\nAnnonce\n")
    asset = VisualAsset(
        url="https://cdn.example/one.mp4",
        source_url="https://publisher.example/news",
        publisher="Publisher",
        game_id="target-game",
        media_type="video",
        confidence=0.95,
        width=1920,
        height=1080,
        is_official=True,
    )

    def fake_contact_sheet(_reel, output):
        output.write_bytes(b"jpeg")

    result = create_preview_package(
        tmp_path / "output",
        PreviewFixture(
            reel_path=source_reel,
            subtitles_path=subtitles,
            script="Le studio confirme la date.",
            assets=(asset, asset),
            quality=QualityReport(passed=True, failures=()),
        ),
        contact_sheet_renderer=fake_contact_sheet,
    )

    assert result.reel.exists()
    assert result.contact_sheet.exists()
    review = json.loads(result.review_json.read_text())
    assert review["publish_enabled"] is False
    assert review["quality"]["passed"] is True
    assert len(review["assets"]) == 2
    assert result.assets_json.exists()
