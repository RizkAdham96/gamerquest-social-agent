# GamerQuest Clean Newsroom Reel Quality Design

## Goal

Generate professional 9:16 GamerQuest news Reels whose visuals directly support the narration. The system must preserve source-media integrity and must never present a technically successful render as a publishable creative. Live Instagram publishing remains disabled during quality development and review.

## Approved visual direction

The approved direction is **B — Clean Newsroom**.

- Use relevant official gameplay, trailers, screenshots, or article images.
- Preserve original image and footage colors.
- Do not apply global color tints, aggressive saturation, or stylistic filters.
- Do not stretch media or crop the principal subject out of frame.
- Use the real GamerQuest logo and established brand colors.
- Use restrained white or black caption cards with high contrast.
- Keep text away from faces, characters, HUD elements, and important action.
- Prefer factual information hierarchy over exaggerated social styling.

## Reel structure

Each Reel lasts approximately 15–25 seconds:

1. **Hook (0–3 seconds):** main verified news point with the most recognisable related visual.
2. **Context (3–9 seconds):** one or two factual details with a different relevant shot.
3. **Impact (9–16 seconds):** what the information means for players, visually illustrated.
4. **Close (final 3–5 seconds):** concise GamerQuest CTA and article reference.

No shot remains unchanged for the entire Reel. Shot changes follow narration rather than an arbitrary timer.

## Media relevance and integrity

Every visual asset records its source URL, publisher or rights-holder, game identity, content type, relevance confidence, and optional narration-beat assignment.

The producer rejects a render when:

- no media confidently matches the subject;
- media belongs to another game or story;
- the main subject cannot survive a 9:16 crop;
- a source cannot be downloaded reliably;
- the sequence cannot support at least two narration beats.

Subject-safe containment is preferred. A blurred or darkened background fill may sit behind landscape media, but the foreground remains sharp, correctly proportioned, and color-accurate.

## Caption system

- Maximum four words per phrase where practical.
- Break at punctuation and natural speech boundaries.
- Use sentence case, not continuous uppercase.
- Use a bold readable sans-serif face.
- Place captions inside compact high-contrast cards.
- Keep captions within Instagram safe zones and away from the primary subject.
- Highlight at most one verified keyword per beat using a real GamerQuest accent color.
- Align timing to the voice; equal-duration chunks are lower-quality fallback only.

## Audio

- Use a natural French neural voice.
- Reject robotic fallback audio from publishable previews.
- Keep optional rights-cleared music low and ducked under narration.
- Normalize output for clear, non-clipping speech.

## Branding

Branding stays restrained:

- small real GamerQuest logo or wordmark in the top safe zone;
- established brand colors only;
- no permanent oversized banner;
- short end card with “L’essentiel du gaming, sans perdre ton temps.”

If the actual logo or definitive colors are unavailable, rendering stops rather than inventing branding.

## Quality gate

Every preview receives automated and human checks before publishing.

Automated checks:

- 1080×1920 H.264/AAC output;
- valid configured duration;
- present, non-silent audio;
- relevant visual assets;
- at least two distinct segments;
- captions inside safe bounds;
- no stretched media;
- no test labels, placeholder footage, or dry-run narration;
- review artifact created.

Human checks:

- inspect a contact sheet covering the full Reel;
- watch the complete preview with audio;
- explicitly approve or reject it.

Instagram remains off until explicit approval. A successful build means only that a preview was produced.

## Components

1. **Beat planner:** turns a verified article summary into timed editorial beats.
2. **Media matcher:** assigns relevant official assets and records provenance.
3. **Subject-safe compositor:** preserves aspect ratio and colors in 9:16.
4. **Caption renderer:** creates phrase-aware, voice-aligned caption cards.
5. **Audio mixer:** combines natural French narration with optional licensed music.
6. **Quality validator:** blocks placeholders, irrelevant media, unsafe layouts, and weak audio.
7. **Preview packager:** exports Reel, contact sheet, script, captions, and asset manifest.

## Error handling

Quality failures block publishing. The workflow records the reason, uploads diagnostics, and never calls Instagram. Temporary source failures may retry; relevance or rights failures require another asset.

## Testing

- Unit tests for beat planning, phrase segmentation, relevance, aspect ratio, safe-zone geometry, and placeholder rejection.
- FFmpeg command tests for color-preserving composition and audio normalization.
- Fixture renders for landscape video, portrait video, screenshots, and subject-safe fills.
- Integration test producing a preview pack without publishing.
- Regression test proving Big Buck Bunny cannot pass the publishable-quality gate.

## Out of scope

- Article-to-Reel automation bridge.
- Automatic Instagram publication.
- Paid AI image, video, or voice services.
- Replacing the website or existing article automation.
