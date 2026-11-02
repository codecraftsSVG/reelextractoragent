"""Job runner: deterministic pipeline execution with trajectory logging.
ADK orchestrator (agents/orchestrator.py) is the LLM-judgment layer; this
runner executes tools and logs every step.
Usage: python workers/runner.py <job_id>
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, Base, engine
from backend.models import Job, Reel, Evaluation
from trajectory.logger import TrajectoryLogger
from agents import scout, fetch, transcript, ocr, writer, verifier, evaluator

def run_job(job_id: int):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    job = db.get(Job, job_id)
    traj = TrajectoryLogger(job_id=job_id)

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

        md_path = writer.write_md(out_dir, f, t, o)

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
