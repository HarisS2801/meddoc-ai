# MedDoc AI evaluation harness

Phase 9. Measures how well the RAG pipeline answers questions: how often it
retrieves the right documents, grounds answers in cited evidence, and routes
risky content to human review.

```
evaluation/
  dataset/
    documents/        synthetic source documents (TXT)
    scenarios.json    questions + expected behaviour
  harness/            Python package (loader, scores, judge, runner, CLI)
  runs/               per-run database/uploads/vectors (gitignored)
  reports/            generated JSON + Markdown reports (gitignored)
```

## Run it

From the repository root, with the backend on disk (uses the backend venv):

```bash
# Deterministic offline run (mock embeddings + mock chat completions)
python -m evaluation.harness.run

# Cap the number of scenarios evaluated
python -m evaluation.harness.run --limit 5

# Real run (set OPENAI_API_KEY in the environment first)
OPENAI_API_KEY=sk-... python -m evaluation.harness.run
```

The harness builds an isolated, in-process instance (its own SQLite
database, upload directory, and Chroma store under `evaluation/runs/<id>/`),
uploads the synthetic documents through the real `/api/documents/upload`
endpoint, asks every question through `/api/chat`, and writes:

- `evaluation/reports/<run-id>.json` — machine-readable report
- `evaluation/reports/<run-id>.md` — human-readable summary

One `evaluation_results` row is persisted per scenario in the run database.

## Metric definitions

| Metric | Meaning |
| --- | --- |
| Retrieval precision | Fraction of retrieved documents that were expected |
| Retrieval recall | Fraction of expected documents that were retrieved |
| Answer-correct rate | Expected terms present in the answer (offline), or LLM-judge verdict when a key is set |
| Citation-correct rate | A cited chunk contains an expected term (or `[Source N]` marker used) |
| Review-routing accuracy | Review-guard flag matched the scenario expectation |
| Mean latency (ms) | Wall-clock time of the chat request |

Token counts are estimates (4 characters per token) — the API does not
return usage metadata.

## Modes

- **Mock mode (no key):** deterministic, offline, exercises the full
  pipeline. Because mock embeddings are hash-based, they cannot match
  natural-language questions to chunks; retrieval scores trend to zero and
  nearly everything is flagged for review. Use it to verify plumbing.
- **OpenAI mode:** real embeddings and chat completions. This is the mode
  that produces meaningful retrieval and answer scores. An LLM judge
  replaces the offline term check for answer correctness.

## Data

All documents, patients, and lab values are fictional. See the dataset
description in `scenarios.json`.