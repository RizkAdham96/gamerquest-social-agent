# Sprint 5 — Zero-cost public media staging

Meta must fetch a Reel from a public URL. Sprint 5 closes that gap without adding a paid CDN.

## Flow

1. Upload the generated MP4 as an asset on one fixed public GitHub prerelease (`gq-media-staging`).
2. Use GitHub's returned `browser_download_url` as Meta's `video_url`.
3. Create/poll/publish the Instagram Reel.
4. Archive the permanent MP4 in Google Drive.
5. Delete only the temporary GitHub release asset in a `finally` block.

The fixed release is reused, so the repository does not accumulate a new tag/release for every Reel.

## Requirements

- the future `gamerquest-social-agent` GitHub repository must be public for unauthenticated Meta fetching
- GitHub Actions token needs `contents: write` to create the staging release and upload/delete release assets
- Meta/Instagram credentials remain repository secrets
- Drive credentials remain repository secrets

## Modules

- `storage/github_release_stage.py`: create/reuse staging release, upload temporary asset, return public URL, cleanup asset
- `social/publish_orchestrator.py`: stage -> Instagram publish -> Drive archive -> cleanup

## Security

Never put Meta, Google, or GitHub credentials in source control. GitHub's `GITHUB_TOKEN` should be used from Actions when the staging release lives in the same repository.
