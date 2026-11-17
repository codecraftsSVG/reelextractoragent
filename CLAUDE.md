# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Operating Rules (hard constraints)

These are invariants; do not weaken them while refactoring.

1. Never print, log, or copy the contents of `credentials/cookies.txt`. (`agents/tools.py:COOKIES` is the only sanctioned reader.)
2. Every `yt-dlp` invocation must pass `--cookies credentials/cookies.txt --sleep-requests 5 --sleep-interval 10 --retries 3`.
3. Max 3 concurrent reel fetches, 8–15s jittered sleep between fetches (`agents/tools.py:_jitter`).
4. Never invent reel URLs, captions, or transcript text. If a source is unreadable, record `[unreadable]` — never hallucinate.
5. Every agent/tool step must be wrapped in `trajectory.logger.TrajectoryLogger.step()` so it lands in the DB and Opik.
6. Output markdown must match `agents/writer.py:MD_TEMPLATE` exactly (frontmatter keys + the four `## Caption / ## Transcript / ## On-screen text / ## Hashtags` sections).
7. If the Verifier reports >3 consecutive failures on check **V1** (video integrity), stop the job and surface a "re-upload cookies" error — do not keep retrying.
   - Implementation: `workers/runner.py:122-125` counts consecutive fetch failures and raises
     `RuntimeError("cookie/session dead - re-upload credentials")` at >3. The Verifier only
     returns `pass` or `retry`; the retry logic lives in the runner.

## Commands

```bash
# Use the repo venv (.venv) — the GLOBAL Python has a broken arize-phoenix
# pytest plugin that crashes pytest at plugin load (pytest.ini blocks it too).
.venv\Scripts\activate        # Windows; on Linux/Mac: source .venv/bin/activate

# Backend (port 8000) — SQLite by default, DATABASE_URL switches to Postgres/Neon
uvicorn backend.main:app --reload --port 8000

# Worker: runs the pipeline for ONE job, synchronously. Also what POST /jobs spawns.
python workers/runner.py <job_id>

# Single-reel CLI (bypasses the DB; Playwright/igexport download path)
python extract_reel.py <reel_url>

# Tests (133 cases). conftest.py forces SQLite + strips Opik env before any backend import.
pytest                              # all
pytest -m unit                      # by marker: unit | api | integration | live
pytest tests/test_agents.py::test_dedupe_lines   # single test

# Frontend (5173, proxies /jobs /trajectory /health /storage -> 8000)
cd frontend && npm install && npm run dev     # or: npm run build (backend serves dist/)

# Windows one-shot launcher (kills stale 8000/5173, waits for health, prints proxy check)
pwsh -File start_local.ps1

# Docker
docker compose up -d
```

`tests/conftest.py` must stay importable before `backend.database` — it sets `DATABASE_URL=sqlite:///./storage/test_reel.db` at module import. Do not import backend modules above it.

## Architecture

Two execution paths share the same agent modules — this is the main thing to understand:

- **Deterministic runner** (`workers/runner.py`) — what production uses. `POST /jobs` (in [backend/routers/jobs.py](backend/routers/jobs.py)) spawns `subprocess.Popen([python, "workers/runner.py", job.id])` fire-and-forget (no queue yet). The runner walks scout → fetch → transcript → OCR → write → verify → evaluate per reel, updating `Job.status/done_reels` as it goes.
- **ADK orchestrator** (`agents/orchestrator.py`) — a `google.adk` `SequentialAgent` graph (scout, then `ParallelAgent` of fetch/transcript/OCR, then writer/verifier/evaluator) whose tools are the same plain functions. It is the "LLM judgment" layer, not the executor.

Both call the same modules under [agents/](agents/); keep those functions deterministic and importable without a DB or API key.

Pipeline per reel:

1. `scout.discover_reels(user)` — yt-dlp `--flat-playlist` over the profile reels tab; returns `{reels:[{url,shortcode,taken_at}], count}`.
2. `fetch.fetch_reel(url, shortcode)` — yt-dlp metadata + video into `storage/tmp/`.
3. `transcript.transcribe(video, shortcode)` — Whisper `tiny`; `avg_confidence` is a *no_speech_prob* mean, so **lower is better**.
4. `ocr.extract_text(video, shortcode, fps=0.5)` — ffmpeg frame sampling + Tesseract, deduped line-by-line.
5. `writer.write_md(out_dir, fetch, transcript, ocr)` — renders `storage/output/@<user>/<shortcode>.md`.
6. `verifier.verify_reel(...)` — checks V1–V7 (video ≥50KB, frame coverage ≥0.4×duration, exact caption match, transcript confidence, no 3× repeated line, MD sections present, reel count). Any failure → `status="retry"`.
7. `evaluator.score(...)` — weighted rubric from [rubric/rubric.yaml](rubric/rubric.yaml); `total >= 85` → publish, `>= 60` → retry, else fail.

**Retry semantics:** a verifier `retry` re-runs OCR once at `fps=1.0`, rewrites the markdown, and re-verifies. That is the only retry loop; there is no retry of the download.

**Runner hardening (deployed services).** `workers/runner.py` sets a per-job
deadline (`JOB_TIMEOUT_S`, default 3600s) — past it the job is marked `error`
instead of hanging forever. On boot it runs `recover_stale_jobs()`: any *other*
job left `running` older than 10 min (killed by a Render deploy/spin-down) is
flipped to `error`. `writer.write_md` collapses caption newlines so V3's exact
match can't loop forever on multi-line Instagram captions.

**Two download backends.** `fetch.fetch_reel` (yt-dlp, authenticated) is the runner path. `extract_reel.py:download_via_igexport` is a separate Playwright-based downloader that scrapes igexport.com and is the only caller in the single-reel job branch — that branch tries yt-dlp first (sanctioned cookie path + sleep flags, rule 2) and falls back to igexport; metadata comes from a real `yt-dlp --dump-json` call, degrading to `[unreadable]` placeholders (rule 4). Treat it as a dev/CLI tool, not the production path.

**Persistence.** `backend/database.py` picks the engine from `DATABASE_URL` (defaults `sqlite:///./storage/reel.db`; `postgresql://` is rewritten to `+psycopg2`). There are no Alembic migrations — `Base.metadata.create_all` plus `ensure_job_reel_url_column()` do ad-hoc `ALTER TABLE` for `jobs.reel_url`, `trajectory_events.error_message`, `trajectory_events.opik_trace_id`. Adding a column means extending that function, not adding a migration.

**Trajectory logging.** `TrajectoryLogger.step(agent, step)` is a context manager: you set `.input`/`.output`, and on exit it hashes the input (sha256, 16 chars), records latency/status/error, writes a `TrajectoryEvent`, mirrors to `AppLogger`, and closes an Opik span. `trajectory/error_middleware.py` catches unhandled exceptions at the FastAPI boundary. Opik degrades to a no-op when `OPIK_API_KEY` is unset or the package is missing — never make it a hard dependency.

**Frontend.** Plain React + Vite, two files in `frontend/src/`, no router or state library. In dev it relies on the Vite proxy; in prod the backend serves `frontend/dist/` and has a catch-all route that excludes the `/jobs`, `/trajectory`, `/health`, `/storage` prefixes.

## Gotchas

- `agents/tools.py` copies `imageio_ffmpeg`'s binary into `storage/downloads/ffmpeg(.exe)` at import and prepends it to `PATH` — ffmpeg is not assumed to be installed.
- `agents/scout.py` and `agents/fetch.py` shell out to the `yt-dlp` binary; it must be on `PATH` (Docker installs it via pip).
- Test files at repo root (`test_deploy.py`, `test_crud_live.py`, `check_postgres.py`, `seed_data.py`, `show_data.py`) are untracked scratch scripts for live Render/Neon probing, not part of the pytest suite (`testpaths = tests`).
- Deployment: `render.yaml` + root `Dockerfile` (Python 3.11, node 18, chromium, tesseract), managed Postgres `reeldb`, `GEMINI_API_KEY` required for ADK. See [DEPLOY_RENDER.md](DEPLOY_RENDER.md).
- CI: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs `pytest -m "unit or api or integration"` on push/PR to `master`, builds the frontend, and has a manual `deploy-check` job that probes the live service. `live` tests are gated behind the `LIVE_TESTS` repo variable.
- Cookies in deployed environments come from the `COOKIES_TXT` env var, materialized by `agents/tools.ensure_cookies()`. Never commit `credentials/`.

## Known bugs (unfixed)

- **No concurrency cap.** Rule 3 (≤3 concurrent fetches) is aspirational — `POST /jobs` spawns unbounded `subprocess.Popen` children and each runner is strictly sequential.