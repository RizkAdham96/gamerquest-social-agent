# GamerQuest Social Agent

Standalone Instagram growth automation for GamerQuestFR. This repository is intentionally isolated from the existing carousel automation.

## Daily hidden-gem Reel

The scheduled workflow now publishes one Reel a day about a well-reviewed, little-known Steam game:

- `agent/hidden_gems.py` picks the game (SteamSpy review data, then the Steam store page for facts and the official trailer) and skips anything already published or unsuitable.
- `content/gem_script.py` asks Groq for a short French description built only from the store facts, validates it, and fact-checks it with a second call. The game's name, price and review figures are filled in by code, never by the model.
- `content/word_captions.py` shows the script one word at a time.
- `media/gem_reel.py` renders 1080x1920: the trailer centred over a blurred fill, with the game's own audio.
- `automation/daily_reel.py` ties it together. A game that fails any check is skipped and the next one is tried; nothing is published unless every check passed.

Required repository secrets: `GROQ_API_KEY`, `GQ_INSTAGRAM_USER_ID`, `GQ_INSTAGRAM_ACCESS_TOKEN`.

Dry run (renders `output/reel.mp4` and `output/script.json`, publishes nothing):

```bash
GROQ_API_KEY=... python -m automation.daily_reel --output-dir output
```

## Sprint 1

Implemented foundations:
- environment-based configuration
- topic model and JSON intake
- deterministic topic scoring
- duplicate-topic memory
- best-topic selection requiring official footage
- French Reel script and caption generation
- CLI preview command

## Preview

```bash
python -m app.main topics.json
```

Example `topics.json`:

```json
[
  {
    "title": "Hades est gratuit pendant 48 heures",
    "url": "https://example.com/hades",
    "source": "epic",
    "official_footage_url": "https://publisher.example/video.mp4",
    "tags": ["free-game"]
  }
]
```

## Sprint 2 — Reel generation layer

Sprint 2 adds the first complete local Reel-generation path:

- official-source footage candidate validation
- official footage candidate selection
- French subtitle segmentation and SRT export
- free offline French TTS fallback through `espeak`
- FFmpeg vertical 9:16 rendering (1080x1920, H.264/AAC)
- optional background-music mixing
- reusable `ReelPipeline` that ties narration, subtitles and rendering together

### Local render example

```python
from pathlib import Path
from media.reel_pipeline import ReelPipeline

ReelPipeline().render(
    footage=Path("input.mp4"),
    voiceover_text="Ton texte français ici.",
    output_dir=Path("output"),
    duration_seconds=15.0,
)
```

`output/` will contain `voice.wav`, `subtitles.srt`, and `reel.mp4`.

The offline `espeak` voice is intentionally a zero-cost fallback. A higher-quality neural/AI French TTS provider can plug into the same `TTSProvider` interface without changing the Reel builder.

## Sprint 3 additions

Sprint 3 adds production integrations: official-footage discovery, direct official-media downloads, natural French Edge TTS with an offline fallback, Google Drive uploads, and a single `ReelProductionPipeline` that joins the media steps together.

For unattended Drive jobs, prefer a service account or another renewable credential flow rather than committing access tokens. Never commit credentials to this repository.


## Sprint 4 additions

Sprint 4 adds Meta/Instagram Reel publishing: container creation, status polling, final publishing, local publish logging, duplicate-topic protection, and the rolling 3-Reels-per-week guard.

Meta must be able to fetch the Reel from a publicly accessible `video_url`. Google Drive remains the archival store; do not assume a private Drive link is a valid Meta ingestion URL. See `SPRINT4.md`.


## Sprint 5 additions

Sprint 5 closes Meta's public-media URL requirement with a temporary GitHub Release staging asset. The MP4 is staged publicly, published to Instagram, archived permanently in Google Drive, then removed from GitHub. See `SPRINT5.md`.


## Sprint 6 — scheduled automation

The standalone agent now includes `.github/workflows/social-agent.yml`, a Monday/Wednesday/Friday GitHub Actions workflow. It defaults to dry-run mode, runs tests first, renders a Reel, and saves the output as a downloadable GitHub Actions artifact for 90 days. Live publishing is enabled only with `GQ_LIVE_PUBLISH=true` plus the required Meta configuration. Google Cloud and Google Drive are not required. See `SPRINT6.md`.
