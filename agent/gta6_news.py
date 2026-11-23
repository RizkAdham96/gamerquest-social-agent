"""Pick one fresh GTA 6 news story per Reel.

The hidden-gem Reel takes its facts from the Steam store; a GTA 6 Reel takes
them from a recent article. Every story comes from a French gaming news feed
(or Google News as a fallback), and its text is read from the article page so
the script is written from what the outlet actually reported.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# French gaming outlets whose article pages can be read. Google News was
# tried and dropped: its links go through a redirect page with no article
# text, so its headlines crowded out every usable story.
FEEDS = (
    ("jeuxvideo.com", "https://www.jeuxvideo.com/rss/rss.xml"),
    ("JV France", "https://www.jvfrance.com/feed/"),
    ("ActuGaming", "https://www.actugaming.net/feed/"),
    ("Gamergen", "https://gamergen.com/rss"),
)
HISTORY_FILE = Path("state/gta6_history.json")

GTA6_PATTERN = re.compile(
    r"\b(gta\s*(6|vi)|grand\s+theft\s+auto\s*(6|vi))\b", re.IGNORECASE
)
MAX_AGE_HOURS = 72
MIN_FACT_CHARS = 350
MAX_FACT_CHARS = 2400
# Two outlets covering the same announcement must not become two Reels.
MAX_TITLE_OVERLAP = 0.5
MAX_ARTICLE_LOOKUPS = 12
# Words that carry no meaning when comparing two headlines.
STOP_WORDS = {
    "gta", "grand", "theft", "auto", "vi", "6", "rockstar", "games", "le", "la", "les",
    "un", "une", "des", "de", "du", "et", "en", "sur", "pour", "avec", "dans", "a",
    "au", "aux", "est", "son", "sa", "ses", "il", "elle", "on", "ce", "cette", "qui",
    "que", "pas", "plus", "the", "of", "to", "and", "in",
}
USER_AGENT = "Mozilla/5.0 (compatible; GamerQuest Reels; +https://gamerquestfr.com)"


@dataclass(frozen=True)
class NewsFacts:
    title: str
    url: str
    source: str
    published: datetime
    text: str

    @property
    def topic_id(self) -> str:
        return "gta6-" + hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:12]

    # The runner prints these for every candidate, like it does for games.
    @property
    def name(self) -> str:
        return self.title


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"})
    with urlopen(request, timeout=30) as response:
        raw = response.read(3_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(text).split())


def is_gta6(text: str) -> bool:
    return bool(GTA6_PATTERN.search(text or ""))


def _parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _child(item: ET.Element, *names: str) -> str:
    for name in names:
        for child in item:
            tag = child.tag.split("}")[-1]
            if tag == name:
                if tag == "link" and child.get("href"):
                    return child.get("href", "")
                return child.text or ""
    return ""


def parse_feed(xml_text: str, source: str) -> list[dict]:
    """Items of an RSS or Atom feed: title, url, source, published, summary."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []
    items = [el for el in root.iter() if el.tag.split("}")[-1] in ("item", "entry")]
    rows = []
    for item in items:
        title = clean_text(_child(item, "title"))
        url = _child(item, "link").strip()
        outlet = source
        if source == "Google News":
            outlet = clean_text(_child(item, "source")) or source
            # Google News appends " - Outlet" to every headline.
            if outlet and title.endswith(" - " + outlet):
                title = title[: -len(outlet) - 3].strip()
        rows.append({
            "title": title,
            "url": url,
            "source": outlet,
            "published": _parse_date(_child(item, "pubDate", "published", "updated", "date")),
            "summary": clean_text(_child(item, "encoded", "description", "summary", "content")),
        })
    return rows


class _ParagraphParser(HTMLParser):
    """Collects <p> text and the page's own description."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.description = ""
        self._depth = 0
        self._skip = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "nav", "footer", "aside", "form"):
            self._skip += 1
        if tag == "meta" and not self.description:
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in ("og:description", "description"):
                self.description = clean_text(attrs.get("content") or "")
        if tag == "p" and not self._skip:
            self._depth += 1
            self._buffer = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "aside", "form") and self._skip:
            self._skip -= 1
        if tag == "p" and self._depth:
            self._depth -= 1
            text = " ".join("".join(self._buffer).split())
            if len(text) >= 60:
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self._depth and not self._skip:
            self._buffer.append(data)


# Lines that are page furniture, not reporting.
BOILERPLATE = re.compile(
    r"(cookie|abonnez-vous|newsletter|publicité|tous droits réservés|javascript|"
    r"inscrivez-vous|connectez-vous|commentaire|partager sur)",
    re.IGNORECASE,
)


def article_text(page_html: str) -> str:
    parser = _ParagraphParser()
    try:
        parser.feed(page_html or "")
    except Exception:
        pass
    parts = [parser.description] if parser.description else []
    for paragraph in parser.paragraphs:
        if BOILERPLATE.search(paragraph) or paragraph in parts:
            continue
        parts.append(paragraph)
        if sum(len(part) for part in parts) >= MAX_FACT_CHARS:
            break
    return " ".join(parts)[:MAX_FACT_CHARS].strip()


def title_words(title: str) -> set[str]:
    words = re.findall(r"[a-zà-ÿ0-9]+", (title or "").lower())
    return {word for word in words if word not in STOP_WORDS and len(word) > 1}


def same_story(title: str, other: str) -> bool:
    first, second = title_words(title), title_words(other)
    if not first or not second:
        return False
    return len(first & second) / min(len(first), len(second)) >= MAX_TITLE_OVERLAP


def load_history(path: Path = HISTORY_FILE) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def record_history(facts: NewsFacts, published_at: datetime, path: Path = HISTORY_FILE) -> None:
    history = load_history(path)
    history.append({
        "topic_id": facts.topic_id,
        "title": facts.title,
        "url": facts.url,
        "source": facts.source,
        "published_at": published_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history[-300:], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def collect_stories(
    *, now: datetime, fetch: Callable[[str], str] = _fetch_text, feeds: Iterable = FEEDS,
) -> list[dict]:
    """Fresh GTA 6 headlines from every feed that answers, newest first."""
    stories = []
    oldest = now - timedelta(hours=MAX_AGE_HOURS)
    for source, feed_url in feeds:
        try:
            rows = parse_feed(fetch(feed_url), source)
        except Exception as exc:
            print(f"GTA 6 news: {source} feed unavailable ({exc}).")
            continue
        kept = 0
        for row in rows:
            if not row["title"] or not row["url"].startswith("http"):
                continue
            if not is_gta6(row["title"]):
                continue
            if row["published"] is None or not oldest <= row["published"] <= now + timedelta(hours=1):
                continue
            stories.append(row)
            kept += 1
        print(f"GTA 6 news: {source} gave {kept} fresh GTA 6 headline(s).")
    stories.sort(key=lambda row: row["published"], reverse=True)
    return stories


def iter_news(
    published_topic_ids: set[str],
    *,
    now: datetime,
    history: list[dict] | None = None,
    fetch: Callable[[str], str] = _fetch_text,
    feeds: Iterable = FEEDS,
    max_lookups: int = MAX_ARTICLE_LOOKUPS,
):
    """Yield usable stories, newest first, skipping anything already covered."""
    history = history if history is not None else load_history()
    covered = [str(entry.get("title") or "") for entry in history]
    lookups = 0
    for row in collect_stories(now=now, fetch=fetch, feeds=feeds):
        facts_id = "gta6-" + hashlib.sha1(row["url"].encode("utf-8")).hexdigest()[:12]
        if facts_id in published_topic_ids:
            continue
        if any(same_story(row["title"], title) for title in covered):
            continue
        if lookups >= max_lookups:
            return
        lookups += 1
        text = ""
        if "news.google.com" not in urlparse(row["url"]).netloc:
            try:
                text = article_text(fetch(row["url"]))
            except Exception as exc:
                print(f"GTA 6 news: could not read {row['url']} ({exc}).")
        # The feed's own summary is the fallback when the page cannot be read.
        if len(text) < MIN_FACT_CHARS and len(row["summary"]) > len(text):
            text = row["summary"][:MAX_FACT_CHARS]
        if len(text) < MIN_FACT_CHARS:
            print(f"GTA 6 news: skipped '{row['title']}' ({row['source']}), only {len(text)} characters of text.")
            continue
        yield NewsFacts(
            title=row["title"], url=row["url"], source=row["source"],
            published=row["published"], text=text,
        )
