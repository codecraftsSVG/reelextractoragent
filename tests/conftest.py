import os
import sys

# Force local SQLite for tests BEFORE any backend import.
# Must be set before backend.database is imported by any test module.
os.environ["DATABASE_URL"] = "sqlite:///./storage/test_reel.db"
os.environ.pop("OPIK_API_KEY", None)
os.environ.pop("OPIK_URL_OVERRIDE", None)
os.environ["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.pathsep + os.environ.get("PYTHONPATH", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.makedirs("storage/logs", exist_ok=True)
os.makedirs("storage/downloads", exist_ok=True)
os.makedirs("storage/tmp", exist_ok=True)
os.makedirs("storage/output", exist_ok=True)
