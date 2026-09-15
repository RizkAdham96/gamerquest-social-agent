from content.subtitle_writer import build_subtitle_cues, cues_to_srt


def test_subtitle_cues_cover_full_duration_without_overlap():
    cues = build_subtitle_cues(
        "Voici une grande annonce gaming qui arrive cette semaine pour tous les joueurs français.",
        duration_seconds=8.0,
        max_words=4,
    )
    assert cues[0].start == 0.0
    assert cues[-1].end == 8.0
    assert all(a.end <= b.start for a, b in zip(cues, cues[1:]))
    assert all(len(cue.text.split()) <= 4 for cue in cues)


def test_srt_contains_numbered_cues_and_timestamp():
    cues = build_subtitle_cues("Une annonce importante arrive maintenant", 4.0, max_words=3)
    srt = cues_to_srt(cues)
    assert "1\n00:00:00,000 -->" in srt
    assert "Une annonce importante" in srt
