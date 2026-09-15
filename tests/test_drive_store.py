from pathlib import Path

from storage.drive_store import DriveStore


def test_drive_store_creates_folder_and_uploads_file(tmp_path):
    calls = []

    class FakeTransport:
        def post_json(self, url, token, payload):
            calls.append(("json", url, payload))
            return {"id": "folder123"}

        def post_multipart(self, url, token, metadata, file_path, mime_type):
            calls.append(("multipart", url, metadata, file_path.name, mime_type))
            return {"id": "file123", "name": file_path.name}

    file_path = tmp_path / "reel.mp4"
    file_path.write_bytes(b"video")
    store = DriveStore(token_provider=lambda: "token", transport=FakeTransport())
    folder_id = store.create_folder("Published", parent_id="root123")
    uploaded = store.upload_file(file_path, parent_id=folder_id, mime_type="video/mp4")

    assert folder_id == "folder123"
    assert uploaded["id"] == "file123"
    assert calls[0][2]["mimeType"] == "application/vnd.google-apps.folder"
    assert calls[1][2]["parents"] == ["folder123"]
