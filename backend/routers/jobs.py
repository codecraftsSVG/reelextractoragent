import os, subprocess, re, sys
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import Job, Reel, Evaluation
from datetime import datetime, timedelta, timezone

router = APIRouter()
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def spawn_runner(job_id: int) -> subprocess.Popen:
    log_dir = os.path.join(ROOT_DIR, "storage", "logs")
    os.makedirs(log_dir, exist_ok=True)
    stdout = open(os.path.join(log_dir, f"runner-{job_id}.out"), "ab")
    stderr = open(os.path.join(log_dir, f"runner-{job_id}.err"), "ab")
    try:
        return subprocess.Popen(
            [sys.executable, "workers/runner.py", str(job_id)],
            cwd=ROOT_DIR,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
        )
    finally:
        stdout.close()
        stderr.close()

def recover_stale_jobs(db: Session) -> list:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    stale = (db.query(Job)
             .filter(Job.status == "running", Job.created_at < cutoff)
             .all())
    for job in stale:
        job.status = "error"
    if stale:
        db.commit()
    return [job.id for job in stale]

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class JobIn(BaseModel):
    target_user: str | None = None
    reel_url: str | None = None

@router.post("")
def create_job(payload: JobIn, db: Session = Depends(get_db)):
    if payload.reel_url:
        reel_url = payload.reel_url.strip()
        if not re.match(r"https://(?:www\.)?instagram\.com/(?:reel|reels)/[A-Za-z0-9_-]+/?(?:\?.*)?$", reel_url):
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Enter a valid Instagram reel URL")
        shortcode = reel_url.split("?")[0].rstrip("/").split("/")[-1]
        job = Job(target_user=f"Reel: {shortcode}", reel_url=reel_url, status="queued",
                  total_reels=1)
    else:
        target_user = (payload.target_user or "").strip().lstrip("@")
        if not target_user:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Enter an Instagram username or reel URL")
        job = Job(target_user=f"@{target_user}", reel_url=None, status="queued")
    db.add(job)
    db.commit()
    try:
        spawn_runner(job.id)
    except Exception as exc:
        job.status = "error"
        db.commit()
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"Could not start the job: {exc}")
    return {"job_id": job.id}

@router.get("")
def list_jobs(db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.id.desc()).all()

@router.get("/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    reels = db.query(Reel).filter(Reel.job_id == job_id).all()
    return {"job": job, "reels": reels}


@router.get("/{job_id}/evaluation")
def job_evaluations(job_id: int, db: Session = Depends(get_db)):
    rows = (db.query(Evaluation, Reel)
              .join(Reel, Evaluation.reel_id == Reel.id)
              .filter(Reel.job_id == job_id).all())
    return [{"shortcode": r.shortcode, "criterion": e.criterion,
             "score": e.score, "justification": e.justification} for e, r in rows]
