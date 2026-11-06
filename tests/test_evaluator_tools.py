import os
import pytest


def _rubric(monkeypatch, tmp_path):
    """Write a minimal rubric.yaml and point evaluator at it."""
    import yaml
    rubric = {
        "rubric": [
            {"criterion": "caption_completeness", "weight": 20,
             "scoring": {20: "full", 10: "partial", 0: "none"}},
            {"criterion": "transcript_accuracy", "weight": 25,
             "scoring": {25: "full", 15: "partial", 5: "garbled", 0: "none"}},
            {"criterion": "onscreen_text_coverage", "weight": 25,
             "scoring": {25: "full", 15: "partial", 5: "sporadic", 0: "none"}},
            {"criterion": "metadata_accuracy", "weight": 10,
             "scoring": {10: "full", 0: "none"}},
            {"criterion": "formatting", "weight": 10,
             "scoring": {10: "full", 5: "minor", 0: "broken"}},
            {"criterion": "no_hallucination", "weight": 10,
             "scoring": {10: "none", 0: "any"}},
        ],
        "thresholds": {"publish": 85, "retry": 60},
    }
    p = tmp_path / "rubric.yaml"
    p.write_text(yaml.safe_dump(rubric))
    import agents.evaluator as ev
    monkeypatch.setattr(ev, "RUBRIC_PATH", str(p))
    return ev


def test_score_full_marks_publish(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    fetch = {"caption": "Amazing reel #cool and long enough text",
             "shortcode": "abc", "url": "https://www.instagram.com/reel/abc/"}
    transcript = {"text": "spoken words here", "avg_confidence": 0.1}
    ocr = {"lines": ["l1", "l2", "l3", "l4"], "duration_s": 10.0}
    verify = {"status": "pass", "failed_checks": []}
    res = ev.score(fetch, transcript, ocr, verify)
    assert res["total"] == pytest.approx(100.0, abs=0.1)
    assert res["verdict"] == "publish"
    assert all(v > 0 for v in res["criteria"].values())


def test_score_empty_caption_and_transcript(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    fetch = {"caption": "", "shortcode": "abc", "url": "u"}
    res = ev.score(fetch, {"text": "", "avg_confidence": 0.9},
                   {"lines": [], "duration_s": 0}, {"status": "retry", "failed_checks": []})
    assert res["criteria"]["caption_completeness"] == 0
    assert res["criteria"]["transcript_accuracy"] == 0
    assert res["criteria"]["onscreen_text_coverage"] == 0
    assert res["verdict"] == "fail"


def test_score_caption_mismatch_caps_hallucination(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    fetch = {"caption": "hi #tag long caption text here", "shortcode": "a", "url": "u"}
    verify = {"status": "retry", "failed_checks": ["V3_caption_match"]}
    res = ev.score(fetch, {"text": "x", "avg_confidence": 0.1},
                   {"lines": ["l"], "duration_s": 5}, verify)
    assert res["criteria"]["no_hallucination"] == 0
    assert res["criteria"]["formatting"] == 5


def test_score_mid_transcript_confidence(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    fetch = {"caption": "cap", "shortcode": "a", "url": "u"}
    res = ev.score(fetch, {"text": "x", "avg_confidence": 0.3},
                   {"lines": [], "duration_s": 0}, {"status": "pass", "failed_checks": []})
    assert res["criteria"]["transcript_accuracy"] == 15


def test_score_low_transcript_confidence(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    fetch = {"caption": "cap", "shortcode": "a", "url": "u"}
    res = ev.score(fetch, {"text": "x", "avg_confidence": 0.15},
                   {"lines": [], "duration_s": 0}, {"status": "pass", "failed_checks": []})
    assert res["criteria"]["transcript_accuracy"] == 25


def test_score_missing_metadata(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    res = ev.score({}, {"text": ""}, {"lines": []}, {"status": "fail", "failed_checks": []})
    assert res["criteria"]["metadata_accuracy"] == 0


def test_score_verdict_boundaries(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    # Build cases that land near thresholds by tweaking on-screen density
    fetch = {"caption": "long caption #tag here ok", "shortcode": "a", "url": "u"}
    transcript = {"text": "t", "avg_confidence": 0.1}
    # dense OCR -> high score -> publish
    dense = ev.score(fetch, transcript, {"lines": ["a"] * 10, "duration_s": 10},
                     {"status": "pass", "failed_checks": []})
    assert dense["verdict"] == "publish"
    # sparse -> fail/retry
    sparse = ev.score(fetch, {"text": "", "avg_confidence": 0.9},
                      {"lines": [], "duration_s": 0},
                      {"status": "retry", "failed_checks": []})
    assert sparse["verdict"] in ("fail", "retry")


def test_score_justification_mentions_verify(monkeypatch, tmp_path):
    ev = _rubric(monkeypatch, tmp_path)
    res = ev.score({"caption": "c", "shortcode": "a", "url": "u"},
                   {"text": "t"}, {"lines": []},
                   {"status": "pass", "failed_checks": []})
    assert "verify=pass" in res["justification"]


def test_load_rubric_missing_file_raises(monkeypatch, tmp_path):
    import agents.evaluator as ev
    monkeypatch.setattr(ev, "RUBRIC_PATH", str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError):
        ev.score({}, {}, {}, {})


# ---------- OCR agent ----------

def test_ocr_extract_text_mocked(monkeypatch):
    import agents.ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "video_duration", lambda p: 4.0)
    monkeypatch.setattr(ocr_mod, "extract_frames", lambda p, s, fps=0.5: ["f1.png", "f2.png"])
    monkeypatch.setattr(ocr_mod, "ocr_frames", lambda frames: [("f1.png", "Hello"), ("f2.png", "Hello")])
    out = ocr_mod.extract_text("/tmp/v.mp4", "abc")
    assert out["duration_s"] == 4.0
    assert out["frames_extracted"] == 2
    assert out["lines"] == ["Hello"]


def test_ocr_extract_text_no_frames(monkeypatch):
    import agents.ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "video_duration", lambda p: 0)
    monkeypatch.setattr(ocr_mod, "extract_frames", lambda p, s, fps=0.5: [])
    monkeypatch.setattr(ocr_mod, "ocr_frames", lambda frames: [])
    out = ocr_mod.extract_text("/tmp/v.mp4", "abc")
    assert out["frames_extracted"] == 0
    assert out["lines"] == []


def test_ocr_frames_unreadable_on_error(monkeypatch, tmp_path):
    # ocr_frames catches per-frame exception and emits [unreadable frame: ...]
    import agents.tools as tools
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    results = tools.ocr_frames([str(bad)])
    assert len(results) == 1
    # Either tesseract missing on this box or bad image -> placeholder or empty;
    # the contract is: tuple of (basename, str) and never raises
    assert results[0][0] == "bad.png"
    assert isinstance(results[0][1], str)


# ---------- Transcript agent ----------

def test_transcript_delegates(monkeypatch):
    import agents.transcript as tr
    monkeypatch.setattr(tr, "transcribe_audio", lambda p, s: {"text": "hi", "avg_confidence": 0.5, "segments": []})
    assert tr.transcribe("/v.mp4", "abc")["text"] == "hi"


# ---------- Fetch agent ----------

def test_fetch_reel_maps_fields(monkeypatch):
    import agents.fetch as fetch
    monkeypatch.setattr(fetch, "ytdlp_json", lambda url: {
        "description": "cap here", "uploader": "me", "upload_date": "20240101",
        "like_count": 42})
    monkeypatch.setattr(fetch, "download_video", lambda url, sc: f"/tmp/{sc}.mp4")
    out = fetch.fetch_reel("https://www.instagram.com/reel/abc/", "abc")
    assert out["caption"] == "cap here"
    assert out["uploader"] == "me"
    assert out["like_count"] == 42
    assert out["video_path"] == "/tmp/abc.mp4"


def test_fetch_reel_falls_back_to_title_and_channel(monkeypatch):
    import agents.fetch as fetch
    monkeypatch.setattr(fetch, "ytdlp_json", lambda url: {"title": "t", "channel": "chan"})
    monkeypatch.setattr(fetch, "download_video", lambda url, sc: "/tmp/x.mp4")
    out = fetch.fetch_reel("u", "sc")
    assert out["caption"] == "t"
    assert out["uploader"] == "chan"


# ---------- Tools: extract_frames / download errors ----------

def test_extract_frames_returns_pngs_sorted(monkeypatch, tmp_path):
    import subprocess
    tmp = tmp_path
    # fake TMP dir via monkeypatching tools.TMP
    import agents.tools as tools
    monkeypatch.setattr(tools, "TMP", str(tmp))
    for name in ["abc_0002.png", "abc_0001.png", "xyz_0001.png"]:
        (tmp / name).write_bytes(b"x")
    class R:
        returncode = 0
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    frames = tools.extract_frames("video.mp4", "abc")
    assert frames == sorted(frames)
    assert len(frames) == 2
    assert all(f.endswith(".png") for f in frames)


def test_download_video_raises_on_yt_dlp_failure(monkeypatch):
    import subprocess
    import agents.tools as tools
    # skip jitter sleep
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    class R:
        returncode = 1
        stderr = "errormsg"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="yt-dlp download failed"):
        tools.download_video("http://x", "abc")


def test_download_video_finds_mp4(monkeypatch, tmp_path):
    import subprocess
    import agents.tools as tools
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    monkeypatch.setattr(tools, "TMP", str(tmp_path))
    (tmp_path / "abc.mp4").write_bytes(b"x")
    class R:
        returncode = 0
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert tools.download_video("http://x", "abc").endswith("abc.mp4")


def test_download_video_missing_file_raises(monkeypatch, tmp_path):
    import subprocess
    import agents.tools as tools
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    monkeypatch.setattr(tools, "TMP", str(tmp_path))
    class R:
        returncode = 0
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="video file not found"):
        tools.download_video("http://x", "missing")


def test_ytdlp_json_raises_on_failure(monkeypatch):
    import subprocess
    import agents.tools as tools
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    class R:
        returncode = 2
        stdout = ""
        stderr = "bad"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="yt-dlp metadata failed"):
        tools.ytdlp_json("http://x")


def test_ytdlp_json_parses_stdout(monkeypatch):
    import subprocess, json
    import agents.tools as tools
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    class R:
        returncode = 0
        stdout = json.dumps({"id": "abc", "title": "T"})
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert tools.ytdlp_json("http://x") == {"id": "abc", "title": "T"}


def test_ytdlp_command_includes_required_flags(monkeypatch):
    import subprocess
    import agents.tools as tools
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    seen = {}
    class R:
        returncode = 0
        stdout = "{}"
        stderr = ""
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    tools.ytdlp_json("https://example.com")
    cmd = " ".join(seen["cmd"])
    # CLAUDE.md rule 2: cookies + retries required on yt-dlp calls
    assert "credentials/cookies.txt" in cmd
    assert "--retries" in cmd


def test_download_command_includes_sleep_flags(monkeypatch, tmp_path):
    import subprocess
    import agents.tools as tools
    monkeypatch.setattr(tools, "_jitter", lambda: None)
    monkeypatch.setattr(tools, "TMP", str(tmp_path))
    (tmp_path / "abc.mp4").write_bytes(b"x")
    seen = {}
    class R:
        returncode = 0
        stderr = ""
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    tools.download_video("https://example.com", "abc")
    cmd = " ".join(seen["cmd"])
    assert "--sleep-requests" in cmd
    assert "--sleep-interval" in cmd
    assert "--cookies" in cmd
