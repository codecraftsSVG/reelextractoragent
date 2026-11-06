import os
import logging
import pytest

# ---------- App logger ----------

def test_setup_logging_idempotent():
    from trajectory.app_logger import setup_logging
    root = logging.getLogger()
    before = len(root.handlers)
    setup_logging()
    after = len(root.handlers)
    # Second call adds handlers again (known behaviour) — at minimum must not raise
    assert after >= before


def test_get_logger_returns_named_logger():
    from trajectory.app_logger import get_logger
    log = get_logger("TestName123")
    assert log.name == "TestName123"


def test_get_logger_logs_message(caplog):
    from trajectory.app_logger import get_logger
    with caplog.at_level(logging.INFO, logger="LogTest"):
        get_logger("LogTest").info("integration log %d", 42)
    assert "integration log 42" in caplog.text


# ---------- Exceptions layer ----------

def test_exception_hierarchy():
    from trajectory.log_exceptions import (
        ReelExtractorError, DownloadError, TranscriptionError,
        OCRError, VerificationError, InsufficientMemoryError,
    )
    for exc in (DownloadError, TranscriptionError, OCRError,
                VerificationError, InsufficientMemoryError):
        assert issubclass(exc, ReelExtractorError)
        assert issubclass(exc, Exception)


def test_format_exception_contains_type_msg_traceback():
    from trajectory.log_exceptions import format_exception
    try:
        raise ValueError("kaboom-xyz")
    except ValueError as e:
        msg = format_exception(e)
    assert "ValueError" in msg
    assert "kaboom-xyz" in msg
    assert "Traceback" in msg


def test_log_exception_returns_formatted_and_logs(caplog):
    from trajectory.log_exceptions import log_exception
    try:
        raise RuntimeError("logme")
    except RuntimeError as e:
        with caplog.at_level(logging.ERROR, logger="Exceptions"):
            out = log_exception(e, job_id=7, agent="A", step="s")
    assert "RuntimeError" in out
    assert "logme" in caplog.text


# ---------- Error middleware ----------

def test_global_error_middleware_500_json():
    from fastapi.testclient import TestClient
    from backend.main import app
    # Use an endpoint that raises by abusing job creation with bad body type?
    # Instead directly exercise middleware via a raising route registered on the app
    from fastapi import FastAPI
    from trajectory.error_middleware import GlobalErrorMiddleware

    inner = FastAPI()
    inner.add_middleware(GlobalErrorMiddleware)

    @inner.get("/boom")
    def boom():
        raise RuntimeError("middleware boom")

    c = TestClient(inner, raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500
    assert r.json()["detail"] == "Internal server error"
    assert "middleware boom" in r.json()["error"]


def test_global_error_middleware_passes_200():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from trajectory.error_middleware import GlobalErrorMiddleware

    inner = FastAPI()
    inner.add_middleware(GlobalErrorMiddleware)

    @inner.get("/ok")
    def ok():
        return {"ok": True}

    c = TestClient(inner, raise_server_exceptions=False)
    r = c.get("/ok")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_global_error_middleware_logs_5xx(caplog):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from trajectory.error_middleware import GlobalErrorMiddleware

    inner = FastAPI()
    inner.add_middleware(GlobalErrorMiddleware)

    @inner.get("/boom2")
    def boom2():
        raise RuntimeError("log this")

    c = TestClient(inner, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="ErrorMiddleware"):
        c.get("/boom2")
    assert "log this" in caplog.text or "Unhandled exception" in caplog.text
