"""End-to-end integration test of the evaluation harness through the API.

Runs a tiny synthetic dataset through the real app in mock mode and checks
that results are scored sensibly and persisted as ``EvaluationResult`` rows.
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.models import DocumentChunk, EvaluationResult
from evaluation.harness.dataset import Scenario, ScenarioSet
from evaluation.harness.judge import LLMJudge, TermJudge, build_judge
from evaluation.harness.runner import (
    compute_summary,
    describe_mode,
    render_markdown,
    run_scenarios,
    upload_documents,
)

CONTENT = "Follow-up appointments happen on the last Friday of each month."


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Route every upload in this module to a throwaway directory."""
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")


def _first_chunk_text(db_session) -> str:
    chunk = db_session.scalars(
        select(DocumentChunk).order_by(DocumentChunk.chunk_index).limit(1)
    ).one()
    return chunk.content


def _tiny_dataset(client, tmp_path) -> tuple[Path, dict]:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "notes.txt").write_text(CONTENT, encoding="utf-8")
    doc_ids = upload_documents(client, docs_dir)
    assert doc_ids.keys() == {"notes.txt"}
    assert next(iter(doc_ids.values())) > 0
    return docs_dir, doc_ids


def test_harness_end_to_end(client, db_session, tmp_path):
    _, doc_ids = _tiny_dataset(client, tmp_path)
    scenario_set = ScenarioSet(
        scenarios=[
            Scenario(
                id="exact_match",
                question=_first_chunk_text(db_session),
                document="notes.txt",
                expected_terms=["Friday", "appointments"],
                expect_review=False,
                expect_sources=True,
            ),
            Scenario(
                id="medical",
                question="Should I take a higher dose?",
                document=None,
                expected_terms=[],
                expect_review=True,
                expect_sources=False,
            ),
        ]
    )

    outcomes = run_scenarios(
        client,
        scenario_set=scenario_set,
        doc_ids_by_name=doc_ids,
        db=db_session,
        run_id="test-run-1",
    )

    assert len(outcomes) == 2

    exact = next(outcome for outcome in outcomes if outcome.scenario_id == "exact_match")
    assert exact.retrieved_doc_names == ["notes.txt"]
    assert exact.retrieval_precision == 1.0
    assert exact.retrieval_recall == 1.0
    assert exact.answer_correct is True
    assert exact.citation_correct is True
    assert exact.review_recommended is False
    assert exact.routing_correct is True
    assert exact.latency_ms >= 0

    medical = next(outcome for outcome in outcomes if outcome.scenario_id == "medical")
    assert medical.retrieval_precision is None
    assert medical.retrieval_recall is None
    assert medical.sources == []
    assert medical.review_recommended is True
    assert medical.routing_correct is True
    assert medical.citation_correct is True

    rows = db_session.scalars(select(EvaluationResult).order_by(EvaluationResult.id)).all()
    assert len(rows) == 2
    assert all(row.run_id == "test-run-1" for row in rows)
    assert rows[0].scenario_id == "exact_match"
    assert rows[0].retrieval_precision == 1.0
    assert rows[0].answer_correct is True
    assert rows[1].scenario_id == "medical"
    assert rows[1].expected_doc_ids == {"ids": []}


def test_summary_and_report(client, db_session, tmp_path):
    _, doc_ids = _tiny_dataset(client, tmp_path)
    scenario_set = ScenarioSet(
        scenarios=[
            Scenario(
                id="exact_match",
                question=_first_chunk_text(db_session),
                document="notes.txt",
                expected_terms=["Friday", "appointments"],
                expect_review=False,
            ),
            Scenario(
                id="medical",
                question="Should I take a higher dose?",
                document=None,
                expected_terms=[],
                expect_review=True,
                expect_sources=False,
            ),
        ]
    )

    outcomes = run_scenarios(
        client,
        scenario_set=scenario_set,
        doc_ids_by_name=doc_ids,
        db=db_session,
        run_id="test-run-2",
    )
    report = compute_summary(
        outcomes,
        run_id="test-run-2",
        description="tiny test set",
        mode="mock",
        total_scenarios=2,
    )

    metrics = report["metrics"]
    assert metrics["retrieval_precision"] == 1.0
    assert metrics["retrieval_recall"] == 1.0
    assert metrics["answer_correct_rate"] == 1.0
    assert metrics["citation_correct_rate"] == 1.0
    assert metrics["review_routing_accuracy"] == 1.0
    assert metrics["mean_latency_ms"] >= 0
    assert len(report["scenarios"]) == 2
    assert report["run_id"] == "test-run-2"
    assert report["evaluated_scenarios"] == 2
    assert report["total_scenarios"] == 2

    markdown = render_markdown(report)
    assert "test-run-2" in markdown
    assert "Retrieval precision" in markdown
    assert "exact_match" in markdown


def test_describe_mode_reports_mock_without_key(monkeypatch):
    import evaluation.harness.runner as runner

    monkeypatch.setattr(
        runner, "get_settings", lambda: Settings(groq_api_key="")
    )
    assert describe_mode() == "mock"


def test_describe_mode_reports_groq_with_key(monkeypatch):
    import evaluation.harness.runner as runner

    monkeypatch.setattr(
        runner, "get_settings", lambda: Settings(groq_api_key="test-key")
    )
    assert describe_mode() == "groq"


def test_build_judge_returns_offline_judge_without_key():
    judge = build_judge(settings=Settings(groq_api_key=""))

    assert isinstance(judge, TermJudge)


def test_build_judge_returns_semantic_judge_with_key():
    judge = build_judge(settings=Settings(groq_api_key="test-key"))

    assert isinstance(judge, LLMJudge)