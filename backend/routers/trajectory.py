from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import TrajectoryEvent

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{job_id}")
def get_trajectory(job_id: int, db: Session = Depends(get_db)):
    events = (db.query(TrajectoryEvent)
                .filter(TrajectoryEvent.job_id == job_id)
                .order_by(TrajectoryEvent.id).all())
    return [{"agent": e.agent, "step": e.step, "status": e.status,
             "latency_ms": e.latency_ms, "output": (e.output or "")[:500],
             "error_message": e.error_message,
             "opik_trace_id": e.opik_trace_id,
             "at": str(e.created_at)} for e in events]
