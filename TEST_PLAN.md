# Reel Extractor — Test Plan (TDD)

## Goals
- Verify **all features locally** without hitting Instagram/Neon/Whisper/Tesseract for unit tests
- Cover happy path + edge cases + failure modes + logging/Opik layers
- TDD: write failing test → minimal fix → green → refactor

## Test layers
| Layer | Scope | Speed | External deps mocked |
|---|---|---|---|
| Unit | agents, tools, writer, verifier, evaluator, logging, opik | ms | yt-dlp, whisper, tesseract, playwright |
| API | FastAPI routes, validation, DB CRUD | ms | subprocess.Popen (runner), Neon → SQLite |
| Integration (local) | TestClient + seeded DB + fake storage | sec | same as above |
| Live smoke (opt-in, `-m live`) | `test_deploy.py`, `test_crud_live.py` | 10s+ | network, Render, Neon |
| E2E (opt-in) | `extract_reel.process_reel` with mocks | 10s+ | igexport/playwright |

## Environment for tests
- `DATABASE_URL=sqlite:///./storage/test_reel.db` (forced in `tests/conftest.py` before backend import)
- No `.env` Neon, no cookies.txt read, no real Whisper model load (monkeypatched)
- `pytest.ini` adds `unit / api / integration / live` markers

## What is verified

### Backend/API (`tests/test_api.py` + edge)
- `GET /health` → `{"status":"ok"}`
- `GET /jobs` empty/list, ordering newest first
- `POST /jobs` valid reel_url (with/without query, trailing slash, `reel`/`reels`, www optional)
- `POST /jobs` valid target_user (`@user`, `user`, whitespace)
- 422 on: `{}`, `{"target_user":""}`, `{"target_user":"   "}`, bad host, `http://`, missing shortcode, invalid shortcode chars, `/p/POST`, empty string reel_url with target_user
- `GET /jobs/{id}` 200 + 404, returns reels[]
- `GET /jobs/{id}/evaluation` empty + seeded case joins Reel
- `GET /trajectory/{id}` shape includes `error_message`, `opik_trace_id`, `output<=500`

### Database (`tests/test_database.py`)
- Job/Reel/Evaluation/TrajectoryEvent CRUD
- FK job↔reel↔event↔eval
- `ensure_job_reel_url_column` idempotent + adds `error_message`/`opik_trace_id` if missing

### Trajectory / Logging / Opik (`tests/test_trajectory.py`, `tests/test_logging.py`, `tests/test_opik.py`, `tests/test_exceptions.py`)
- `TrajectoryLogger.step` success + failure logs `status=error`, `error_message` contains traceback, latency>0, input_hash stable
- `AppLogger` / `get_logger` produce log records (caplog)
- `setup_logging()` idempotent (does not duplicate handlers on second call guard via `if not handlers`)
- `format_exception` includes type + message + traceback
- Custom exception hierarchy: all subclass `ReelExtractorError`
- `OpikClient`: disabled when no `OPIK_API_KEY`; disabled when `opik` missing; doesn't crash when enabled client raises; `track_step`/`end_span` no-op safely when disabled; `get_opik_client` singleton
- `GlobalErrorMiddleware`: 500 path returns JSON `{"detail":"Internal server error"}` and logs; 200 passes through

### Agents (`tests/test_agents.py`, `tests/test_verifier.py`, `tests/test_writer.py`, `tests/test_evaluator.py`, `tests/test_tools.py`)
- `dedupe_lines`: empty, single frame, all duplicates, non-consecutive dup kept, blank lines stripped
- `video_duration`: parses `Duration:` from ffmpeg stderr, `0.0` on no match / bad values
- `verify_reel` V1-V7 each:
  - V1 missing/small video fails
  - V2 frame coverage `<0.4*duration` fails, 0 duration passes
  - V3 caption mismatch (whitespace tolerant) fails
  - V4 low confidence fails
  - V5 triple consecutive dup fails
  - V6 missing md / missing section fails
  - V7 count mismatch fails, `None` → passes
- `write_md`: template match, hashtags extracted, fallbacks `[no speech detected]`/`[no on-screen text detected]`/`[none]`, creates dirs, `score=None` → blank
- `evaluator.score`: caption empty→0, transcript empty→0, low conf→low score, caption mismatch caps `no_hallucination=0`, `verify!=pass` caps `formatting=5`, verdict thresholds publish/retry/fail at 85/60, rubric load
- `ocr.extract_text` with mocked `video_duration`/`extract_frames`/`ocr_frames`
- `transcript.transcribe` mocked `transcribe_audio`
- `fetch.fetch_reel` mocked `ytdlp_json`/`download_video` mapping description→caption

### Runner / Extract (`tests/test_runner.py`, `tests/test_extract_reel.py`)
- `runner.run_job` reel_url path: mocks `download_via_igexport`, `transcribe`, `ocr`, `writer`, `verifier`, `evaluator` → job `done`, reel `pass`, evaluations written, trajectory events in order
- `runner.run_job` reel_url error path → `job.status=error`, trajectory error event, raises
- `runner.run_job` profile path: mocks `scout.discover_reels` + fetch/transcribe/ocr → `done`, consecutive failures >3 → error + `RuntimeError("cookie/session dead")`
- `extract_reel.process_reel` shortcode parsing with query/trailing slash, mocked pipeline returns dict with score/verdict
- `extract_reel.download_via_igexport` returns cached file if exists (no network)

### CLAUDE.md rules
- Never log cookies.txt (test `scout._load_cookies` only parses sessionid line)
- yt-dlp commands must contain cookies/sleep/retries flags (assert via mock subprocess)
- No hallucination: `[unreadable]` path in `ocr_frames` on exception
- MD template invariant

## Edge cases checklist
- [ ] Empty/whitespace user and url
- [ ] URL variants: `reels/` vs `reel/`, `www.` vs bare, uppercase host, `?igsh=`, `#frag`→rejected or stripped? (currently `?` allowed, `#` not — test documents)
- [ ] Duplicate job submission creates 2 rows (no dedup — documented)
- [ ] Job with 0 reels, job 404, negative id → 422
- [ ] Trajectory for unknown job → `[]` (not 404 — documented)
- [ ] Very long output truncated to 4000 DB / 500 API
- [ ] Video exactly 50KB boundary (fails `<=`? uses `>` → 50KB exactly fails)
- [ ] OCR lines with only spaces
- [ ] Whisper empty segments → avg_confidence 0.5 fallback
- [ ] Evaluator with missing rubric file → FileNotFoundError (tested via tmp cwd)
- [ ] Opik API key set but import fails → disabled, no crash
- [ ] Storage markdown served via `/storage` (TestClient)

## How to run
```bash
.venv\Scripts\python -m pytest tests/ -v
.venv\Scripts\python -m pytest tests/ -m "not live" -v   # default
.venv\Scripts\python test_deploy.py                        # live Render smoke
.venv\Scripts\python show_data.py                          # local DB dump (uses DATABASE_URL from .env — Neon if set)
```

## TDD loop
1. Pick a row from checklist → write test in `tests/test_*.py`
2. Run `pytest tests/test_*.py::test_x -v` → red
3. Minimal code change (or fix test if spec wrong) → green
4. Full suite → ensure no regression
5. Add new edge discovered in review → repeat
