from __future__ import annotations

import json
import time
from typing import Protocol, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MetaTransport(Protocol):
    def post(self, url: str, params: dict[str, str]) -> dict: ...
    def get(self, url: str, params: dict[str, str]) -> dict: ...


class UrllibMetaTransport:
    def post(self, url: str, params: dict[str, str]) -> dict:
        data = urlencode(params).encode("utf-8")
        request = Request(url, data=data, method="POST")
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def get(self, url: str, params: dict[str, str]) -> dict:
        full_url = f"{url}?{urlencode(params)}"
        request = Request(full_url, method="GET")
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class ContainerStatusError(RuntimeError):
    pass


class InstagramPublisher:
    GRAPH_BASE = "https://graph.facebook.com"

    def __init__(
        self,
        *,
        ig_user_id: str,
        access_token: str,
        api_version: str = "v26.0",
        transport: MetaTransport | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self.ig_user_id = ig_user_id.strip()
        self.access_token = access_token.strip()
        self.api_version = api_version.strip() or "v26.0"
        self.transport = transport or UrllibMetaTransport()
        self.sleep_fn = sleep_fn or time.sleep
        if not self.ig_user_id:
            raise ValueError("ig_user_id is required")
        if not self.access_token:
            raise ValueError("access_token is required")

    def _url(self, path: str) -> str:
        return f"{self.GRAPH_BASE}/{self.api_version}/{path.lstrip('/')}"

    def create_reel_container(
        self,
        video_url: str,
        caption: str,
        *,
        share_to_feed: bool = True,
    ) -> str:
        if not video_url.startswith(("https://", "http://")):
            raise ValueError("Instagram publishing requires a publicly accessible http(s) video_url")
        response = self.transport.post(
            self._url(f"{self.ig_user_id}/media"),
            {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "share_to_feed": "true" if share_to_feed else "false",
                "access_token": self.access_token,
            },
        )
        container_id = response.get("id")
        if not container_id:
            raise RuntimeError("Meta container creation returned no id")
        return str(container_id)

    def get_container_status(self, container_id: str) -> dict:
        return self.transport.get(
            self._url(container_id),
            {
                "fields": "status_code,status",
                "access_token": self.access_token,
            },
        )

    def wait_until_ready(
        self,
        container_id: str,
        *,
        max_attempts: int = 30,
        poll_seconds: float = 2.0,
    ) -> dict:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        for attempt in range(max_attempts):
            status = self.get_container_status(container_id)
            code = str(status.get("status_code", "")).upper()
            if code == "FINISHED":
                return status
            if code in {"ERROR", "EXPIRED", "PUBLISHED"}:
                raise ContainerStatusError(
                    f"container {container_id} reached terminal status {code}: {status.get('status', '')}"
                )
            if attempt < max_attempts - 1:
                self.sleep_fn(poll_seconds)
        raise TimeoutError(f"container {container_id} was not ready after {max_attempts} attempts")

    def publish_container(self, container_id: str) -> str:
        response = self.transport.post(
            self._url(f"{self.ig_user_id}/media_publish"),
            {
                "creation_id": container_id,
                "access_token": self.access_token,
            },
        )
        media_id = response.get("id")
        if not media_id:
            raise RuntimeError("Meta publish returned no media id")
        return str(media_id)
