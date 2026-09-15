from __future__ import annotations

from dataclasses import dataclass


PLACEHOLDER_URL_MARKERS = (
    "big_buck_bunny",
    "mediaelement-files/master/big_buck_bunny",
)
TEST_COPY_MARKERS = ("dry run", "dry-run", "test reel")


@dataclass(frozen=True)
class ValidationInput:
    width: int
    height: int
    video_codec: str
    audio_codec: str
    duration: float
    has_audio: bool
    audio_publishable: bool
    source_urls: tuple[str, ...]
    narration: str
    distinct_visuals: int
    minimum_relevance_confidence: float
    captions_in_safe_zone: bool
    brand_assets_present: bool


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    failures: tuple[str, ...]


class QualityGateError(RuntimeError):
    def __init__(self, report: QualityReport):
        self.report = report
        super().__init__("; ".join(report.failures))


def validate_preview(value: ValidationInput) -> QualityReport:
    failures: list[str] = []
    joined_urls = " ".join(value.source_urls).lower()
    narration = value.narration.lower()

    if (value.width, value.height) != (1080, 1920):
        failures.append("output is not 1080x1920")
    if value.video_codec.lower() not in {"h264", "avc1"}:
        failures.append("video codec is not H.264")
    if value.audio_codec.lower() != "aac":
        failures.append("audio codec is not AAC")
    if not 15.0 <= value.duration <= 25.0:
        failures.append("duration is outside 15-25 seconds")
    if not value.has_audio:
        failures.append("audio stream is missing")
    if not value.audio_publishable:
        failures.append("narration did not pass the neural audio gate")
    if any(marker in joined_urls for marker in PLACEHOLDER_URL_MARKERS):
        failures.append("placeholder media")
    if any(marker in narration for marker in TEST_COPY_MARKERS):
        failures.append("test narration")
    if value.distinct_visuals < 2:
        failures.append("fewer than two distinct visual segments")
    if value.minimum_relevance_confidence < 0.8:
        failures.append("visual relevance confidence is below 0.8")
    if not value.captions_in_safe_zone:
        failures.append("captions leave the safe zone")
    if not value.brand_assets_present:
        failures.append("real GamerQuest brand assets are missing")

    unique_failures = tuple(dict.fromkeys(failures))
    return QualityReport(
        passed=not unique_failures,
        failures=unique_failures,
    )


def require_quality(value: ValidationInput) -> QualityReport:
    report = validate_preview(value)
    if not report.passed:
        raise QualityGateError(report)
    return report
