# Deploying Reel Extractor on Render

This repository is fully configured for deployment on [Render](https://render.com/) as a Docker Web Service.

## Prerequisites
- A Render account (free tier is supported).
- Your repository pushed to GitHub or GitLab.

---

## Deployment Steps

### Method 1: Using `render.yaml` (Blueprint - Recommended)
1. Push your code to your GitHub or GitLab repository.
2. Go to your [Render Dashboard](https://dashboard.render.com/).
3. Click **New** -> **Blueprint**.
4. Connect your GitHub/GitLab repository.
5. Render will automatically detect `render.yaml` and configure the **reel-extractor** web service using the root `Dockerfile`.
6. Click **Apply**.

### Method 2: Manual Web Service Setup
1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** -> **Web Service**.
3. Connect your repository.
4. Configure the service settings:
   - **Name:** `reel-extractor`
   - **Environment:** `Docker`
   - **Region:** Choose your preferred region
   - **Branch:** `master` (the repo's default branch)
   - **Docker Command:** Leave blank (it defaults to the `CMD` specified in `Dockerfile`)
   - **Plan:** Free (or higher as needed)
5. Click **Create Web Service**.

---

## Environment Variables
The `.env.render` file in the repo root is the paste-ready reference (it is
gitignored — keep it that way). Set these in Render Dashboard → Service →
Environment:

- `PYTHONUNBUFFERED=1` — streams uvicorn logs to Render in real-time.
- `GEMINI_API_KEY` — the value of the `geminikey=` line in your local `.env`.
  Required for the Google ADK agents. (The deterministic runner path —
  `workers/runner.py` — does not call Gemini; the ADK orchestrator layer does.)
- `COOKIES_TXT` — **Required.** `credentials/` is gitignored, so the file is
  never in the image. `agents/tools.ensure_cookies()` writes this value to
  `credentials/cookies.txt` on first yt-dlp call. Paste the **full contents** of
  your exported `cookies.txt` (Netscape format, including the leading
  `# Netscape HTTP Cookie File` comment lines). Render's env-var box accepts a
  multi-line paste. Without it every fetch fails; rotating this value is how you
  recover from expired Instagram sessions.
- `DATABASE_URL=sqlite:///./storage/reel.db` — SQLite on the mounted disk
  (survives restarts). To use the Render managed Postgres instead, set its
  `postgresql://...` connection string; `backend/database.py` rewrites it to
  `postgresql+psycopg2://` automatically.
- `JOB_TIMEOUT_S` (optional, default `3600`) — hard ceiling per job. A runner
  that passes the deadline marks its job `error` instead of hanging forever.

## Operational notes (free tier)
- **Spin-down / restarts.** Free web services sleep after inactivity and are
  recycled on deploy; the log line `INFO: Shutting down` with no traceback
  means Render stopped the process, not that the app crashed. A request wakes
  the service again (first hit after idle pays the cold start).
- **Jobs die with the process.** `POST /jobs` spawns `workers/runner.py` as a
  fire-and-forget `subprocess.Popen`. If Render restarts the service while a
  job is mid-pipeline, the child is killed and the job row stays `running`.
  On the **next** job start, `workers/runner.py:recover_stale_jobs()` flips any
  such stale `running` job (older than 10 min, not the current job) to `error`.
  For reliable processing, run the runner as a separate Render **Background
  Worker** (same image, queue-driven) or move to a real broker
  (Celery/RQ/Arq). Until then, treat long jobs as best-effort.
- **Reading the logs.** `[DfBMxNAp-wv] Attempting download via yt-dlp...`
  followed by `yt-dlp download successful!` = the authenticated download path
  works. A `0%|... | x/72.1M` progress bar with no completion line = the
  process was recycled mid-download (see above), not an Instagram error.
- **Cookies dead?** If consecutive fetch failures exceed 3 the runner stops the
  job with `cookie/session dead - re-upload credentials` (CLAUDE.md rule 7).
  Paste fresh `COOKIES_TXT` and redeploy/restart the service.

## Verifying a deploy
Use the repo's virtualenv — the global Python has a broken `phoenix`/`pydantic`
combo that crashes pytest at plugin load:
```bash
.venv\Scripts\activate          # or: .venv\Scripts\python.exe -m pytest
pytest                          # expect all green
```

Live checks (PowerShell: `$env:` prefix instead of bash `VAR=`):
```powershell
.\render_status.ps1                                  # service status, deploys, env names
curl https://<your-service>.onrender.com/health      # {"status":"ok"}
$env:LIVE_BASE_URL="https://<your-service>.onrender.com"; python test_deploy.py
$env:LIVE_BASE_URL="https://<your-service>.onrender.com"; python test_all_apis.py
```
`test_deploy.py` / `test_all_apis.py` default to the current live URL
(`https://reelextractoragent-wr3s.onrender.com`) and can be overridden with
`LIVE_BASE_URL`.


## Database (PostgreSQL)
- The codebase includes `psycopg2-binary` and dynamic database support in `backend/database.py`.
- `render.yaml` is now configured to automatically provision a **Render Managed PostgreSQL Database** (`reeldb`) and link its connection string via `DATABASE_URL` to your web service.

