"""Render a hidden-gem Reel: centred gameplay over a blurred fill, narrated.

Layout follows the reference Reel the editor supplied: the trailer keeps its
shape in the middle of a 1080x1920 frame and a blurred copy fills the top and
bottom. A narration plays over the quietened game audio, with the script shown
as short phrases in step with the voice.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

WIDTH = 1080
HEIGHT = 1920
FOREGROUND_HEIGHT = 1216
CLIP_SECONDS = 2.4
TRAILER_INTRO_SKIP_SECONDS = 6.0
TRAILER_OUTRO_SKIP_SECONDS = 4.0
MAX_TRAILER_SECONDS = 120
MIN_USABLE_TRAILER_SECONDS = 14.0
CAPTIONS_FILE = "captions.ass"
TRAILER_FILE = "trailer.mp4"
VOICE_FILE = "voice.mp3"
# Game audio stays audible under the narration without competing with it.
GAME_VOLUME_UNDER_VOICE = 0.14
REEL_FILE = "reel.mp4"


# Trailer suitability. A first dry run produced an almost black Reel from a
# dark, letterboxed trailer; such footage is refused and another game is tried.
BLACK_BAR_LUMA_LIMIT = 40
MIN_MEAN_LUMA = 55.0
# Grey or sepia footage (menus, text screens) reads as lifeless at Reel size.
# Measured on real trailers: colourful games 17-39, muted 3D games 11-13,
# grey text interfaces and monochrome art below 10.
MIN_MEAN_SATURATION = 10.0
MAX_PICTURE_ASPECT = 2.2
MIN_PICTURE_HEIGHT = 480
ANALYSIS_SECONDS = 40


@dataclass(frozen=True)
class TrailerLook:
    crop: str
    width: int
    height: int
    mean_luma: float
    mean_saturation: float = 100.0


def analyze_trailer(path: Path, run=subprocess.run) -> TrailerLook:
    """Find baked-in black bars and how bright the picture inside them is."""
    base = [
        _ffmpeg(), "-hide_banner", "-ss", str(TRAILER_INTRO_SKIP_SECONDS),
        "-t", str(ANALYSIS_SECONDS), "-i", str(path),
    ]
    detect = run(
        base + ["-vf", f"fps=2,cropdetect=limit={BLACK_BAR_LUMA_LIMIT}:round=2:reset=0",
                "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", detect.stderr or "")
    if not crops:
        raise RuntimeError("the trailer's picture area could not be measured")
    width, height, x, y = (int(value) for value in crops[-1])
    crop = f"{width}:{height}:{x}:{y}"
    stats = run(
        base + ["-vf", f"crop={crop},fps=1,signalstats,"
                       "metadata=print:key=lavfi.signalstats.YAVG:file=-,"
                       "metadata=print:key=lavfi.signalstats.SATAVG:file=-",
                "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    luma = [float(value) for value in re.findall(r"YAVG=([0-9.]+)", stats.stdout or "")]
    saturation = [float(value) for value in re.findall(r"SATAVG=([0-9.]+)", stats.stdout or "")]
    if not luma or not saturation:
        raise RuntimeError("the trailer's brightness could not be measured")
    return TrailerLook(
        crop, width, height,
        round(sum(luma) / len(luma), 1),
        round(sum(saturation) / len(saturation), 1),
    )


def check_trailer_look(look: TrailerLook) -> None:
    if look.height < MIN_PICTURE_HEIGHT or look.width / look.height > MAX_PICTURE_ASPECT:
        raise RuntimeError(
            f"the trailer's picture is a {look.width}x{look.height} strip, "
            "too wide for the centre of a vertical Reel"
        )
    if look.mean_luma < MIN_MEAN_LUMA:
        raise RuntimeError(
            f"the trailer is too dark for a Reel (brightness {look.mean_luma:.0f}, "
            f"minimum {MIN_MEAN_LUMA:.0f})"
        )
    if look.mean_saturation < MIN_MEAN_SATURATION:
        raise RuntimeError(
            f"the trailer is nearly colourless (saturation {look.mean_saturation:.0f}, "
            f"minimum {MIN_MEAN_SATURATION:.0f})"
        )


@dataclass(frozen=True)
class RenderedReel:
    path: Path
    duration_seconds: float
    clip_count: int


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def download_trailer(url: str, output_dir: Path, run=subprocess.run) -> Path:
    """Fetch the official trailer stream; stream copy first, re-encode if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / TRAILER_FILE
    base = [_ffmpeg(), "-v", "error", "-y", "-i", url, "-t", str(MAX_TRAILER_SECONDS)]
    try:
        run(base + ["-c", "copy", str(target)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        run(
            base + ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(target)],
            check=True, capture_output=True,
        )
    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("the official trailer could not be downloaded")
    return target


def probe(path: Path, run=subprocess.run) -> dict:
    result = run(
        [
            _ffprobe(), "-v", "error", "-print_format", "json",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration": float((data.get("format") or {}).get("duration") or 0.0),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def clip_starts(trailer_seconds: float, reel_seconds: float) -> list[float]:
    """Spread the cuts across the trailer, away from logos and end cards."""
    usable = trailer_seconds - TRAILER_INTRO_SKIP_SECONDS - TRAILER_OUTRO_SKIP_SECONDS
    if usable < MIN_USABLE_TRAILER_SECONDS:
        raise RuntimeError(
            f"the trailer is too short for a Reel ({trailer_seconds:.0f}s)"
        )
    count = math.ceil(reel_seconds / CLIP_SECONDS)
    span = usable - CLIP_SECONDS
    if count == 1:
        return [TRAILER_INTRO_SKIP_SECONDS]
    step = span / (count - 1)
    return [round(TRAILER_INTRO_SKIP_SECONDS + index * step, 2) for index in range(count)]


def build_filter_graph(
    starts: list[float], has_audio: bool, has_voice: bool = False, crop: str = "",
) -> str:
    parts = []
    video_labels = ""
    audio_labels = ""
    count = len(starts)
    # Remove baked-in black bars once, then cut the clips from the clean picture.
    source = f"[0:v]crop={crop}," if crop else "[0:v]"
    parts.append(source + f"split={count}" + "".join(f"[s{i}]" for i in range(count)) + ";")
    for index, start in enumerate(starts):
        parts.append(
            f"[s{index}]trim=start={start}:duration={CLIP_SECONDS},setpts=PTS-STARTPTS[v{index}];"
        )
        video_labels += f"[v{index}]"
        if has_audio:
            parts.append(
                f"[0:a]atrim=start={start}:duration={CLIP_SECONDS},asetpts=PTS-STARTPTS[a{index}];"
            )
            audio_labels += f"[a{index}]"
    graph = "".join(parts)
    graph += f"{video_labels}concat=n={count}:v=1:a=0,fps=30,split[bgsrc][fgsrc];"
    graph += (
        f"[bgsrc]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},gblur=sigma=36,eq=brightness=-0.06[bg];"
    )
    graph += f"[fgsrc]scale=-2:{FOREGROUND_HEIGHT},crop={WIDTH}:{FOREGROUND_HEIGHT}[fg];"
    graph += f"[bg][fg]overlay=0:(H-h)/2,ass={CAPTIONS_FILE},setsar=1[vout]"
    if has_audio:
        # Official game audio, levelled so trailers of any loudness sit alike.
        game = f";{audio_labels}concat=n={count}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11"
        if has_voice:
            graph += game + f",volume={GAME_VOLUME_UNDER_VOICE}[game]"
            graph += ";[1:a]loudnorm=I=-15:TP=-1.5:LRA=11[voice]"
            graph += ";[voice][game]amix=inputs=2:duration=longest:normalize=0[aout]"
        else:
            graph += game + "[aout]"
    elif has_voice:
        graph += ";[1:a]loudnorm=I=-15:TP=-1.5:LRA=11[aout]"
    return graph


def build_command(
    starts: list[float], reel_seconds: float, has_audio: bool, has_voice: bool = False,
    crop: str = "",
) -> list[str]:
    command = [_ffmpeg(), "-v", "error", "-y", "-i", TRAILER_FILE]
    if has_voice:
        command += ["-i", VOICE_FILE]
    command += [
        "-filter_complex", build_filter_graph(starts, has_audio, has_voice, crop),
        "-map", "[vout]",
    ]
    if has_audio or has_voice:
        command += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        command += ["-an"]
    command += [
        "-t", f"{reel_seconds:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30",
        "-movflags", "+faststart", REEL_FILE,
    ]
    return command


def render_reel(
    *,
    trailer: Path,
    captions_ass: str,
    reel_seconds: float,
    output_dir: Path,
    voice: Path | None = None,
    run=subprocess.run,
) -> RenderedReel:
    output_dir.mkdir(parents=True, exist_ok=True)
    if trailer.resolve() != (output_dir / TRAILER_FILE).resolve():
        shutil.copyfile(trailer, output_dir / TRAILER_FILE)
    if voice is not None and voice.resolve() != (output_dir / VOICE_FILE).resolve():
        shutil.copyfile(voice, output_dir / VOICE_FILE)
    (output_dir / CAPTIONS_FILE).write_text(captions_ass, encoding="utf-8")

    info = probe(output_dir / TRAILER_FILE, run=run)
    look = analyze_trailer(output_dir / TRAILER_FILE, run=run)
    check_trailer_look(look)
    starts = clip_starts(info["duration"], reel_seconds)
    # Relative file names and cwd keep Windows drive letters out of the
    # filter graph, where a colon would need escaping.
    run(
        build_command(starts, reel_seconds, info["has_audio"], voice is not None, look.crop),
        check=True, capture_output=True, cwd=output_dir,
    )

    reel = output_dir / REEL_FILE
    verify_reel(reel, reel_seconds, require_audio=voice is not None, run=run)
    return RenderedReel(path=reel, duration_seconds=reel_seconds, clip_count=len(starts))


def verify_reel(
    reel: Path, expected_seconds: float, require_audio: bool = False, run=subprocess.run,
) -> None:
    """Refuse to hand a malformed file to Instagram."""
    if not reel.exists() or reel.stat().st_size < 200_000:
        raise RuntimeError("the rendered Reel is missing or empty")
    info = probe(reel, run=run)
    if (info["width"], info["height"]) != (WIDTH, HEIGHT):
        raise RuntimeError(f"the Reel is {info['width']}x{info['height']}, expected {WIDTH}x{HEIGHT}")
    if require_audio and not info["has_audio"]:
        raise RuntimeError("the Reel has no audio track although it is narrated")
    if abs(info["duration"] - expected_seconds) > 1.0:
        raise RuntimeError(
            f"the Reel lasts {info['duration']:.1f}s, expected about {expected_seconds:.1f}s"
        )
