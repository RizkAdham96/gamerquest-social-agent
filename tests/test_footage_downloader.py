from pathlib import Path

from media.footage_downloader import FootageDownloader
from media.footage_validator import FootageCandidate


def test_downloader_rejects_youtube_watch_pages(tmp_path):
    downloader = FootageDownloader(fetch_bytes=lambda url: b"x")
    candidate = FootageCandidate("https://www.youtube.com/watch?v=abc", "Official", True)
    try:
        downloader.download(candidate, tmp_path)
    except ValueError as exc:
        assert "direct media" in str(exc)
    else:
        raise AssertionError("expected rejection")


def test_downloader_writes_direct_mp4(tmp_path):
    downloader = FootageDownloader(fetch_bytes=lambda url: b"video-bytes")
    candidate = FootageCandidate("https://cdn.example.com/trailer.mp4", "Official", True)
    path = downloader.download(candidate, tmp_path)
    assert path.suffix == ".mp4"
    assert path.read_bytes() == b"video-bytes"


def test_downloader_uses_ffmpeg_for_hls_manifest(tmp_path):
    captured = {}

    def fake_run(cmd, check, capture_output):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"stream-video")

    downloader = FootageDownloader(
        fetch_bytes=lambda url: b"unused",
        run_command=fake_run,
    )
    candidate = FootageCandidate(
        "https://video.akamai.steamstatic.com/trailer/master.m3u8?t=1",
        "Steam HLS: Launch",
        True,
    )
    path = downloader.download(candidate, tmp_path)
    assert path.name == "footage.mp4"
    assert path.read_bytes() == b"stream-video"
    assert "-i" in captured["cmd"]
    assert candidate.url in captured["cmd"]
