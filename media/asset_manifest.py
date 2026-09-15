from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class VisualAsset:
    url: str
    source_url: str
    publisher: str
    game_id: str
    media_type: str
    confidence: float
    width: int
    height: int
    is_official: bool

    def validation_errors(self, minimum_confidence: float = 0.8) -> tuple[str, ...]:
        errors: list[str] = []
        for name, value in (("url", self.url), ("source_url", self.source_url)):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{name} must be an https URL")
        if not self.publisher.strip():
            errors.append("publisher is required")
        if not self.game_id.strip():
            errors.append("game_id is required")
        if self.media_type not in {"video", "image"}:
            errors.append("media_type must be video or image")
        if self.confidence < minimum_confidence:
            errors.append("confidence below minimum")
        if self.width <= 0 or self.height <= 0:
            errors.append("positive dimensions are required")
        if not self.is_official:
            errors.append("asset is not official")
        return tuple(errors)
