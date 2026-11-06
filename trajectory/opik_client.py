import os
import logging
from typing import Optional

try:
    from opik import Opik
    OPIK_AVAILABLE = True
except ImportError:
    Opik = None  # placeholder so tests can monkeypatch oc.Opik
    OPIK_AVAILABLE = False

logger = logging.getLogger("OpikClient")

class OpikClient:
    """Optional Opik LLM/Tool tracing client."""
    def __init__(self, project_name: str = "reel-extractor"):
        self.enabled = False
        self.client = None
        self.project_name = project_name
        
        api_key = os.getenv("OPIK_API_KEY")
        url_override = os.getenv("OPIK_URL_OVERRIDE", "https://www.cometapi.com/opik")
        
        if not OPIK_AVAILABLE:
            if api_key:
                logger.warning("Opik is configured but 'opik' package is not installed.")
            return
            
        if not api_key:
            logger.info("Opik tracing disabled: OPIK_API_KEY not set.")
            return
            
        try:
            self.client = Opik(project_name=project_name, url_override=url_override)
            self.enabled = True
            logger.info(f"Opik tracing enabled on project '{project_name}'")
        except Exception as e:
            logger.error(f"Failed to initialize Opik client: {e}", exc_info=True)

    def track_step(self, name: str, job_id: int, agent: str, step: str):
        """Initialize a span for a pipeline step, returns span or None."""
        if not self.enabled or not self.client:
            return None
        try:
            # Create a new span or use tracker context
            span = self.client.span(
                name=f"{agent}.{step}",
                metadata={"job_id": job_id, "agent": agent, "step": step}
            )
            logger.debug(f"Opik span created: {span.id} for {name}")
            return span
        except Exception as e:
            logger.warning(f"Opik span error: {e}")
            return None
            
    def log_trace(self, trace_id: str, name: str, output: str, latency_ms: int, status: str, error: Optional[str] = None):
        if not self.enabled or not self.client:
            return
        try:
            # End span with result
            self.client.flush()
        except Exception as e:
            logger.debug(f"Opik flush skipped: {e}")

    def end_span(self, span, output: str, latency_ms: int, status: str, error_msg: Optional[str] = None):
        if not span:
            return
        try:
            metadata = {"output": str(output)[:1000], "latency_ms": latency_ms, "status": status}
            if error_msg:
                metadata["error"] = error_msg[:1000]
            span.update(metadata=metadata)
            if status == "error":
                span.update(error_info={"exception_type": "StepFailed", "exception_message": error_msg or "Step error"})
            span.end()
            self.client.flush()
        except Exception as e:
            logger.debug(f"Opik end_span error: {e}")

_opik_client = None

def get_opik_client() -> OpikClient:
    global _opik_client
    if _opik_client is None:
        _opik_client = OpikClient()
    return _opik_client
