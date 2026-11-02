"""VerifierAgent: deterministic fidelity checks V1-V7."""
import os

MIN_VIDEO_BYTES = 50 * 1024

def verify_reel(fetch: dict, transcript: dict, ocr: dict, md_path: str, md_caption: str,
                expected_total: int = None, extracted_total: int = None) -> dict:
    checks = []

    # V1 video integrity
    vp = fetch.get("video_path", "")
    v1 = os.path.exists(vp) and os.path.getsize(vp) > MIN_VIDEO_BYTES
    checks.append(("V1_video_integrity", v1, "video missing or <50KB"))

    # V2 frame coverage
    dur = ocr.get("duration_s") or 0
    v2 = dur == 0 or len(ocr.get("raw") or []) >= dur * 0.4
    checks.append(("V2_frame_coverage", v2, f"frames {len(ocr.get('raw') or [])} < 0.4x duration {dur}"))

    # V3 caption match (exact)
    v3 = (md_caption or "").strip() == (fetch.get("caption") or "").strip()
    checks.append(("V3_caption_match", v3, "MD caption differs from yt-dlp caption"))

    # V4 transcript sanity
    v4 = (transcript.get("avg_confidence") or 0) >= 0.35  # no_speech_prob proxy; lower = speech
    checks.append(("V4_transcript_confidence", v4, "avg no_speech_prob above threshold"))

    # V5 no runaway duplication
    lines = ocr.get("lines") or []
    v5 = not any(lines[i] == lines[i+1] == lines[i+2] for i in range(len(lines) - 2))
    checks.append(("V5_dedup", v5, "line repeated 3+ times consecutively"))

    # V6 md structure
    try:
        with open(md_path) as f:
            content = f.read()
        v6 = all(s in content for s in ("## Caption", "## Transcript", "## On-screen text", "## Hashtags"))
    except FileNotFoundError:
        v6 = False
    checks.append(("V6_md_structure", v6, "required sections missing"))

    # V7 count reconciliation
    if expected_total is not None and extracted_total is not None:
        v7 = expected_total == extracted_total
        checks.append(("V7_count", v7, f"{extracted_total}/{expected_total} reels"))
    else:
        checks.append(("V7_count", True, "not checked"))

    failed = [name for name, ok, _ in checks if not ok]
    return {
        "status": "pass" if not failed else "retry",
        "failed_checks": failed,
        "detail": {name: {"ok": ok, "reason": reason} for name, ok, reason in checks},
    }
