# Reel Extractor — System Architecture & Workflow

## 1. Overview
Reel Extractor is an end-to-end automated system designed to discover, fetch, transcribe, analyze, OCR, verify, and evaluate Instagram Reels. It features a FastAPI backend, multi-agent processing pipeline, structured logging, Opik tracing, and a robust database layer.

---

## 2. High-Level Architecture

```
┌─────────────────────────┐               ┌─────────────────────────┐
│     Frontend UI         │               │     External Services   │
│   (React / Vite :5173)  │               │ (Instagram / IGExport / │
└────────────▲────────────┘               │  Whisper / Tesseract)   │
             │ HTTP / REST                └────────────▲────────────┘
             │                                         │
             ▼                                         │
┌──────────────────────────────────────────────────────┴──┐
│                     FastAPI Backend (:8000)             │
│  - REST API Routers (/jobs, /trajectory, /health)       │
│  - Global Error Middleware & Exception Handling         │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                 Extraction Pipeline & Agents            │
│  - Scout / Discover (V1-V3)                             │
│  - Fetcher (yt-dlp + igexport)                          │
│  - Transcriber (Whisper)                                │
│  - OCR Extractor (OpenCV + Tesseract)                   │
│  - Markdown Writer & Template Invariant                 │
│  - Verifier (V1-V7 rules engine)                        │
│  - Evaluator & Rubric Scoring Engine                    │
└────────────────────────────┬────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌───────────────────────┐         ┌───────────────────────┐
│     Database Layer    │         │  Trajectory & Opik    │
│  (SQLAlchemy / SQLite │         │  - Step-by-step logs  │
│   / PostgreSQL / Neon)│         │  - Trace ID tracking  │
└───────────────────────┘         └───────────────────────┘
```

---

## 3. Core Processing Pipeline & Agents

The reel processing pipeline (`trajectory/runner.py`, `workers/`) executes a sequential multi-step workflow:
1. **Scouting (`agents/scout.py`)**: Discovers reels from user profiles or direct URLs securely.
2. **Fetching (`agents/fetch.py`)**: Downloads videos using `yt-dlp` with rate-limiting, retries, and sleeps.
3. **Transcription (`agents/transcript.py`)**: Transcribes audio using OpenAI Whisper with confidence fallbacks.
4. **OCR (`agents/ocr.py`)**: Samples video frames via OpenCV and extracts on-screen text using Tesseract OCR.
5. **Writing (`agents/writer.py`)**: Synthesizes caption, transcript, and OCR text into structured Markdown adhering to template invariants.
6. **Verification (`agents/verifier.py`)**: Executes 7 rigorous verification checks (V1 to V7 covering video size, frame coverage, caption mismatch, confidence, duplicates, markdown structure, and counts).
7. **Evaluation (`agents/evaluator.py`)**: Scores content against rubrics and computes final verdicts (`publish`, `retry`, `fail`).

---

## 4. Trajectory, Logging, and Opik Layer

- **Structured Logging (`trajectory/logger.py`, `trajectory/app_logger.py`)**: Records latency, input hashes, trace IDs, error messages, and tracebacks per step.
- **Exception Hierarchy (`trajectory/log_exceptions.py`)**: Custom exceptions inheriting from `ReelExtractorError`.
- **Global Error Middleware (`trajectory/error_middleware.py`)**: Catches unhandled exceptions at the FastAPI boundary, returning JSON error payloads.
- **Opik Tracing (`trajectory/opik_client.py`)**: Integrates Opik for LLM/pipeline tracing with safe `Opik = None` fallback for CI/mockability.

---

## 5. Database & Testing

- **Models (`backend/models.py`)**: `Job`, `Reel`, `Evaluation`, `TrajectoryEvent` (with `error_message` and `opik_trace_id` tracking).
- **Database (`backend/database.py`)**: Supports SQLite (local/test) and PostgreSQL/Neon with automated schema migrations.
- **Testing (`tests/`)**: 133 pytest cases spanning unit, API, integration, and live smoke tests.
- **Local Runner (`start_local.ps1`)**: PowerShell launcher for backend (`:8000`) and frontend (`:5173`).
