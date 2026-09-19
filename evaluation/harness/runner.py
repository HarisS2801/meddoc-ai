"""Scenario execution, scoring, persistence, and report building.

The runner drives a real MedDoc AI API client (``fastapi.testclient``
in-process, or any object exposing the same endpoints) through a full
harness run: upload the synthetic documents, ask every question, score
retrieval / answer / citation / routing, and persist one
``EvaluationResult`` row per scenario.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EvaluationResult

from evaluation.harness.dataset import Scenario, ScenarioSet
from evaluation.harness.judge import AnswerJudge, TermJudge
from evaluation.harness import scores


@dataclass
class ScenarioOutcome:
    """Per-scenario metrics and metadata for reporting."""

    scenario_id: str
    question: str
    expected_document: str | None
    expected_doc_ids: list[int]
    retrieved_doc_ids: list[int]
    retrieved_doc_names: list[str]
    answer: str
    sources: list[dict]
    review_recommended: bool
    review_expected: bool
    retrieval_precision: float | None
    retrieval_recall: float | None
    answer_correct: bool
    citation_correct: bool
    routing_correct: bool
    latency_ms: int
    tokens_in: int
    tokens_out: int


def estimate_tokens(text: str) -> int:
    """Rough OpenAI-style token estimate (4 chars per token)."""
    return max(1, len(text) // 4)


def upload_documents(client, docs_dir: Path) -> dict[str, int]:
    """Upload every file in ``docs_dir`` and map filename -> document id."""
    doc_ids: dict[str, int] = {}
    for path in sorted(docs_dir.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        response = client.post(
            "/api/documents/upload",
            files={"file": (path.name, data, "text/plain")},
        )
        if response.status_code != 201:
            raise RuntimeError(
                f"Failed to upload '{path.name}': HTTP {response.status_code} "
                f"{response.text[:200]}"
            )
        body = response.json()
        if body["status"] != "processed":
            raise RuntimeError(
                f"Document '{path.name}' was not processed successfully: {body}"
            )
        doc_ids[body["filename"]] = body["id"]
    return doc_ids


def _expected_ids(
    scenario: Scenario, doc_ids_by_name: dict[str, int]
) -> list[int]:
    if scenario.document is None:
        return []
    document_id = doc_ids_by_name.get(scenario.document)
    if document_id is None:
        raise RuntimeError(
            f"Scenario '{scenario.id}' references '{scenario.document}' "
            "which was not uploaded."
        )
    return [document_id]


def _score_scenario(
    client,
    scenario: Scenario,
    expected_ids: list[int],
    judge: AnswerJudge,
    run_id: str,
    db: Session,
    fallback_ids: list[int],
) -> ScenarioOutcome:
    # Chat is strictly scoped to an active document: the question is always
    # answered against exactly one workspace, never the whole collection.
    # Scenarios without an expected document (negative controls) are still
    # evaluated against an uploaded document so the "no evidence" path is
    # tested rather than an outright "no document selected" error.
    scope_ids = expected_ids or fallback_ids
    payload = {"question": scenario.question, "document_ids": scope_ids}
    started = perf_counter()
    response = client.post("/api/chat", json=payload)
    latency_ms = int((perf_counter() - started) * 1000)
    if response.status_code != 200:
        raise RuntimeError(
            f"Scenario '{scenario.id}' failed: HTTP {response.status_code} "
            f"{response.text[:200]}"
        )

    body = response.json()
    answer = body["answer"]
    sources = body["sources"]
    review_recommended = bool(body["review_recommended"])

    retrieved_ids: list[int] = []
    retrieved_names: list[str] = []
    for source in sources:
        document_id = source["document_id"]
        if document_id not in retrieved_ids:
            retrieved_ids.append(document_id)
            retrieved_names.append(source["filename"])

    expected_set = set(expected_ids)
    has_expected = bool(expected_set)
    outcome = ScenarioOutcome(
        scenario_id=scenario.id,
        question=scenario.question,
        expected_document=scenario.document,
        expected_doc_ids=expected_ids,
        retrieved_doc_ids=retrieved_ids,
        retrieved_doc_names=retrieved_names,
        answer=answer,
        sources=sources,
        review_recommended=review_recommended,
        review_expected=scenario.expect_review,
        retrieval_precision=(
            scores.retrieval_precision(expected_set, retrieved_ids) if has_expected else None
        ),
        retrieval_recall=(
            scores.retrieval_recall(expected_set, retrieved_ids) if has_expected else None
        ),
        answer_correct=judge.verdict(scenario.question, answer, scenario.expected_terms),
        citation_correct=scores.citation_correct(
            answer, sources, scenario.expected_terms, scenario.expect_sources
        ),
        routing_correct=scores.routing_correct(
            scenario.expect_review, review_recommended
        ),
        latency_ms=latency_ms,
        tokens_in=estimate_tokens(scenario.question),
        tokens_out=estimate_tokens(answer),
    )

    _persist_result(db, run_id, scenario, outcome, expected_ids)
    return outcome


def _persist_result(
    db: Session,
    run_id: str,
    scenario: Scenario,
    outcome: ScenarioOutcome,
    expected_ids: list[int],
) -> None:
    row = EvaluationResult(
        run_id=run_id,
        scenario_id=scenario.id,
        question=scenario.question,
        retrieved_doc_ids={"ids": outcome.retrieved_doc_ids},
        expected_doc_ids={"ids": expected_ids},
        answer=outcome.answer,
        retrieval_precision=outcome.retrieval_precision or 0.0,
        retrieval_recall=outcome.retrieval_recall or 0.0,
        answer_correct=outcome.answer_correct,
        citation_correct=outcome.citation_correct,
        latency_ms=outcome.latency_ms,
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
    )
    db.add(row)
    db.commit()


def run_scenarios(
    client,
    *,
    scenario_set: ScenarioSet,
    doc_ids_by_name: dict[str, int],
    db: Session,
    run_id: str,
    judge: AnswerJudge | None = None,
    limit: int | None = None,
) -> list[ScenarioOutcome]:
    """Run a scenario set against the client and persist results."""
    judge = judge or TermJudge()
    scenarios = scenario_set.scenarios
    if limit is not None:
        scenarios = scenarios[:limit]

    outcomes: list[ScenarioOutcome] = []
    fallback_ids = list(doc_ids_by_name.values())[:1]
    for scenario in scenarios:
        expected_ids = _expected_ids(scenario, doc_ids_by_name)
        outcomes.append(
            _score_scenario(
                client,
                scenario,
                expected_ids,
                judge,
                run_id,
                db,
                fallback_ids,
            )
        )
    return outcomes


def compute_summary(
    outcomes: list[ScenarioOutcome],
    *,
    run_id: str,
    description: str,
    mode: str,
    total_scenarios: int,
) -> dict:
    """Aggregate per-scenario outcomes into a report dictionary."""
    scored = list(outcomes)

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    retrieval = [o.retrieval_precision for o in scored if o.retrieval_precision is not None]
    retrieval_recall = [o.retrieval_recall for o in scored if o.retrieval_recall is not None]

    report = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "mode": mode,
        "total_scenarios": total_scenarios,
        "evaluated_scenarios": len(scored),
        "metrics": {
            "retrieval_precision": mean(retrieval),
            "retrieval_recall": mean(retrieval_recall),
            "answer_correct_rate": round(
                sum(o.answer_correct for o in scored) / len(scored), 4
            )
            if scored
            else 0.0,
            "citation_correct_rate": round(
                sum(o.citation_correct for o in scored) / len(scored), 4
            )
            if scored
            else 0.0,
            "review_routing_accuracy": round(
                sum(o.routing_correct for o in scored) / len(scored), 4
            )
            if scored
            else 0.0,
            "mean_latency_ms": round(
                sum(o.latency_ms for o in scored) / len(scored), 1
            )
            if scored
            else 0,
            "total_estimated_tokens_in": sum(o.tokens_in for o in scored),
            "total_estimated_tokens_out": sum(o.tokens_out for o in scored),
        },
        "scenarios": [asdict(outcome) for outcome in scored],
    }
    return report


def render_markdown(report: dict) -> str:
    """Human-readable markdown from a report dictionary."""
    metrics = report["metrics"]
    lines = [
        f"# MedDoc AI evaluation report - {report['run_id']}",
        "",
        f"- **Description:** {report['description']}",
        f"- **Created:** {report['created_at']}",
        f"- **Mode:** {report['mode']}",
        f"- **Scenarios evaluated:** {report['evaluated_scenarios']} / {report['total_scenarios']}",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Retrieval precision | {metrics['retrieval_precision']} |",
        f"| Retrieval recall | {metrics['retrieval_recall']} |",
        f"| Answer-correct rate | {metrics['answer_correct_rate']} |",
        f"| Citation-correct rate | {metrics['citation_correct_rate']} |",
        f"| Review-routing accuracy | {metrics['review_routing_accuracy']} |",
        f"| Mean latency (ms) | {metrics['mean_latency_ms']} |",
        f"| Estimated tokens in | {metrics['total_estimated_tokens_in']} |",
        f"| Estimated tokens out | {metrics['total_estimated_tokens_out']} |",
        "",
        "## Per-scenario results",
        "",
        "| id | precision | recall | answer | citation | routing | ms |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scenario in report["scenarios"]:
        lines.append(
            "| {id} | {precision} | {recall} | {answer} | {citation} | {routing} | {ms} |".format(
                id=scenario["scenario_id"],
                precision=(
                    scenario["retrieval_precision"]
                    if scenario["retrieval_precision"] is not None
                    else "-"
                ),
                recall=(
                    scenario["retrieval_recall"]
                    if scenario["retrieval_recall"] is not None
                    else "-"
                ),
                answer="yes" if scenario["answer_correct"] else "no",
                citation="yes" if scenario["citation_correct"] else "no",
                routing="yes" if scenario["routing_correct"] else "no",
                ms=scenario["latency_ms"],
            )
        )
    lines.append("")
    lines.append(
        "Answer = expected terms present; citation = cited chunk carries an "
        "expected term; routing = review guard matched the expectation."
    )
    lines.append("")
    return "\n".join(lines)


def describe_mode() -> str:
    """Return the provider family selected by the configured API keys."""
    settings = get_settings()
    if settings.groq_api_key:
        return "groq"
    return "mock"