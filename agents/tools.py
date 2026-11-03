"""Tool implementations: yt-dlp, ffmpeg, tesseract, whisper wrappers."""
import json, os, random, subprocess, time, shutil
import imageio_ffmpeg

_ffmpeg_source = imageio_ffmpeg.get_ffmpeg_exe()
_ffmpeg_dir = os.path.abspath("storage/downloads")
os.makedirs(_ffmpeg_dir, exist_ok=True)
_ffmpeg_target = os.path.join(_ffmpeg_dir, "ffmpeg.exe")
if not os.path.exists(_ffmpeg_target):
    shutil.copyfile(_ffmpeg_source, _ffmpeg_target)
os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

COOKIES = "credentials/cookies.txt"
TMP = "storage/tmp"
os.makedirs(TMP, exist_ok=True)

def _jitter():
    time.sleep(random.uniform(8, 15))

def ytdlp_json(url: str) -> dict:
    """Full metadata for a reel via yt-dlp."""
    _jitter()
    r = subprocess.run(
        ["yt-dlp", "--cookies", COOKIES, "--dump-json", "--retries", "3", url],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {r.stderr[-500:]}")
    return json.loads(r.stdout)

def download_video(url: str, shortcode: str) -> str:
    """Download the reel video; return local path."""
    _jitter()
    out = os.path.join(TMP, f"{shortcode}.%(ext)s")
    r = subprocess.run(
        ["yt-dlp", "--cookies", COOKIES, "-o", out,
         "--sleep-requests", "5", "--sleep-interval", "10", url],
        capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {r.stderr[-500:]}")
    for ext in ("mp4", "webm", "mkv"):
        p = os.path.join(TMP, f"{shortcode}.{ext}")
        if os.path.exists(p):
            return p
    raise RuntimeError("video file not found after download")

def extract_frames(video_path: str, shortcode: str, fps: float = 0.5) -> list:
    """Extract frames at given fps; return list of png paths."""
    pattern = os.path.join(TMP, f"{shortcode}_%04d.png")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", f"fps={fps}", pattern],
        capture_output=True, text=True, timeout=300)
    frames = sorted(f for f in os.listdir(TMP) if f.startswith(f"{shortcode}_") and f.endswith(".png"))
    return [os.path.join(TMP, f) for f in frames]

def ocr_frames(frames: list) -> list:
    """OCR each frame; return list of (frame, text) tuples."""
    import pytesseract
    from PIL import Image
    results = []
    for f in frames:
        try:
            txt = pytesseract.image_to_string(Image.open(f))
        except Exception as e:
            txt = f"[unreadable frame: {e}]"
        results.append((os.path.basename(f), txt.strip()))
    return results

def transcribe_audio(video_path: str, shortcode: str) -> dict:
    """Transcribe with whisper tiny; returns segments with confidences."""
    import whisper
    model = whisper.load_model("tiny")
    result = model.transcribe(video_path)
    return {
        "text": result["text"],
        "avg_confidence": sum(s.get("no_speech_prob", 0.5) for s in result["segments"]) / max(1, len(result["segments"])),
        "segments": [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in result["segments"]],
    }

def video_duration(video_path: str) -> float:
    r = subprocess.run(
        ["ffmpeg", "-i", video_path], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            try:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            except Exception:
                pass
    return 0.0

def dedupe_lines(ocr_results: list) -> list:
    """Remove consecutive duplicate OCR lines (captions persist across frames)."""
    seen_run, out = None, []
    for frame, txt in ocr_results:
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        for l in lines:
            if l != seen_run:
                out.append(l)
                seen_run = l
    return out
