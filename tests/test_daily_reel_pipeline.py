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
from content.voice_types import SpokenWord
from content.word_captions import (
    build_karaoke_ass,
    build_phrase_cues,
    build_word_cues,
    cues_to_ass,
    total_duration,
)
from media.gem_reel import (
    CLIP_PATTERN,
    CLIP_SECONDS,
    plan_clips,
    TrailerLook,
    build_command,
    build_filter_graph,
    check_trailer_look,
    clip_starts,
)

GOOD_BODY = (
    "Dans ce jeu, c'est pas toi qui fuis les boss, c'est toi qui les traques. "
    "Tu débarques dans un monde coloré et déjanté, corrompu par le Vide, et ta mission est simple : "
    "retrouver chaque boss, le faire sortir de sa cachette et l'éliminer. "
    "Sauf que les boss ne restent pas plantés là à t'attendre. Ils se baladent, ils fuient, "
    "et ils reviennent quand tu t'y attends le moins. "
    "Pour t'en sortir, tu mélanges des armes à distance et de mêlée avec des bonus qui changent tout. "
    "Et franchement, le concept est malin : ici, le chasseur, c'est toi. "
    "Tu enchaînes les combats, tu esquives, tu étourdis tes ennemis et tu repars à la chasse. "
    "En plus, tu peux même y jouer à deux en coopération."
)
assert 90 <= len(GOOD_BODY.split()) <= 130


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


def store_and_tags(tags):
    def fetch(url):
        if "steamspy.com" in url:
            return {"tags": {tag: 100 for tag in tags}}
        return {"1304680": {"success": True, "data": steam_details()}}

    return fetch


def test_text_based_games_and_software_are_skipped_by_tag():
    assert list(iter_games([CANDIDATE], set(), seed="d", fetch_json=store_and_tags(["Visual Novel"]))) == []
    assert list(iter_games([CANDIDATE], set(), seed="d", fetch_json=store_and_tags(["Software"]))) == []
    kept = list(iter_games([CANDIDATE], set(), seed="d", fetch_json=store_and_tags(["Roguelike"])))
    assert [game.name for game in kept] == ["Voidigo"]


def test_tag_lookup_outage_does_not_stop_the_run():
    def fetch(url):
        if "steamspy.com" in url:
            raise OSError("steamspy down")
        return {"1304680": {"success": True, "data": steam_details()}}

    assert len(list(iter_games([CANDIDATE], set(), seed="d", fetch_json=fetch))) == 1


def test_software_sold_on_steam_is_not_a_game():
    software = steam_details(genres=[{"description": "Indie"}, {"description": "Design & Illustration"}])
    assert build_facts(CANDIDATE, software) is None


def test_published_games_are_never_picked_again():
    def fetch(url):
        if "steamspy.com" in url:
            return {"tags": {}}
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


def test_forbidden_terms_match_whole_words_only():
    steampunk = GOOD_BODY.replace("coloré et déjanté", "steampunk et déjanté")
    assert validate_body(steampunk, facts()) == steampunk
    with pytest.raises(ScriptRejected, match="steam"):
        validate_body(GOOD_BODY.replace("coloré et déjanté", "disponible sur Steam"), facts())


def test_writer_reasons_harder_than_the_checker():
    efforts = []

    def chat(messages, max_tokens, reasoning):
        efforts.append(reasoning)
        if "Vérifie" in messages[-1]["content"]:
            return json.dumps({"valid": True, "unsupported": [], "language_errors": []})
        return json.dumps({"body": GOOD_BODY})

    write_gem_script(facts(), chat=chat)
    assert efforts == ["medium", "low"]


def test_caption_figures_come_from_store_data():
    caption = build_caption(facts(), today=datetime(2026, 10, 6, tzinfo=timezone.utc))
    assert "Jeu : Voidigo" in caption
    assert "Prix : 2,29€ (prix Steam au 06/10/2026)" in caption
    assert "Avis Steam : 97 % positifs" in caption


def test_script_is_written_then_fact_checked():
    replies = iter([json.dumps({"body": GOOD_BODY}), json.dumps({"valid": True, "unsupported": []})])
    script = write_gem_script(facts(), chat=lambda messages, **options: next(replies))
    assert script.on_screen_text == (
        f"{GOOD_BODY} {FOLLOW_LINE} Ce jeu, c'est Voidigo, et il est dispo sur PC, sur Steam."
    )


def test_failed_fact_check_is_retried_then_rejected():
    calls = []

    def chat(messages, **options):
        calls.append(messages[-1]["content"])
        if "Vérifie" in messages[-1]["content"]:
            return json.dumps({"valid": False, "unsupported": ["mode en ligne"]})
        return json.dumps({"body": GOOD_BODY})

    with pytest.raises(ScriptRejected, match="fact-check failed: mode en ligne"):
        write_gem_script(facts(), chat=chat)
    assert len(calls) == 6
    assert "CORRECTION DEMANDÉE" in calls[2]


def test_unusable_model_reply_is_rejected_not_published():
    with pytest.raises(ScriptRejected):
        write_gem_script(facts(), chat=lambda messages, **options: "")


def groq_reply(content):
    return {"choices": [{"message": {"content": content}}]}


def http_error(code, body):
    from io import BytesIO
    from urllib.error import HTTPError

    return HTTPError("https://api.groq.com", code, "error", {}, BytesIO(body.encode("utf-8")))


def test_groq_call_leaves_room_for_the_answer_after_reasoning():
    from content.gem_script import WRITER_MAX_TOKENS, groq_chat

    sent = {}

    def post(payload, api_key):
        sent.update(payload)
        return groq_reply('{"body": "x"}')

    assert groq_chat([], max_tokens=WRITER_MAX_TOKENS, api_key="k", post=post) == '{"body": "x"}'
    assert sent["reasoning_effort"] == "low"
    assert sent["max_tokens"] >= 4000


def test_empty_model_reply_is_a_rejected_draft_not_a_crash():
    from content.gem_script import groq_chat

    def post(payload, api_key):
        raise http_error(400, '{"error":{"code":"json_validate_failed","failed_generation":""}}')

    with pytest.raises(ScriptRejected, match="json_validate_failed"):
        groq_chat([], max_tokens=10, api_key="k", post=post)


def test_unsupported_reasoning_option_is_dropped_and_the_call_repeated():
    from content.gem_script import groq_chat

    payloads = []

    def post(payload, api_key):
        payloads.append(dict(payload))
        if "reasoning_effort" in payload:
            raise http_error(400, '{"error":{"message":"reasoning_effort is not supported"}}')
        return groq_reply('{"body": "x"}')

    assert groq_chat([], max_tokens=10, api_key="k", post=post) == '{"body": "x"}'
    assert len(payloads) == 2 and "reasoning_effort" not in payloads[1]


def test_per_minute_rate_limit_waits_and_retries():
    from content.gem_script import groq_chat

    waits = []
    replies = iter([
        http_error(429, "Rate limit reached on tokens per minute (TPM). Please try again in 3.9225s."),
        groq_reply('{"body": "x"}'),
    ])

    def post(payload, api_key):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    assert groq_chat([], max_tokens=10, api_key="k", post=post, sleep=waits.append) == '{"body": "x"}'
    assert waits == [pytest.approx(5.9225)]


def test_daily_rate_limit_is_not_waited_out():
    from content.gem_script import groq_chat

    waits = []

    def post(payload, api_key):
        raise http_error(429, "Rate limit reached on tokens per day (TPD).")

    with pytest.raises(RuntimeError, match="HTTP 429"):
        groq_chat([], max_tokens=10, api_key="k", post=post, sleep=waits.append)
    assert waits == []


def test_groq_outage_is_reported_as_a_run_error():
    from content.gem_script import groq_chat

    def post(payload, api_key):
        raise http_error(503, "unavailable")

    with pytest.raises(RuntimeError, match="HTTP 503"):
        groq_chat([], max_tokens=10, api_key="k", post=post)


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


def spoken(text, step=0.4):
    return [
        SpokenWord(index * step, index * step + step - 0.05, word.strip(".,!?"))
        for index, word in enumerate(text.split())
    ]


def test_phrases_follow_the_voice_and_break_at_punctuation():
    script = "Dans ce jeu, tu pars à la chasse aux boss. Abonne-toi !"
    cues = build_phrase_cues(spoken(script), script)
    assert [cue.text for cue in cues] == [
        "Dans ce jeu,", "tu pars à la", "chasse aux boss.", "Abonne-toi !",
    ]
    assert cues[1].start == pytest.approx(1.2)
    assert all(later.start >= earlier.end for earlier, later in zip(cues, cues[1:]))
    assert all(len(cue.text.split()) <= 4 for cue in cues)


def test_phrase_captions_use_the_bottom_style():
    script = "Dans ce jeu, tu explores."
    text = cues_to_ass(build_phrase_cues(spoken(script), script), style="Phrase")
    assert ",Phrase,,0,0,0,,Dans ce jeu," in text


def test_karaoke_captions_highlight_the_word_being_spoken():
    script = "Dans ce jeu, tu traques les boss."
    text = build_karaoke_ass(spoken(script), script)
    lines = [line for line in text.splitlines() if line.startswith("Dialogue:")]
    # One line per spoken word, each showing its short phrase.
    assert len(lines) == len(script.split())
    assert lines[0].endswith(r"{\c&H00E5FF&}Dans{\c&HFFFFFF&} ce jeu,")
    assert lines[1].endswith(r"Dans {\c&H00E5FF&}ce{\c&HFFFFFF&} jeu,")
    assert lines[3].split(",,")[-1].count(" ") <= 2
    assert all(",Karaoke," in line for line in lines)


def test_clips_vary_in_length_and_cover_the_reel():
    clips = plan_clips(trailer_seconds=95.0, reel_seconds=36.0)
    durations = [duration for _start, duration in clips]
    assert sum(durations) >= 36.0
    assert len(set(durations)) > 1 and set(durations) <= set(CLIP_PATTERN)
    starts = [start for start, _duration in clips]
    assert starts == sorted(starts) and starts[0] == 6.0
    assert starts[-1] + durations[-1] <= 95.0 - 4.0
    graph = build_filter_graph(clips, has_audio=False)
    assert f"trim=start={starts[1]}:duration={durations[1]}" in graph


def test_cuts_are_moved_off_logo_and_black_moments():
    from media.gem_reel import avoid_dull_moments

    clips = [(6.0, 2.0), (20.0, 3.0), (40.0, 2.4)]
    dull = {20, 21, 22}
    moved = avoid_dull_moments(clips, dull, trailer_seconds=90.0)
    assert moved[0] == (6.0, 2.0) and moved[2] == (40.0, 2.4)
    start, duration = moved[1]
    assert not any(second in dull for second in range(int(start), int(start + duration) + 1))
    assert abs(start - 20.0) <= 8.0


def test_cut_stays_put_when_no_clean_footage_is_near():
    from media.gem_reel import avoid_dull_moments

    dull = set(range(0, 60))
    assert avoid_dull_moments([(20.0, 3.0)], dull, trailer_seconds=90.0) == [(20.0, 3.0)]


def test_verdicts_on_the_game_are_rejected():
    body = GOOD_BODY.replace(
        "le concept est malin : ici, le chasseur, c'est toi.",
        "ça te tient en haleine du début à la fin.",
    )
    with pytest.raises(ScriptRejected, match="forbidden"):
        validate_body(body, facts())


def test_script_prompt_asks_for_a_hook_first_spoken_script():
    from content.gem_script import build_checker_messages, build_writer_messages

    writer = build_writer_messages(facts())[-1]["content"]
    assert "accroche" in writer and "tournures parlées" in writer
    assert "Entre 90 et 130 mots" in writer
    assert "registre oral est voulu" in build_checker_messages(facts(), GOOD_BODY)[-1]["content"]


def test_narrated_reel_mixes_voice_over_quiet_game_audio():
    graph = build_filter_graph([6.0, 20.0], has_audio=True, has_voice=True)
    assert "volume=0.14[game]" in graph and "[voice][game]amix" in graph
    command = build_command([6.0, 20.0], 24.0, has_audio=True, has_voice=True)
    assert command.count("-i") == 2 and "voice.mp3" in command


def test_narration_still_plays_over_a_silent_trailer():
    graph = build_filter_graph([6.0], has_audio=False, has_voice=True)
    assert "[1:a]" in graph and graph.endswith("[aout]")
    assert "-an" not in build_command([6.0], 20.0, has_audio=False, has_voice=True)


def test_produce_narrates_and_times_the_reel_from_the_voice(tmp_path):
    from automation.daily_reel import produce

    script = GemScript(body=GOOD_BODY, on_screen_text=GOOD_BODY, caption="caption")
    captured = {}

    def speak(text, path):
        path.write_bytes(b"voice")
        return spoken(text)

    def render(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(path=tmp_path / "reel.mp4", duration_seconds=kwargs["reel_seconds"])

    _, rendered = produce(
        facts(), tmp_path, write_script=lambda game: script, speak=speak,
        fetch_trailer=lambda url, out: tmp_path / "trailer.mp4", render=render,
        inspect_trailer=lambda trailer: None,
    )
    words = len(GOOD_BODY.split())
    assert rendered.duration_seconds == pytest.approx((words - 1) * 0.4 + 0.35 + 0.8)
    assert captured["voice"] == tmp_path / "voice.mp3"
    assert ",Karaoke," in captured["captions_ass"]


def test_failed_narration_stops_the_reel(tmp_path):
    from automation.daily_reel import produce

    script = GemScript(body=GOOD_BODY, on_screen_text=GOOD_BODY, caption="caption")

    def speak(text, path):
        raise RuntimeError("narration could not be produced")

    with pytest.raises(RuntimeError, match="narration"):
        produce(
            facts(), tmp_path, write_script=lambda game: script, speak=speak,
            fetch_trailer=lambda url, out: tmp_path / "trailer.mp4",
            inspect_trailer=lambda trailer: None,
        )


def test_unusable_trailer_rules_the_game_out_before_any_script_is_written(tmp_path):
    from automation.daily_reel import produce

    def refuse(trailer):
        raise RuntimeError("the trailer is too dark for a Reel")

    def write_script(game):
        raise AssertionError("no AI call expected for a refused trailer")

    with pytest.raises(RuntimeError, match="too dark"):
        produce(
            facts(), tmp_path, write_script=write_script,
            fetch_trailer=lambda url, out: tmp_path / "trailer.mp4",
            inspect_trailer=refuse,
        )


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
    assert "overlay=0:150" in graph and "ass=captions.ass" in graph
    command = build_command(starts, 24.0, has_audio=True)
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "[aout]" in command


def test_silent_trailer_renders_without_audio_track():
    command = build_command([6.0], 20.0, has_audio=False)
    assert "-an" in command and "[aout]" not in command


def test_bright_full_frame_trailer_is_accepted():
    check_trailer_look(TrailerLook("1920:1080:0:0", 1920, 1080, 84.7))


@pytest.mark.parametrize(
    "look, reason",
    [
        (TrailerLook("1280:336:0:192", 1280, 336, 63.7), "strip"),
        (TrailerLook("1920:1080:0:0", 1920, 1080, 31.0), "too dark"),
        (TrailerLook("1920:1080:0:0", 1920, 1080, 89.5, 9.6), "colourless"),
    ],
)
def test_letterboxed_or_dark_trailers_are_refused(look, reason):
    with pytest.raises(RuntimeError, match=reason):
        check_trailer_look(look)


def test_black_bars_are_cropped_before_the_clips_are_cut():
    graph = build_filter_graph([6.0, 20.0], has_audio=False, crop="1920:800:0:140")
    assert graph.startswith("[0:v]crop=1920:800:0:140,split=2[s0][s1];")
    assert "[s1]trim=start=20.0" in graph


def test_store_plumbing_never_reaches_the_script_facts():
    built = build_facts(CANDIDATE, steam_details(
        about_the_game="<p>Hunt bosses across a <b>colourful</b> world.</p>",
        categories=[
            {"description": "Single-player"}, {"description": "Co-op"},
            {"description": "Steam Cloud"}, {"description": "Full controller support"},
        ],
    ))
    assert built.modes == ["solo", "coopération"]
    assert built.about == "Hunt bosses across a colourful world."


def test_store_features_in_the_text_are_rejected():
    # Same length as the original sentence, so only the forbidden term is at fault.
    body = GOOD_BODY.replace("tu peux même y jouer à deux", "tu débloques des succès à deux")
    with pytest.raises(ScriptRejected, match="forbidden"):
        validate_body(body, facts())


def test_language_errors_fail_the_check():
    def chat(messages, **options):
        if "Vérifie" in messages[-1]["content"]:
            return json.dumps({"valid": True, "unsupported": [], "language_errors": ["au manette"]})
        return json.dumps({"body": GOOD_BODY})

    with pytest.raises(ScriptRejected, match="au manette"):
        write_gem_script(facts(), chat=chat)


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


def test_editor_can_request_an_extra_reel_the_same_day(tmp_path):
    log = tmp_path / "log.json"
    now = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
    log.write_text(
        json.dumps([{"topic_id": "steam-9", "published_at": "2026-10-06T15:20:00Z"}]),
        encoding="utf-8",
    )
    orchestrator = FakeOrchestrator()
    result = run_once(
        output_dir=tmp_path, publish_log_path=log, live_publish=True,
        orchestrator=orchestrator, games=iter([facts()]), produce_fn=fake_produce(),
        now=now, allow_extra_today=True,
    )
    assert result.status == "published"
    assert orchestrator.published == ["steam-1304680"]


def test_scheduled_runs_can_never_request_an_extra_reel():
    workflow = Path(".github/workflows/social-agent.yml").read_text(encoding="utf-8")
    assert (
        "GQ_ALLOW_EXTRA_REEL: ${{ github.event_name == 'workflow_dispatch' "
        "&& inputs.extra_reel_today && 'true' || 'false' }}"
    ) in workflow


def test_checker_is_told_to_verify_translations():
    from content.gem_script import build_checker_messages, build_writer_messages

    checker = build_checker_messages(facts(), GOOD_BODY)[-1]["content"]
    assert "faux ami" in checker and "éperonner" in checker
    assert "éperonner" in build_writer_messages(facts())[-1]["content"]


def test_workflow_runs_the_daily_reel_once_a_day_with_groq():
    workflow = Path(".github/workflows/social-agent.yml").read_text(encoding="utf-8")
    assert "python -m automation.daily_reel" in workflow
    assert "GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}" in workflow
    assert 'cron: "17 15 * * *"' in workflow
