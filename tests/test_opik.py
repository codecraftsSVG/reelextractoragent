import os
import importlib
import pytest


def _fresh_opik_module(monkeypatch):
    """Reload opik_client with clean singleton."""
    import trajectory.opik_client as oc
    monkeypatch.setattr(oc, "_opik_client", None)
    return oc


def test_opik_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    oc = _fresh_opik_module(monkeypatch)
    client = oc.OpikClient()
    assert client.enabled is False
    assert client.client is None


def test_opik_disabled_without_package(monkeypatch):
    monkeypatch.setenv("OPIK_API_KEY", "fake-key-123")
    oc = _fresh_opik_module(monkeypatch)
    monkeypatch.setattr(oc, "OPIK_AVAILABLE", False)
    client = oc.OpikClient()
    assert client.enabled is False


def test_opik_init_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("OPIK_API_KEY", "fake-key-123")
    oc = _fresh_opik_module(monkeypatch)
    monkeypatch.setattr(oc, "OPIK_AVAILABLE", True)

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("opik down")

    monkeypatch.setattr(oc, "Opik", Boom)
    client = oc.OpikClient()
    assert client.enabled is False


def test_opik_track_and_end_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    oc = _fresh_opik_module(monkeypatch)
    client = oc.OpikClient()
    assert client.track_step("s", 1, "A", "s") is None
    client.end_span(None, "out", 10, "ok")  # must not raise
    client.log_trace("tid", "n", "out", 10, "ok")


def test_opik_get_client_singleton(monkeypatch):
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    oc = _fresh_opik_module(monkeypatch)
    a = oc.get_opik_client()
    b = oc.get_opik_client()
    assert a is b


def test_opik_enabled_path_with_mock(monkeypatch):
    monkeypatch.setenv("OPIK_API_KEY", "test-key")
    oc = _fresh_opik_module(monkeypatch)

    class FakeSpan:
        def __init__(self):
            self.id = "span-1"
            self.meta = {}
            self.ended = False
            self.name = None
        def update(self, **kw):
            if "metadata" in kw and isinstance(kw["metadata"], dict):
                self.meta.update(kw["metadata"])
            else:
                self.meta.update(kw)
        def end(self):
            self.ended = True

    class FakeOpik:
        def __init__(self, project_name=None, url_override=None):
            self.project_name = project_name
            self.flushed = False
        def span(self, name=None, metadata=None):
            s = FakeSpan()
            s.name = name
            return s
        def flush(self):
            self.flushed = True

    monkeypatch.setattr(oc, "OPIK_AVAILABLE", True)
    monkeypatch.setattr(oc, "Opik", FakeOpik)
    client = oc.OpikClient(project_name="p")
    assert client.enabled is True
    span = client.track_step("s", 42, "DownloadAgent", "fetch")
    assert span is not None
    assert span.name == "DownloadAgent.fetch"
    client.end_span(span, "done-output", 123, "ok")
    assert span.ended is True
    assert span.meta["latency_ms"] == 123


def test_opik_end_span_error_path(monkeypatch):
    monkeypatch.setenv("OPIK_API_KEY", "test-key")
    oc = _fresh_opik_module(monkeypatch)

    class FakeSpan:
        def __init__(self):
            self.id = "s"
        def update(self, **kw):
            pass
        def end(self):
            pass

    class FakeOpik:
        def __init__(self, *a, **k):
            pass
        def span(self, **k):
            return FakeSpan()
        def flush(self):
            pass

    monkeypatch.setattr(oc, "OPIK_AVAILABLE", True)
    monkeypatch.setattr(oc, "Opik", FakeOpik)
    client = oc.OpikClient()
    span = client.track_step("s", 1, "A", "s")
    client.end_span(span, "out", 5, "error", "some failure")
    assert span is not None  # no raise


def test_trajectory_logger_with_opik_enabled(monkeypatch):
    """TrajectoryLogger.log writes opik_trace_id when Opik is enabled (mocked)."""
    monkeypatch.setenv("OPIK_API_KEY", "test-key")
    oc = _fresh_opik_module(monkeypatch)

    class FakeSpan:
        def __init__(self):
            self.id = "span-x"
        def update(self, **kw):
            pass
        def end(self):
            pass

    class FakeOpik:
        def __init__(self, *a, **k):
            pass
        def span(self, **k):
            return FakeSpan()
        def flush(self):
            pass

    monkeypatch.setattr(oc, "OPIK_AVAILABLE", True)
    monkeypatch.setattr(oc, "Opik", FakeOpik)
    monkeypatch.setattr(oc, "_opik_client", None)

    from backend.database import Base, engine, SessionLocal
    from backend.models import Job, TrajectoryEvent
    from trajectory.logger import TrajectoryLogger

    Base.metadata.create_all(engine)
    db = SessionLocal()
    job = Job(target_user="@opiktest", status="running")
    db.add(job)
    db.commit()
    jid = job.id
    db.close()

    logger = TrajectoryLogger(job_id=jid)
    with logger.step(agent="A", step="s") as st:
        st.input = "in"
        st.output = "out"

    db = SessionLocal()
    ev = db.query(TrajectoryEvent).filter_by(job_id=jid).first()
    assert ev is not None
    assert ev.opik_trace_id is not None
    db.close()
    Base.metadata.drop_all(engine)
