"""Produce and publish one hidden-gem Reel.

Each candidate game must pass every gate (suitable store page, script checks,
fact-check, render verification). A game that fails any of them is skipped and
the next one is tried; nothing is published unless all gates passed.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.hidden_gems import GameFacts, iter_games, load_candidates
from app.config import Settings
from content.gem_script import ScriptRejected, write_gem_script
from content.voice import synthesize
from content.word_captions import build_phrase_cues, cues_to_ass
from media.gem_reel import VOICE_FILE, download_trailer, render_reel
from storage.publish_log import PublishLog

MAX_GAMES_PER_RUN = 3
MIN_REEL_SECONDS = 14.0
MAX_REEL_SECONDS = 40.0
VOICE_TAIL_SECONDS = 0.8
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DailyReelResult:
    status: str
    topic_id: str = ""
    game: str = ""
    reel_path: str = ""
    duration_seconds: float = 0.0
    media_id: str = ""
    reason: str = ""


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_VALUES


def produce(facts: GameFacts, output_dir: Path, *, write_script=write_gem_script,
            speak=synthesize, fetch_trailer=download_trailer, render=render_reel):
    script = write_script(facts)
    output_dir.mkdir(parents=True, exist_ok=True)
    voice_path = output_dir / VOICE_FILE
    # The narration sets the Reel's length and the captions follow its timing,
    # so a Reel is never published silent or out of step with its text.
    spoken = speak(script.on_screen_text, voice_path)
    cues = build_phrase_cues(spoken, script.on_screen_text)
    seconds = round(spoken[-1].end + VOICE_TAIL_SECONDS, 2)
    if not MIN_REEL_SECONDS <= seconds <= MAX_REEL_SECONDS:
        raise ScriptRejected(f"the script would run {seconds:.1f}s")
    trailer = fetch_trailer(facts.trailer_url, output_dir)
    rendered = render(
        trailer=trailer,
        captions_ass=cues_to_ass(cues, style="Phrase"),
        reel_seconds=seconds,
        output_dir=output_dir,
        voice=voice_path,
    )
    (output_dir / "script.json").write_text(
        json.dumps(
            {
                "game": facts.name,
                "store_url": facts.store_url,
                "official_description": facts.description,
                "body": script.body,
                "on_screen_text": script.on_screen_text,
                "caption": script.caption,
                "duration_seconds": seconds,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return script, rendered


def published_today(log_path: Path, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if not log_path.exists():
        return False
    for record in json.loads(log_path.read_text(encoding="utf-8")):
        stamp = str(record.get("published_at") or "")
        try:
            published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if published.astimezone(timezone.utc).date() == now.date():
            return True
    return False


def run_once(
    *,
    output_dir: Path,
    publish_log_path: Path,
    live_publish: bool,
    orchestrator=None,
    candidates: list[dict] | None = None,
    games=None,
    produce_fn=produce,
    now: datetime | None = None,
) -> DailyReelResult:
    now = now or datetime.now(timezone.utc)
    publish_log = PublishLog(publish_log_path)
    if live_publish and published_today(publish_log_path, now):
        return DailyReelResult(status="skipped", reason="a Reel was already published today")

    if games is None:
        candidates = candidates if candidates is not None else load_candidates()
        if not candidates:
            return DailyReelResult(status="skipped", reason="no candidate games available")
        games = iter_games(candidates, publish_log.topic_ids(), seed=now.strftime("%Y-%m-%d"))

    reasons = []
    for attempt, facts in enumerate(games, start=1):
        if attempt > MAX_GAMES_PER_RUN:
            break
        print(f"Candidate {attempt}: {facts.name} ({facts.review_percent}% positive)")
        try:
            script, rendered = produce_fn(facts, Path(output_dir))
        except (ScriptRejected, RuntimeError, OSError) as exc:
            reasons.append(f"{facts.name}: {exc}")
            print(f"Skipped {facts.name}: {exc}")
            continue

        if not live_publish:
            return DailyReelResult(
                status="dry-run", topic_id=facts.topic_id, game=facts.name,
                reel_path=str(rendered.path), duration_seconds=rendered.duration_seconds,
            )
        published = orchestrator.publish_reel(
            topic_id=facts.topic_id, reel_path=rendered.path, caption=script.caption,
        )
        return DailyReelResult(
            status="published", topic_id=facts.topic_id, game=facts.name,
            reel_path=str(rendered.path), duration_seconds=rendered.duration_seconds,
            media_id=str(published.media_id),
        )

    return DailyReelResult(
        status="skipped",
        reason="no candidate passed every check: " + " | ".join(reasons or ["no suitable game"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce the daily GamerQuest hidden-gem Reel")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--publish-log", type=Path, default=Path("state/publish_log.json"))
    args = parser.parse_args()

    live_publish = env_flag("GQ_LIVE_PUBLISH", False)
    orchestrator = None
    if live_publish:
        from automation.main import build_publish_orchestrator

        orchestrator = build_publish_orchestrator(Settings.from_env(), PublishLog(args.publish_log))

    result = run_once(
        output_dir=args.output_dir,
        publish_log_path=args.publish_log,
        live_publish=live_publish,
        orchestrator=orchestrator,
    )
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
