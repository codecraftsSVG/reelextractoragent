"""OCRAgent: on-screen text extraction, deduplicated and ordered."""
from .tools import extract_frames, ocr_frames, dedupe_lines, video_duration

def extract_text(video_path: str, shortcode: str, fps: float = 0.5) -> dict:
    duration = video_duration(video_path)
    frames = extract_frames(video_path, shortcode, fps=fps)
    raw = ocr_frames(frames)
    lines = dedupe_lines(raw)
    return {
        "duration_s": duration,
        "frames_extracted": len(frames),
        "raw": raw,
        "lines": lines,
    }
