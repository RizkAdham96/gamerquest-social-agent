"""Connect the TikTok account once, then post each Reel there too."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from social.tiktok_publish import (
    TikTokError,
    TikTokPost,
    exchange_code,
    publish_video,
    refresh_tokens,
)
from storage.tiktok_tokens import TOKEN_FILE, load_refresh_token, save_refresh_token


def credentials() -> tuple[str, str]:
    return (
        os.getenv("TIKTOK_CLIENT_KEY", "").strip(),
        os.getenv("TIKTOK_CLIENT_SECRET", "").strip(),
    )


def is_connected(token_file: Path = TOKEN_FILE) -> bool:
    key, secret = credentials()
    return bool(key and secret and token_file.exists())


def extract_code(value: str) -> str:
    """Accept the bare code or the whole address TikTok redirected to.

    The code arrives percent-encoded in the address bar; TikTok expects it
    decoded, and a code copied with its "&scopes=..." tail would be refused.
    """
    value = value.strip()
    if "code=" in value:
        query = parse_qs(urlparse(value).query or value.split("?", 1)[-1])
        codes = query.get("code") or []
        return codes[0] if codes else ""
    return unquote(value.split("&", 1)[0])


def connect(code: str, token_file: Path = TOKEN_FILE, exchange=exchange_code) -> str:
    """Trade the one-time sign-in code for tokens and store the refresh token."""
    key, secret = credentials()
    if not key or not secret:
        raise TikTokError("Missing TIKTOK_CLIENT_KEY or TIKTOK_CLIENT_SECRET")
    code = extract_code(code)
    if not code:
        raise TikTokError("No sign-in code was provided")
    tokens = exchange(key, secret, code)
    save_refresh_token(tokens.refresh_token, secret, token_file)
    return tokens.open_id


def post_reel(
    reel: Path,
    caption: str,
    token_file: Path = TOKEN_FILE,
    refresh=refresh_tokens,
    publish=publish_video,
) -> TikTokPost | None:
    """Post to TikTok; report and return None on any problem.

    TikTok is a second destination. Nothing that goes wrong here may undo or
    block the Instagram Reel that was already published.
    """
    if not is_connected(token_file):
        print("TikTok: not connected; skipping.")
        return None
    key, secret = credentials()
    try:
        tokens = refresh(key, secret, load_refresh_token(secret, token_file))
        # TikTok may rotate the refresh token; keep whichever is current.
        save_refresh_token(tokens.refresh_token, secret, token_file)
        result = publish(access_token=tokens.access_token, video=Path(reel), caption=caption)
    except (TikTokError, RuntimeError, OSError, ValueError) as exc:
        print(f"TikTok: post failed, Instagram is unaffected: {exc}")
        return None
    print(f"TikTok: {result.status} (visibility {result.privacy_level}, id {result.publish_id})")
    return result


def make_test_video(output: Path) -> Path:
    """A short clip that is unmistakably a test, for checking the connection."""
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output),
        ],
        check=True, capture_output=True,
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="GamerQuest TikTok connection")
    commands = parser.add_subparsers(dest="command", required=True)
    connect_parser = commands.add_parser("connect", help="store tokens from a sign-in code")
    connect_parser.add_argument("--code", required=True)
    commands.add_parser("test-post", help="post a private test clip")
    args = parser.parse_args()

    if args.command == "connect":
        open_id = connect(args.code)
        print(f"TikTok account connected (open id ending {open_id[-6:] or 'unknown'}).")
        return
    clip = make_test_video(Path("output/tiktok-test.mp4"))
    result = post_reel(clip, "Test de connexion GamerQuest FR. #test")
    if result is None:
        raise SystemExit("TikTok test post failed; see the message above.")


if __name__ == "__main__":
    main()
