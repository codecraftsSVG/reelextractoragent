import os
import pytest
from agents.tools import dedupe_lines, video_duration
from agents.verifier import verify_reel
from agents.writer import write_md

# ---------- dedupe_lines ----------

def test_dedupe_lines():
    ocr_results = [
        ("frame_0001.png", "Hello World\nLine two"),
        ("frame_0002.png", "Line two\nUnique line"),
        ("frame_0003.png", "Unique line\nEnd line"),
    ]
    assert dedupe_lines(ocr_results) == ["Hello World", "Line two", "Unique line", "End line"]


def test_dedupe_empty():
    assert dedupe_lines([]) == []


def test_dedupe_all_same_frame():
    assert dedupe_lines([("f1.png", "same\nsame\nsame")]) == ["same"]


def test_dedupe_blank_lines_stripped():
    assert dedupe_lines([("f1.png", "  \nHello\n\n  World  \n")]) == ["Hello", "World"]


def test_dedupe_non_consecutive_dup_kept():
    results = [("f1.png", "A"), ("f2.png", "B"), ("f3.png", "A")]
    assert dedupe_lines(results) == ["A", "B", "A"]


# ---------- video_duration ----------

def test_video_duration_parses_ffmpeg_stderr(monkeypatch):
    import subprocess
    class R:
        stderr = "  Duration: 00:01:23.45, start: 0.000000, bitrate: 500 kb/s"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert video_duration("anything.mp4") == pytest.approx(83.45)


def test_video_duration_no_duration_line(monkeypatch):
    import subprocess
    class R:
        stderr = "no duration here"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert video_duration("anything.mp4") == 0.0


def test_video_duration_bad_numbers(monkeypatch):
    import subprocess
    class R:
        stderr = "Duration: xx:yy:zz, bitrate: 1 kb/s"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert video_duration("anything.mp4") == 0.0


# ---------- verify_reel ----------

def _good_md(tmp_path, caption="Test caption #hashtag"):
    md = tmp_path / "abc.md"
    md.write_text(f"""---
reel_url: https://www.instagram.com/reel/abc/
shortcode: abc
creator: test
date: 20230101
likes: 10
verify_status: pending
score:
---

## Caption
{caption}

## Transcript (spoken)
Hello world

## On-screen text
Test caption

## Hashtags
#hashtag
""")
    return str(md)


def _good_args(tmp_path, **over):
    dummy = tmp_path / "test.mp4"
    dummy.write_bytes(b"0" * (60 * 1024))
    args = dict(
        fetch={"video_path": str(dummy), "caption": "Test caption #hashtag",
               "url": "https://www.instagram.com/reel/abc/"},
        transcript={"text": "Hello world", "avg_confidence": 0.8},
        ocr={"duration_s": 5.0, "raw": ["f1", "f2", "f3"], "lines": ["Test caption"]},
        md_path=_good_md(tmp_path),
        md_caption="Test caption #hashtag",
        expected_total=1,
        extracted_total=1,
    )
    args.update(over)
    return args


def test_verify_reel_passing(tmp_path):
    res = verify_reel(**_good_args(tmp_path))
    assert res["status"] == "pass"
    assert res["failed_checks"] == []


def test_verify_v1_missing_video_fails(tmp_path):
    args = _good_args(tmp_path)
    args["fetch"] = {"video_path": str(tmp_path / "nope.mp4"), "caption": "Test caption #hashtag"}
    res = verify_reel(**args)
    assert "V1_video_integrity" in res["failed_checks"]
    assert res["status"] == "retry"


def test_verify_v1_small_video_fails(tmp_path):
    small = tmp_path / "small.mp4"
    small.write_bytes(b"0" * 1000)
    args = _good_args(tmp_path)
    args["fetch"] = dict(args["fetch"], video_path=str(small))
    res = verify_reel(**args)
    assert "V1_video_integrity" in res["failed_checks"]


def test_verify_v2_insufficient_frames_fails(tmp_path):
    args = _good_args(tmp_path)
    args["ocr"] = {"duration_s": 10.0, "raw": ["f1"], "lines": ["x"]}
    res = verify_reel(**args)
    assert "V2_frame_coverage" in res["failed_checks"]


def test_verify_v2_zero_duration_passes(tmp_path):
    args = _good_args(tmp_path)
    args["ocr"] = {"duration_s": 0, "raw": [], "lines": []}
    res = verify_reel(**args)
    assert "V2_frame_coverage" not in res["failed_checks"]


def test_verify_v3_caption_mismatch_fails(tmp_path):
    res = verify_reel(**_good_args(tmp_path, md_caption="different caption"))
    assert "V3_caption_match" in res["failed_checks"]


def test_verify_v3_whitespace_tolerant(tmp_path):
    res = verify_reel(**_good_args(tmp_path, md_caption="  Test caption #hashtag  "))
    assert "V3_caption_match" not in res["failed_checks"]


def test_verify_v4_low_confidence_fails(tmp_path):
    args = _good_args(tmp_path)
    args["transcript"] = {"text": "hi", "avg_confidence": 0.1}
    res = verify_reel(**args)
    assert "V4_transcript_confidence" in res["failed_checks"]


def test_verify_v4_missing_confidence_fails(tmp_path):
    args = _good_args(tmp_path)
    args["transcript"] = {"text": "hi"}
    res = verify_reel(**args)
    assert "V4_transcript_confidence" in res["failed_checks"]


def test_verify_v5_triple_dup_fails(tmp_path):
    args = _good_args(tmp_path)
    args["ocr"] = dict(args["ocr"], lines=["a", "a", "a"])
    res = verify_reel(**args)
    assert "V5_dedup" in res["failed_checks"]


def test_verify_v6_missing_md_fails(tmp_path):
    res = verify_reel(**_good_args(tmp_path, md_path=str(tmp_path / "missing.md")))
    assert "V6_md_structure" in res["failed_checks"]


def test_verify_v6_missing_section_fails(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("## Caption\nonly this\n")
    res = verify_reel(**_good_args(tmp_path, md_path=str(bad)))
    assert "V6_md_structure" in res["failed_checks"]


def test_verify_v7_count_mismatch_fails(tmp_path):
    res = verify_reel(**_good_args(tmp_path, expected_total=3, extracted_total=1))
    assert "V7_count" in res["failed_checks"]


def test_verify_v7_none_passes(tmp_path):
    res = verify_reel(**_good_args(tmp_path, expected_total=None, extracted_total=None))
    assert "V7_count" not in res["failed_checks"]


def test_verify_detail_shape(tmp_path):
    res = verify_reel(**_good_args(tmp_path))
    assert "detail" in res
    for name, info in res["detail"].items():
        assert "ok" in info and "reason" in info


# ---------- write_md ----------

def test_write_md(tmp_path):
    fetch_data = {
        "url": "https://www.instagram.com/reel/xyz/",
        "shortcode": "xyz",
        "uploader": "creator_guy",
        "upload_date": "20231015",
        "like_count": 500,
        "caption": "Amazing reel #cool #python",
    }
    path = write_md(str(tmp_path / "output"), fetch_data,
                    {"text": "Python is awesome"},
                    {"lines": ["Amazing reel"]},
                    verify_status="pass", score=92.5)
    assert os.path.exists(path)
    content = open(path).read()
    assert "shortcode: xyz" in content
    assert "## Caption" in content
    assert "Amazing reel #cool #python" in content
    assert "Python is awesome" in content
    assert "verify_status: pass" in content
    assert "score: 92.5" in content
    assert "#cool #python" in content


def test_write_md_fallbacks(tmp_path):
    fetch_data = {"url": "u", "shortcode": "s1", "uploader": "x",
                  "upload_date": "", "like_count": 0, "caption": "no tags here"}
    path = write_md(str(tmp_path), fetch_data, {}, {})
    content = open(path).read()
    assert "[no speech detected]" in content
    assert "[no on-screen text detected]" in content
    assert "[none]" in content
    assert "score:" in content


def test_write_md_creates_nested_dirs(tmp_path):
    fetch_data = {"url": "u", "shortcode": "s2", "uploader": "x",
                  "upload_date": "", "like_count": 0, "caption": ""}
    path = write_md(str(tmp_path / "a" / "b" / "c"), fetch_data, {}, {})
    assert os.path.exists(path)
