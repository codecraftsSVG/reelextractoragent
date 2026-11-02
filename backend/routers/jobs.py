import os, subprocess
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import Job, Reel, Evaluation

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class JobIn(BaseModel):
    target_user: str

@router.post("")
def create_job(payload: JobIn, db: Session = Depends(get_db)):
    job = Job(target_user=payload.target_user.lstrip("@"), status="queued")
    db.add(job)
    db.commit()
    # Fire-and-forget runner (use Celery in production)
    subprocess.Popen(["python", "workers/runner.py", str(job.id)],
                     cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return {"job_id": job.id}

@router.get("")
def list_jobs(db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.id.desc()).all()

@router.get("/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    reels = db.query(Reel).filter(Reel.job_id == job_id).all()
    return {"job": job, "reels": reels}

@router.get("/{job_id}/evaluation")
def job_evaluations(job_id: int, db: Session = Depends(get_db)):
    rows = (db.query(Evaluation, Reel)
              .join(Reel, Evaluation.reel_id == Reel.id)
              .filter(Reel.job_id == job_id).all())
    return [{"shortcode": r.shortcode, "criterion": e.criterion,
             "score": e.score, "justification": e.justification} for e, r in rows]
