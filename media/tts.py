from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import sys


class EspeakTTS:
    provider_name = "espeak"
    def __init__(self, voice: str = "fr", speed: int = 165):
        self.voice = voice
        self.speed = speed

    def build_command(self, text: str, output: Path) -> list[str]:
        binary = shutil.which("espeak") or "espeak"
        return [binary, "-v", self.voice, "-s", str(self.speed), "-w", str(output), text]

    def synthesize(self, text: str, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self.build_command(text, output), check=True, capture_output=True)
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("TTS did not produce audio")
        return output


class EdgeTTS:
    provider_name = "edge-tts"
    def __init__(self, voice: str = "fr-FR-DeniseNeural", rate: str = "+0%"):
        self.voice = voice
        self.rate = rate

    def build_command(self, text: str, output: Path) -> list[str]:
        binary = shutil.which("edge-tts")
        prefix = [binary] if binary else [sys.executable, "-m", "edge_tts"]
        return prefix + [
            "--voice",
            self.voice,
            f"--rate={self.rate}",
            "--text",
            text,
            "--write-media",
            str(output),
        ]

    def synthesize(self, text: str, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self.build_command(text, output), check=True, capture_output=True)
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("Edge TTS did not produce audio")
        return output


class SmartFrenchTTS:
    """Uses a natural online neural voice first and the offline eSpeak path as a hard fallback."""

    def __init__(self, primary=None, fallback=None):
        self.primary = primary or EdgeTTS()
        self.fallback = fallback or EspeakTTS()
        self.last_provider_name = ""

    def synthesize(self, text: str, output: Path) -> Path:
        try:
            result = self.primary.synthesize(text, output)
            self.last_provider_name = getattr(
                self.primary, "provider_name", type(self.primary).__name__
            )
            return result
        except (OSError, RuntimeError, subprocess.SubprocessError):
            if output.exists():
                output.unlink()
            result = self.fallback.synthesize(text, output)
            self.last_provider_name = getattr(
                self.fallback, "provider_name", type(self.fallback).__name__
            )
            return result
