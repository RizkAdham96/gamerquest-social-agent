# Sprint 4 — Instagram automatic publishing

Sprint 4 adds the production-side Instagram publishing adapter and safety gates.

## Implemented

- Meta Graph API Reel container creation (`media_type=REELS`)
- configurable Graph API version, default `v26.0`
- container status polling until `FINISHED`
- explicit failure on `ERROR`, `EXPIRED`, and unexpected already-`PUBLISHED` states
- final `media_publish` call
- durable JSON publish log
- duplicate-topic protection before any Meta API call
- rolling 7-day publish cap (default: 3 Reels)
- public-URL validation before container creation

## Required Meta configuration

Facebook Login path:
- `instagram_basic`
- `instagram_content_publish`
- `pages_show_list`
- `pages_read_engagement`

Instagram Login path uses the corresponding `instagram_business_*` permissions, including `instagram_business_content_publish`.

## Important public-media requirement

Meta fetches the Reel from `video_url`. The URL must therefore be reachable publicly over HTTP(S) while Meta is creating the container.

Google Drive is used as the archive in this project, but a normal private Drive URL is **not** treated as the publishing CDN URL. A public temporary media-hosting step will be wired into the end-to-end scheduled workflow separately.

## Example

```python
from social.instagram_publish import InstagramPublisher
from social.instagram_pipeline import InstagramPublishPipeline
from storage.publish_log import PublishLog

publisher = InstagramPublisher(
    ig_user_id="YOUR_IG_USER_ID",
    access_token="YOUR_TOKEN",
    api_version="v26.0",
)

pipeline = InstagramPublishPipeline(
    publisher=publisher,
    publish_log=PublishLog("data/publish_log.json"),
    max_reels_per_week=3,
)

result = pipeline.publish(
    topic_id="topic-id",
    media_url="https://public-cdn.example/reel.mp4",
    caption="Ton caption GamerQuestFR",
)
print(result.media_id)
```
