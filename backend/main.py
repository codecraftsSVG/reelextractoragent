from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from .database import Base, engine, ensure_job_reel_url_column
from .routers import jobs, trajectory

Base.metadata.create_all(engine)
ensure_job_reel_url_column()
os.makedirs("storage", exist_ok=True)

app = FastAPI(title="Reel Extractor API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(trajectory.router, prefix="/trajectory", tags=["trajectory"])

@app.get("/health")
def health():
    return {"status": "ok"}
