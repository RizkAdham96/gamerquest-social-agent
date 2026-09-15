from dataclasses import replace

from quality.reel_validator import ValidationInput, validate_preview


def _valid_input():
    return ValidationInput(
        width=1080,
        height=1920,
        video_codec="h264",
        audio_codec="aac",
        duration=20.0,
        has_audio=True,
        audio_publishable=True,
        source_urls=(
            "https://publisher.example/one.mp4",
            "https://publisher.example/two.mp4",
        ),
        narration="Le studio confirme le nouveau mode. Il arrive vendredi.",
        distinct_visuals=2,
        minimum_relevance_confidence=0.91,
        captions_in_safe_zone=True,
        brand_assets_present=True,
    )


def test_big_buck_bunny_and_dry_run_copy_are_blocked():
    bad = replace(
        _valid_input(),
        source_urls=(
            "https://raw.githubusercontent.com/mediaelement/mediaelement-files/master/big_buck_bunny.mp4",
        ),
        narration="GamerQuest dry run",
    )

    report = validate_preview(bad)

    assert not report.passed
    assert "placeholder media" in report.failures
    assert "test narration" in report.failures


def test_valid_preview_requires_two_visual_segments():
    report = validate_preview(replace(_valid_input(), distinct_visuals=1))

    assert report.failures == (
        "fewer than two distinct visual segments",
    )


def test_valid_preview_passes():
    report = validate_preview(_valid_input())

    assert report.passed
    assert report.failures == ()


def test_missing_brand_and_robotic_audio_are_blocked():
    report = validate_preview(
        replace(
            _valid_input(),
            brand_assets_present=False,
            audio_publishable=False,
        )
    )

    assert "real GamerQuest brand assets are missing" in report.failures
    assert "narration did not pass the neural audio gate" in report.failures
