"""Fresh GTA 6 footage from Twitch clips (free official API).

Each run asks Twitch for the most-watched GTA 6 clips of the last day, skips
clips already used and streamers on the skip list, downloads a few with
yt-dlp and joins them into one silent 1920x1080 montage. The renderer then
cuts the Reel from that montage, like it does from a trailer. Streamers are
credited in the caption.

Needs a free Twitch developer app: TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from media.gem_reel import TRAILER_FILE, probe

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"
GAME_NAMES = ("Grand Theft Auto VI", "Grand Theft Auto 6", "GTA VI")
USED_CLIPS_FILE = Path("state/gta6_used_clips.json")
SKIP_LIST_FILE = Path("gta6/streamer_skip_list.json")
LOOKBACK_HOURS = 24
MIN_CLIP_SECONDS = 10.0
MAX_CLIPS_PER_REEL = 6
# Clips open on a webcam reaction or a cut-in; their first second is dropped.
CLIP_HEAD_SKIP = 1.0
# The montage is longer than the Reel so the cuts are spread over varied shots.
MONTAGE_FACTOR = 1.5
MIN_EXTRA_SECONDS = 15.0


@dataclass(frozen=True)
class Clip:
    id: str
    url: str
    broadcaster: str
    title: str
    views: int
    duration: float
    language: str = ""


@dataclass(frozen=True)
class Montage:
    path: Path
    clips: list[Clip]

    @property
    def credits(self) -> list[str]:
        names = []
        for clip in self.clips:
            if clip.broadcaster not in names:
                names.append(clip.broadcaster)
        return names


def _request_json(url: str, *, headers: dict | None = None, data: bytes | None = None) -> dict:
    request = Request(url, headers={"User-Agent": "gamerquest-social-agent", **(headers or {})}, data=data)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def credentials() -> tuple[str, str]:
    return (
        os.getenv("TWITCH_CLIENT_ID", "").strip(),
        os.getenv("TWITCH_CLIENT_SECRET", "").strip(),
    )


class TwitchClips:
    def __init__(self, client_id: str, client_secret: str, *, request=_request_json, run=subprocess.run,
                 probe_fn=probe, game_id: str | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.request = request
        self.run = run
        self.probe = probe_fn
        self.game_id = game_id if game_id is not None else os.getenv("GQ_TWITCH_GAME_ID", "").strip()
        self._token = ""

    def _headers(self) -> dict:
        if not self._token:
            reply = self.request(
                TOKEN_URL,
                data=urlencode({
                    "client_id": self.client_id, "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                }).encode("utf-8"),
            )
            self._token = str(reply.get("access_token") or "")
            if not self._token:
                raise RuntimeError("Twitch refused the app credentials")
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {self._token}"}

    def find_game_id(self) -> str:
        if self.game_id:
            return self.game_id
        for name in GAME_NAMES:
            data = self.request(f"{HELIX}/games?{urlencode({'name': name})}", headers=self._headers())
            for game in data.get("data") or []:
                self.game_id = str(game["id"])
                print(f"Twitch: GTA 6 category is '{game.get('name')}' ({self.game_id}).")
                return self.game_id
        raise RuntimeError("Twitch has no GTA 6 category under the expected names")

    def top_clips(self, now: datetime) -> list[Clip]:
        query = urlencode({
            "game_id": self.find_game_id(),
            "started_at": (now - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ended_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "first": 100,
        })
        data = self.request(f"{HELIX}/clips?{query}", headers=self._headers())
        clips = [
            Clip(
                id=str(row["id"]), url=str(row["url"]), broadcaster=str(row.get("broadcaster_name") or ""),
                title=str(row.get("title") or ""), views=int(row.get("view_count") or 0),
                duration=float(row.get("duration") or 0), language=str(row.get("language") or ""),
            )
            for row in data.get("data") or []
        ]
        clips.sort(key=lambda clip: clip.views, reverse=True)
        return clips

    def _download(self, clip: Clip, folder: Path) -> Path | None:
        target = folder / f"clip-{clip.id}.mp4"
        ytdlp = shutil.which("yt-dlp") or "yt-dlp"
        try:
            self.run(
                [ytdlp, "--quiet", "--no-warnings", "-f", "best[height<=1080]/best",
                 "-o", str(target), clip.url],
                check=True, capture_output=True, text=True, timeout=300,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            print(f"Twitch: could not download clip {clip.id} ({str(detail).strip()[:200]}).")
            return None
        return target if target.exists() and target.stat().st_size > 0 else None

    def _normalise(self, source: Path, target: Path, seconds: float) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self.run(
            [
                ffmpeg, "-v", "error", "-y", "-ss", f"{CLIP_HEAD_SKIP}", "-i", str(source),
                "-t", f"{seconds:.2f}", "-an",
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                str(target),
            ],
            check=True, capture_output=True,
        )

    def montage(
        self, reel_seconds: float, output_dir: Path, *, now: datetime,
        skip_ids: set[str] = frozenset(), skip_streamers: set[str] = frozenset(),
    ) -> Montage:
        """Join the top unused clips into output_dir/trailer.mp4 (silent)."""
        wanted = max(reel_seconds * MONTAGE_FACTOR, reel_seconds + MIN_EXTRA_SECONDS)
        work = output_dir / "clips"
        work.mkdir(parents=True, exist_ok=True)
        parts: list[Path] = []
        used: list[Clip] = []
        streamers: set[str] = set()
        total = 0.0
        for clip in self.top_clips(now):
            if total >= wanted or len(used) >= MAX_CLIPS_PER_REEL:
                break
            name = clip.broadcaster.lower()
            if clip.id in skip_ids or name in skip_streamers or clip.duration < MIN_CLIP_SECONDS:
                continue
            # One clip per streamer keeps the Reel varied and spreads the credit.
            if name in streamers:
                continue
            downloaded = self._download(clip, work)
            if downloaded is None:
                continue
            try:
                length = self.probe(downloaded)["duration"] - CLIP_HEAD_SKIP
                if length < MIN_CLIP_SECONDS - CLIP_HEAD_SKIP:
                    continue
                part = work / f"part-{len(parts):02d}.mp4"
                self._normalise(downloaded, part, length)
            except Exception as exc:
                print(f"Twitch: clip {clip.id} is unusable ({exc}).")
                continue
            parts.append(part)
            used.append(clip)
            streamers.add(name)
            total += length
        if total < reel_seconds + 12:
            raise RuntimeError(
                f"only {total:.0f}s of new GTA 6 Twitch clips for a {reel_seconds:.0f}s Reel"
            )
        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
        target = output_dir / TRAILER_FILE
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self.run(
            [ffmpeg, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", str(target.resolve())],
            check=True, capture_output=True, cwd=work,
        )
        print("Twitch: montage of " + ", ".join(f"{c.broadcaster} ({c.views} vues)" for c in used))
        return Montage(path=target, clips=used)


def load_used_clips(path: Path = USED_CLIPS_FILE) -> set[str]:
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return set()


def record_used_clips(clip_ids: list[str], path: Path = USED_CLIPS_FILE) -> None:
    existing = []
    try:
        existing = list(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        pass
    merged = existing + [clip_id for clip_id in clip_ids if clip_id not in existing]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged[-1000:], indent=1) + "\n", encoding="utf-8")


def load_skip_list(path: Path = SKIP_LIST_FILE) -> set[str]:
    try:
        return {str(name).strip().lower() for name in json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError, TypeError):
        return set()
