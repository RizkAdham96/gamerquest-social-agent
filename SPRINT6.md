# Sprint 6 — GitHub Actions orchestration

Sprint 6 turns the existing modules into one scheduled end-to-end job while keeping the existing `gamerquest-automation` repository completely untouched.

## What it does

- Runs Monday, Wednesday, and Friday at 17:00 UTC.
- Runs the full pytest suite before content generation.
- Loads candidate topics from `GQ_TOPICS_URL`.
- Selects the best eligible topic and builds a French script/caption.
- Finds/downloads official footage, renders a 9:16 Reel, French voice-over, subtitles and audio.
- In dry-run mode, stops after rendering and uploads the result as a GitHub Actions artifact.
- In live mode, stages the MP4 temporarily as a public GitHub Release asset, publishes it through Meta, then removes the temporary staging asset.
- Saves every generated Reel as a downloadable GitHub Actions artifact for 90 days.
- Persists `state/publish_log.json` back to this repo so duplicate protection and the rolling 3-Reels-per-7-days cap work across workflow runs.

## Required GitHub configuration before live mode

Repository variables:
- `GQ_LIVE_PUBLISH` = `false` for the first dry run; switch to `true` only after verification.
- `GQ_TOPICS_URL` = public JSON endpoint containing candidate topics.
- Optional: `GQ_MAX_REELS_PER_WEEK` (default `3`), `GQ_MIN_TOPIC_SCORE` (default `55`), `GQ_META_API_VERSION` (default `v26.0`).

Repository secrets:
- `GQ_INSTAGRAM_USER_ID`
- `GQ_INSTAGRAM_ACCESS_TOKEN`
- Optional: `GQ_YOUTUBE_API_KEY`.

GitHub's built-in `GITHUB_TOKEN` is used for temporary Release staging and does not need to be added manually.

## Safety gate

The scheduled workflow refuses to publish live when `GQ_TOPICS_URL` is missing. It never uses `topics.sample.json` for a live publish.
