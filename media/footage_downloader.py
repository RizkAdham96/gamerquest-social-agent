from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from .footage_validator import FootageCandidate, FootageValidator


def _fetch_bytes(url: str) -> bytes:
    with urlopen(url, timeout=120) as response:
        return response.read()


class FootageDownloader:
    def __init__(self, fetch_bytes: Callable[[str], bytes] = _fetch_bytes, validator: FootageValidator | None = None):
        self.fetch_bytes = fetch_bytes
        self.validator = validator or FootageValidator()

    def download(self, candidate: FootageCandidate, output_dir: Path) -> Path:
        validation = self.validator.validate(candidate)
        if not validation.ok:
            raise ValueError(validation.reason)
        parsed = urlparse(candidate.url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if "youtube.com" in host or "youtu.be" in host:
            raise ValueError("candidate is not a direct media URL")
        if not path.endswith((".mp4", ".webm", ".mov", ".m4v")):
            raise ValueError("candidate is not a direct media URL")
        data = self.fetch_bytes(candidate.url)
        if not data:
            raise RuntimeError("downloaded footage is empty")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(parsed.path).suffix.lower() or ".mp4"
        output = output_dir / f"footage{suffix}"
        output.write_bytes(data)
        return output
