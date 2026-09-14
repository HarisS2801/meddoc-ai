# MedDoc AI – AI Healthcare Document Assistant

> **Educational prototype — NOT medical software.** Do not use with real
> patient data. All demo content is synthetic. Always verify AI output with a
> qualified professional and the original documents.

Upload healthcare-related documents (PDF/TXT) and ask questions answered
**only from those documents**, with source citations and page references.
Uncertain or medically-sensitive results are routed to a human review queue.

**Status:** Phase 1 complete (project skeleton). More phases planned — see
Section 9 of the plan and the roadmap below.

## Current state

- [x] Phase 1 — Project setup: backend skeleton with `/api/health`, frontend scaffold, tests
- [ ] Phase 2 — Database and Pydantic schemas
- [ ] Phase 3 — Document upload & processing
- [ ] Phase 4 — Embeddings & vector store
- [ ] Phase 5 — RAG chat
- [ ] Phase 6 — Summarization & extraction
- [ ] Phase 7 — Human review workflow
- [ ] Phase 8 — Frontend development
- [ ] Phase 9 — AI evaluation
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
uvicorn app.main:app --reload    # http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

### Tests

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ../frontend
npm run build                    # type-checks + bundles
```

## Environment variables

Copy `.env.example` to `backend/.env`. See the template for every available
variable. `OPENAI_API_KEY` is optional until Phase 4/5 — the app runs in a
mock mode for tests without it.

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