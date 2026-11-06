import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

os.makedirs("storage", exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./storage/reel.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    if DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def ensure_job_reel_url_column():
    insp = inspect(engine)
    if "jobs" in insp.get_table_names():
        columns = {column["name"] for column in insp.get_columns("jobs")}
        if "reel_url" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN reel_url VARCHAR"))
    
    if "trajectory_events" in insp.get_table_names():
        columns = {column["name"] for column in insp.get_columns("trajectory_events")}
        with engine.begin() as connection:
            if "error_message" not in columns:
                connection.execute(text("ALTER TABLE trajectory_events ADD COLUMN error_message TEXT"))
            if "opik_trace_id" not in columns:
                connection.execute(text("ALTER TABLE trajectory_events ADD COLUMN opik_trace_id VARCHAR"))



