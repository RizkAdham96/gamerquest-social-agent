from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class FootageCandidate:
    url: str
    source_name: str
    is_official: bool


@dataclass(frozen=True)
class FootageValidation:
    ok: bool
    reason: str


class FootageValidator:
    def validate(self, candidate: FootageCandidate) -> FootageValidation:
        if not candidate.is_official:
            return FootageValidation(False, "source_not_official")
        parsed = urlparse(candidate.url)
        if parsed.scheme != "https" or not parsed.netloc:
            return FootageValidation(False, "invalid_media_url")
        if not candidate.source_name.strip():
            return FootageValidation(False, "missing_source_name")
        return FootageValidation(True, "official_https_source")
