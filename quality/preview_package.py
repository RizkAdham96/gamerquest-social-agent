from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from media.asset_manifest import VisualAsset
from .reel_validator import QualityReport


@dataclass(frozen=True)
class PreviewFixture:
    reel_path: Path
    subtitles_path: Path
    script: str
    assets: tuple[VisualAsset, ...]
    quality: QualityReport


@dataclass(frozen=True)
class PreviewPackage:
    reel: Path
    contact_sheet: Path
    review_json: Path
    subtitles: Path
    assets_json: Path


def _render_contact_sheet(reel_path: Path, output: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(reel_path),
            "-vf",
            "fps=1/5,scale=270:480,tile=4x1",
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
        capture_output=True,
    )


def create_preview_package(
    output_dir: Path,
    fixture: PreviewFixture,
    *,
    contact_sheet_renderer: Callable[[Path, Path], None] = _render_contact_sheet,
) -> PreviewPackage:
    output_dir.mkdir(parents=True, exist_ok=True)
    reel = output_dir / "reel.mp4"
    subtitles = output_dir / "subtitles.srt"
    contact_sheet = output_dir / "contact-sheet.jpg"
    review_json = output_dir / "review.json"
    assets_json = output_dir / "assets.json"

    if fixture.reel_path.resolve() != reel.resolve():
        shutil.copy2(fixture.reel_path, reel)
    if fixture.subtitles_path.resolve() != subtitles.resolve():
        shutil.copy2(fixture.subtitles_path, subtitles)
    contact_sheet_renderer(reel, contact_sheet)

    assets = [asdict(asset) for asset in fixture.assets]
    assets_json.write_text(
        json.dumps(assets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    review_json.write_text(
        json.dumps(
            {
                "publish_enabled": False,
                "script": fixture.script,
                "quality": asdict(fixture.quality),
                "assets": assets,
                "human_review": "pending",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return PreviewPackage(
        reel=reel,
        contact_sheet=contact_sheet,
        review_json=review_json,
        subtitles=subtitles,
        assets_json=assets_json,
    )
