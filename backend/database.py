import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://reel:reel@localhost:5432/reel")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def ensure_job_reel_url_column():
    """Add reel_url to databases created before reel-link job support."""
    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    if "reel_url" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN reel_url VARCHAR"))
