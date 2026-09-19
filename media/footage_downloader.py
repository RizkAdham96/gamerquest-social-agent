from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlparse
from urllib.request import urlopen

from .footage_validator import FootageCandidate, FootageValidator


def _fetch_bytes(url: str) -> bytes:
    with urlopen(url, timeout=120) as response:
        return response.read()


class FootageDownloader:
    def __init__(
        self,
        fetch_bytes: Callable[[str], bytes] = _fetch_bytes,
        validator: FootageValidator | None = None,
        run_command: Callable[..., object] = subprocess.run,
    ):
        self.fetch_bytes = fetch_bytes
        self.validator = validator or FootageValidator()
        self.run_command = run_command

    def _download_stream(self, url: str, output: Path) -> Path:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        copy_cmd = [
            ffmpeg, "-y", "-i", url,
            "-t", "45",
            "-c", "copy",
            "-movflags", "+faststart",
            str(output),
        ]
        try:
            self.run_command(copy_cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            encode_cmd = [
                ffmpeg, "-y", "-i", url,
                "-t", "45",
                "-c:v", "libx264", "-preset", "veryfast",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(output),
            ]
            self.run_command(encode_cmd, check=True, capture_output=True)

        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("ffmpeg did not download Steam trailer stream")
        return output

    def download(self, candidate: FootageCandidate, output_dir: Path) -> Path:
        validation = self.validator.validate(candidate)
        if not validation.ok:
            raise ValueError(validation.reason)

        parsed = urlparse(candidate.url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()

        if "youtube.com" in host or "youtu.be" in host:
            raise ValueError("candidate is not a direct media URL")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if path.endswith((".m3u8", ".mpd")):
            return self._download_stream(candidate.url, output_dir / "footage.mp4")

        if not path.endswith((".mp4", ".webm", ".mov", ".m4v")):
            raise ValueError("candidate is not a direct media URL")

        data = self.fetch_bytes(candidate.url)
        if not data:
            raise RuntimeError("downloaded footage is empty")
        suffix = Path(parsed.path).suffix.lower() or ".mp4"
        output = output_dir / f"footage{suffix}"
        output.write_bytes(data)
        return output
