from media.asset_manifest import VisualAsset
from media.clean_newsroom_compositor import build_segment_filter


def _asset(width, height):
    return VisualAsset(
        url="https://cdn.example/clip.mp4",
        source_url="https://publisher.example/news",
        publisher="Publisher",
        game_id="target-game",
        media_type="video",
        confidence=0.99,
        width=width,
        height=height,
        is_official=True,
    )


def test_landscape_media_is_contained_without_color_filter():
    value = build_segment_filter(_asset(1920, 1080))

    assert "force_original_aspect_ratio=decrease" in value
    assert "pad=1080:1920" in value
    assert "eq=" not in value
    assert "hue=" not in value
    assert "crop=1080:1920" not in value


def test_portrait_media_is_never_stretched():
    value = build_segment_filter(_asset(1080, 1920))

    assert "setsar=1" in value
    assert "scale=1080:1920" not in value


def test_invalid_dimensions_are_rejected():
    asset = _asset(0, 1080)

    try:
        build_segment_filter(asset)
    except ValueError as exc:
        assert "dimensions" in str(exc)
    else:
        raise AssertionError("invalid dimensions must fail")
