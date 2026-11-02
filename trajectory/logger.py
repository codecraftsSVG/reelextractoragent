import hashlib, json, time
from backend.database import SessionLocal
from backend.models import TrajectoryEvent

class TrajectoryLogger:
    """Log every agent/tool step. Usage:
        log = TrajectoryLogger(job_id=1, reel_id=5)
        with log.step(agent="FetchAgent", step="fetch"):
            result = fetch_reel(url)
    """

    def __init__(self, job_id: int, reel_id: int = None):
        self.job_id = job_id
        self.reel_id = reel_id

    def step(self, agent: str, step: str):
        return _Step(self, agent, step)

    def log(self, agent: str, step: str, input_obj, output_obj, latency_ms: int, status: str = "ok"):
        db = SessionLocal()
        try:
            db.add(TrajectoryEvent(
                job_id=self.job_id, reel_id=self.reel_id,
                agent=agent, step=step,
                input_hash=hashlib.sha256(
                    json.dumps(str(input_obj), sort_keys=True, default=str).encode()).hexdigest()[:16],
                output=str(output_obj)[:4000],
                latency_ms=latency_ms, status=status,
            ))
            db.commit()
        finally:
            db.close()

class _Step:
    def __init__(self, logger, agent, step):
        self.logger, self.agent, self.step_name = logger, agent, step
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.output = getattr(self, "output", None)
        self.input = getattr(self, "input", None)
        self.logger.log(self.agent, self.step_name, self.input, self.output,
                        int((time.time() - self.t0) * 1000),
                        "ok" if exc_type is None else "error")
        return False
