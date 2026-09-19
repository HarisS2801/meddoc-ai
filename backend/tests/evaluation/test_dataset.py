"""Tests for the dataset loader/validator."""

from pathlib import Path

import pytest

from evaluation.harness.dataset import (
    Scenario,
    ScenarioSet,
    load_scenarios,
    validate_dataset,
    validate_or_raise,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "evaluation" / "dataset"
DOCS_DIR = DATASET_DIR / "documents"


class TestShippedDataset:
    def test_loads_and_validates(self):
        scenario_set = load_scenarios(DATASET_DIR / "scenarios.json")
        assert scenario_set.scenarios
        assert validate_dataset(DOCS_DIR, scenario_set) == []

    def test_referenced_documents_exist(self):
        scenario_set = load_scenarios(DATASET_DIR / "scenarios.json")
        docs = {path.name for path in DOCS_DIR.iterdir()}
        for scenario in scenario_set.scenarios:
            if scenario.document is not None:
                assert scenario.document in docs

    def test_ids_are_unique(self):
        scenario_set = load_scenarios(DATASET_DIR / "scenarios.json")
        ids = [scenario.id for scenario in scenario_set.scenarios]
        assert len(ids) == len(set(ids))


class TestValidation:
    def test_missing_document_file(self):
        scenario_set = ScenarioSet(
            scenarios=[Scenario(id="a", question="q", document="missing.txt", expected_terms=["x"])]
        )
        problems = validate_dataset(DOCS_DIR, scenario_set)
        assert any("missing.txt" in problem for problem in problems)

    def test_duplicate_ids(self):
        scenario_set = ScenarioSet(
            scenarios=[
                Scenario(id="a", question="q1", expected_terms=["x"]),
                Scenario(id="a", question="q2", expected_terms=["y"]),
            ]
        )
        problems = validate_dataset(DOCS_DIR, scenario_set)
        assert any("duplicate" in problem for problem in problems)

    def test_expect_sources_without_document(self):
        scenario_set = ScenarioSet(
            scenarios=[Scenario(id="a", question="q", expected_terms=["x"])]
        )
        problems = validate_dataset(DOCS_DIR, scenario_set)
        assert any("expect_sources is true" in problem for problem in problems)

    def test_expect_sources_without_terms(self):
        scenario_set = ScenarioSet(
            scenarios=[
                Scenario(id="a", question="q", document="notes.txt", expect_sources=True)
            ]
        )
        problems = validate_dataset(DOCS_DIR, scenario_set)
        assert any("expected_terms is empty" in problem for problem in problems)

    def test_expect_no_sources_with_terms(self):
        scenario_set = ScenarioSet(
            scenarios=[
                Scenario(
                    id="a", question="q", expected_terms=["x"], expect_sources=False
                )
            ]
        )
        problems = validate_dataset(DOCS_DIR, scenario_set)
        assert any("expected_terms is not empty" in problem for problem in problems)

    def test_validate_or_raise_raises(self):
        bad = ScenarioSet(
            scenarios=[
                Scenario(id="a", question="q1", expected_terms=["x"]),
                Scenario(id="a", question="q2", expected_terms=["y"]),
            ]
        )
        with pytest.raises(ValueError, match="duplicate"):
            validate_or_raise(DOCS_DIR, bad)