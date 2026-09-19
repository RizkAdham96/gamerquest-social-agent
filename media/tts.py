from __future__ import annotations
from pathlib import Path
import shutil
import subprocess


class EspeakTTS:
    def __init__(self, voice: str = "fr", speed: int = 155):
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
    def __init__(
        self,
        voice: str = "fr-FR-HenriNeural",
        rate: str = "-8%",
        pitch: str = "-2Hz",
        volume: str = "+0%",
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume

    def build_command(self, text: str, output: Path) -> list[str]:
        binary = shutil.which("edge-tts") or "edge-tts"
        return [
            binary,
            "--voice",
            self.voice,
            f"--rate={self.rate}",
            f"--pitch={self.pitch}",
            f"--volume={self.volume}",
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

    def synthesize(self, text: str, output: Path) -> Path:
        try:
            return self.primary.synthesize(text, output)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            if output.exists():
                output.unlink()
            return self.fallback.synthesize(text, output)
