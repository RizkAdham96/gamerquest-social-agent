from __future__ import annotations
from collections.abc import Iterable
from .footage_validator import FootageCandidate, FootageValidator


class FootageFinder:
    def __init__(self, validator: FootageValidator | None = None):
        self.validator = validator or FootageValidator()

    def select(self, candidates: Iterable[FootageCandidate]) -> FootageCandidate | None:
        for candidate in candidates:
            if self.validator.validate(candidate).ok:
                return candidate
        return None
