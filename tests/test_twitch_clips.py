import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from media.twitch_clips import TwitchClips, load_skip_list, record_used_clips

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def clip(id, name, views, duration=30.0):
    return {"id": id, "url": f"https://clips.twitch.tv/{id}", "broadcaster_name": name,
            "title": "t", "view_count": views, "duration": duration, "language": "fr"}


def fake_api(clips, games=({"id": "123", "name": "Grand Theft Auto VI"},)):
    calls = []

    def request(url, *, headers=None, data=None):
        calls.append(url)
        if url.startswith("https://id.twitch.tv"):
            return {"access_token": "tok"}
        if "/games?" in url:
            return {"data": list(games)}
        if "/clips?" in url:
            return {"data": clips}
        raise AssertionError(url)

    return request, calls


def fake_run(lengths):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if "-o" in command:  # yt-dlp
            Path(command[command.index("-o") + 1]).write_bytes(b"clip")
        else:  # ffmpeg writes its last argument
            Path(command[-1]).write_bytes(b"video")

    return run, commands


def make(clips, lengths=None):
    request, calls = fake_api(clips)
    run, commands = fake_run(lengths)
    probe = lambda path: {"duration": 31.0}
    return TwitchClips("id", "secret", request=request, run=run, probe_fn=probe, game_id=""), calls, commands


def test_top_clips_are_sorted_by_views_for_the_gta6_category():
    twitch, calls, _ = make([clip("a", "A", 10), clip("b", "B", 500)])
    assert [c.id for c in twitch.top_clips(NOW)] == ["b", "a"]
    clips_call = next(url for url in calls if "/clips?" in url)
    assert "game_id=123" in clips_call and "started_at=2026-11-22T12%3A00%3A00Z" in clips_call


def test_montage_skips_used_clips_skipped_streamers_short_clips_and_repeat_streamers(tmp_path):
    twitch, _, commands = make([
        clip("used", "A", 900), clip("blocked", "Nope", 800), clip("short", "C", 700, duration=5),
        clip("b1", "B", 600), clip("b2", "B", 590), clip("d", "D", 500), clip("e", "E", 400),
    ])
    montage = twitch.montage(40.0, tmp_path, now=NOW, skip_ids={"used"}, skip_streamers={"nope"})
    assert [c.id for c in montage.clips] == ["b1", "d"]
    assert montage.credits == ["B", "D"]
    assert montage.path == tmp_path / "trailer.mp4" and montage.path.exists()
    normalise = [c for c in commands if "-an" in c]
    assert len(normalise) == 2


def test_montage_refuses_when_there_is_not_enough_new_footage(tmp_path):
    twitch, _, _ = make([clip("a", "A", 10)])
    with pytest.raises(RuntimeError, match="Twitch clips"):
        twitch.montage(40.0, tmp_path, now=NOW)


def test_missing_category_is_reported():
    request, _ = fake_api([], games=())
    twitch = TwitchClips("id", "secret", request=request, game_id="")
    with pytest.raises(RuntimeError, match="no GTA 6 category"):
        twitch.find_game_id()


def test_used_clips_and_skip_list_files(tmp_path):
    used = tmp_path / "used.json"
    record_used_clips(["a", "b"], used)
    record_used_clips(["b", "c"], used)
    assert json.loads(used.read_text()) == ["a", "b", "c"]
    skip = tmp_path / "skip.json"
    skip.write_text('["SomeStreamer"]')
    assert load_skip_list(skip) == {"somestreamer"}
    assert load_skip_list(tmp_path / "missing.json") == set()
