import os
import logging
import sys

# Configure unified logging format for the entire application
LOG_FORMAT = "%(asctime)s | %(levelname)s | [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

os.makedirs("storage/logs", exist_ok=True)
LOG_DIR = "storage/logs"

def setup_logging(level: str = "INFO"):
    """Configures root logger with both console and file output."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "reel_extractor.log"))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Suppress noisy dependencies
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return root_logger

def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    if not logging.getLogger().hasHandlers():
        setup_logging()
    return logging.getLogger(name)
