from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    target_user = Column(String, nullable=False)
    reel_url = Column(String, nullable=True)
    status = Column(String, default="queued")  # queued/running/done/error
    total_reels = Column(Integer, default=0)
    done_reels = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

class Reel(Base):
    __tablename__ = "reels"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    shortcode = Column(String)
    reel_url = Column(String)
    md_path = Column(String)
    verify_status = Column(String, default="pending")  # pending/pass/retry/fail
    score = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

class TrajectoryEvent(Base):
    __tablename__ = "trajectory_events"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    reel_id = Column(Integer, ForeignKey("reels.id"), nullable=True)
    agent = Column(String)
    step = Column(String)
    input_hash = Column(String)
    output = Column(Text)
    latency_ms = Column(Integer)
    status = Column(String, default="ok")
    created_at = Column(DateTime, server_default=func.now())

class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True)
    reel_id = Column(Integer, ForeignKey("reels.id"))
    criterion = Column(String)
    score = Column(Float)
    justification = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
