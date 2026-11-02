"""FetchAgent: metadata + video download for one reel."""
from .tools import ytdlp_json, download_video

def fetch_reel(url: str, shortcode: str) -> dict:
    meta = ytdlp_json(url)
    video_path = download_video(url, shortcode)
    return {
        "shortcode": shortcode,
        "url": url,
        "caption": meta.get("description") or meta.get("title") or "",
        "uploader": meta.get("uploader") or meta.get("channel") or "",
        "upload_date": meta.get("upload_date"),
        "like_count": meta.get("like_count"),
        "video_path": video_path,
    }
