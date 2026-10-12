import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from agent.deals import DealFacts, clean_name, deal_candidates, iter_deals, live_discount
from automation.daily_reel import produce, run_once
from content.deal_script import (
    DEAL_BODY_WORDS,
    build_caption,
    on_screen_text,
    spoken_price,
    write_deal_script,
    written_price,
)
from content.gem_script import GemScript, ScriptRejected
from content.voice_types import SpokenWord

NOW = datetime(2026, 10, 12, 16, 0, tzinfo=timezone.utc)
BODY = (
    "T'es un jeune élève de kung-fu, et chaque défaite te fait vieillir. "
    "Tu traverses la ville pour retrouver ceux qui ont tué ta famille, et tu te bats à mains nues "
    "contre des groupes entiers. Tu pares, tu esquives, tu ramasses ce qui traîne pour frapper. "
    "Sauf que chaque fois que tu tombes, tu te relèves plus vieux : tu frappes plus fort, "
    "mais tu encaisses moins. Du coup, chaque erreur compte vraiment. "
    "Franchement, l'idée est maligne."
)
assert DEAL_BODY_WORDS[0] <= len(BODY.split()) <= DEAL_BODY_WORDS[1]


def deal(**overrides):
    values = dict(
        appid=2138710, name="Sifu", description="A kung fu action game about revenge and ageing.",
        genres=["Action"], features=["Single-player"], price="9,99€", review_percent=92,
        review_count=21129, trailer_url="https://video.example/sifu.m3u8",
        original_cents=3999, sale_cents=999, discount_percent=75,
        ends_at=datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc), month="202610",
    )
    values.update(overrides)
    return DealFacts(**values)


def store(price=None, spy=None, details=None, specials=None, search=None):
    price = price or {"currency": "EUR", "initial": 3999, "final": 999, "discount_percent": 75,
                      "final_formatted": "9,99€"}
    spy = spy or {"positive": 19536, "negative": 1593, "tags": {"Action": 1}}
    data = {
        "type": "game", "name": "Sifu™", "required_age": 0,
        "short_description": "Sifu is a kung fu action game about revenge, with tight hand-to-hand combat.",
        "release_date": {"coming_soon": False}, "price_overview": price,
        "genres": [{"description": "Action"}], "categories": [{"description": "Single-player"}],
        "movies": [{"hls_h264": "https://video.example/sifu.m3u8"}],
    }
    data.update(details or {})

    def fetch(url):
        if "featuredcategories" in url:
            return {"specials": {"items": specials if specials is not None else [
                {"id": 2138710, "type": 0, "discount_expiration": 1792688400},
            ]}}
        if "search/results" in url:
            return {"items": search or []}
        if "steamspy" in url:
            return spy
        return {"2138710": {"success": True, "data": data}}

    return fetch


# --- choosing the deal ------------------------------------------------------

def test_a_live_well_reviewed_discount_becomes_a_deal():
    found = list(iter_deals(set(), now=NOW, fetch_json=store()))
    assert len(found) == 1
    sifu = found[0]
    assert (sifu.name, sifu.original_cents, sifu.sale_cents, sifu.discount_percent) == ("Sifu", 3999, 999, 75)
    assert sifu.review_percent == 92 and sifu.topic_id == "deal-2138710-202610"
    assert sifu.ends_at.year == 2026


def test_prices_come_from_the_live_store_page_not_the_sale_list():
    ended = {"currency": "EUR", "initial": 3999, "final": 3999, "discount_percent": 0}
    assert list(iter_deals(set(), now=NOW, fetch_json=store(price=ended))) == []


def test_small_discounts_and_other_currencies_are_not_deals():
    assert live_discount({"price_overview": {"currency": "EUR", "initial": 2000, "final": 1200, "discount_percent": 40}}) is None
    assert live_discount({"price_overview": {"currency": "USD", "initial": 2000, "final": 500, "discount_percent": 75}}) is None
    assert live_discount({"price_overview": {"currency": "EUR", "initial": 2000, "final": 0, "discount_percent": 100}}) is None
    assert live_discount({}) is None


def test_poorly_reviewed_or_little_reviewed_games_are_not_recommended():
    assert list(iter_deals(set(), now=NOW, fetch_json=store(spy={"positive": 6000, "negative": 4000}))) == []
    assert list(iter_deals(set(), now=NOW, fetch_json=store(spy={"positive": 500, "negative": 10}))) == []
    assert list(iter_deals(set(), now=NOW, fetch_json=store(spy={"positive": 0}))) == []


def test_adult_games_and_software_are_never_deals():
    assert list(iter_deals(set(), now=NOW, fetch_json=store(details={"required_age": "18"}))) == []
    spy = {"positive": 19536, "negative": 1593, "tags": {"Utilities": 1}}
    assert list(iter_deals(set(), now=NOW, fetch_json=store(spy=spy))) == []


def test_a_deal_is_not_repeated_in_the_same_month_but_may_return_later():
    assert list(iter_deals({"deal-2138710-202610"}, now=NOW, fetch_json=store())) == []
    assert len(list(iter_deals({"deal-2138710-202609", "steam-2138710"}, now=NOW, fetch_json=store()))) == 1


def test_sale_lists_are_merged_and_bundles_ignored():
    search = [
        {"name": "Game", "logo": "https://cdn.example/store_item_assets/steam/apps/42/x/capsule.jpg"},
        {"name": "Bundle", "logo": "https://cdn.example/store_item_assets/steam/bundles/7/capsule.jpg"},
    ]
    found = deal_candidates(store(search=search))
    assert set(found) == {2138710, 42} and found[42] is None


def test_one_sale_list_failing_does_not_hide_the_other():
    def fetch(url):
        if "featuredcategories" in url:
            raise OSError("down")
        return {"items": [{"logo": "https://cdn.example/steam/apps/42/capsule.jpg"}]}

    assert set(deal_candidates(fetch)) == {42}


def test_trademark_signs_are_dropped_from_names():
    assert clean_name("Sekiro™: Shadows Die Twice ®") == "Sekiro: Shadows Die Twice"


# --- script -----------------------------------------------------------------

def test_prices_are_written_for_the_voice_and_for_the_caption():
    assert spoken_price(1499) == "14 euros 99"
    assert spoken_price(2000) == "20 euros"
    assert spoken_price(100) == "1 euro"
    assert spoken_price(105) == "1 euro 05"
    assert spoken_price(89) == "89 centimes"
    assert written_price(999) == "9,99 €" and written_price(2000) == "20,00 €"


def test_spoken_text_names_the_game_and_both_prices_from_store_data():
    text = on_screen_text(deal(), BODY)
    assert text.startswith("Bon plan : Sifu est à moins 75 pour cent sur Steam. ")
    assert "Sifu passe de 39 euros 99 à 9 euros 99 sur Steam." in text
    assert text.endswith("Abonne-toi pour ne rater aucun bon plan.")


def test_caption_carries_dated_prices_and_the_end_of_the_sale():
    caption = build_caption(deal(), today=NOW)
    assert "Sifu à -75 % sur Steam" in caption
    assert "Prix : 9,99 € au lieu de 39,99 €" in caption
    assert "Offre annoncée jusqu'au 19/10/2026" in caption
    assert "Prix relevé sur Steam le 12/10/2026" in caption
    assert "Avis Steam : 92 % positifs" in caption


def test_an_end_date_that_is_unknown_or_past_is_left_out():
    assert "Offre annoncée" not in build_caption(deal(ends_at=None), today=NOW)
    past = datetime(2026, 10, 11, tzinfo=timezone.utc)
    assert "Offre annoncée" not in build_caption(deal(ends_at=past), today=NOW)


def test_the_model_writes_only_the_description_and_it_is_fact_checked():
    seen = []

    def chat(messages, **options):
        seen.append(messages[-1]["content"])
        if "Vérifie" in messages[-1]["content"]:
            return json.dumps({"valid": True, "unsupported": [], "language_errors": []})
        return json.dumps({"body": BODY})

    script = write_deal_script(deal(), chat=chat)
    assert len(seen) == 2 and "Entre 70 et 100 mots" in seen[0]
    assert "39" not in seen[0] and "75" not in seen[0]
    assert script.body == BODY and "39 euros 99" in script.on_screen_text


def test_a_description_that_mentions_money_is_rejected():
    def chat(messages, **options):
        return json.dumps({"body": BODY.replace("Franchement, l'idée est maligne.", "Et le prix est mini.")})

    try:
        write_deal_script(deal(), chat=chat)
    except ScriptRejected as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("a description quoting a price must be rejected")


# --- run --------------------------------------------------------------------

class Orchestrator:
    def __init__(self):
        self.published = []

    def publish_reel(self, *, topic_id, reel_path, caption):
        self.published.append(topic_id)
        return SimpleNamespace(media_id="1", container_id="2", drive_file_id=None)


def fake_produce(reject=()):
    made = []

    def make(game, output_dir):
        made.append(game.topic_id)
        if game.name in reject:
            raise ScriptRejected("fact-check failed")
        script = GemScript(body=BODY, on_screen_text=BODY, caption="caption")
        return script, SimpleNamespace(path=Path(output_dir) / "reel.mp4", duration_seconds=30.0)

    make.made = made
    return make


GEM = {"appid": 1304680, "name": "Voidigo", "review_percent": 97, "review_count": 4289}


def gem_store(url):
    if "steamspy" in url:
        return {"tags": {"Roguelike": 1}}
    return {"1304680": {"success": True, "data": {
        "type": "game", "name": "Voidigo", "required_age": 0,
        "short_description": "A vividly animated action roguelite focused on boss hunting, with weapons.",
        "release_date": {"coming_soon": False}, "price_overview": {"final_formatted": "2,29€"},
        "genres": [{"description": "Action"}], "categories": [{"description": "Co-op"}],
        "movies": [{"hls_h264": "https://video.example/trailer.m3u8"}],
    }}}


def run(tmp_path, monkeypatch, *, stamps=(), kind="auto", deals=(deal(),), reject=(), now=NOW):
    import agent.hidden_gems as gems

    monkeypatch.setattr(gems, "_fetch_json", gem_store)
    monkeypatch.setattr(gems.iter_games, "__kwdefaults__", {**gems.iter_games.__kwdefaults__, "fetch_json": gem_store})
    log = tmp_path / "log.json"
    log.write_text(json.dumps([
        {"topic_id": f"steam-{index}", "published_at": stamp} for index, stamp in enumerate(stamps)
    ]), encoding="utf-8")
    orchestrator, make = Orchestrator(), fake_produce(reject)

    def find(published, *, now):
        if isinstance(deals, Exception):
            raise deals
        yield from deals

    result = run_once(
        output_dir=tmp_path, publish_log_path=log, live_publish=True, orchestrator=orchestrator,
        candidates=[GEM], produce_fn=make, now=now, reel_kind=kind, find_deals=find,
    )
    return result, orchestrator, make


def test_the_first_reel_of_the_day_is_a_hidden_gem(tmp_path, monkeypatch):
    result, orchestrator, _ = run(tmp_path, monkeypatch)
    assert result.status == "published" and orchestrator.published == ["steam-1304680"]


def test_the_second_reel_of_the_day_is_a_deal(tmp_path, monkeypatch):
    result, orchestrator, _ = run(tmp_path, monkeypatch, stamps=("2026-10-12T10:30:00Z",))
    assert result.status == "published" and orchestrator.published == ["deal-2138710-202610"]


def test_without_a_good_deal_the_second_reel_is_a_hidden_gem(tmp_path, monkeypatch):
    result, orchestrator, _ = run(tmp_path, monkeypatch, stamps=("2026-10-12T10:30:00Z",), deals=())
    assert result.status == "published" and orchestrator.published == ["steam-1304680"]


def test_a_deal_that_fails_its_checks_gives_way_to_a_hidden_gem(tmp_path, monkeypatch):
    result, orchestrator, make = run(
        tmp_path, monkeypatch, stamps=("2026-10-12T10:30:00Z",), reject=("Sifu",),
    )
    assert make.made == ["deal-2138710-202610", "steam-1304680"]
    assert orchestrator.published == ["steam-1304680"]


def test_a_store_outage_on_deals_does_not_cost_the_reel(tmp_path, monkeypatch):
    result, orchestrator, _ = run(
        tmp_path, monkeypatch, stamps=("2026-10-12T10:30:00Z",), deals=OSError("down"),
    )
    assert result.status == "published" and orchestrator.published == ["steam-1304680"]


def test_at_most_three_deals_are_tried_in_a_run(tmp_path, monkeypatch):
    many = tuple(deal(appid=number, name=f"Game {number}") for number in (1, 2, 3, 4))
    _, _, make = run(
        tmp_path, monkeypatch, stamps=("2026-10-12T10:30:00Z",), deals=many,
        reject=("Game 1", "Game 2", "Game 3", "Game 4"),
    )
    assert make.made == ["deal-1-202610", "deal-2-202610", "deal-3-202610", "steam-1304680"]


def test_an_editor_can_ask_for_a_deal_or_a_gem_by_hand(tmp_path, monkeypatch):
    result, orchestrator, _ = run(tmp_path, monkeypatch, kind="deal")
    assert orchestrator.published == ["deal-2138710-202610"]
    result, orchestrator, _ = run(tmp_path, monkeypatch, kind="deal", deals=())
    assert result.status == "skipped" and orchestrator.published == []
    result, orchestrator, _ = run(tmp_path, monkeypatch, stamps=("2026-10-12T10:30:00Z",), kind="gem")
    assert orchestrator.published == ["steam-1304680"]


def test_a_deal_reel_is_narrated_with_the_deal_script(tmp_path):
    spoken_text = []

    def speak(text, path):
        spoken_text.append(text)
        Path(path).write_bytes(b"voice")
        return [SpokenWord(0.0, 30.0, "fin")]

    def render(**options):
        return SimpleNamespace(path=tmp_path / "reel.mp4", duration_seconds=options["reel_seconds"])

    import content.deal_script as deal_script

    original = deal_script.write_gem_script
    deal_script.write_gem_script = lambda facts, chat, words=None: GemScript(BODY, BODY, "c")
    try:
        script, _ = produce(
            deal(), tmp_path, speak=speak, render=render,
            fetch_trailer=lambda url, directory: tmp_path / "trailer.mp4",
            inspect_trailer=lambda trailer: None,
        )
    finally:
        deal_script.write_gem_script = original
    assert "Sifu passe de 39 euros 99 à 9 euros 99" in spoken_text[0]
    assert json.loads((tmp_path / "script.json").read_text(encoding="utf-8"))["kind"] == "deal"
    assert "au lieu de 39,99 €" in script.caption


def test_workflow_lets_an_editor_choose_the_kind():
    workflow = Path(".github/workflows/social-agent.yml").read_text(encoding="utf-8")
    assert "GQ_REEL_KIND: ${{ inputs.reel_kind || 'auto' }}" in workflow
    assert "- deal" in workflow and "- gem" in workflow
