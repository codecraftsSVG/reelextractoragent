# Reel Extractor — Instagram Reels → Markdown Platform

Extract ALL reels of a specific Instagram user into per-reel `.md` files,
with verification (VerifierAgent), rubric scoring (EvaluatorAgent) and
full trajectory tracking.

## Quick start

```bash
# 1. Infra
docker compose up -d

# 2. Python deps (or use venv)
pip install -r requirements.txt

# 3. Instagram credentials (REQUIRED)
#    Export cookies from your browser (Get cookies.txt LOCALLY extension)
#    and save as credentials/cookies.txt

# 4. Backend
uvicorn backend.main:app --reload --port 8000

# 5. Worker (agent runtime)
python workers/runner.py

# 6. Frontend
cd frontend && npm i && npm run dev    # http://localhost:5173
```

Then open http://localhost:5173, submit a target username, watch progress live.

## Architecture

Frontend (React) ──REST/WS──► Backend (FastAPI) ──enqueue──► Agent Runner (ADK)

ADK pipeline per reel:
ProfileScout → [Fetch ∥ Transcript ∥ OCR] → MDWriter → Verifier → Evaluator
Every step is logged to the trajectory store (Postgres).

See CLAUDE.md for the agent operating instructions.
