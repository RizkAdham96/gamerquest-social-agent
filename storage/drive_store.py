from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Callable, Protocol
from urllib.request import Request, urlopen


class DriveTransport(Protocol):
    def post_json(self, url: str, token: str, payload: dict) -> dict: ...
    def post_multipart(self, url: str, token: str, metadata: dict, file_path: Path, mime_type: str) -> dict: ...


class UrllibDriveTransport:
    def post_json(self, url: str, token: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_multipart(self, url: str, token: str, metadata: dict, file_path: Path, mime_type: str) -> dict:
        boundary = f"gq_{uuid.uuid4().hex}"
        media = file_path.read_bytes()
        chunks = [
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
            json.dumps(metadata).encode("utf-8"),
            f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode(),
            media,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        request = Request(
            url,
            data=b"".join(chunks),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
        )
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))


class EnvAccessTokenProvider:
    def __init__(self, env_name: str = "GQ_GOOGLE_DRIVE_ACCESS_TOKEN"):
        self.env_name = env_name

    def __call__(self) -> str:
        token = os.getenv(self.env_name, "").strip()
        if not token:
            raise RuntimeError(f"Missing {self.env_name}")
        return token


class ServiceAccountTokenProvider:
    """Refreshes a Drive token from a Google service-account JSON file when google-auth is installed."""

    def __init__(self, credentials_file: str | Path, scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/drive.file",)):
        self.credentials_file = str(credentials_file)
        self.scopes = scopes

    def __call__(self) -> str:
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2 import service_account
        except ImportError as exc:
            raise RuntimeError("google-auth is required for service-account Drive auth") from exc
        credentials = service_account.Credentials.from_service_account_file(self.credentials_file, scopes=self.scopes)
        credentials.refresh(GoogleAuthRequest())
        if not credentials.token:
            raise RuntimeError("Google authentication did not return a token")
        return credentials.token


class DriveStore:
    FILES_URL = "https://www.googleapis.com/drive/v3/files"
    UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"

    def __init__(self, token_provider: Callable[[], str], transport: DriveTransport | None = None):
        self.token_provider = token_provider
        self.transport = transport or UrllibDriveTransport()

    def create_folder(self, name: str, parent_id: str | None = None) -> str:
        metadata: dict = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        response = self.transport.post_json(self.FILES_URL, self.token_provider(), metadata)
        folder_id = response.get("id")
        if not folder_id:
            raise RuntimeError("Drive folder creation returned no id")
        return folder_id

    def upload_file(self, file_path: Path, parent_id: str | None = None, mime_type: str | None = None) -> dict:
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        metadata: dict = {"name": file_path.name}
        if parent_id:
            metadata["parents"] = [parent_id]
        resolved_mime = mime_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        response = self.transport.post_multipart(
            self.UPLOAD_URL,
            self.token_provider(),
            metadata,
            file_path,
            resolved_mime,
        )
        if not response.get("id"):
            raise RuntimeError("Drive upload returned no id")
        return response
