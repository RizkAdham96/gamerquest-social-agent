"""Produce and publish one GTA 6 news Reel.

The same pipeline as the hidden-gem Reel (script → fact-check → voice →
word captions → 1080x1920 render → Instagram), with the content swapped:
the story is a fresh GTA 6 article and the footage is the day's most-watched
GTA 6 Twitch clips (an official Rockstar trailer when Twitch is unavailable). A story that fails any check is skipped and the next one is tried;
nothing is published unless every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path

from agent.gta6_news import NewsFacts, iter_news, load_history, record_history
from app.config import Settings
from automation.daily_reel import (
    MAX_REEL_SECONDS,
    MIN_REEL_SECONDS,
    VOICE_TAIL_SECONDS,
    DailyReelResult,
    daily_slot_reason,
    env_flag,
    narration_seconds,
)
from content.gem_script import ScriptRejected
from content.gta6_script import GTA6_HASHTAGS, write_gta6_script
from content.voice import synthesize
from content.word_captions import build_karaoke_ass
from media.gem_reel import VOICE_FILE, render_reel
from media.gta6_footage import footage_library, footage_window
from media.twitch_clips import (
    TwitchClips,
    load_skip_list,
    load_used_clips,
    record_used_clips,
)
from media.twitch_clips import credentials as twitch_credentials
from storage.publish_log import PublishLog

MAX_STORIES_PER_RUN = 6
MAX_SCRIPT_REJECTIONS_PER_RUN = 3
# A dark clip or night shot can make the footage too dim for the renderer.
MAX_FOOTAGE_TRIES = 4
MAX_REELS_PER_DAY = 3
MIN_HOURS_BETWEEN_REELS = 3.0
EARLIEST_PUBLISH_HOUR_UTC = 9
PUBLISH_LOG = Path("state/gta6_publish_log.json")


@dataclass(frozen=True)
class Footage:
    path: Path
    credits: list[str] = field(default_factory=list)
    clip_ids: list[str] = field(default_factory=list)


class FootageSource:
    """Fresh Twitch clips first; the official trailer library when Twitch fails."""

    def __init__(self, *, now: datetime, twitch=None, load_library=footage_library,
                 cut_window=footage_window, used_clips: set[str] | None = None,
                 skip_streamers: set[str] | None = None):
        self.now = now
        self.twitch = twitch
        self.load_library = load_library
        self.cut_window = cut_window
        self.used_clips = used_clips if used_clips is not None else load_used_clips()
        self.skip_streamers = skip_streamers if skip_streamers is not None else load_skip_list()
        self._library = None

    def get(self, seconds: float, output_dir: Path, *, seed: str, exclude: set[str]) -> Footage:
        if self.twitch is not None:
            try:
                montage = self.twitch.montage(
                    seconds, output_dir, now=self.now,
                    skip_ids=self.used_clips | exclude, skip_streamers=self.skip_streamers,
                )
                return Footage(montage.path, montage.credits, [clip.id for clip in montage.clips])
            except Exception as exc:
                print(f"Twitch clips unavailable for this Reel ({exc}); using the trailer library.")
        if self._library is None:
            self._library = self.load_library()
        return Footage(self.cut_window(self._library, seconds, output_dir, seed=seed))


def with_credits(caption: str, credits: list[str]) -> str:
    if not credits:
        return caption
    line = "🎥 Clips Twitch : " + ", ".join(credits)
    if GTA6_HASHTAGS in caption:
        return caption.replace(GTA6_HASHTAGS, f"{line}\n\n{GTA6_HASHTAGS}")
    return f"{caption}\n\n{line}"


def produce(
    facts: NewsFacts, output_dir: Path, *, footage,
    write_script=write_gta6_script, speak=synthesize, render=render_reel,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    script = write_script(facts)
    voice_path = output_dir / VOICE_FILE
    spoken = speak(script.on_screen_text, voice_path)
    seconds = round(max(spoken[-1].end, narration_seconds(voice_path)) + VOICE_TAIL_SECONDS, 2)
    if not MIN_REEL_SECONDS <= seconds <= MAX_REEL_SECONDS:
        raise ScriptRejected(f"the script would run {seconds:.1f}s")
    captions = build_karaoke_ass(spoken, script.on_screen_text)
    last_error: Exception | None = None
    refused: set[str] = set()
    for attempt in range(MAX_FOOTAGE_TRIES):
        chosen = footage.get(seconds, output_dir, seed=f"{facts.topic_id}-{attempt}", exclude=refused)
        try:
            rendered = render(
                trailer=chosen.path, captions_ass=captions, reel_seconds=seconds,
                output_dir=output_dir, voice=voice_path,
            )
            break
        except RuntimeError as exc:
            last_error = exc
            # A dark or broken clip set is not offered again in this run.
            refused.update(chosen.clip_ids)
            print(f"Footage {attempt + 1} refused: {exc}")
    else:
        raise RuntimeError(f"no usable footage: {last_error}")
    script = replace(script, caption=with_credits(script.caption, chosen.credits))
    (output_dir / "script.json").write_text(
        json.dumps(
            {
                "kind": "gta6",
                "title": facts.title,
                "source": facts.source,
                "url": facts.url,
                "article_text": facts.text,
                "body": script.body,
                "on_screen_text": script.on_screen_text,
                "caption": script.caption,
                "twitch_clips": chosen.clip_ids,
                "duration_seconds": seconds,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return script, rendered, chosen.clip_ids


def run_once(
    *,
    output_dir: Path,
    publish_log_path: Path,
    live_publish: bool,
    orchestrator=None,
    stories=None,
    footage=None,
    produce_fn=produce,
    now: datetime | None = None,
    allow_extra_today: bool = False,
    max_per_day: int = MAX_REELS_PER_DAY,
    min_gap_hours: float = MIN_HOURS_BETWEEN_REELS,
    earliest_hour: int = 0,
    history_path: Path | None = None,
    used_clips_path: Path | None = None,
) -> DailyReelResult:
    now = now or datetime.now(timezone.utc)
    publish_log = PublishLog(publish_log_path)
    if live_publish and not allow_extra_today:
        reason = daily_slot_reason(publish_log_path, now, max_per_day, min_gap_hours, earliest_hour)
        if reason:
            return DailyReelResult(status="skipped", reason=reason)

    history_kwargs = {"path": history_path} if history_path else {}
    if stories is None:
        stories = iter_news(publish_log.topic_ids(), now=now, history=load_history(**history_kwargs))
    stories = iter(stories)
    first = next(stories, None)
    if first is None:
        return DailyReelResult(status="skipped", reason="no fresh GTA 6 story to cover")
    if footage is None:
        client_id, client_secret = twitch_credentials()
        twitch = TwitchClips(client_id, client_secret) if client_id and client_secret else None
        if twitch is None:
            print("Twitch: no TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET; using the trailer library.")
        footage = FootageSource(now=now, twitch=twitch)

    reasons = []
    tried = rejected = 0
    for facts in chain([first], stories):
        if tried >= MAX_STORIES_PER_RUN or rejected >= MAX_SCRIPT_REJECTIONS_PER_RUN:
            break
        tried += 1
        print(f"Story {tried}: {facts.title} ({facts.source}, {facts.published:%Y-%m-%d %H:%M} UTC)")
        try:
            script, rendered, clip_ids = produce_fn(facts, Path(output_dir), footage=footage)
        except (RuntimeError, OSError) as exc:
            rejected += isinstance(exc, ScriptRejected)
            reasons.append(f"{facts.title}: {exc}")
            print(f"Skipped '{facts.title}': {exc}")
            continue

        if not live_publish:
            return DailyReelResult(
                status="dry-run", topic_id=facts.topic_id, game=facts.title,
                reel_path=str(rendered.path), duration_seconds=rendered.duration_seconds,
            )
        published = orchestrator.publish_reel(
            topic_id=facts.topic_id, reel_path=rendered.path, caption=script.caption,
        )
        record_history(facts, now, **history_kwargs)
        record_used_clips(clip_ids, **({"path": used_clips_path} if used_clips_path else {}))
        return DailyReelResult(
            status="published", topic_id=facts.topic_id, game=facts.title,
            reel_path=str(rendered.path), duration_seconds=rendered.duration_seconds,
            media_id=str(published.media_id),
        )

    return DailyReelResult(
        status="skipped",
        reason="no story passed every check: " + " | ".join(reasons or ["no suitable story"]),
    )


def gta6_settings() -> Settings:
    """The main account's settings, or a separate GTA 6 account when one is set."""
    settings = Settings.from_env()
    user_id = os.getenv("GQ_GTA6_INSTAGRAM_USER_ID", "").strip()
    token = os.getenv("GQ_GTA6_INSTAGRAM_ACCESS_TOKEN", "").strip()
    if user_id and token:
        settings = replace(settings, instagram_user_id=user_id, instagram_access_token=token)
    return settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce a GamerQuest GTA 6 news Reel")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--publish-log", type=Path, default=PUBLISH_LOG)
    args = parser.parse_args()

    live_publish = env_flag("GQ_LIVE_PUBLISH", False)
    orchestrator = None
    if live_publish:
        from automation.main import build_publish_orchestrator

        orchestrator = build_publish_orchestrator(gta6_settings(), PublishLog(args.publish_log))

    result = run_once(
        output_dir=args.output_dir,
        publish_log_path=args.publish_log,
        live_publish=live_publish,
        orchestrator=orchestrator,
        allow_extra_today=env_flag("GQ_ALLOW_EXTRA_REEL", False),
        max_per_day=int(os.getenv("GQ_GTA6_MAX_REELS_PER_DAY", "").strip() or MAX_REELS_PER_DAY),
        earliest_hour=EARLIEST_PUBLISH_HOUR_UTC if os.getenv("GITHUB_EVENT_NAME") == "schedule" else 0,
    )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
