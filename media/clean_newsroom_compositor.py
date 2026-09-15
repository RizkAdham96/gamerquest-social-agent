from __future__ import annotations

from .asset_manifest import VisualAsset
from .media_matcher import BeatAsset


def build_segment_filter(
    asset: VisualAsset,
    *,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Contain source media without stretching, cropping, or recoloring it."""
    if asset.width <= 0 or asset.height <= 0:
        raise ValueError("positive source dimensions are required")
    if width <= 0 or height <= 0:
        raise ValueError("positive output dimensions are required")
    return (
        f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1"
    )


def build_timeline_filter(assignments: list[BeatAsset]) -> str:
    if not assignments:
        raise ValueError("at least one beat assignment is required")
    segments: list[str] = []
    labels: list[str] = []
    for index, assignment in enumerate(assignments):
        duration = round(assignment.beat.end - assignment.beat.start, 3)
        if duration <= 0:
            raise ValueError("beat durations must be positive")
        label = f"segment{index}"
        segments.append(
            f"[{index}:v]{build_segment_filter(assignment.asset)},"
            f"trim=duration={duration},setpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")
    return ";".join(segments) + ";" + "".join(labels) + (
        f"concat=n={len(labels)}:v=1:a=0[outv]"
    )
