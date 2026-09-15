import pytest

from app.models import EditorialBeat
from media.asset_manifest import VisualAsset
from media.media_matcher import MediaMatchError, match_assets


def _beats():
    return [
        EditorialBeat(0, "hook", 0, 3, "Annonce.", "target game"),
        EditorialBeat(1, "context", 3, 8, "Contexte.", "target gameplay"),
        EditorialBeat(2, "impact", 8, 14, "Impact.", "target co-op"),
        EditorialBeat(3, "close", 14, 18, "GamerQuest.", ""),
    ]


def _asset(url, game_id="target-game", confidence=0.95, official=True):
    return VisualAsset(
        url=url,
        source_url="https://publisher.example/news",
        publisher="Publisher",
        game_id=game_id,
        media_type="video",
        confidence=confidence,
        width=1920,
        height=1080,
        is_official=official,
    )


def test_matcher_rejects_wrong_game_and_requires_two_assets():
    wrong = _asset("https://cdn.example/other.mp4", game_id="other-game")

    with pytest.raises(MediaMatchError, match="matching visual assets"):
        match_assets(_beats(), [wrong], expected_game_id="target-game")


def test_matcher_records_two_distinct_relevant_assets():
    assets = [
        _asset("https://cdn.example/one.mp4", confidence=0.90),
        _asset("https://cdn.example/two.mp4", confidence=0.99),
    ]

    assigned = match_assets(_beats(), assets, expected_game_id="target-game")

    assert len({item.asset.url for item in assigned}) >= 2
    assert all(item.asset.confidence >= 0.8 for item in assigned)
    assert assigned[0].asset.url == "https://cdn.example/two.mp4"


@pytest.mark.parametrize(
    "asset",
    [
        _asset("http://cdn.example/not-secure.mp4"),
        _asset("https://cdn.example/low.mp4", confidence=0.5),
        _asset("https://cdn.example/unofficial.mp4", official=False),
    ],
)
def test_matcher_rejects_untrusted_assets(asset):
    with pytest.raises(MediaMatchError):
        match_assets(_beats(), [asset], expected_game_id="target-game")
