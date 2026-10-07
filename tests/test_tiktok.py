import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from automation import tiktok
from automation.daily_reel import run_once
from social.tiktok_publish import (
    CREATOR_INFO_URL,
    STATUS_URL,
    TOKEN_URL,
    VIDEO_INIT_URL,
    TikTokError,
    TikTokTokens,
    authorize_url,
    choose_privacy,
    exchange_code,
    publish_video,
    refresh_tokens,
)
from storage.tiktok_tokens import load_refresh_token, save_refresh_token

needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")


class FakeTikTok:
    """Records every request and answers like the Content Posting API."""

    def __init__(self, *, privacy_options=("PUBLIC_TO_EVERYONE", "SELF_ONLY"), statuses=("PUBLISH_COMPLETE",)):
        self.calls = []
        self.privacy_options = list(privacy_options)
        self.statuses = list(statuses)

    def __call__(self, url, *, data, headers, method="POST", timeout=120):
        self.calls.append(SimpleNamespace(url=url, data=data, headers=headers, method=method))
        if url == TOKEN_URL:
            return {"access_token": "act.new", "refresh_token": "rft.new", "open_id": "open-123456"}
        if url == CREATOR_INFO_URL:
            return {"data": {"privacy_level_options": self.privacy_options}, "error": {"code": "ok"}}
        if url == VIDEO_INIT_URL:
            return {
                "data": {"publish_id": "v_pub_1", "upload_url": "https://upload.example/video"},
                "error": {"code": "ok"},
            }
        if url == STATUS_URL:
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return {"data": {"status": status, "fail_reason": "bad_video"}, "error": {"code": "ok"}}
        return {}

    def body(self, url):
        return json.loads(next(call.data for call in self.calls if call.url == url))


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "reel.mp4"
    path.write_bytes(b"0" * 1000)
    return path


def test_authorize_url_requests_only_the_needed_scopes():
    query = parse_qs(urlparse(authorize_url("KEY")).query)
    assert query["client_key"] == ["KEY"]
    assert query["scope"] == ["user.info.basic,video.publish"]
    assert query["redirect_uri"] == ["https://gamerquestfr.com/"]
    assert query["response_type"] == ["code"]


def test_code_and_refresh_exchanges_send_the_right_grant():
    api = FakeTikTok()
    tokens = exchange_code("KEY", "SECRET", "the-code", post=api)
    assert tokens == TikTokTokens("act.new", "rft.new", "open-123456")
    sent = parse_qs(api.calls[0].data.decode())
    assert sent["grant_type"] == ["authorization_code"] and sent["code"] == ["the-code"]
    assert sent["redirect_uri"] == ["https://gamerquestfr.com/"]

    refresh_tokens("KEY", "SECRET", "rft.old", post=api)
    sent = parse_qs(api.calls[1].data.decode())
    assert sent["grant_type"] == ["refresh_token"] and sent["refresh_token"] == ["rft.old"]


def test_rejected_code_is_an_error_not_empty_tokens():
    def post(url, **kwargs):
        return {"error": "invalid_grant", "error_description": "Authorization code is expired."}

    with pytest.raises(TikTokError, match="expired"):
        exchange_code("KEY", "SECRET", "old-code", post=post)


def test_visibility_falls_back_to_private_when_public_is_not_offered():
    assert choose_privacy("PUBLIC_TO_EVERYONE", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]) == "PUBLIC_TO_EVERYONE"
    assert choose_privacy("PUBLIC_TO_EVERYONE", ["SELF_ONLY"]) == "SELF_ONLY"
    assert choose_privacy("SELF_ONLY", []) == "SELF_ONLY"


def test_video_is_posted_private_by_default_with_the_ai_label(video, monkeypatch):
    monkeypatch.delenv("GQ_TIKTOK_PRIVACY", raising=False)
    api = FakeTikTok()
    result = publish_video(access_token="act", video=video, caption="Légende", post=api, sleep=lambda s: None)

    assert result.status == "PUBLISH_COMPLETE" and result.privacy_level == "SELF_ONLY"
    init = api.body(VIDEO_INIT_URL)
    assert init["post_info"]["privacy_level"] == "SELF_ONLY"
    assert init["post_info"]["is_aigc"] is True
    assert init["post_info"]["title"] == "Légende"
    assert init["source_info"] == {
        "source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1,
    }
    upload = next(call for call in api.calls if call.url == "https://upload.example/video")
    assert upload.method == "PUT"
    assert upload.headers["Content-Range"] == "bytes 0-999/1000"
    assert upload.data == video.read_bytes()


def test_public_visibility_is_used_once_configured(video, monkeypatch):
    monkeypatch.setenv("GQ_TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")
    api = FakeTikTok()
    result = publish_video(access_token="act", video=video, caption="c", post=api, sleep=lambda s: None)
    assert result.privacy_level == "PUBLIC_TO_EVERYONE"


def test_publish_waits_for_processing_and_reports_failure(video):
    waiting = FakeTikTok(statuses=["PROCESSING_UPLOAD", "PROCESSING_UPLOAD", "PUBLISH_COMPLETE"])
    assert publish_video(
        access_token="act", video=video, caption="c", post=waiting, sleep=lambda s: None,
    ).status == "PUBLISH_COMPLETE"

    with pytest.raises(TikTokError, match="bad_video"):
        publish_video(
            access_token="act", video=video, caption="c",
            post=FakeTikTok(statuses=["FAILED"]), sleep=lambda s: None,
        )


def test_api_error_codes_are_raised(video):
    def post(url, **kwargs):
        return {"error": {"code": "unaudited_client_can_only_post_to_private_accounts", "message": "x"}}

    with pytest.raises(TikTokError, match="unaudited_client"):
        publish_video(access_token="act", video=video, caption="c", post=post, sleep=lambda s: None)


@needs_openssl
def test_refresh_token_is_stored_encrypted(tmp_path):
    path = tmp_path / "token.enc"
    save_refresh_token("rft.secret-value", "client-secret", path)
    assert b"rft.secret-value" not in path.read_bytes()
    assert load_refresh_token("client-secret", path) == "rft.secret-value"
    with pytest.raises(RuntimeError):
        load_refresh_token("another-key", path)


@needs_openssl
def test_posting_rotates_the_stored_refresh_token(tmp_path, video, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "KEY")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "SECRET")
    token_file = tmp_path / "token.enc"
    save_refresh_token("rft.old", "SECRET", token_file)
    used = {}

    def refresh(key, secret, refresh_token):
        used["refresh_token"] = refresh_token
        return TikTokTokens("act.new", "rft.rotated")

    def publish(**kwargs):
        used.update(kwargs)
        return SimpleNamespace(status="PUBLISH_COMPLETE", privacy_level="SELF_ONLY", publish_id="p1")

    result = tiktok.post_reel(video, "caption", token_file, refresh=refresh, publish=publish)
    assert result.publish_id == "p1"
    assert used["refresh_token"] == "rft.old" and used["access_token"] == "act.new"
    assert load_refresh_token("SECRET", token_file) == "rft.rotated"


def test_sign_in_code_is_accepted_bare_encoded_or_as_the_full_address():
    assert tiktok.extract_code("abc123") == "abc123"
    assert tiktok.extract_code("abc%2A123%21x") == "abc*123!x"
    assert tiktok.extract_code("abc%2A123&scopes=user.info.basic&state=gamerquest") == "abc*123"
    assert tiktok.extract_code(
        "https://gamerquestfr.com/?code=abc%2A123%21x&scopes=user.info.basic%2Cvideo.publish&state=gamerquest"
    ) == "abc*123!x"


def test_not_connected_means_no_post_and_no_error(tmp_path, video, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "KEY")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "SECRET")
    assert tiktok.post_reel(video, "caption", tmp_path / "missing.enc") is None


@needs_openssl
def test_tiktok_failure_is_swallowed(tmp_path, video, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "KEY")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "SECRET")
    token_file = tmp_path / "token.enc"
    save_refresh_token("rft.old", "SECRET", token_file)

    def refresh(key, secret, refresh_token):
        raise TikTokError("TikTok HTTP 500")

    assert tiktok.post_reel(video, "caption", token_file, refresh=refresh) is None


def test_reel_goes_to_tiktok_only_after_instagram_and_never_fails_the_run(tmp_path):
    from tests.test_daily_reel_pipeline import FakeOrchestrator, facts, fake_produce

    order = []
    orchestrator = FakeOrchestrator()
    original = orchestrator.publish_reel

    def publish_reel(**kwargs):
        order.append("instagram")
        return original(**kwargs)

    orchestrator.publish_reel = publish_reel

    def tiktok_poster(reel, caption):
        order.append("tiktok")
        raise RuntimeError("tiktok exploded")

    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=True,
        orchestrator=orchestrator, games=iter([facts()]), produce_fn=fake_produce(),
        tiktok_poster=tiktok_poster,
    )
    assert order == ["instagram", "tiktok"]
    assert result.status == "published"


def test_dry_run_never_posts_to_tiktok(tmp_path):
    from tests.test_daily_reel_pipeline import facts, fake_produce

    def tiktok_poster(reel, caption):
        raise AssertionError("no TikTok post in a dry run")

    result = run_once(
        output_dir=tmp_path, publish_log_path=tmp_path / "log.json", live_publish=False,
        games=iter([facts()]), produce_fn=fake_produce(), tiktok_poster=tiktok_poster,
    )
    assert result.status == "dry-run"
