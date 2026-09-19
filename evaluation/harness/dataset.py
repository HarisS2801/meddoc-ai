"""Evaluation dataset loading and validation.

A dataset is a set of synthetic documents plus a list of scenarios. Each
scenario records the expected source document, a small list of terms that
must appear in a correct answer, and the expected human-review routing.
Loading is strict so a bad scenario can never silently pollute a run.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class Scenario(BaseModel):
    """One question to ask the system, plus the expected behaviour."""

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    document: str | None = None
    expected_terms: list[str] = Field(default_factory=list)
    expect_review: bool = False
    expect_sources: bool = True
    note: str | None = None


class ScenarioSet(BaseModel):
    """A named collection of evaluation scenarios."""

    description: str = ""
    scenarios: list[Scenario] = Field(min_length=1)


def load_scenarios(path: Path | str) -> ScenarioSet:
    """Read and parse a scenarios.json file."""
    return ScenarioSet.model_validate_json(Path(path).read_text(encoding="utf-8"))


def validate_dataset(docs_dir: Path | str, scenario_set: ScenarioSet) -> list[str]:
    """Return a list of problems in a dataset (empty list means valid).

    Checks that scenario ids are unique, referenced documents exist, and
    the expectations are internally consistent.
    """
    problems: list[str] = []
    docs = Path(docs_dir)

    seen_ids: set[str] = set()
    for index, scenario in enumerate(scenario_set.scenarios):
        label = f"scenario[{index}] '{scenario.id}'"
        if scenario.id in seen_ids:
            problems.append(f"{label}: duplicate scenario id")
        seen_ids.add(scenario.id)

        if scenario.document is not None:
            if scenario.document not in {path.name for path in docs.glob("*")}:
                problems.append(f"{label}: referenced document '{scenario.document}' not found")
        elif scenario.expect_sources:
            problems.append(
                f"{label}: expect_sources is true but no document is referenced"
            )

        if scenario.expect_sources and not scenario.expected_terms:
            problems.append(
                f"{label}: expect_sources is true but expected_terms is empty"
            )
        if not scenario.expect_sources and scenario.expected_terms:
            problems.append(
                f"{label}: expect_sources is false but expected_terms is not empty"
            )

    return problems


def validate_or_raise(docs_dir: Path | str, scenario_set: ScenarioSet) -> None:
    """Like :func:`validate_dataset` but raises ``ValueError`` on problems."""
    problems = validate_dataset(docs_dir, scenario_set)
    if problems:
        raise ValueError("Invalid evaluation dataset:\n- " + "\n- ".join(problems))