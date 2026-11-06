import hashlib
import json
import time
import logging
import traceback
from typing import Optional

from backend.database import SessionLocal
from backend.models import TrajectoryEvent
from .opik_client import get_opik_client
from .log_exceptions import format_exception

logger = logging.getLogger("TrajectoryLogger")

class AppLogger:
    """Unified application logger with file + console output."""
    def __init__(self, name: str = "App"):
        self._logger = logging.getLogger(name)
        
    def info(self, msg: str, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)
        
    def error(self, msg: str, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)
        
    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)
        
    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

def get_logger(name: str = "App") -> AppLogger:
    return AppLogger(name)

class TrajectoryLogger:
    """Log every agent/tool step with exception & Opik tracing."""

    def __init__(self, job_id: int, reel_id: int = None):
        self.job_id = job_id
        self.reel_id = reel_id
        self.opik = get_opik_client()
        self.app_log = get_logger(f"Job{job_id}")

    def step(self, agent: str, step: str):
        return _Step(self, agent, step)

    def log(self, agent: str, step: str, input_obj, output_obj, latency_ms: int, status: str = "ok", error_message: Optional[str] = None):
        db = SessionLocal()
        opik_trace_id = None
        try:
            input_hash = hashlib.sha256(
                json.dumps(str(input_obj), sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            
            if self.opik.enabled:
                opik_trace_id = str(self.job_id)
                
            event = TrajectoryEvent(
                job_id=self.job_id, reel_id=self.reel_id,
                agent=agent, step=step,
                input_hash=input_hash,
                output=str(output_obj or "")[:4000],
                latency_ms=latency_ms, status=status,
                error_message=error_message,
                opik_trace_id=opik_trace_id
            )
            db.add(event)
            db.commit()
            
            log_msg = f"[{agent}.{step}] Status={status} Latency={latency_ms}ms"
            if error_message:
                self.app_log.error(f"{log_msg} Error: {error_message}")
            else:
                self.app_log.info(f"{log_msg} Output={str(output_obj)[:200]}")

        except Exception as e:
            db.rollback()
            self.app_log.error(f"Trajectory log DB error: {e}", exc_info=True)
        finally:
            db.close()

class _Step:
    def __init__(self, logger: TrajectoryLogger, agent, step):
        self.logger = logger
        self.agent = agent
        self.step_name = step
        self.t0 = None
        self.opik_span = None

    def __enter__(self):
        self.t0 = time.time()
        self.logger.app_log.info(f"Starting step {self.agent}.{self.step_name} for Job {self.logger.job_id}")
        self.opik_span = self.logger.opik.track_step(self.step_name, self.logger.job_id, self.agent, self.step_name)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.output = getattr(self, "output", None)
        self.input = getattr(self, "input", None)
        latency_ms = int((time.time() - self.t0) * 1000)
        status = "ok" if exc_type is None else "error"
        error_msg = format_exception(exc) if exc else None
        
        if exc:
            self.logger.app_log.error(f"Step {self.agent}.{self.step_name} failed: {error_msg}", exc_info=True)

        self.logger.log(self.agent, self.step_name, self.input, self.output, latency_ms, status, error_msg)
        self.logger.opik.end_span(self.opik_span, self.output, latency_ms, status, error_msg)
        return False
