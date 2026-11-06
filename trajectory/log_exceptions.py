import sys
import traceback
import logging
from typing import Optional

logger = logging.getLogger("Exceptions")

class ReelExtractorError(Exception):
    """Base exception for reel extractor errors."""
    pass

class DownloadError(ReelExtractorError):
    """Raised when yt-dlp or Playwright download fails."""
    pass

class TranscriptionError(ReelExtractorError):
    """Raised when Whisper transcription fails."""
    pass

class OCRError(ReelExtractorError):
    """Raised when OCR frame/text extraction fails."""
    pass

class VerificationError(ReelExtractorError):
    """Raised when content verification fails critically."""
    pass

class InsufficientMemoryError(ReelExtractorError):
    """Raised when pipeline runs out of system memory."""
    pass

def format_exception(e: Exception) -> str:
    """Formats an exception with full traceback for logs."""
    tb = traceback.format_exc()
    return f"{type(e).__name__}: {str(e)}\n{tb}"

def log_exception(e: Exception, job_id: Optional[int] = None, agent: str = "System", step: str = "unknown"):
    """Logs exception with detailed traceback to standard logger."""
    msg = format_exception(e)
    logger.error(f"[{agent}.{step}] Job {job_id}: {msg}", exc_info=e)
    return msg
