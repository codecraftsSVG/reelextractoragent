import os
import pytest


def test_shortcode_parsing_variants():
    # Mirrors workers/runner.py + extract_reel.py shortcode extraction
    cases = {
        "https://www.instagram.com/reel/abc123/": "abc123",
        "https://www.instagram.com/reel/abc123": "abc123",
        "https://www.instagram.com/reel/abc123/?utm=x&y=1": "abc123",
        "https://www.instagram.com/reels/abc-1_X/": "abc-1_X",
    }
    for url, expected in cases.items():
        got = url.split("?")[0].rstrip("/").split("/")[-1]
        assert got == expected, url


def test_process_reel_end_to_end_mocked(monkeypatch):
    import extract_reel

    monkeypatch.setattr(extract_reel.transcript, "transcribe",
                        lambda p, s: {"text": "spoken", "avg_confidence": 0.8})
    monkeypatch.setattr(extract_reel.ocr, "extract_text",
                        lambda p, s, fps=0.5: {"duration_s": 5.0, "frames_extracted": 2,
                                              "raw": [], "lines": ["on screen"]})
    monkeypatch.setattr(extract_reel.writer, "write_md",
                        lambda *a, **k: "/tmp/report.md")
    monkeypatch.setattr(extract_reel.verifier, "verify_reel",
                        lambda *a, **k: {"status": "pass", "failed_checks": [], "detail": {}})
    monkeypatch.setattr(extract_reel.evaluator, "score",
                        lambda *a, **k: {"total": 88.0, "criteria": {}, "justification": "j",
                                         "verdict": "publish"})
    monkeypatch.setattr(extract_reel.asyncio, "run",
                        lambda coro: (coro.close() or "/tmp/vid.mp4"))

    out = extract_reel.process_reel(
        "https://www.instagram.com/reel/abc123/?utm=x",
        caption="my caption", uploader="alice")
    assert out["shortcode"] == "abc123"
    assert out["video_path"] == "/tmp/vid.mp4"
    assert out["score"] == 88.0
    assert out["verdict"] == "publish"


def test_download_via_igexport_uses_cache(monkeypatch, tmp_path):
    import extract_reel
    monkeypatch.setattr(extract_reel, "DOWNLOADS_DIR", str(tmp_path))
    cached = tmp_path / "abc123.mp4"
    cached.write_bytes(b"existing")

    import asyncio as _aio
    # Must not launch playwright:
    async def _run():
        return await extract_reel.download_via_igexport("https://x/reel/abc123/", "abc123")
    result = _aio.run(_run())
    assert result == str(cached)
    assert os.path.exists(result)


@pytest.mark.live
def test_live_render_health():
    requests = pytest.importorskip("requests")
    url = os.getenv("LIVE_BASE_URL", "https://reelextractoragent.onrender.com")
    r = requests.get(f"{url}/health", timeout=60)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
