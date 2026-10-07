from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpokenWord:
    start: float
    end: float
    text: str
