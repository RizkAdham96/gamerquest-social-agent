"""Keep the TikTok refresh token between runs.

GitHub Actions cannot update its own secrets, and TikTok may issue a new
refresh token whenever one is used, so the current token is stored in the
repository as an encrypted file. It is AES-256 encrypted with a key derived
from the app's client secret, which only exists as a repository secret; the
file is useless without it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

TOKEN_FILE = Path("state/tiktok_token.enc")
PBKDF2_ITERATIONS = "200000"


def _openssl(args: list[str], key: str, data: bytes) -> bytes:
    binary = shutil.which("openssl") or "openssl"
    result = subprocess.run(
        [binary, "enc", "-aes-256-cbc", "-pbkdf2", "-iter", PBKDF2_ITERATIONS, "-md", "sha256",
         "-pass", "env:GQ_TIKTOK_TOKEN_KEY", *args],
        input=data,
        capture_output=True,
        env={**os.environ, "GQ_TIKTOK_TOKEN_KEY": key},
    )
    if result.returncode != 0:
        raise RuntimeError("the stored TikTok token could not be processed")
    return result.stdout


def save_refresh_token(refresh_token: str, key: str, path: Path = TOKEN_FILE) -> None:
    if not refresh_token or not key:
        raise ValueError("a refresh token and an encryption key are required")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_openssl(["-salt", "-a"], key, refresh_token.encode("utf-8")))


def load_refresh_token(key: str, path: Path = TOKEN_FILE) -> str:
    if not key or not path.exists():
        return ""
    return _openssl(["-d", "-a"], key, path.read_bytes()).decode("utf-8").strip()
