"""Evaluation harness command-line runner.

Usage (from the repository root):

    python -m evaluation.harness.run [--limit 5] [--dataset-dir evaluation/dataset]

Builds an isolated in-process MedDoc AI instance (own database, upload
directory, and vector store), uploads the synthetic documents, runs every
scenario, and writes a JSON + Markdown report under ``evaluation/reports/``.

Without a configured Groq key, the stack runs in deterministic regex/lexical
mode (answers are only produced when a context passage is retrieved); with a
key it runs on the real Groq models.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MedDoc AI evaluation harness.")
    parser.add_argument(
        "--dataset-dir",
        default=str(ROOT / "evaluation" / "dataset"),
        help="Directory containing documents/ and scenarios.json",
    )
    parser.add_argument(
        "--report-dir",
        default=str(ROOT / "evaluation" / "reports"),
        help="Where JSON/Markdown reports are written",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of scenarios evaluated",
    )
    return parser


def _link_app_paths(run_id: str, data_dir: Path) -> None:
    """Point settings at the isolated run directories before app import."""
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'eval.db').as_posix()}"
    os.environ["UPLOAD_DIR"] = str(data_dir / "uploads")
    os.environ["CHROMA_DIR"] = str(data_dir / "chroma")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    docs_dir = dataset_dir / "documents"
    scenarios_path = dataset_dir / "scenarios.json"
    if not scenarios_path.is_file():
        parser.error(f"scenarios.json not found at {scenarios_path}")

    run_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    data_dir = ROOT / "evaluation" / "runs" / run_id
    data_dir.mkdir(parents=True, exist_ok=False)

    _link_app_paths(run_id, data_dir)

    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415
    from app.db.session import SessionLocal, init_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    init_db()
    client = TestClient(create_app())

    from evaluation.harness.dataset import (  # noqa: PLC0415
        load_scenarios,
        validate_or_raise,
    )
    from evaluation.harness.judge import build_judge  # noqa: PLC0415
    from evaluation.harness.runner import (  # noqa: PLC0415
        compute_summary,
        describe_mode,
        render_markdown,
        run_scenarios,
        upload_documents,
    )

    scenario_set = load_scenarios(scenarios_path)
    validate_or_raise(docs_dir, scenario_set)

    doc_ids = upload_documents(client, docs_dir)
    outcomes = run_scenarios(
        client,
        scenario_set=scenario_set,
        doc_ids_by_name=doc_ids,
        db=SessionLocal(),
        run_id=run_id,
        judge=build_judge(),
        limit=args.limit,
    )

    report = compute_summary(
        outcomes,
        run_id=run_id,
        description=scenario_set.description,
        mode=describe_mode(),
        total_scenarios=len(scenario_set.scenarios),
    )

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{run_id}.json"
    md_path = report_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(render_markdown(report))
    print(f"Reports written to {json_path} and {md_path}")
    print(f"Run data (DB, uploads, vectors) kept in {data_dir}")
    settings = get_settings()
    print("Mode:", describe_mode(), "- key:", "set" if settings.groq_api_key else "unset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())