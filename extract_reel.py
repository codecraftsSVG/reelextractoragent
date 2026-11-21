"""End-to-end reel downloader and extractor using igexport.com and local pipeline agents."""
import os
import sys
import urllib.request
import asyncio
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import transcript, ocr, writer, verifier, evaluator
from agents.tools import _cookie_path

DOWNLOADS_DIR = os.path.abspath("storage/downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

async def download_via_igexport(reel_url: str, shortcode: str) -> str:
    video_path = os.path.join(DOWNLOADS_DIR, f"{shortcode}.mp4")
    if os.path.exists(video_path):
        return video_path

    # Primary: try yt-dlp with cookies (per CLAUDE.md rules)
    try:
        import subprocess
        print(f"[{shortcode}] Attempting download via yt-dlp...")
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--cookies", _cookie_path(),
            "--sleep-requests", "5",
            "--sleep-interval", "10",
            "--retries", "3",
            "-o", video_path,
            reel_url
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode == 0 and os.path.exists(video_path) and os.path.getsize(video_path) > 50000:
            print(f"[{shortcode}] yt-dlp download successful!")
            return video_path
        else:
            print(f"[{shortcode}] yt-dlp failed or output too small: {res.stderr}")
            if "429" in (res.stderr or "") or "Too Many Requests" in (res.stderr or ""):
                raise RuntimeError("Instagram download is rate-limited (HTTP 429). Retry later.")
    except Exception as e:
        print(f"[{shortcode}] yt-dlp exception: {e}")

    # Fallback: Playwright igexport.com
    print(f"[{shortcode}] Falling back to igexport.com via Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://igexport.com/en/reels-download/", timeout=60000)
            input_box = await page.wait_for_selector('input[type="search"], input[type="text"], input[type="url"], input', timeout=15000)
            await input_box.fill(reel_url)
            await page.keyboard.press("Enter")

            video_elem = await page.wait_for_selector('video', timeout=30000)
            video_src = await video_elem.get_attribute('src')
            if not video_src:
                raise RuntimeError("Could not find video src on igexport page")

            print(f"Downloading video from CDN for {shortcode}...")
            urllib.request.urlretrieve(video_src, video_path)
        finally:
            await browser.close()
    return video_path


def _fetch_metadata(reel_url: str) -> dict:
    """Reel metadata via yt-dlp --dump-json. Never fabricates: on any failure
    returns {} so callers fall back to [unreadable] placeholders (rule 4)."""
    try:
        import json as _json
        import subprocess
        cmd = ["yt-dlp", "--no-warnings", "--cookies", _cookie_path(),
               "--dump-json", "--sleep-requests", "5", "--sleep-interval", "10",
               "--retries", "3", reel_url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode == 0 and res.stdout.strip():
            return _json.loads(res.stdout.splitlines()[0])
    except Exception as e:
        print(f"[metadata] yt-dlp --dump-json failed: {e}")
    return {}


def process_reel(reel_url: str, caption: str | None = None, uploader: str | None = None) -> dict:
    # Extract shortcode from URL
    clean_url = reel_url.split("?")[0].rstrip("/")
    shortcode = clean_url.split("/")[-1]

    # Ensure ffmpeg is in PATH via imageio_ffmpeg
    import imageio_ffmpeg, shutil
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    target = os.path.join(DOWNLOADS_DIR, 'ffmpeg.exe')
    if not os.path.exists(target):
        shutil.copy(exe, target)
    os.environ['PATH'] = DOWNLOADS_DIR + os.pathsep + os.environ['PATH']

    # 1. Download video
    print(f"[{shortcode}] Step 1: Downloading video...")
    video_path = asyncio.run(download_via_igexport(reel_url, shortcode))

    # 2. Real metadata when reachable; [unreadable] placeholders otherwise (rule 4).
    #    Explicit caption/uploader arguments are honoured (CLI/dev use).
    meta = _fetch_metadata(reel_url)
    caption = caption or meta.get("description") or meta.get("title") or "[unreadable]"
    uploader = uploader or meta.get("uploader") or meta.get("channel") or "[unreadable]"
    upload_date = meta.get("upload_date") or "[unreadable]"
    like_count = meta.get("like_count") or 0

    fetch_data = {
        'shortcode': shortcode,
        'url': reel_url,
        'caption': caption,
        'uploader': uploader,
        'upload_date': upload_date,
        'like_count': like_count,
        'video_path': video_path
    }

    # 2. Transcribe
    print(f"[{shortcode}] Step 2: Transcribing audio...")
    t = transcript.transcribe(video_path, shortcode)

    # 3. OCR
    print(f"[{shortcode}] Step 3: Extracting OCR text...")
    o = ocr.extract_text(video_path, shortcode)

    # 4. Write Markdown
    print(f"[{shortcode}] Step 4: Rendering Markdown...")
    md_path = writer.write_md(DOWNLOADS_DIR, fetch_data, t, o)

    # 5. Verify & Score
    print(f"[{shortcode}] Step 5: Verifying & Scoring...")
    v = verifier.verify_reel(fetch_data, t, o, md_path, caption)
    if v['status'] == 'retry':
        o2 = ocr.extract_text(video_path, shortcode, fps=1.0)
        md_path = writer.write_md(DOWNLOADS_DIR, fetch_data, t, o2)
        v = verifier.verify_reel(fetch_data, t, o2, md_path, caption)
        o = o2

    ev = evaluator.score(fetch_data, t, o, v)

    print(f"[{shortcode}] Complete! Video: {video_path} | Markdown: {md_path} | Score: {ev['total']}")
    return {
        "shortcode": shortcode,
        "video_path": video_path,
        "md_path": md_path,
        "score": ev['total'],
        "verdict": ev['verdict']
    }

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.instagram.com/reel/DfBMxNAp-wv/"
    process_reel(url)
