from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    max_reels_per_week: int = 3
    dedupe_days: int = 30
    language: str = "fr"
    min_topic_score: int = 55
    meta_api_version: str = "v26.0"
    instagram_user_id: str = ""
    instagram_access_token: str = ""

    @classmethod
    def from_env(cls):
        return cls(
            max_reels_per_week=int(os.getenv("GQ_MAX_REELS_PER_WEEK", "3")),
            dedupe_days=int(os.getenv("GQ_DEDUPE_DAYS", "30")),
            language=os.getenv("GQ_LANGUAGE", "fr"),
            min_topic_score=int(os.getenv("GQ_MIN_TOPIC_SCORE", "55")),
            meta_api_version=os.getenv("GQ_META_API_VERSION", "v26.0"),
            instagram_user_id=os.getenv("GQ_INSTAGRAM_USER_ID", ""),
            instagram_access_token=os.getenv("GQ_INSTAGRAM_ACCESS_TOKEN", ""),
        )
