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
   - **Branch:** `main` (or your default branch)
   - **Docker Command:** Leave blank (it defaults to the `CMD` specified in `Dockerfile`)
   - **Plan:** Free (or higher as needed)
5. Click **Create Web Service**.

---

## Environment Variables
- `PYTHONUNBUFFERED`: Set to `1` (ensures logs stream to Render in real-time).
- `GEMINI_API_KEY`: Required for the Google ADK AI agents (`ProfileScoutAgent`, `FetchAgent`, `TranscriptAgent`, `OCRAgent`, `VerifierAgent`, `EvaluatorAgent`, etc.). Get your API key from Google AI Studio and add it in your Render Service -> Environment settings.


## Storage and Persistence
- The SQLite database is stored at `storage/reel.db`, and downloaded videos/reports are saved in `storage/`.
- `render.yaml` automatically provisions a **Render Persistent Disk** mounted at `/app/storage` (1 GB), ensuring that your database and extraction reports **never get wiped out** during container restarts or redeploys.

