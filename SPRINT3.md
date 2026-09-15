# Sprint 3 — Production Integrations

Sprint 3 connects the Reel engine to real external sources while preserving safe fallbacks.

## Added

- Official footage discovery from an explicit trusted URL.
- Steam trailer discovery for topics with a Steam app ID. Steam results expose direct trailer files that the renderer can download.
- YouTube Data API search restricted to explicitly trusted publisher/developer channel IDs. YouTube results are discovery references only; watch-page URLs are never downloaded by the agent.
- Direct-footage downloader that accepts HTTPS direct video files and rejects YouTube watch pages or non-media URLs.
- `EdgeTTS` natural French neural voice path using `fr-FR-DeniseNeural` by default.
- `SmartFrenchTTS` fallback chain: Edge neural voice first, then offline eSpeak if the network/provider fails.
- Google Drive v3 folder creation and multipart file upload.
- Drive access-token and service-account token providers.
- `ReelProductionPipeline` orchestrating discovery -> download -> render -> optional Drive archive.

## Required production secrets

- `GQ_YOUTUBE_API_KEY` if YouTube official-channel discovery is enabled.
- `GQ_GOOGLE_DRIVE_ROOT_FOLDER_ID` for the archive location.
- Either a short-lived Drive access token for testing or a service-account credentials file for unattended jobs.

## Copyright/source rule

Only explicit official URLs, Steam store trailers, and videos returned from pre-approved publisher/developer YouTube channel IDs may be classified as official. The pipeline deliberately does not download YouTube watch pages.

## Voice behavior

When `edge-tts` is installed and reachable, the natural French neural voice is used. If the provider is unavailable, the Reel still renders using the offline eSpeak fallback.
