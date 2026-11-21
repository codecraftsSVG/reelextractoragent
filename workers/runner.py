"""Job runner: deterministic pipeline execution with trajectory logging.
ADK orchestrator (agents/orchestrator.py) is the LLM-judgment layer; this
runner executes tools and logs every step.
Usage: python workers/runner.py <job_id>
"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, Base, engine
from backend.models import Job, Reel, Evaluation
from trajectory.logger import TrajectoryLogger
from agents import scout, fetch, transcript, ocr, writer, verifier, evaluator

# Hard ceiling for one job. Render recycles free-tier web services and
# redeploys kill the fire-and-forget runner mid-job; without this a wedged
# job would sit in "running" forever.
JOB_TIMEOUT_S = int(os.environ.get("JOB_TIMEOUT_S", "3600"))

def recover_stale_jobs(db, current_job_id: int) -> list:
    """Mark jobs stuck in 'running' by a DEAD process as 'error'.
    A runner is spawned per job and sets its own job 'running' only after this
    sweep, so any other 'running' job older than the grace window belongs to a
    runner that died (deploy recycle, spin-down, crash)."""
    # created_at is a naive column; use naive UTC to avoid the utcnow deprecation
    # while keeping comparisons type-consistent.
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    stale = (db.query(Job)
             .filter(Job.status == "running",
                     Job.id != current_job_id,
                     Job.created_at < cutoff)
             .all())
    for j in stale:
        j.status = "error"
    if stale:
        db.commit()
    return [j.id for j in stale]

def run_job(job_id: int):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    job = db.get(Job, job_id)
    if job is None:
        raise RuntimeError(f"job {job_id} not found")
    traj = TrajectoryLogger(job_id=job_id)
    recovered = recover_stale_jobs(db, job_id)
    if recovered:
        print(f"recovered stale 'running' jobs -> error: {recovered}")
    deadline = time.time() + JOB_TIMEOUT_S

    if getattr(job, "reel_url", None):
        reel_url = job.reel_url.strip()
        shortcode = reel_url.split("?")[0].rstrip("/").split("/")[-1]
        job.status = "running"
        db.commit()
        traj.reel_id = None
        r = Reel(job_id=job_id, shortcode=shortcode, reel_url=reel_url)
        db.add(r)
        db.commit()
        traj.reel_id = r.id

        if time.time() > deadline:
            job.status = "error"
            db.commit()
            raise RuntimeError(f"job {job_id} exceeded {JOB_TIMEOUT_S}s deadline")

        try:
            from extract_reel import download_via_igexport
            with traj.step("DownloadAgent", "igexport_download") as s:
                s.input = reel_url
                video_path = asyncio.run(download_via_igexport(reel_url, shortcode))
                s.output = video_path

            f = {
                "shortcode": shortcode,
                "url": reel_url,
                # Real metadata when yt-dlp can read it, [unreadable] otherwise
                # (CLAUDE.md rule 4 - never fabricate caption/metadata).
                "caption": "[unreadable]",
                "uploader": "[unreadable]",
                "upload_date": "[unreadable]",
                "like_count": 0,
                "video_path": video_path,
            }
            with traj.step("FetchAgent", "metadata") as s:
                s.input = reel_url
                try:
                    import agents.tools as _tools
                    meta = _tools.ytdlp_json(reel_url)
                    f["caption"] = meta.get("description") or meta.get("title") or "[unreadable]"
                    f["uploader"] = meta.get("uploader") or meta.get("channel") or "[unreadable]"
                    f["upload_date"] = meta.get("upload_date") or "[unreadable]"
                    f["like_count"] = meta.get("like_count") or 0
                    s.output = "metadata retrieved"
                except Exception as e:
                    s.output = f"metadata unavailable: {e}"
                    print(f"metadata unavailable, using [unreadable]: {e}")
            with traj.step("TranscriptAgent", "transcribe") as s:
                s.input = video_path
                t = transcript.transcribe(video_path, shortcode)
                s.output = f"chars={len(t['text'])}"
            with traj.step("OCRAgent", "ocr") as s:
                s.input = video_path
                o = ocr.extract_text(video_path, shortcode)
                s.output = f"frames={o['frames_extracted']} lines={len(o['lines'])}"

            out_dir = os.path.join("storage", "output", f"@reel-{shortcode}")
            md_path = writer.write_md(out_dir, f, t, o)
            with traj.step("VerifierAgent", "verify") as s:
                s.input = md_path
                v = verifier.verify_reel(f, t, o, md_path, f["caption"])
                s.output = json.dumps(v["detail"])[:2000]
                if v["status"] == "retry":
                    o2 = ocr.extract_text(video_path, shortcode, fps=1.0)
                    md_path = writer.write_md(out_dir, f, t, o2)
                    v = verifier.verify_reel(f, t, o2, md_path, f["caption"])
                    o = o2
            with traj.step("EvaluatorAgent", "evaluate") as s:
                s.input = md_path
                ev = evaluator.score(f, t, o, v)
                s.output = f"total={ev['total']} verdict={ev['verdict']}"

            r.md_path = md_path
            r.verify_status = v["status"]
            r.score = ev["total"]
            for crit, sc in ev["criteria"].items():
                db.add(Evaluation(reel_id=r.id, criterion=crit, score=sc,
                                  justification=ev["justification"][:500]))
            job.done_reels = 1
            job.status = "done"
            db.commit()
            print(f"Job {job_id} complete -> {md_path}")
            return
        except Exception as e:
            job.status = "error"
            db.commit()
            with traj.step("DownloadAgent", "reel_job") as s:
                s.input = reel_url
                s.output = str(e)
            raise

    # 1. Scout
    with traj.step("ProfileScoutAgent", "scout") as s:
        s.input = job.target_user
        result = scout.discover_reels(job.target_user)
        s.output = f"count={result['count']}"
    job.total_reels = result["count"]
    job.status = "running"
    db.commit()

    out_dir = os.path.join("storage/output", f"@{job.target_user}")
    consecutive_failures = 0

    for i, reel_info in enumerate(result["reels"]):
        shortcode = reel_info["shortcode"]
        url = reel_info["url"]
        traj.reel_id = None
        r = Reel(job_id=job_id, shortcode=shortcode, reel_url=url)
        db.add(r); db.commit()
        traj.reel_id = r.id

        if time.time() > deadline:
            job.status = "error"
            db.commit()
            raise RuntimeError(f"job {job_id} exceeded {JOB_TIMEOUT_S}s deadline")

        try:
            with traj.step("FetchAgent", "fetch") as s:
                s.input = url
                f = fetch.fetch_reel(url, shortcode)
                s.output = f"video={os.path.basename(f['video_path'])}"
            consecutive_failures = 0
        except Exception as e:
            with traj.step("FetchAgent", "fetch") as s:
                s.input = url; s.output = str(e)
            consecutive_failures += 1
            if consecutive_failures > 3:
                job.status = "error"
                db.commit()
                raise RuntimeError("cookie/session dead - re-upload credentials")
            continue

        with traj.step("TranscriptAgent", "transcribe") as s:
            s.input = f["video_path"]
            t = transcript.transcribe(f["video_path"], shortcode)
            s.output = f"chars={len(t['text'])}"

        with traj.step("OCRAgent", "ocr") as s:
            s.input = f["video_path"]
            o = ocr.extract_text(f["video_path"], shortcode)
            s.output = f"frames={o['frames_extracted']} lines={len(o['lines'])}"

        with traj.step("WriterAgent", "write_md") as s:
            s.input = f["shortcode"]
            md_path = writer.write_md(out_dir, f, t, o)
            s.output = md_path

        with traj.step("VerifierAgent", "verify") as s:
            s.input = md_path
            v = verifier.verify_reel(f, t, o, md_path, f["caption"])
            s.output = json.dumps(v["detail"])[:2000]
            if v["status"] == "retry":
                o2 = ocr.extract_text(f["video_path"], shortcode, fps=1.0)
                md_path = writer.write_md(out_dir, f, t, o2)
                v = verifier.verify_reel(f, t, o2, md_path, f["caption"])

        with traj.step("EvaluatorAgent", "evaluate") as s:
            s.input = md_path
            ev = evaluator.score(f, t, o, v)
            s.output = f"total={ev['total']} verdict={ev['verdict']}"

        r.md_path = md_path
        r.verify_status = v["status"]
        r.score = ev["total"]
        for crit, sc in ev["criteria"].items():
            db.add(Evaluation(reel_id=r.id, criterion=crit, score=sc,
                              justification=ev["justification"][:500]))
        db.commit()
        job.done_reels = i + 1
        db.commit()

    job.status = "done"
    db.commit()
    print(f"Job {job_id} complete -> {out_dir}")

if __name__ == "__main__":
    run_job(int(sys.argv[1]))
