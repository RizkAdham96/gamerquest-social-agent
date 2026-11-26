"""Official GTA 6 footage for the news Reels.

GTA 6 is not on Steam, so there is no store trailer to stream. The Reels cut
from a small library of official Rockstar trailers instead:

1. any .mp4 attached to the GitHub release tagged ``gta6-footage`` (the
   reliable route: upload a trailer there once and every run reuses it);
2. otherwise the trailers listed in ``gta6/footage.json``, fetched with
   yt-dlp. GitHub's runners are sometimes refused by YouTube, so the workflow
   caches what it downloaded.

Each Reel takes a different random window of a trailer, so two Reels never
show the same cuts. The trailers' audio is dropped: it carries licensed music
that Instagram mutes or blocks, and the narration carries the Reel.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from media.gem_reel import TRAILER_FILE, probe

FOOTAGE_LIST = Path("gta6/footage.json")
CACHE_DIR = Path("footage_cache/gta6")
RELEASE_TAG = "gta6-footage"
MIN_FOOTAGE_SECONDS = 40.0
# Skip the Rockstar logo at the start and the title card at the end.
EDGE_SKIP_SECONDS = 8.0
# The window is wider than the Reel so the cuts are spread over varied shots.
WINDOW_FACTOR = 1.8
MIN_WINDOW_SECONDS = 50.0


def _github_get(url: str, token: str, accept: str = "application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "gamerquest-social-agent"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urlopen(Request(url, headers=headers), timeout=300)


def release_footage(
    cache_dir: Path = CACHE_DIR,
    *,
    repository: str | None = None,
    token: str | None = None,
    get=_github_get,
) -> list[Path]:
    """Download the release's .mp4 assets that are not cached yet."""
    repository = repository if repository is not None else os.getenv("GITHUB_REPOSITORY", "").strip()
    token = token if token is not None else os.getenv("GITHUB_TOKEN", "").strip()
    if not repository:
        return []
    try:
        with get(f"https://api.github.com/repos/{repository}/releases/tags/{RELEASE_TAG}", token) as response:
            release = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"GTA 6 footage: no '{RELEASE_TAG}' release ({exc}).")
        return []
    cache_dir.mkdir(parents=True, exist_ok=True)
    found = []
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if not name.lower().endswith(".mp4"):
            continue
        target = cache_dir / f"release-{name}"
        if not target.exists() or target.stat().st_size != int(asset.get("size") or -1):
            try:
                with get(str(asset["url"]), token, accept="application/octet-stream") as response:
                    with open(target, "wb") as handle:
                        shutil.copyfileobj(response, handle)
            except Exception as exc:
                print(f"GTA 6 footage: could not download release asset {name} ({exc}).")
                continue
        found.append(target)
    return found


def listed_footage(
    cache_dir: Path = CACHE_DIR, listing: Path = FOOTAGE_LIST, run=subprocess.run,
) -> list[Path]:
    """Download the listed official trailers that are not cached yet."""
    if not listing.exists():
        return []
    cache_dir.mkdir(parents=True, exist_ok=True)
    found = []
    for entry in json.loads(listing.read_text(encoding="utf-8")):
        target = cache_dir / f"{entry['id']}.mp4"
        if not target.exists() or target.stat().st_size == 0:
            ytdlp = shutil.which("yt-dlp") or "yt-dlp"
            try:
                run(
                    [
                        ytdlp, "--no-playlist", "--quiet", "--no-warnings",
                        # Video only: the audio is dropped anyway.
                        "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b[height<=1080]/b",
                        "--remux-video", "mp4",
                        "-o", str(target), str(entry["url"]),
                    ],
                    check=True, capture_output=True, text=True, timeout=600,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                detail = getattr(exc, "stderr", "") or str(exc)
                print(f"GTA 6 footage: could not download {entry['id']}: {str(detail).strip()[:300]}")
                target.unlink(missing_ok=True)
                continue
        if target.exists() and target.stat().st_size > 0:
            found.append(target)
    return found


def footage_library(cache_dir: Path = CACHE_DIR, *, run=subprocess.run, probe_fn=probe) -> list[Path]:
    library = release_footage(cache_dir) + listed_footage(cache_dir, run=run)
    usable = []
    for path in library:
        try:
            if probe_fn(path)["duration"] >= MIN_FOOTAGE_SECONDS:
                usable.append(path)
        except Exception as exc:
            print(f"GTA 6 footage: {path.name} is unreadable ({exc}).")
    if not usable:
        raise RuntimeError(
            "no GTA 6 footage available: attach an official trailer (.mp4) to a GitHub "
            f"release tagged '{RELEASE_TAG}', or check the yt-dlp errors above"
        )
    return usable


def footage_window(
    library: list[Path],
    reel_seconds: float,
    output_dir: Path,
    *,
    seed: str,
    run=subprocess.run,
    probe_fn=probe,
) -> Path:
    """Cut a random, silent window of one trailer to output_dir/trailer.mp4."""
    rng = random.Random(seed)
    source = rng.choice(sorted(library))
    duration = probe_fn(source)["duration"]
    window = min(
        max(reel_seconds * WINDOW_FACTOR, MIN_WINDOW_SECONDS),
        duration - 2 * EDGE_SKIP_SECONDS,
    )
    if window < reel_seconds + 12:
        # Short footage: use all of it and let the renderer spread the cuts.
        start, window = 0.0, duration
    else:
        start = rng.uniform(EDGE_SKIP_SECONDS, duration - EDGE_SKIP_SECONDS - window)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / TRAILER_FILE
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    run(
        [
            ffmpeg, "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", str(source),
            "-t", f"{window:.2f}", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
            str(target),
        ],
        check=True, capture_output=True,
    )
    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("the GTA 6 footage window could not be cut")
    print(f"GTA 6 footage: {source.name} from {start:.0f}s for {window:.0f}s.")
    return target
