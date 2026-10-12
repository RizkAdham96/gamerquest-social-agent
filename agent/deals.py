"""Pick one well-reviewed Steam game that is heavily discounted right now.

Every figure a viewer acts on (both prices, the discount, the review score)
is read from the store at the moment the Reel is made, never from an article
or a cached list: a deal that ended an hour ago must not be announced.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime, timezone

from agent.hidden_gems import (
    BLOCKED_TAGS,
    STEAMSPY_APP,
    GameFacts,
    _details,
    _fetch_json,
    build_facts,
)

FEATURED = "https://store.steampowered.com/api/featuredcategories/?cc=FR&l=french"
TOP_SPECIALS = (
    "https://store.steampowered.com/search/results/"
    "?specials=1&json=1&cc=FR&l=french&count=50&filter=topsellers"
)

MIN_DISCOUNT_PERCENT = 50
MIN_REVIEWS = 2_000
MIN_POSITIVE_RATIO = 0.85
# Most games on the sale lists fail the discount test on the first request;
# ten lookups once left a single usable deal, whose trailer was then refused.
MAX_DEAL_LOOKUPS = 40


@dataclass(frozen=True)
class DealFacts(GameFacts):
    original_cents: int = 0
    sale_cents: int = 0
    discount_percent: int = 0
    ends_at: datetime | None = None
    month: str = ""

    @property
    def topic_id(self) -> str:
        # A game can come back in a later sale, but not twice in one month,
        # and a deal Reel never blocks the same game's hidden-gem Reel.
        return f"deal-{self.appid}-{self.month}"


def clean_name(name: str) -> str:
    return " ".join(re.sub(r"[™®©]", "", str(name or "")).split())


def deal_candidates(fetch_json: Callable[[str], dict] = _fetch_json) -> dict[int, datetime | None]:
    """App ids currently on sale, with the announced end of the sale if known."""
    found: dict[int, datetime | None] = {}
    try:
        for item in (fetch_json(FEATURED).get("specials") or {}).get("items") or []:
            if not item.get("id") or int(item.get("type") or 0) != 0:
                continue
            stamp = item.get("discount_expiration")
            found[int(item["id"])] = (
                datetime.fromtimestamp(int(stamp), tz=timezone.utc) if stamp else None
            )
    except Exception as exc:
        print(f"Deals: featured specials unavailable ({exc}).")
    try:
        for item in fetch_json(TOP_SPECIALS).get("items") or []:
            # Bundles and packages have /subs/ or /bundles/ in the image path.
            match = re.search(r"/steam/apps/(\d+)/", str(item.get("logo") or ""))
            if match:
                found.setdefault(int(match.group(1)), None)
    except Exception as exc:
        print(f"Deals: specials search unavailable ({exc}).")
    return found


def live_discount(french: dict | None) -> tuple[int, int, int] | None:
    """(original cents, sale cents, percent) when the game is on a real sale."""
    price = (french or {}).get("price_overview") or {}
    try:
        original, sale = int(price.get("initial") or 0), int(price.get("final") or 0)
        percent = int(price.get("discount_percent") or 0)
    except (TypeError, ValueError):
        return None
    if price.get("currency") != "EUR" or percent < MIN_DISCOUNT_PERCENT:
        return None
    if not 0 < sale < original:
        return None
    return original, sale, percent


def iter_deals(
    published_topic_ids: set[str],
    *,
    now: datetime,
    fetch_json: Callable[[str], dict] = _fetch_json,
    max_lookups: int = MAX_DEAL_LOOKUPS,
):
    """Yield suitable discounted games in a day-specific order."""
    month = now.strftime("%Y%m")
    candidates = deal_candidates(fetch_json)
    appids = [appid for appid in candidates if f"deal-{appid}-{month}" not in published_topic_ids]
    random.Random(now.strftime("%Y-%m-%d")).shuffle(appids)
    for appid in appids[:max_lookups]:
        try:
            french = _details(appid, "french", fetch_json)
            discount = live_discount(french)
            if discount is None:
                continue
            english = _details(appid, "english", fetch_json)
            reception = fetch_json(STEAMSPY_APP.format(appid=appid))
        except Exception as exc:
            print(f"Deals: lookup failed for app {appid}: {exc}")
            continue
        positive = int(reception.get("positive") or 0)
        total = positive + int(reception.get("negative") or 0)
        if total < MIN_REVIEWS or positive / total < MIN_POSITIVE_RATIO:
            continue
        tags = reception.get("tags") or {}
        if isinstance(tags, dict) and set(tags) & BLOCKED_TAGS:
            continue
        name = clean_name((english or {}).get("name"))
        if not name or not name.isascii():
            continue
        game = build_facts(
            {
                "appid": appid, "name": name,
                "review_percent": round(positive / total * 100), "review_count": total,
            },
            english, french,
        )
        if game is None:
            continue
        values = {item.name: getattr(game, item.name) for item in fields(game)}
        values["name"] = name
        original, sale, percent = discount
        yield DealFacts(
            **values, original_cents=original, sale_cents=sale, discount_percent=percent,
            ends_at=candidates.get(appid), month=month,
        )
