from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable


class AudioQualityError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioReport:
    provider_name: str
    duration: float
    mean_volume: float
    publishable: bool


def _probe_audio(path: Path) -> dict[str, float]:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    volume = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", volume.stderr)
    if not match:
        raise AudioQualityError("Unable to measure narration volume")
    return {"duration": duration, "mean_volume": float(match.group(1))}


def validate_narration(
    path: Path,
    *,
    provider_name: str,
    probe: Callable[[Path], dict[str, float]] = _probe_audio,
) -> AudioReport:
    if not path.exists() or path.stat().st_size == 0:
        raise AudioQualityError("Narration audio is missing")
    if provider_name.strip().lower() in {"espeak", "espeaktts"}:
        raise AudioQualityError(
            "A natural neural narration provider is required"
        )
    values = probe(path)
    duration = float(values["duration"])
    mean_volume = float(values["mean_volume"])
    if duration <= 1.0:
        raise AudioQualityError("Narration is too short")
    if mean_volume < -45.0:
        raise AudioQualityError("Narration is effectively silent")
    return AudioReport(
        provider_name=provider_name,
        duration=duration,
        mean_volume=mean_volume,
        publishable=True,
    )
