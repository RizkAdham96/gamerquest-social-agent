import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.hidden_gems import GameFacts, build_facts, iter_games, load_candidates, select_candidates
from automation.daily_reel import run_once
from content.gem_script import (
    FOLLOW_LINE,
    GemScript,
    ScriptRejected,
    build_caption,
    validate_body,
    write_gem_script,
)
from content.word_captions import build_word_cues, cues_to_ass, total_duration
from media.gem_reel import CLIP_SECONDS, build_command, build_filter_graph, clip_starts

GOOD_BODY = (
    "Dans ce jeu, tu pars à la chasse aux boss dans un monde coloré et déjanté. "
    "Tu enchaînes les armes et les bonus les plus variés pour repousser la corruption du Vide. "
    "Chaque partie est différente, et tu peux même y jouer à deux en coopération."
)


def facts(**overrides):
    values = dict(
        appid=1304680,
        name="Voidigo",
        description="A vividly animated action roguelite focused on boss hunting.",
        genres=["Action"],
        features=["Single-player", "Co-op"],
        price="2,29€",
        review_percent=97,
        review_count=4289,
        trailer_url="https://video.example/trailer.m3u8",
    )
    values.update(overrides)
    return GameFacts(**values)


def steam_details(**overrides):
    data = {
        "type": "game",
        "name": "Voidigo",
        "required_age": 0,
        "short_description": "A vividly animated action roguelite focused on boss hunting, with weapons.",
        "release_date": {"coming_soon": False},
        "content_descriptors": {"ids": [2]},
        "price_overview": {"final_formatted": "2,29€"},
        "genres": [{"description": "Action"}],
        "categories": [{"description": "Co-op"}],
        "movies": [{"hls_h264": "https://video.example/trailer.m3u8"}],
    }
    data.update(overrides)
    return data


CANDIDATE = {"appid": 1304680, "name": "Voidigo", "review_percent": 97, "review_count": 4289}


# --- game selection ---------------------------------------------------------

def test_candidates_are_well_reviewed_but_little_known():
    payload = {
        "1": {"appid": 1, "name": "Loved Small Game", "positive": 1900, "negative": 60},
        "2": {"appid": 2, "name": "Blockbuster", "positive": 900_000, "negative": 20_000},
        "3": {"appid": 3, "name": "Mixed Game", "positive": 800, "negative": 400},
        "4": {"appid": 4, "name": "Tiny Game", "positive": 50, "negative": 1},
        "5": {"appid": 5, "name": "Hentai Puzzle", "positive": 3000, "negative": 10},
    }
    assert [row["name"] for row in select_candidates(payload)] == ["Loved Small Game"]


def test_cached_candidates_are_used_when_steamspy_is_down(tmp_path):
    cache = tmp_path / "gems.json"
    cache.write_text(json.dumps([CANDIDATE]), encoding="utf-8")

    def failing(url):
        raise OSError("steamspy down")

    assert load_candidates(fetch_json=failing, cache_path=cache) == [CANDIDATE]


@pytest.mark.parametrize(
    "override",
    [
        {"type": "dlc"},
        {"required_age": "18"},
        {"content_descriptors": {"ids": [1, 5]}},
        {"release_date": {"coming_soon": True}},
        {"movies": []},
        {"short_description": "Too short."},
        {"price_overview": None},
    ],
)
def test_unsuitable_store_pages_are_rejected(override):
    assert build_facts(CANDIDATE, steam_details(**override)) is None


def test_suitable_game_carries_store_facts():
    built = build_facts(CANDIDATE, steam_details())
    assert built.name == "Voidigo"
    assert built.price == "2,29€"
    assert built.trailer_url.endswith(".m3u8")
    assert built.topic_id == "steam-1304680"


def test_published_games_are_never_picked_again():
    def fetch(url):
        return {"1304680": {"success": True, "data": steam_details()}}

    assert list(iter_games([CANDIDATE], {"steam-1304680"}, seed="d", fetch_json=fetch)) == []
    assert len(list(iter_games([CANDIDATE], set(), seed="d", fetch_json=fetch))) == 1


# --- script -----------------------------------------------------------------

def test_good_body_passes_validation():
    assert validate_body(GOOD_BODY, facts()) == GOOD_BODY


@pytest.mark.parametrize(
    "body, reason",
    [
        ("Trop court.", "words"),
        (GOOD_BODY.replace("coopération.", "coopération pour dix euros seulement."), "forbidden"),
        (GOOD_BODY.replace("à deux", "à 2"), "number"),
        (GOOD_BODY.replace("Dans ce jeu", "Dans Voidigo"), "name"),
        (GOOD_BODY.replace("coopération.", "coopération sur PS5."), "forbidden"),
        (GOOD_BODY.rstrip("."), "complete sentence"),
    ],
)
def test_bad_bodies_are_rejected(body, reason):
    with pytest.raises(ScriptRejected, match=reason):
        validate_body(body, facts())


def test_caption_figures_come_from_store_data():
    caption = build_caption(facts(), today=datetime(2026, 10, 6, tzinfo=timezone.utc))
    assert "Jeu : Voidigo" in caption
    assert "Prix : 2,29€ (prix Steam au 06/10/2026)" in caption
    assert "Avis Steam : 97 % positifs" in caption


def test_script_is_written_then_fact_checked():
    replies = iter([json.dumps({"body": GOOD_BODY}), json.dumps({"valid": True, "unsupported": []})])
    script = write_gem_script(facts(), chat=lambda messages, max_tokens: next(replies))
    assert script.on_screen_text == f"{GOOD_BODY} Le jeu s'appelle Voidigo. {FOLLOW_LINE}"


def test_failed_fact_check_is_retried_then_rejected():
    calls = []

    def chat(messages, max_tokens):
        calls.append(messages[-1]["content"])
        if "Vérifie" in messages[-1]["content"]:
            return json.dumps({"valid": False, "unsupported": ["mode en ligne"]})
        return json.dumps({"body": GOOD_BODY})

    with pytest.raises(ScriptRejected, match="fact-check failed: mode en ligne"):
        write_gem_script(facts(), chat=chat)
    assert len(calls) == 4
    assert "CORRECTION DEMANDÉE" in calls[2]


def test_unusable_model_reply_is_rejected_not_published():
    with pytest.raises(ScriptRejected):
        write_gem_script(facts(), chat=lambda messages, max_tokens: "")


# --- captions ---------------------------------------------------------------

def test_one_cue_per_word_in_order_without_overlap():
    cues = build_word_cues("Dans ce jeu, tu explores. Abonne-toi !")
    assert [cue.text for cue in cues] == ["Dans", "ce", "jeu,", "tu", "explores.", "Abonne-toi", "!"]
    assert all(later.start >= earlier.end for earlier, later in zip(cues, cues[1:]))
    # A sentence end leaves a longer breath than a plain word boundary.
    assert cues[5].start - cues[4].end > cues[1].start - cues[0].end
    assert total_duration(cues) > cues[-1].end


def test_ass_output_is_centred_and_escaped():
    text = cues_to_ass(build_word_cues("Salut {toi}"))
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert ",5,40,40,0,1" in text  # Alignment 5 = middle centre
    assert "(toi)" in text and "{toi}" not in text


# --- render -----------------------------------------------------------------

def test_cuts_avoid_trailer_intro_and_outro():
    starts = clip_starts(trailer_seconds=90.0, reel_seconds=24.0)
    assert len(starts) == 10
    assert starts[0] == 6.0
    assert starts[-1] + CLIP_SECONDS <= 90.0 - 4.0
    assert starts == sorted(starts)


def test_short_trailer_is_refused():
    with pytest.raises(RuntimeError, match="too short"):
        clip_starts(trailer_seconds=18.0, reel_seconds=24.0)


def test_render_command_targets_vertical_h264_with_reference_layout():
    starts = [6.0, 20.0]
    graph = build_filter_graph(starts, has_audio=True)
    assert "crop=1080:1920" in graph and "gblur" in graph
    assert "overlay=0:(H-h)/2" in graph and "ass=captions.ass" in graph
    command = build_command(starts, 24.0, has_audio=True)
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "[aout]" in command


def test_silent_trailer_renders_without_audio_track():
    command = build_command([6.0], 20.0, has_audio=False)
    assert "-an" in command and "[aout]" not in command


# --- orchestration ----------------------------------------------------------

def fake_produce(reject=()):
    def produce(game, output_dir):
        if game.name in reject:
            raise ScriptRejected("fact-check failed")
        script = GemScript(body=GOOD_BODY, on_screen_text=GOOD_BODY, caption="caption")
        return script, SimpleNamespace(path=Path(output_dir) / "reel.mp4", duration_seconds=24.0)

    return produce


class FakeOrchestrator:
    def __init__(self):
        self.published = []

    def publish_reel(self, *, topic_id, reel_path, caption):
        self.published.append(topic_id)
        return SimpleNamespace(media_id="123", container_id="456", drive_file_id=None)


def test_dry_run_never_publishes(tmp_path):
    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=False,
        games=iter([facts()]), produce_fn=fake_produce(),
    )
    assert result.status == "dry-run" and result.game == "Voidigo"


def test_rejected_game_is_skipped_and_the_next_one_published(tmp_path):
    orchestrator = FakeOrchestrator()
    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=True,
        orchestrator=orchestrator,
        games=iter([facts(name="Bad Game", appid=1), facts()]),
        produce_fn=fake_produce(reject={"Bad Game"}),
    )
    assert result.status == "published"
    assert orchestrator.published == ["steam-1304680"]


def test_nothing_is_published_when_every_candidate_fails(tmp_path):
    orchestrator = FakeOrchestrator()
    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=True,
        orchestrator=orchestrator,
        games=iter([facts(name="Bad Game", appid=1)]),
        produce_fn=fake_produce(reject={"Bad Game"}),
    )
    assert result.status == "skipped" and "Bad Game" in result.reason
    assert orchestrator.published == []


def test_only_one_reel_is_published_per_day(tmp_path):
    log = tmp_path / "log.json"
    now = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
    log.write_text(
        json.dumps([{"topic_id": "steam-9", "published_at": "2026-10-06T15:20:00Z"}]),
        encoding="utf-8",
    )
    orchestrator = FakeOrchestrator()
    result = run_once(
        output_dir=tmp_path, publish_log_path=log, live_publish=True,
        orchestrator=orchestrator, games=iter([facts()]), produce_fn=fake_produce(), now=now,
    )
    assert result.status == "skipped" and "already published today" in result.reason
    assert orchestrator.published == []


def test_workflow_runs_the_daily_reel_once_a_day_with_groq():
    workflow = Path(".github/workflows/social-agent.yml").read_text(encoding="utf-8")
    assert "python -m automation.daily_reel" in workflow
    assert "GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}" in workflow
    assert 'cron: "17 15 * * *"' in workflow
