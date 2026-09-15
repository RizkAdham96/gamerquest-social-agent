from media.footage_finder import FootageFinder
from media.footage_validator import FootageCandidate


def test_finder_returns_first_valid_official_candidate():
    candidates = [
        FootageCandidate("https://example.com/fan.mp4", "Fan", False),
        FootageCandidate("https://cdn.publisher.com/official.mp4", "Publisher", True),
    ]
    selected = FootageFinder().select(candidates)
    assert selected is not None
    assert selected.source_name == "Publisher"
