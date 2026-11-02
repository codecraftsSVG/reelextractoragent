"""ProfileScoutAgent: discover all reel URLs of a target user."""
import re, requests
from .tools import COOKIES

def _load_cookies() -> dict:
    jar = {}
    with open(COOKIES) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 7 and parts[5] == "sessionid":
                jar["sessionid"] = parts[6]
    return jar

def discover_reels(username: str, max_pages: int = 50) -> dict:
    """Paginate the profile reels tab. Returns {"reels": [{url, shortcode, taken_at}], "count": N}."""
    # Primary path: yt-dlp flat extraction (handles pagination + login)
    import subprocess, json
    r = subprocess.run(
        ["yt-dlp", "--cookies", COOKIES, "--flat-playlist", "--dump-single-json",
         f"https://www.instagram.com/{username}/reels/"],
        capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"scout failed: {r.stderr[-500:]}")
    data = json.loads(r.stdout)
    reels = []
    for e in data.get("entries", []):
        if not e:
            continue
        reels.append({
            "url": e.get("url") or e.get("webpage_url"),
            "shortcode": e.get("id") or (e.get("url") or "").rstrip("/").split("/")[-1],
            "taken_at": e.get("upload_date") or e.get("timestamp"),
        })
    return {"reels": reels, "count": len(reels)}
