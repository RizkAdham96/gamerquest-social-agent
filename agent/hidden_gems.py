"""Pick one well-reviewed, little-known Steam game per Reel.

News articles carry no trailer, which is why the old Reel pipeline ended every
run with "no official footage candidates found". A game chosen from Steam
always comes with its official trailer and the facts needed to describe it.
"""

from __future__ import annotations

import html
import json
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

STEAMSPY_INDIE = "https://steamspy.com/api.php?request=tag&tag=Indie"
APP_DETAILS = "https://store.steampowered.com/api/appdetails?appids={appid}&l={lang}&cc=FR"
CANDIDATE_CACHE = Path("state/gem_candidates.json")

MIN_REVIEWS = 800
MAX_REVIEWS = 25_000
MIN_POSITIVE_RATIO = 0.92
POOL_SIZE = 400
MAX_DETAIL_LOOKUPS = 12

# Steam content descriptor ids: 1 nudity/sexual content, 3 adult-only sexual
# content, 4 frequent nudity/sexual content. 2 (violence) and 5 (mature) stay.
BLOCKED_DESCRIPTOR_IDS = {1, 3, 4}
BLOCKED_NAME_WORDS = (
    "hentai", "sex", "nsfw", "waifu", "strip", "dating", "lewd", "erotic",
    "soundtrack", "demo", "playtest", "dlc",
)


@dataclass(frozen=True)
class GameFacts:
    appid: int
    name: str
    description: str
    genres: list[str]
    features: list[str]
    price: str
    review_percent: int
    review_count: int
    trailer_url: str
    developers: list[str] = field(default_factory=list)

    @property
    def topic_id(self) -> str:
        return f"steam-{self.appid}"

    @property
    def store_url(self) -> str:
        return f"https://store.steampowered.com/app/{self.appid}/"


def _fetch_json(url: str):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (GamerQuest Reels)"})
    with urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean_text(value) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(text).split())


def select_candidates(steamspy_payload: dict) -> list[dict]:
    """Loved by the players who found it, but found by few."""
    rows = []
    for entry in (steamspy_payload or {}).values():
        if not isinstance(entry, dict):
            continue
        positive = int(entry.get("positive") or 0)
        negative = int(entry.get("negative") or 0)
        total = positive + negative
        if not MIN_REVIEWS <= total <= MAX_REVIEWS:
            continue
        ratio = positive / total
        if ratio < MIN_POSITIVE_RATIO:
            continue
        name = str(entry.get("name") or "").strip()
        if not name or not name.isascii():
            continue
        if any(word in name.lower() for word in BLOCKED_NAME_WORDS):
            continue
        rows.append({
            "appid": int(entry["appid"]),
            "name": name,
            "review_percent": round(ratio * 100),
            "review_count": total,
        })
    rows.sort(key=lambda row: (row["review_percent"], row["review_count"]), reverse=True)
    return rows[:POOL_SIZE]


def load_candidates(
    fetch_json: Callable[[str], dict] = _fetch_json,
    cache_path: Path = CANDIDATE_CACHE,
) -> list[dict]:
    """Fresh list when SteamSpy answers, the committed list when it does not."""
    try:
        candidates = select_candidates(fetch_json(STEAMSPY_INDIE))
    except Exception as exc:
        print(f"SteamSpy unavailable ({exc}); using the cached candidate list.")
        candidates = []
    if candidates:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(candidates, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        return candidates
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    return []


def _price_text(data: dict) -> str:
    if data.get("is_free"):
        return "Gratuit"
    price = data.get("price_overview") or {}
    return str(price.get("final_formatted") or "").strip()


def _trailer_url(data: dict) -> str:
    for movie in data.get("movies") or []:
        if isinstance(movie, dict) and movie.get("hls_h264"):
            return str(movie["hls_h264"])
    return ""


def build_facts(candidate: dict, english: dict, french: dict | None = None) -> GameFacts | None:
    """Return the game's facts, or None when it is unsuitable for a Reel."""
    if not isinstance(english, dict) or english.get("type") != "game":
        return None
    if (english.get("release_date") or {}).get("coming_soon"):
        return None
    try:
        if int(str(english.get("required_age") or "0").strip() or 0) >= 18:
            return None
    except ValueError:
        return None
    descriptor_ids = set((english.get("content_descriptors") or {}).get("ids") or [])
    if descriptor_ids & BLOCKED_DESCRIPTOR_IDS:
        return None

    description = _clean_text(english.get("short_description"))
    trailer = _trailer_url(english)
    price = _price_text(french or english)
    if len(description) < 60 or not trailer or not price:
        return None

    localized = french or english
    return GameFacts(
        appid=int(candidate["appid"]),
        name=str(english.get("name") or candidate["name"]).strip(),
        description=description,
        genres=[
            str(item.get("description", "")).strip()
            for item in localized.get("genres") or []
            if str(item.get("description", "")).strip()
        ],
        features=[
            str(item.get("description", "")).strip()
            for item in english.get("categories") or []
            if str(item.get("description", "")).strip()
        ],
        price=price,
        review_percent=int(candidate["review_percent"]),
        review_count=int(candidate["review_count"]),
        trailer_url=trailer,
        developers=[str(item) for item in english.get("developers") or []],
    )


def _details(appid: int, lang: str, fetch_json) -> dict | None:
    payload = fetch_json(APP_DETAILS.format(appid=int(appid), lang=lang)).get(str(appid)) or {}
    return payload.get("data") if payload.get("success") else None


def iter_games(
    candidates: list[dict],
    published_topic_ids: set[str],
    *,
    seed: str,
    fetch_json: Callable[[str], dict] = _fetch_json,
    max_lookups: int = MAX_DETAIL_LOOKUPS,
):
    """Yield suitable games in a day-specific order, skipping published ones."""
    pool = [row for row in candidates if f"steam-{row['appid']}" not in published_topic_ids]
    random.Random(seed).shuffle(pool)
    lookups = 0
    for candidate in pool:
        if lookups >= max_lookups:
            return
        lookups += 1
        try:
            english = _details(candidate["appid"], "english", fetch_json)
            french = _details(candidate["appid"], "french", fetch_json) if english else None
        except Exception as exc:
            print(f"Steam lookup failed for {candidate['name']}: {exc}")
            continue
        facts = build_facts(candidate, english, french)
        if facts is not None:
            yield facts
