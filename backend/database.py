import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./reel.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
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
