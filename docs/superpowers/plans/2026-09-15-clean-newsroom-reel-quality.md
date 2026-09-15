# Clean Newsroom Reel Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a preview-only Reel pipeline that produces professional Clean Newsroom videos with narration-matched visuals, preserved source colors, safe composition, natural captions, and blocking quality validation.

**Architecture:** Add focused planning, media-manifest, composition, and validation units around the existing production pipeline. The orchestrator will produce a review package and will remain unable to publish unless a validated approval record exists; this plan stops at preview-only mode.

**Tech Stack:** Python 3.12, dataclasses, FFmpeg/ffprobe, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-clean-newsroom-reel-quality-design.md`

## Global Constraints

- Visual direction is **B — Clean Newsroom**.
- Preserve original media colors; no global tint or saturation filter.
- Do not stretch media or crop the principal subject out of frame.
- Use only relevant official or article-sourced media with provenance.
- Require at least two distinct visual segments.
- Use real GamerQuest branding; do not invent logo assets or colors.
- Captions use natural phrase boundaries, sentence case, and safe zones.
- Reject robotic fallback narration from publishable previews.
- Instagram live publishing remains disabled throughout this plan.
- No paid AI services.

---

## File Structure

- `content/beat_planner.py`: convert a verified topic into timed editorial beats.
- `media/asset_manifest.py`: define visual provenance, relevance, and beat assignments.
- `media/media_matcher.py`: validate and assign assets to beats.
- `media/clean_newsroom_compositor.py`: build color-safe FFmpeg segment filters.
- `media/audio_quality.py`: validate narration and define normalized mixing.
- `quality/reel_validator.py`: enforce blocking publishable-preview requirements.
- `quality/preview_package.py`: export review manifest and contact sheet.
- `automation/runner.py`: call the new preview pipeline without publishing.
- `.github/workflows/social-agent.yml`: upload complete review package.
- Focused tests mirror each new module under `tests/`.

### Task 1: Editorial Beat Planner

**Files:**
- Create: `content/beat_planner.py`
- Create: `tests/test_beat_planner.py`
- Modify: `app/models.py`

**Interfaces:**
- Consumes: `Topic(title, url, source, summary, tags)`
- Produces: `plan_beats(topic: Topic, duration_seconds: float) -> list[EditorialBeat]`
- `EditorialBeat(index: int, role: str, start: float, end: float, narration: str, visual_query: str)`

- [ ] **Step 1: Write failing model and behavior tests**

```python
from app.models import Topic
from content.beat_planner import plan_beats

def test_plan_has_hook_context_impact_and_close():
    topic = Topic(
        title="Le mode Horde arrive vendredi",
        url="https://gamerquestfr.com/horde",
        source="gamerquest",
        summary="Le studio confirme le mode Horde vendredi. Il sera jouable en coopération."
    )
    beats = plan_beats(topic, 20.0)
    assert [beat.role for beat in beats] == ["hook", "context", "impact", "close"]
    assert beats[0].start == 0.0
    assert beats[-1].end == 20.0
    assert all(a.end == b.start for a, b in zip(beats, beats[1:]))
    assert all(beat.visual_query.strip() for beat in beats[:-1])
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/test_beat_planner.py -v`  
Expected: FAIL because `content.beat_planner` and `EditorialBeat` do not exist.

- [ ] **Step 3: Implement deterministic four-beat planning**

Create the frozen `EditorialBeat` dataclass in `app/models.py`. Implement `plan_beats` with ratios `0.15, 0.30, 0.35, 0.20`, require a non-empty verified summary, and generate short factual French narration from the topic title and summary without adding facts.

- [ ] **Step 4: Run focused and full tests**

Run: `pytest tests/test_beat_planner.py -v && pytest -q`  
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py content/beat_planner.py tests/test_beat_planner.py
git commit -m "feat: plan factual Reel narration beats"
```

### Task 2: Provenance-Aware Media Manifest and Matcher

**Files:**
- Create: `media/asset_manifest.py`
- Create: `media/media_matcher.py`
- Create: `tests/test_media_matcher.py`
- Modify: `media/official_footage.py`

**Interfaces:**
- Consumes: `list[EditorialBeat]`, `list[VisualAsset]`
- Produces: `match_assets(beats, assets, minimum_confidence=0.8) -> list[BeatAsset]`
- `VisualAsset(url, source_url, publisher, game_id, media_type, confidence, width, height, is_official)`
- `BeatAsset(beat: EditorialBeat, asset: VisualAsset)`

- [ ] **Step 1: Write failing relevance and diversity tests**

```python
import pytest
from media.asset_manifest import VisualAsset
from media.media_matcher import MediaMatchError, match_assets

def test_matcher_rejects_wrong_game_and_requires_two_assets(beats):
    wrong = VisualAsset(
        url="https://cdn.example/other.mp4",
        source_url="https://publisher.example/other",
        publisher="Publisher",
        game_id="other-game",
        media_type="video",
        confidence=0.99,
        width=1920,
        height=1080,
        is_official=True,
    )
    with pytest.raises(MediaMatchError, match="matching visual assets"):
        match_assets(beats, [wrong], expected_game_id="target-game")

def test_matcher_records_two_distinct_relevant_assets(beats, relevant_assets):
    assigned = match_assets(beats, relevant_assets, expected_game_id="target-game")
    assert len({item.asset.url for item in assigned}) >= 2
    assert all(item.asset.confidence >= 0.8 for item in assigned)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/test_media_matcher.py -v`  
Expected: FAIL because the manifest and matcher do not exist.

- [ ] **Step 3: Implement manifest validation and deterministic assignment**

Validate HTTP(S) URLs, non-empty provenance, supported types `video|image`, positive dimensions, official status, matching `game_id`, and confidence `>= 0.8`. Assign the highest-confidence unused asset before reuse. Raise `MediaMatchError` when fewer than two distinct assets remain.

- [ ] **Step 4: Adapt official-footage discovery**

Return `VisualAsset` entries instead of anonymous candidates while preserving publisher and source URLs. Do not infer `is_official=True` for an untrusted host.

- [ ] **Step 5: Run focused and full tests**

Run: `pytest tests/test_media_matcher.py tests/test_official_footage.py -v && pytest -q`  
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add media/asset_manifest.py media/media_matcher.py media/official_footage.py tests/test_media_matcher.py tests/test_official_footage.py
git commit -m "feat: require relevant provenanced Reel media"
```

### Task 3: Color-Safe 9:16 Compositor

**Files:**
- Create: `media/clean_newsroom_compositor.py`
- Create: `tests/test_clean_newsroom_compositor.py`
- Modify: `media/reel_builder.py`

**Interfaces:**
- Consumes: `list[BeatAsset]`, output dimensions `1080x1920`
- Produces: `build_segment_filter(asset: VisualAsset) -> str`
- Produces: `build_timeline_filter(assignments: list[BeatAsset]) -> str`

- [ ] **Step 1: Write failing FFmpeg-filter tests**

```python
from media.clean_newsroom_compositor import build_segment_filter

def test_landscape_media_is_contained_without_color_filter(landscape_asset):
    value = build_segment_filter(landscape_asset)
    assert "force_original_aspect_ratio=decrease" in value
    assert "pad=1080:1920" in value
    assert "eq=" not in value
    assert "hue=" not in value
    assert "crop=1080:1920" not in value

def test_portrait_media_is_never_stretched(portrait_asset):
    value = build_segment_filter(portrait_asset)
    assert "setsar=1" in value
    assert "scale=1080:1920" not in value
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/test_clean_newsroom_compositor.py -v`  
Expected: FAIL because the compositor does not exist.

- [ ] **Step 3: Implement safe composition**

Use `scale=1080:1920:force_original_aspect_ratio=decrease`, centered padding, `setsar=1`, and source color metadata preservation. For landscape media, build a separately scaled blurred background layer and overlay the sharp contained foreground. Do not include `eq`, `hue`, or destructive full-frame crop filters.

- [ ] **Step 4: Replace the current global crop and saturation filter**

Change `ReelBuilder` to consume the compositor’s timeline filter. Remove `force_original_aspect_ratio=increase`, `crop=1080:1920`, and `eq=contrast=1.04:saturation=1.08`.

- [ ] **Step 5: Run focused, render, and full tests**

Run: `pytest tests/test_clean_newsroom_compositor.py tests/test_reel_builder.py -v && pytest -q`  
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add media/clean_newsroom_compositor.py media/reel_builder.py tests/test_clean_newsroom_compositor.py tests/test_reel_builder.py
git commit -m "feat: preserve source colors and aspect ratios"
```

### Task 4: Clean Caption Cards and Narration Quality

**Files:**
- Modify: `content/subtitle_writer.py`
- Modify: `media/reel_pipeline.py`
- Modify: `media/reel_builder.py`
- Create: `media/audio_quality.py`
- Create: `tests/test_audio_quality.py`
- Modify: `tests/test_subtitles.py`
- Modify: `tests/test_reel_builder.py`

**Interfaces:**
- Consumes: narration audio and `list[EditorialBeat]`
- Produces: phrase-safe SRT/ASS captions and `validate_narration(path: Path, provider_name: str) -> AudioReport`

- [ ] **Step 1: Write failing caption and audio tests**

```python
import pytest
from media.audio_quality import AudioQualityError, validate_narration

def test_robotic_fallback_is_not_publishable(tmp_path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"fixture")
    with pytest.raises(AudioQualityError, match="neural"):
        validate_narration(audio, provider_name="espeak", probe=lambda _: {"duration": 5, "mean_volume": -20})

def test_caption_style_has_cards_but_no_invented_color_filter(tmp_path):
    joined = " ".join(ReelBuilder().build_command(make_spec(tmp_path)))
    assert "BorderStyle=3" in joined
    assert "Alignment=2" in joined
    assert "eq=" not in joined
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_audio_quality.py tests/test_subtitles.py tests/test_reel_builder.py -v`  
Expected: FAIL because audio validation is absent and the old builder still applies color changes.

- [ ] **Step 3: Implement narration validation**

Use `ffprobe` to require duration `> 1.0` seconds and use FFmpeg `volumedetect` to reject silent audio below `-45 dB`. Mark `espeak` as preview-debug-only and raise `AudioQualityError` for a publishable preview.

- [ ] **Step 4: Implement restrained caption cards**

Keep punctuation-aware maximum-four-word phrases. Render sentence-case white text on compact black or white cards within safe margins. Remove the invented purple permanent banner. Require explicit logo path and brand accent configuration; missing values produce `BrandAssetError`.

- [ ] **Step 5: Run focused and full tests**

Run: `pytest tests/test_audio_quality.py tests/test_subtitles.py tests/test_reel_builder.py -v && pytest -q`  
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add content/subtitle_writer.py media/reel_pipeline.py media/reel_builder.py media/audio_quality.py tests/test_audio_quality.py tests/test_subtitles.py tests/test_reel_builder.py
git commit -m "feat: add Clean Newsroom captions and audio gate"
```

### Task 5: Blocking Quality Validator

**Files:**
- Create: `quality/__init__.py`
- Create: `quality/reel_validator.py`
- Create: `tests/test_reel_validator.py`
- Modify: `automation/runner.py`

**Interfaces:**
- Consumes: `ValidationInput(reel_path, assignments, captions, narration_report, is_dry_run)`
- Produces: `QualityReport(passed: bool, failures: tuple[str, ...])`
- Raises: `QualityGateError` before any publishing path.

- [ ] **Step 1: Write failing quality-gate regression tests**

```python
from quality.reel_validator import validate_preview

def test_big_buck_bunny_and_dry_run_copy_are_blocked(valid_input):
    bad = valid_input.replace(
        source_urls=("https://raw.githubusercontent.com/mediaelement/mediaelement-files/master/big_buck_bunny.mp4",),
        narration="GamerQuest dry run",
    )
    report = validate_preview(bad)
    assert not report.passed
    assert "placeholder media" in report.failures
    assert "test narration" in report.failures

def test_valid_preview_requires_two_visual_segments(valid_input):
    report = validate_preview(valid_input.replace(distinct_visuals=1))
    assert report.failures == ("fewer than two distinct visual segments",)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_reel_validator.py -v`  
Expected: FAIL because `quality.reel_validator` does not exist.

- [ ] **Step 3: Implement explicit blocking rules**

Check output resolution, codecs, duration, audio presence, non-silence, provenance, relevance confidence, distinct assets, caption bounds, placeholder denylist, test copy denylist, branding availability, and neural narration status. Return all failures together.

- [ ] **Step 4: Gate runner before publication**

Call `validate_preview` after rendering. Raise `QualityGateError` on any failure. Remove or hard-disable the publish-orchestrator call in this preview-quality branch.

- [ ] **Step 5: Run focused and full tests**

Run: `pytest tests/test_reel_validator.py tests/test_sprint6_main.py -v && pytest -q`  
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add quality automation/runner.py tests/test_reel_validator.py tests/test_sprint6_main.py
git commit -m "feat: block low-quality Reel previews"
```

### Task 6: Review Package and GitHub Workflow

**Files:**
- Create: `quality/preview_package.py`
- Create: `tests/test_preview_package.py`
- Modify: `automation/main.py`
- Modify: `.github/workflows/social-agent.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: Reel, script, captions, quality report, and asset manifest.
- Produces: `output/reel.mp4`, `output/contact-sheet.jpg`, `output/review.json`, `output/subtitles.srt`, and `output/assets.json`.

- [ ] **Step 1: Write failing preview-package test**

```python
import json
from quality.preview_package import create_preview_package

def test_package_contains_review_materials(tmp_path, preview_fixture):
    result = create_preview_package(tmp_path / "output", preview_fixture)
    assert result.reel.exists()
    assert result.contact_sheet.exists()
    review = json.loads(result.review_json.read_text())
    assert review["publish_enabled"] is False
    assert review["quality"]["passed"] is True
    assert len(review["assets"]) >= 2
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_preview_package.py -v`  
Expected: FAIL because preview packaging does not exist.

- [ ] **Step 3: Implement package generation**

Use FFmpeg to sample one frame per editorial beat into a labeled contact sheet. Serialize script, beat timings, asset provenance, audio report, validation result, and `publish_enabled: false` into `review.json`.

- [ ] **Step 4: Make GitHub Actions preview-only**

Set `GQ_LIVE_PUBLISH: false` unconditionally during this phase. Remove the demo Bunny topic. Require a real topic fixture or explicit preview input. Upload the entire `output/` package and fail if validation does not pass.

- [ ] **Step 5: Document the reviewer workflow**

Document where to download the artifact, which five files to inspect, and that a green Action means “valid preview package,” not “approved creative.”

- [ ] **Step 6: Run all verification**

Run: `pytest -q`  
Expected: all tests PASS.

Run a fixture render and verify with `ffprobe`:
```bash
ffprobe -v error -show_entries stream=codec_name,width,height -of json output/reel.mp4
```
Expected: video is H.264 at 1080×1920 and audio is AAC.

- [ ] **Step 7: Commit**

```bash
git add quality/preview_package.py tests/test_preview_package.py automation/main.py .github/workflows/social-agent.yml README.md
git commit -m "feat: produce reviewable Reel preview packages"
```

### Task 7: Final Regression and Visual Review

**Files:**
- Modify: tests only if a genuine uncovered regression is identified.
- Produce: local or Actions `output/` review package.

**Interfaces:**
- Consumes: the complete preview-only pipeline.
- Produces: evidence that the approved Clean Newsroom specification is met.

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -q`  
Expected: all tests PASS with zero skips related to the new quality gate.

- [ ] **Step 2: Generate one real-topic preview**

Use a verified GamerQuest topic with at least two relevant official assets. Keep publishing disabled.

- [ ] **Step 3: Inspect the contact sheet**

Confirm original colors, correct game, at least two visual changes, safe crops, readable cards, and no covered primary subject.

- [ ] **Step 4: Watch the complete Reel**

Confirm natural French voice, narration-to-visual agreement, readable pacing, no robotic fallback, and no audio clipping.

- [ ] **Step 5: Record approval status**

Set the human review status in the review record to `approved` or `rejected`; do not add any Instagram API call.

- [ ] **Step 6: Commit any verified regression fix separately**

```bash
git add <exact changed test and implementation files>
git commit -m "fix: address Clean Newsroom preview regression"
```

- [ ] **Step 7: Report evidence**

Provide the test count, workflow URL, artifact URL, selected topic, asset provenance summary, and explicit confirmation that Instagram publishing stayed disabled.
