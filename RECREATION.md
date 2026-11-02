# Reel Extractor Platform — Recreation & Setup Guide

This guide details how to recreate, set up, and run the **Reel Extractor** platform from scratch.

---

## 1. Project Overview & Architecture

Reel Extractor is an end-to-end AI-powered pipeline designed to ingest Instagram reel links, download videos via automated web navigation (`igexport.com`), transcribe audio using OpenAI Whisper, extract on-screen text via OCR, render structured Markdown reports, run deterministic fidelity checks (`VerifierAgent`), and score outputs against quality rubrics (`EvaluatorAgent`).

### Core Components:
- **Downloader / Pipeline (`extract_reel.py`)**: Automates browser navigation via Playwright to fetch direct CDN video streams from `https://igexport.com/en/reels-download/`.
- **Backend API & Agents (`agents/`)**:
  - `agents/tools.py`: Wraps `yt-dlp`, Whisper (`tiny` model for CPU optimization), Tesseract OCR, and FFmpeg.
  - `agents/transcript.py`: Handles audio extraction and Whisper transcription.
  - `agents/ocr.py`: Extracts frame-by-frame text overlays.
  - `agents/writer.py`: Generates standardized Markdown reports.
  - `agents/verifier.py`: Runs deterministic fidelity checks (V1–V7).
  - `agents/evaluator.py`: Scores extractions against `rubric/rubric.yaml`.
- **Frontend (`frontend/`)**: React + Vite single-page application for interacting with the platform.
- **Storage (`storage/downloads/`)**: Single consolidated folder storing downloaded `.mp4` videos and generated `.md` markdown reports.

---

## 2. System Prerequisites

Before installation, ensure your environment has:
1. **Python 3.10+** (with `pip`)
2. **Node.js 18+ & npm** (for frontend development)
3. **FFmpeg / FFprobe** (bundled automatically via `imageio-ffmpeg` or installed globally)
4. **Tesseract OCR** (optional, for on-screen text extraction)

---

## 3. Installation & Setup

### Step 1: Clone Repository & Install Python Dependencies
```bash
git clone https://github.com/codecraftsSVG/reelextractoragent.git
cd reel-extractor
pip install -r requirements.txt
```

`requirements.txt` includes:
```text
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
pydantic
python-multipart
websockets
google-adk
yt-dlp
openai-whisper
pytesseract
pillow
pyyaml
requests
playwright
imageio-ffmpeg
```

Install Playwright browsers (required for automated igexport downloading):
```bash
playwright install
```

### Step 2: Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

---

## 4. Configuration & Credentials

1. Create a `credentials/` folder in the project root.
2. Place your Instagram Netscape-format cookies in `credentials/cookies.txt`.
3. Ensure `.env` (if used) is present locally but kept out of version control (already configured in `.gitignore`).

---

## 5. Running an End-to-End Extraction

To run an automated extraction on a specific Instagram reel link:

```bash
python extract_reel.py https://www.instagram.com/reel/<shortcode>/
```

This workflow:
1. Launches headless Playwright to download the video via `igexport.com`.
2. Stores the `.mp4` video and generated `.md` report in `storage/downloads/`.
3. Transcribes audio using Whisper (`tiny`).
4. Extracts on-screen OCR text.
5. Runs `VerifierAgent` (checks V1–V7) and `EvaluatorAgent` (rubric scoring 0–100).

---

## 6. Running the Application Stack

### Start Backend API
```bash
uvicorn app:app --reload --port 8000
```

### Start Frontend Dev Server
```bash
cd frontend
npm run dev
```

---

## 7. Evaluating Extraction Quality

Extraction quality is evaluated programmatically and inspected via:
- **VerifierAgent V1–V7 Reports:** Validates video integrity, frame coverage, caption matching, transcript confidence, and deduplication.
- **EvaluatorAgent Rubric Score (0–100):** Evaluates completeness, accuracy, and formatting, assigning a verdict (`publish`, `retry`, or `fail`).
- **Markdown Reports:** Stored in [storage/downloads/](storage/downloads/), containing structured sections for Caption, Spoken Transcript, On-Screen Text, and Hashtags.
