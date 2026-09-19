"""MedDoc AI evaluation harness.

Run scenarios against the RAG API, score retrieval / answer / citation /
routing behaviour, persist results, and produce reports.

    python -m evaluation.harness.run --help

Importing this package does not import the MedDoc AI app, so it is safe to
import without the backend directory on ``sys.path``.
"""