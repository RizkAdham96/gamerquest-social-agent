from __future__ import annotations

from dataclasses import dataclass

from app.models import EditorialBeat
from .asset_manifest import VisualAsset


class MediaMatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class BeatAsset:
    beat: EditorialBeat
    asset: VisualAsset


def match_assets(
    beats: list[EditorialBeat],
    assets: list[VisualAsset],
    *,
    expected_game_id: str,
    minimum_confidence: float = 0.8,
) -> list[BeatAsset]:
    eligible = [
        asset
        for asset in assets
        if asset.game_id == expected_game_id
        and not asset.validation_errors(minimum_confidence)
    ]
    eligible.sort(key=lambda asset: (-asset.confidence, asset.url))

    if len({asset.url for asset in eligible}) < 2:
        raise MediaMatchError(
            "At least two matching visual assets are required"
        )
    if not beats:
        raise MediaMatchError("At least one editorial beat is required")

    return [
        BeatAsset(beat=beat, asset=eligible[index % len(eligible)])
        for index, beat in enumerate(beats)
    ]
