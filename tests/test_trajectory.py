import pytest
from trajectory.logger import TrajectoryLogger
from backend.database import Base, engine, SessionLocal
from backend.models import Job, TrajectoryEvent


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _make_job():
    db = SessionLocal()
    job = Job(target_user="@testuser", status="running")
    db.add(job)
    db.commit()
    jid = job.id
    db.close()
    return jid


def test_trajectory_logger_success():
    jid = _make_job()
    logger = TrajectoryLogger(job_id=jid)
    with logger.step(agent="TestAgent", step="test_step") as step:
        step.input = {"foo": "bar"}
        step.output = {"result": "success"}
    db = SessionLocal()
    event = db.query(TrajectoryEvent).filter_by(job_id=jid).first()
    assert event is not None
    assert event.agent == "TestAgent"
    assert event.step == "test_step"
    assert event.status == "ok"
    assert event.input_hash is not None
    assert len(event.input_hash) == 16
    assert event.latency_ms >= 0
    assert event.error_message is None
    db.close()


def test_trajectory_logger_failure_records_error_and_traceback():
    jid = _make_job()
    logger = TrajectoryLogger(job_id=jid)
    with pytest.raises(ValueError, match="boom"):
        with logger.step(agent="FailAgent", step="bad_step") as step:
            step.input = "in"
            raise ValueError("boom")
    db = SessionLocal()
    event = db.query(TrajectoryEvent).filter_by(job_id=jid).first()
    assert event.status == "error"
    assert "ValueError" in event.error_message
    assert "boom" in event.error_message
    assert "Traceback" in event.error_message
    db.close()


def test_trajectory_logger_does_not_swallow_exception():
    jid = _make_job()
    logger = TrajectoryLogger(job_id=jid)
    try:
        with logger.step(agent="A", step="s"):
            raise RuntimeError("should propagate")
        assert False, "exception swallowed"
    except RuntimeError:
        pass


def test_trajectory_logger_input_hash_stable_for_same_input(caplog):
    jid = _make_job()
    logger = TrajectoryLogger(job_id=jid)
    with logger.step(agent="A", step="s1") as s1:
        s1.input = {"a": 1}
        s1.output = "x"
    with logger.step(agent="A", step="s2") as s2:
        s2.input = {"a": 1}
        s2.output = "y"
    db = SessionLocal()
    rows = db.query(TrajectoryEvent).filter_by(job_id=jid).all()
    assert len(rows) == 2
    assert rows[0].input_hash == rows[1].input_hash
    db.close()


def test_trajectory_logger_long_output_truncated_to_4000():
    jid = _make_job()
    logger = TrajectoryLogger(job_id=jid)
    with logger.step(agent="A", step="s") as step:
        step.input = "in"
        step.output = "z" * 9000
    db = SessionLocal()
    event = db.query(TrajectoryEvent).filter_by(job_id=jid).first()
    assert len(event.output) <= 4000
    db.close()


def test_trajectory_logger_none_output_becomes_empty_string():
    jid = _make_job()
    logger = TrajectoryLogger(job_id=jid)
    with logger.step(agent="A", step="s") as step:
        step.input = None
        step.output = None
    db = SessionLocal()
    event = db.query(TrajectoryEvent).filter_by(job_id=jid).first()
    assert (event.output or "") == ""
    db.close()


def test_app_logger_writes_records(caplog):
    from trajectory.logger import get_logger
    with caplog.at_level("INFO", logger="MyApp"):
        get_logger("MyApp").info("hello world")
    assert "hello world" in caplog.text


def test_app_logger_error(caplog):
    from trajectory.logger import get_logger
    with caplog.at_level("ERROR", logger="ErrApp"):
        get_logger("ErrApp").error("bad thing")
    assert "bad thing" in caplog.text
