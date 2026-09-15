from media.footage_validator import FootageCandidate, FootageValidator


def test_accepts_https_official_candidate_with_source_label():
    candidate = FootageCandidate(
        url="https://media.playstation.com/trailer.mp4",
        source_name="PlayStation",
        is_official=True,
    )
    result = FootageValidator().validate(candidate)
    assert result.ok is True
    assert result.reason == "official_https_source"


def test_rejects_unofficial_candidate_even_with_https_url():
    candidate = FootageCandidate(
        url="https://youtube.com/randomcreator/video",
        source_name="Random Creator",
        is_official=False,
    )
    result = FootageValidator().validate(candidate)
    assert result.ok is False
    assert result.reason == "source_not_official"
