from pathlib import Path

import pytest

from content import voice
from content.align import align_script, ending_was_spoken, spread_evenly
from content.voice_types import SpokenWord


def heard(*words):
    return [SpokenWord(start, start + 0.3, text) for text, start in words]


def test_alignment_follows_recognised_words_and_keeps_script_spelling():
    script = "Dans ce jeu, c'est toi le chasseur."
    result = align_script(
        script,
        heard(("Dans", 0.1), ("ce", 0.4), ("jeu", 0.7), ("c'est", 1.2), ("toi", 1.6), ("le", 1.9), ("chasseur", 2.1)),
        duration=3.0,
    )
    assert [word.text for word in result] == script.split()
    assert [word.start for word in result] == [0.1, 0.4, 0.7, 1.2, 1.6, 1.9, 2.1]


def test_unrecognised_words_are_placed_between_their_neighbours():
    result = align_script(
        "un deux trois quatre",
        heard(("un", 0.0), ("quatre", 3.0)),
        duration=4.0,
    )
    starts = [word.start for word in result]
    assert starts[0] == 0.0 and starts[3] == 3.0
    assert 0.3 <= starts[1] < starts[2] < 3.0


def test_timings_never_run_backwards():
    result = align_script("a b c d", heard(("a", 2.0), ("b", 1.0), ("c", 3.0), ("d", 3.5)), duration=5.0)
    starts = [word.start for word in result]
    assert starts == sorted(starts)


def test_no_recognition_spreads_words_over_the_audio():
    result = align_script("court trèslongmot", [], duration=10.0)
    assert result == spread_evenly(["court", "trèslongmot"], 10.0)
    assert result[0].end - result[0].start < result[1].end - result[1].start
    assert result[-1].end == pytest.approx(10.0)


def test_fish_voice_is_used_when_its_key_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    monkeypatch.setenv("GQ_FISH_VOICE_ID", "voice-123")
    monkeypatch.setenv("GQ_FISH_MODEL", "s2.1-pro")
    monkeypatch.setenv("GQ_FISH_SPEED", "1.2")
    monkeypatch.setenv("GQ_FISH_TEMPO", "1.0")
    sent = {}

    def request(text, api_key, voice_id, model, speed):
        sent.update(text=text, api_key=api_key, voice_id=voice_id, model=model, speed=speed)
        return b"\x00" * 20_000

    output = tmp_path / "voice.mp3"
    words = voice.fish_synthesize(
        "Bonjour toi", output, request=request,
        listen=lambda text, audio: ([SpokenWord(0.0, 0.4, "Bonjour"), SpokenWord(0.4, 0.8, "toi")], True),
    )
    assert sent == {"text": "Bonjour toi", "api_key": "key", "voice_id": "voice-123", "model": "s2.1-pro", "speed": 1.2}
    assert output.stat().st_size == 20_000
    assert [word.text for word in words] == ["Bonjour", "toi"]


def test_fish_failure_falls_back_to_the_free_voice(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    calls = []

    def failing(text, output):
        raise RuntimeError("Fish Audio HTTP 402: insufficient balance")

    def edge(text, output, voice_name, rate):
        calls.append("edge")
        return [SpokenWord(0.0, 0.5, "ok")]

    monkeypatch.setattr(voice, "fish_synthesize", failing)
    monkeypatch.setattr(voice, "edge_synthesize", edge)
    assert voice.synthesize("ok", tmp_path / "v.mp3") == [SpokenWord(0.0, 0.5, "ok")]
    assert calls == ["edge"]


def test_free_voice_is_used_without_a_fish_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.setattr(voice, "fish_synthesize", lambda *a, **k: pytest.fail("Fish must not be called"))
    monkeypatch.setattr(voice, "edge_synthesize", lambda text, output, v, r: [SpokenWord(0.0, 0.5, "ok")])
    assert voice.synthesize("ok", tmp_path / "v.mp3") == [SpokenWord(0.0, 0.5, "ok")]


def test_fish_waits_between_retries_after_a_server_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    monkeypatch.setenv("GQ_FISH_TEMPO", "1.0")
    waits = []
    replies = iter([RuntimeError("Fish Audio HTTP 503"), RuntimeError("Fish Audio HTTP 503"), bytes(20_000)])

    def request(*args):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    words = voice.fish_synthesize(
        "Bonjour", tmp_path / "v.mp3", request=request, sleep=waits.append,
        listen=lambda text, audio: ([SpokenWord(0.0, 0.4, "Bonjour")], True),
    )
    assert waits == [15.0, 30.0]
    assert [word.text for word in words] == ["Bonjour"]


def test_fish_narration_is_slowed_before_captions_are_timed(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    monkeypatch.setenv("GQ_FISH_TEMPO", "0.9")
    order = []
    monkeypatch.setattr(voice, "slow_down", lambda audio, tempo: order.append(("tempo", tempo)))

    def listen(text, audio):
        order.append(("timing", None))
        return [SpokenWord(0.0, 0.4, "Bonjour")], True

    voice.fish_synthesize(
        "Bonjour", tmp_path / "v.mp3", request=lambda *args: bytes(20_000), listen=listen,
    )
    assert order == [("tempo", 0.9), ("timing", None)]


def test_tempo_of_one_leaves_the_audio_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    monkeypatch.setenv("GQ_FISH_TEMPO", "1.0")
    monkeypatch.setattr(voice, "slow_down", lambda audio, tempo: pytest.fail("no stretch expected"))
    voice.fish_synthesize(
        "Bonjour", tmp_path / "v.mp3", request=lambda *args: bytes(20_000),
        listen=lambda text, audio: ([SpokenWord(0.0, 0.4, "Bonjour")], True),
    )


CLOSING = "Ce jeu, c'est Grunn, et il est dispo sur PC, sur Steam."


def test_narration_that_stops_before_the_game_name_is_detected():
    cut_short = heard(("pour", 27.0), ("ne", 27.3), ("rien", 27.6), ("manquer", 28.0), ("Ce", 29.5), ("jeu", 29.8), ("c'est", 30.2))
    assert ending_was_spoken(CLOSING, cut_short) is False
    complete = cut_short + heard(("Grune", 30.8), ("et", 31.2), ("il", 31.4), ("est", 31.6), ("dispo", 31.9), ("sur", 32.3), ("PC", 32.6), ("sur", 33.0), ("Steam", 33.3))
    assert ending_was_spoken(CLOSING, complete) is True


def test_unheard_narration_is_not_condemned():
    assert ending_was_spoken(CLOSING, []) is True


def test_fish_is_asked_again_when_the_narration_is_cut_short(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    monkeypatch.setenv("GQ_FISH_TEMPO", "1.0")
    verdicts = iter([False, True])
    requests = []

    def request(*args):
        requests.append(1)
        return bytes(20_000)

    words = voice.fish_synthesize(
        CLOSING, tmp_path / "v.mp3", request=request, sleep=lambda seconds: None,
        listen=lambda text, audio: ([SpokenWord(0.0, 0.4, "Ce")], next(verdicts)),
    )
    assert len(requests) == 2
    assert [word.text for word in words] == ["Ce"]


def test_fish_that_keeps_cutting_the_ending_gives_way_to_the_free_voice(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "key")
    monkeypatch.setenv("GQ_FISH_TEMPO", "1.0")
    monkeypatch.setattr(voice, "_fish_request", lambda *args: bytes(20_000))
    monkeypatch.setattr(voice, "FISH_RETRY_WAIT_SECONDS", 0.0)
    monkeypatch.setattr("content.align.listen", lambda text, audio: ([SpokenWord(0.0, 0.4, "Ce")], False))
    monkeypatch.setattr(voice, "edge_synthesize", lambda text, output, v, r: [SpokenWord(0.0, 0.5, "complet")])
    assert voice.synthesize(CLOSING, tmp_path / "v.mp3") == [SpokenWord(0.0, 0.5, "complet")]
