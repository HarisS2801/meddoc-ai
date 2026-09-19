# MedDoc AI – AI Healthcare Document Assistant

> **Educational prototype — NOT medical software.** Do not use with real
> patient data. All demo content is synthetic. Always verify AI output with a
> qualified professional and the original documents.

Upload healthcare-related documents (PDF/TXT) and ask questions answered
**only from those documents**, with source citations and page references.
Uncertain or medically-sensitive results are routed to a human review queue.

**Status:** Phase 9 complete (synthetic QA dataset + evaluation harness).
More phases planned — see Section 9 of the plan and the roadmap below.

## Current state

- [x] Phase 1 — Project setup: backend skeleton with `/api/health`, frontend scaffold, tests
- [x] Phase 2 — Database and Pydantic schemas
- [x] Phase 3 — Document upload & processing
- [x] Phase 4 — Embeddings & vector store
- [x] Phase 5 — RAG chat
- [x] Phase 6 — Summarization & extraction
- [x] Phase 7 — Human review workflow
- [x] Phase 8 — Frontend development
- [x] Phase 9 — AI evaluation
- [ ] Phase 10 — Docs & deployment

## Tech stack

FastAPI · Pydantic · SQLite/SQLAlchemy · ChromaDB · PyMuPDF · OpenAI ·
React · TypeScript · Vite · Tailwind CSS · Pytest

## Quickstart

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env          # then edit backend/.env if needed
uvicorn app.main:app --reload --host 0.0.0.0   # http://localhost:8000/docs
```

`--host 0.0.0.0` makes the backend reachable from other devices on the same
LAN (for local-only use, plain `uvicorn app.main:app --reload` is fine).

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

The Vite dev server binds `0.0.0.0` (LAN) and proxies `/api` to the backend,
so a phone on the same Wi-Fi can open `http://<your-laptop-ip>:5173` — find the
IP with `ipconfig`. If you build/run the frontend without the proxy instead,
point it at the backend with `VITE_API_URL=http://<your-laptop-ip>:8000` and
add that origin to the backend's `CORS_ORIGINS`.

### Tests

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ../frontend
npm run build                    # type-checks + bundles
```

### Evaluation (Phase 9)

```bash
cd backend  # use the backend venv
cd ..\evaluation
..\backend\.venv\Scripts\python.exe -m evaluation.harness.run
```

Runs a synthetic QA dataset against an isolated instance of the app and
writes aggregate + per-scenario reports. Set `OPENAI_API_KEY` for a real
(mock-free) run. See `evaluation/README.md`.

## Environment variables

Copy `.env.example` to `backend/.env`. See the template for every available
variable. `OPENAI_API_KEY` is optional; without it the app runs in a mock
mode for tests and offline development.

Frontend config lives in `frontend/.env.local` (optional):
`VITE_API_URL` overrides the API base URL (defaults to `/api`, served via the
Vite proxy). Backend `CORS_ORIGINS` is a comma-separated list of browser
origins allowed to call the API (dev default: `http://localhost:5173,http://127.0.0.1:5173`).

## Repository layout

```
backend/    FastAPI service (app, tests)
frontend/   React + Vite + Tailwind SPA
docs/       architecture, API, evaluation reports (coming)
evaluation/ synthetic QA dataset + evaluation harness (Phase 9)
```

## Disclaimer

MedDoc AI is a portfolio/educational prototype built with synthetic data. It
does not provide clinical advice, is not validated for medical use, and must
never be used with real patient information.