"""Post a Reel to TikTok through the Content Posting API.

TikTok is an extra destination: every failure here is reported and swallowed
by the caller so the Instagram Reel is never held back by it.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://open.tiktokapis.com"
TOKEN_URL = f"{API}/v2/oauth/token/"
CREATOR_INFO_URL = f"{API}/v2/post/publish/creator_info/query/"
VIDEO_INIT_URL = f"{API}/v2/post/publish/video/init/"
STATUS_URL = f"{API}/v2/post/publish/status/fetch/"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"

REDIRECT_URI = "https://gamerquestfr.com/"
SCOPES = "user.info.basic,video.publish"
# Until TikTok has audited the app, the API only accepts private posts.
DEFAULT_PRIVACY = "SELF_ONLY"
MAX_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024
MAX_CAPTION_CHARS = 2200
STATUS_POLLS = 20
STATUS_POLL_SECONDS = 6.0


class TikTokError(RuntimeError):
    pass


@dataclass(frozen=True)
class TikTokTokens:
    access_token: str
    refresh_token: str
    open_id: str = ""


@dataclass(frozen=True)
class TikTokPost:
    publish_id: str
    status: str
    privacy_level: str


def authorize_url(client_key: str, state: str = "gamerquest") -> str:
    """The page the account owner opens once to connect the TikTok account."""
    query = urlencode({
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    })
    return f"{AUTHORIZE_URL}?{query}"


def _request(url: str, *, data: bytes, headers: dict, method: str = "POST", timeout: int = 120) -> dict:
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise TikTokError(f"TikTok HTTP {exc.code}: {detail}") from exc
    return json.loads(body) if body.strip() else {}


def _token_call(fields: dict, post: Callable[..., dict]) -> TikTokTokens:
    payload = post(
        TOKEN_URL,
        data=urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if not payload.get("access_token") or not payload.get("refresh_token"):
        # TikTok answers 200 with an error body for a bad or expired code.
        reason = payload.get("error_description") or payload.get("error") or "no tokens returned"
        raise TikTokError(f"TikTok did not issue tokens: {reason}")
    return TikTokTokens(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        open_id=str(payload.get("open_id") or ""),
    )


def exchange_code(client_key: str, client_secret: str, code: str, post=_request) -> TikTokTokens:
    return _token_call(
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        post,
    )


def refresh_tokens(client_key: str, client_secret: str, refresh_token: str, post=_request) -> TikTokTokens:
    """Access tokens last a day; each run trades the refresh token for a new pair."""
    return _token_call(
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        post,
    )


def _api(url: str, access_token: str, body: dict, post) -> dict:
    payload = post(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
    )
    error = payload.get("error") or {}
    if error.get("code") not in (None, "", "ok"):
        raise TikTokError(f"TikTok refused the request: {error.get('code')}: {error.get('message', '')}")
    return payload.get("data") or {}


def choose_privacy(requested: str, allowed: list[str]) -> str:
    """Use the requested visibility only if this account offers it."""
    if requested in allowed:
        return requested
    if DEFAULT_PRIVACY in allowed or not allowed:
        return DEFAULT_PRIVACY
    return allowed[0]


def publish_video(
    *,
    access_token: str,
    video: Path,
    caption: str,
    privacy: str | None = None,
    post=_request,
    sleep=time.sleep,
) -> TikTokPost:
    video = Path(video)
    size = video.stat().st_size
    if size > MAX_SINGLE_CHUNK_BYTES:
        raise TikTokError(f"the video is {size} bytes, above the single-upload limit")

    creator = _api(CREATOR_INFO_URL, access_token, {}, post)
    requested = privacy or os.getenv("GQ_TIKTOK_PRIVACY", "").strip() or DEFAULT_PRIVACY
    privacy_level = choose_privacy(requested, list(creator.get("privacy_level_options") or []))

    init = _api(
        VIDEO_INIT_URL,
        access_token,
        {
            "post_info": {
                "title": caption[:MAX_CAPTION_CHARS],
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                # The narration and script are AI-generated; TikTok requires the label.
                "is_aigc": True,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        },
        post,
    )
    publish_id = str(init.get("publish_id") or "")
    upload_url = str(init.get("upload_url") or "")
    if not publish_id or not upload_url:
        raise TikTokError("TikTok did not return an upload address")

    post(
        upload_url,
        data=video.read_bytes(),
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        },
        method="PUT",
        timeout=600,
    )

    status = "PROCESSING_UPLOAD"
    for _ in range(STATUS_POLLS):
        data = _api(STATUS_URL, access_token, {"publish_id": publish_id}, post)
        status = str(data.get("status") or status)
        if status == "PUBLISH_COMPLETE":
            break
        if status == "FAILED":
            raise TikTokError(f"TikTok could not publish the video: {data.get('fail_reason', 'unknown')}")
        sleep(STATUS_POLL_SECONDS)
    return TikTokPost(publish_id=publish_id, status=status, privacy_level=privacy_level)
