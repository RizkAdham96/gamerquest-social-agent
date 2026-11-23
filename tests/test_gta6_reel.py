import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.gta6_news import (
    NewsFacts,
    article_text,
    collect_stories,
    is_gta6,
    iter_news,
    parse_feed,
    record_history,
    same_story,
)
from automation.gta6_reel import Footage, FootageSource, produce, run_once
from content.gem_script import GemScript, ScriptRejected
from content.gta6_script import (
    GTA6_BODY_WORDS,
    GTA6_FOLLOW_LINE,
    build_caption,
    build_writer_messages,
    validate_body,
    write_gta6_script,
)
from content.voice_types import SpokenWord
from media.gta6_footage import footage_window, listed_footage

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
ARTICLE = (
    "Rockstar Games a publié un nouveau patch pour GTA 6 sur PS5 et Xbox Series. "
    "La mise à jour 1.02 corrige des plantages dans les missions de Lucia et Jason à Vice City "
    "et améliore la stabilité du mode photo. Le studio précise que d'autres correctifs arriveront "
    "dans les prochaines semaines, sans donner de date. Les joueurs signalaient depuis la sortie "
    "du jeu le 19 novembre des chutes de framerate dans les Keys, que ce patch vise aussi à réduire."
)
BODY = (
    "GTA 6 vient de recevoir son premier gros patch, et il était attendu. "
    "La mise à jour 1.02 arrive sur PS5 et Xbox Series, et elle corrige des plantages dans les "
    "missions de Lucia et Jason à Vice City. Elle améliore aussi la stabilité du mode photo. "
    "Et y a un autre point important : depuis la sortie le 19 novembre, plein de joueurs "
    "se plaignaient de chutes de framerate dans les Keys, et ce patch veut les réduire. "
    "Rockstar promet d'autres correctifs dans les prochaines semaines, sans date pour l'instant. "
    "Et toi, t'as eu des plantages ?"
)
assert GTA6_BODY_WORDS[0] <= len(BODY.split()) <= GTA6_BODY_WORDS[1]


def story(**overrides):
    values = dict(
        title="GTA 6 : le patch 1.02 corrige les plantages", url="https://www.jvfrance.com/gta-6-patch",
        source="JV France", published=NOW - timedelta(hours=3), text=ARTICLE,
    )
    values.update(overrides)
    return NewsFacts(**values)


def rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate>"
        f"<description>{s}</description></item>"
        for t, u, d, s in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


def test_is_gta6_matches_the_usual_names_only():
    assert is_gta6("GTA 6 : nouveau patch")
    assert is_gta6("Grand Theft Auto VI dépasse les ventes")
    assert is_gta6("gta vi online date")
    assert not is_gta6("GTA 5 reçoit une mise à jour")
    assert not is_gta6("GTA San Andreas remaster")


def test_parse_feed_reads_rss_and_strips_google_news_outlet():
    xml = rss([("GTA 6 : patch - Gamekult", "https://news.google.com/x", "Mon, 23 Nov 2026 09:00:00 GMT", "")])
    xml = xml.replace("</item>", "<source url='https://gamekult.com'>Gamekult</source></item>")
    row = parse_feed(xml, "Google News")[0]
    assert row["title"] == "GTA 6 : patch"
    assert row["source"] == "Gamekult"
    assert row["published"] == datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)


def test_parse_feed_reads_atom():
    xml = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>GTA VI news</title>'
        '<link href="https://site.fr/a"/><updated>2026-11-23T08:00:00Z</updated>'
        "<summary>texte</summary></entry></feed>"
    )
    row = parse_feed(xml, "Site")[0]
    assert row["url"] == "https://site.fr/a" and row["title"] == "GTA VI news"


def test_collect_stories_keeps_fresh_gta6_items_newest_first():
    xml = rss([
        ("GTA 6 : vieux", "https://a.fr/1", "Mon, 16 Nov 2026 09:00:00 GMT", ""),
        ("GTA 6 : récent", "https://a.fr/2", "Mon, 23 Nov 2026 10:00:00 GMT", ""),
        ("GTA 6 : hier", "https://a.fr/3", "Sun, 22 Nov 2026 10:00:00 GMT", ""),
        ("Zelda : rien à voir", "https://a.fr/4", "Mon, 23 Nov 2026 11:00:00 GMT", ""),
    ])
    rows = collect_stories(now=NOW, fetch=lambda url: xml, feeds=[("A", "feed")])
    assert [row["title"] for row in rows] == ["GTA 6 : récent", "GTA 6 : hier"]


def test_a_broken_feed_does_not_stop_the_others():
    good = rss([("GTA 6 : ok", "https://b.fr/1", "Mon, 23 Nov 2026 10:00:00 GMT", "")])

    def fetch(url):
        if url == "bad":
            raise OSError("down")
        return good

    rows = collect_stories(now=NOW, fetch=fetch, feeds=[("Bad", "bad"), ("Good", "good")])
    assert len(rows) == 1


def test_article_text_takes_description_and_paragraphs_without_furniture():
    page = (
        '<html><head><meta property="og:description" content="Rockstar publie le patch 1.02 de GTA 6.">'
        "</head><body><nav><p>Menu menu menu menu menu menu menu menu menu menu menu menu menu</p></nav>"
        "<p>La mise à jour corrige des plantages dans les missions principales du jeu.</p>"
        "<p>Acceptez les cookies pour continuer votre lecture sur notre site web.</p>"
        "<script>var x = '<p>nope nope nope nope nope nope nope nope nope nope nope</p>';</script>"
        "</body></html>"
    )
    text = article_text(page)
    assert text.startswith("Rockstar publie le patch 1.02")
    assert "plantages" in text
    assert "cookies" not in text and "Menu" not in text


def test_same_story_detects_two_outlets_covering_one_announcement():
    assert same_story("GTA 6 : le patch 1.02 corrige les plantages", "GTA 6 patch 1.02 : les plantages corrigés")
    assert not same_story("GTA 6 : le patch 1.02 corrige les plantages", "GTA 6 Online : date de lancement")


def test_iter_news_skips_published_and_already_covered_stories_and_thin_ones():
    xml = rss([
        ("GTA 6 : patch 1.02 corrige les plantages", "https://a.fr/patch", "Mon, 23 Nov 2026 10:00:00 GMT", ""),
        ("GTA 6 Online : date annoncée", "https://a.fr/online", "Mon, 23 Nov 2026 09:00:00 GMT", ""),
        ("GTA 6 : ventes record", "https://a.fr/ventes", "Mon, 23 Nov 2026 08:00:00 GMT", ""),
        ("GTA 6 : article vide", "https://a.fr/vide", "Mon, 23 Nov 2026 07:00:00 GMT", ""),
    ])
    pages = {
        "https://a.fr/online": f"<p>{ARTICLE}</p>",
        "https://a.fr/ventes": f"<p>{ARTICLE}</p>",
        "https://a.fr/vide": "<p>Trop court pour écrire quoi que ce soit dessus ici.</p>",
    }

    def fetch(url):
        return xml if url == "feed" else pages[url]

    published = {story(url="https://a.fr/ventes").topic_id}
    history = [{"title": "Le patch 1.02 de GTA 6 corrige les plantages"}]
    found = list(iter_news(published, now=NOW, history=history, fetch=fetch, feeds=[("A", "feed")]))
    assert [facts.url for facts in found] == ["https://a.fr/online"]


def test_record_history_appends(tmp_path):
    path = tmp_path / "h.json"
    record_history(story(), NOW, path=path)
    record_history(story(url="https://x.fr/2"), NOW, path=path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 2 and data[0]["published_at"] == "2026-11-23T12:00:00Z"


def test_validate_body_accepts_a_good_text_and_refuses_bad_ones():
    assert validate_body(BODY) == BODY
    with pytest.raises(ScriptRejected):
        validate_body("GTA 6 sort bientôt.")
    with pytest.raises(ScriptRejected):
        validate_body(BODY.replace("Et toi", "Lien en bio, et toi"))
    with pytest.raises(ScriptRejected):
        validate_body(BODY.replace("GTA 6", "Le jeu"))
    with pytest.raises(ScriptRejected):
        validate_body(BODY[:-1])


def test_writer_asks_to_flag_rumours_only_when_the_article_does():
    rumour = story(text=ARTICLE + " Selon une rumeur, un DLC serait en préparation.")
    assert "rumeur" in build_writer_messages(rumour)[1]["content"].split("RÈGLES")[1][:2000]
    assert "Présente seulement comme officiel" in build_writer_messages(story())[1]["content"]


def test_caption_credits_the_source():
    caption = build_caption(story())
    assert "JV France" in caption and "https://www.jvfrance.com/gta-6-patch" in caption
    assert "#GTA6" in caption


def test_write_script_retries_after_a_failed_fact_check():
    replies = iter([
        json.dumps({"body": BODY}),
        json.dumps({"valid": False, "unsupported": ["date inventée"], "language_errors": []}),
        json.dumps({"body": BODY}),
        json.dumps({"valid": True, "unsupported": [], "language_errors": []}),
    ])
    prompts = []

    def chat(messages, **kwargs):
        prompts.append(messages[1]["content"])
        return next(replies)

    script = write_gta6_script(story(), chat=chat)
    assert script.on_screen_text.endswith(GTA6_FOLLOW_LINE)
    assert "date inventée" in prompts[2]


def test_write_script_gives_up_after_three_rejections():
    def chat(messages, **kwargs):
        return json.dumps({"body": "Trop court."})

    with pytest.raises(ScriptRejected):
        write_gta6_script(story(), chat=chat)


def test_listed_footage_downloads_missing_trailers_and_survives_failures(tmp_path):
    listing = tmp_path / "footage.json"
    listing.write_text(json.dumps([
        {"id": "t1", "url": "https://youtube.example/1"},
        {"id": "t2", "url": "https://youtube.example/2"},
    ]), encoding="utf-8")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[-1].endswith("/2"):
            import subprocess
            raise subprocess.CalledProcessError(1, command, stderr="Sign in to confirm")
        Path(command[command.index("-o") + 1]).write_bytes(b"video")

    found = listed_footage(tmp_path / "cache", listing, run=run)
    assert [path.name for path in found] == ["t1.mp4"]
    # Cached trailers are not downloaded again.
    calls.clear()
    listed_footage(tmp_path / "cache", listing, run=run)
    assert all(not command[-1].endswith("/1") for command in calls)


def test_footage_window_is_silent_and_varies_with_the_seed(tmp_path):
    source = tmp_path / "t.mp4"
    source.write_bytes(b"x")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"cut")

    probe = lambda path: {"duration": 150.0}
    footage_window([source], 40.0, tmp_path / "out", seed="a", run=run, probe_fn=probe)
    footage_window([source], 40.0, tmp_path / "out", seed="b", run=run, probe_fn=probe)
    assert all("-an" in command for command in commands)
    starts = [float(command[command.index("-ss") + 1]) for command in commands]
    assert starts[0] != starts[1]
    assert all(8.0 <= start <= 150 - 8 - 72 for start in starts)


def spoken(seconds=40.0):
    return [SpokenWord(text="GTA", start=0.2, end=seconds)]


class FakeFootage:
    def __init__(self, path, credits=(), clip_ids=()):
        self.calls = []
        self.path, self.credits, self.clip_ids = path, list(credits), list(clip_ids)

    def get(self, seconds, output_dir, *, seed, exclude):
        self.calls.append(set(exclude))
        return Footage(self.path, self.credits, [f"{c}-{len(self.calls)}" for c in self.clip_ids])


def test_produce_retries_dark_footage_and_credits_streamers(tmp_path):
    footage = FakeFootage(tmp_path / "trailer.mp4", ["Streamer1", "Streamer2"], ["c"])

    def render(**kwargs):
        if len(footage.calls) == 1:
            raise RuntimeError("the trailer is too dark for a Reel")
        return SimpleNamespace(path=tmp_path / "reel.mp4", duration_seconds=kwargs["reel_seconds"])

    script, rendered, clip_ids = produce(
        story(), tmp_path, footage=footage,
        write_script=lambda facts: GemScript(BODY, BODY, build_caption(facts)),
        speak=lambda text, path: spoken(), render=render,
    )
    # The refused clips are not offered again.
    assert footage.calls[1] == {"c-1"}
    assert clip_ids == ["c-2"]
    assert "🎥 Clips Twitch : Streamer1, Streamer2\n\n#GTA6" in script.caption
    saved = json.loads((tmp_path / "script.json").read_text(encoding="utf-8"))
    assert saved["kind"] == "gta6" and saved["twitch_clips"] == ["c-2"]


def test_produce_refuses_a_script_that_runs_too_long(tmp_path):
    with pytest.raises(ScriptRejected):
        produce(
            story(), tmp_path, footage=FakeFootage(tmp_path / "t.mp4"),
            write_script=lambda facts: GemScript(BODY, BODY, "caption"),
            speak=lambda text, path: spoken(80.0),
        )


def test_footage_source_falls_back_to_trailers_when_twitch_fails(tmp_path):
    class BrokenTwitch:
        def montage(self, *args, **kwargs):
            raise RuntimeError("only 12s of new GTA 6 Twitch clips")

    source = FootageSource(
        now=NOW, twitch=BrokenTwitch(), load_library=lambda: [tmp_path / "t.mp4"],
        cut_window=lambda library, seconds, out, *, seed: out / "trailer.mp4",
        used_clips=set(), skip_streamers=set(),
    )
    chosen = source.get(40.0, tmp_path, seed="s", exclude=set())
    assert chosen.path == tmp_path / "trailer.mp4" and chosen.credits == []


def test_footage_source_passes_used_clips_and_skip_list_to_twitch(tmp_path):
    seen = {}

    class Twitch:
        def montage(self, seconds, output_dir, *, now, skip_ids, skip_streamers):
            seen.update(skip_ids=skip_ids, skip_streamers=skip_streamers)
            clip = SimpleNamespace(id="new")
            return SimpleNamespace(path=output_dir / "trailer.mp4", credits=["A"], clips=[clip])

    source = FootageSource(now=NOW, twitch=Twitch(), used_clips={"old"}, skip_streamers={"nope"})
    chosen = source.get(40.0, tmp_path, seed="s", exclude={"dark"})
    assert seen == {"skip_ids": {"old", "dark"}, "skip_streamers": {"nope"}}
    assert chosen.clip_ids == ["new"]


def test_run_once_skips_when_there_is_no_story_without_touching_footage(tmp_path):
    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=False,
        stories=[], now=NOW,
    )
    assert result.status == "skipped" and "no fresh" in result.reason


def test_run_once_moves_to_the_next_story_and_dry_runs(tmp_path):
    def fake_produce(facts, output_dir, *, footage):
        if "patch" in facts.title:
            raise ScriptRejected("fact-check failed")
        return GemScript(BODY, BODY, "c"), SimpleNamespace(path=tmp_path / "reel.mp4", duration_seconds=40.0), []

    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=False,
        stories=[story(), story(title="GTA 6 Online : date annoncée", url="https://a.fr/o")],
        footage=object(), produce_fn=fake_produce, now=NOW,
    )
    assert result.status == "dry-run" and result.game == "GTA 6 Online : date annoncée"


def test_run_once_publishes_and_records_history_and_used_clips(tmp_path):
    published = []

    class Orchestrator:
        def publish_reel(self, **kwargs):
            published.append(kwargs)
            return SimpleNamespace(media_id="123")

    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=True,
        orchestrator=Orchestrator(), stories=[story()], footage=object(),
        produce_fn=lambda facts, out, *, footage: (
            GemScript(BODY, BODY, "caption"),
            SimpleNamespace(path=tmp_path / "r.mp4", duration_seconds=40.0),
            ["clip1", "clip2"],
        ),
        now=NOW, history_path=tmp_path / "history.json", used_clips_path=tmp_path / "used.json",
    )
    assert result.status == "published" and published[0]["caption"] == "caption"
    assert json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))[0]["source"] == "JV France"
    assert json.loads((tmp_path / "used.json").read_text(encoding="utf-8")) == ["clip1", "clip2"]


def test_run_once_respects_the_daily_limit(tmp_path):
    log = tmp_path / "log.json"
    log.write_text(json.dumps([
        {"topic_id": f"gta6-{i}", "published_at": f"2026-11-23T0{i}:00:00Z"} for i in range(3)
    ]), encoding="utf-8")
    result = run_once(
        output_dir=tmp_path, publish_log_path=log, live_publish=True, stories=[story()],
        footage=object(), now=NOW, max_per_day=3,
    )
    assert result.status == "skipped" and "limit 3" in result.reason


def test_gta6_workflow_publishes_only_on_schedule_or_explicit_request():
    workflow = Path(".github/workflows/gta6-reels.yml").read_text(encoding="utf-8")
    assert "GQ_LIVE_PUBLISH: ${{ github.event_name == 'schedule' && 'true' || (github.event_name == 'workflow_dispatch' && inputs.publish_to_instagram && 'true' || 'false') }}" in workflow
    assert 'GQ_BYPASS_WEEKLY_LIMIT: "false"' in workflow
    assert "python -m automation.gta6_reel" in workflow
