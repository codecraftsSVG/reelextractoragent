from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import traceback

logger = logging.getLogger("ErrorMiddleware")

class GlobalErrorMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and logs them with full tracebacks."""
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            response = await call_next(request)
            if response.status_code >= 500:
                logger.error(f"HTTP {response.status_code} on {request.url} from {request.client.host}")
            return response
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Unhandled exception on {request.method} {request.url}: {e}\n{tb}", exc_info=e)
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "error": str(e)}
            )
