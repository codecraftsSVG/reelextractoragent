"""MDWriterAgent: render the final markdown file."""
import os

MD_TEMPLATE = """---
reel_url: {url}
shortcode: {shortcode}
creator: {uploader}
date: {upload_date}
likes: {like_count}
verify_status: {verify_status}
score: {score}
---

## Caption
{caption}

## Transcript (spoken)
{transcript}

## On-screen text
{onscreen}

## Hashtags
{hashtags}
"""

def write_md(output_dir: str, fetch: dict, transcript: dict, ocr: dict,
             verify_status: str = "pending", score=None) -> str:
    os.makedirs(output_dir, exist_ok=True)
    # Normalize caption to a single line: verifier V3 compares the rendered
    # `## Caption` section against fetch["caption"] exactly, and a caption with
    # embedded newlines would wrap and never match (permanent retry loop).
    caption = " ".join((fetch.get("caption") or "").split())
    hashtags = " ".join(t for t in caption.split() if t.startswith("#"))
    md = MD_TEMPLATE.format(
        url=fetch.get("url"), shortcode=fetch.get("shortcode"),
        uploader=fetch.get("uploader"), upload_date=fetch.get("upload_date"),
        like_count=fetch.get("like_count"), verify_status=verify_status,
        score=score if score is not None else "",
        caption=caption,
        transcript=transcript.get("text") or "[no speech detected]",
        onscreen="\n".join(ocr.get("lines") or []) or "[no on-screen text detected]",
        hashtags=hashtags or "[none]",
    )
    path = os.path.join(output_dir, f"{fetch['shortcode']}.md")
    with open(path, "w") as f:
        f.write(md)
    return path
