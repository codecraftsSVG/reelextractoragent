import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, ensure_job_reel_url_column
from backend.models import Job, Reel, TrajectoryEvent, Evaluation


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_job_model(db_session):
    job = Job(target_user="@testuser", status="queued", total_reels=1)
    db_session.add(job)
    db_session.commit()
    saved = db_session.query(Job).filter_by(target_user="@testuser").first()
    assert saved is not None
    assert saved.status == "queued"
    assert saved.total_reels == 1
    assert saved.created_at is not None


def test_job_defaults(db_session):
    job = Job(target_user="@x")
    db_session.add(job)
    db_session.commit()
    assert job.status == "queued"
    assert job.total_reels == 0
    assert job.done_reels == 0
    assert job.reel_url is None


def test_reel_and_evaluation_models(db_session):
    job = Job(target_user="@testuser", status="done", total_reels=1)
    db_session.add(job)
    db_session.commit()
    reel = Reel(job_id=job.id, shortcode="abc123XYZ",
                reel_url="https://www.instagram.com/reel/abc123XYZ/",
                verify_status="pass", score=85.0)
    db_session.add(reel)
    db_session.commit()
    eval_row = Evaluation(reel_id=reel.id, criterion="Clarity",
                          score=90.0, justification="Clear.")
    db_session.add(eval_row)
    db_session.commit()
    saved_reel = db_session.query(Reel).filter_by(shortcode="abc123XYZ").first()
    assert saved_reel.score == 85.0
    saved_eval = db_session.query(Evaluation).filter_by(reel_id=saved_reel.id).first()
    assert saved_eval.criterion == "Clarity"
    assert saved_eval.score == 90.0


def test_trajectory_event_foreign_keys(db_session):
    job = Job(target_user="@t", status="running")
    db_session.add(job)
    db_session.commit()
    reel = Reel(job_id=job.id, shortcode="s1")
    db_session.add(reel)
    db_session.commit()
    ev = TrajectoryEvent(job_id=job.id, reel_id=reel.id, agent="A", step="s",
                         input_hash="h", output="o", latency_ms=10,
                         status="ok", error_message="err", opik_trace_id="tid-1")
    db_session.add(ev)
    db_session.commit()
    got = db_session.get(TrajectoryEvent, ev.id)
    assert got.agent == "A"
    assert got.error_message == "err"
    assert got.opik_trace_id == "tid-1"


def test_trajectory_event_reel_id_nullable(db_session):
    job = Job(target_user="@t", status="running")
    db_session.add(job)
    db_session.commit()
    ev = TrajectoryEvent(job_id=job.id, reel_id=None, agent="A", step="s")
    db_session.add(ev)
    db_session.commit()
    assert ev.reel_id is None


def test_ensure_job_reel_url_column_idempotent_in_memory():
    # On the live test engine (SQLite) this must not raise
    ensure_job_reel_url_column()
    ensure_job_reel_url_column()
