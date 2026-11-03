from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

frontend_dist = os.path.join("frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/")
    def serve_root():
        return FileResponse(os.path.join(frontend_dist, "index.html"))

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        if full_path.startswith("jobs") or full_path.startswith("trajectory") or full_path.startswith("health") or full_path.startswith("storage"):
            raise HTTPException(status_code=404, detail="Not found")
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))


