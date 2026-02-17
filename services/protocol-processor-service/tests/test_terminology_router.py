"""Tests for TerminologyRouter routing logic.

Tests YAML config loading, entity type routing, Demographic skip behavior,
and unknown entity type logging. Does not test live API calls.
"""

import logging
from pathlib import Path

import pytest
import yaml

from protocol_processor.tools.terminology_router import TerminologyRouter


@pytest.fixture()
def default_router() -> TerminologyRouter:
    """TerminologyRouter using the default config/routing.yaml."""
    return TerminologyRouter()


@pytest.fixture()
def custom_config_path(tmp_path: Path) -> Path:
    """Write a minimal routing.yaml to a temp path."""
    config = {
        "routing_rules": {
            "TestEntity": ["api_a", "api_b"],
            "SkipEntity": {"skip": True},
        },
        "api_configs": {
            "api_a": {"source": "tooluniverse", "tool_name": "api_a_search"},
            "api_b": {"source": "tooluniverse", "tool_name": "api_b_search"},
        },
    }
    config_path = tmp_path / "routing.yaml"
    config_path.write_text(yaml.dump(config))
    return config_path


class TestYamlConfigLoading:
    """Tests that YAML config loads correctly."""

    def test_default_config_loads(self, default_router: TerminologyRouter) -> None:
        """Default routing.yaml must be loadable and non-empty."""
        assert default_router.config is not None
        assert "routing_rules" in default_router.config
        assert "api_configs" in default_router.config

    def test_custom_config_path_works(self, custom_config_path: Path) -> None:
        """Custom config path must be accepted and loaded."""
        router = TerminologyRouter(config_path=custom_config_path)
        assert "routing_rules" in router.config
        assert "TestEntity" in router.config["routing_rules"]

    def test_all_entity_types_present_in_default_config(
        self, default_router: TerminologyRouter
    ) -> None:
        """Default config must include all roadmap entity types."""
        expected_types = {
            "Medication",
            "Condition",
            "Lab_Value",
            "Biomarker",
            "Procedure",
            "Phenotype",
            "Demographic",
        }
        routing_rules = default_router.config["routing_rules"]
        actual_types = set(routing_rules.keys())
        assert expected_types.issubset(actual_types), (
            f"Missing entity types in routing.yaml: {expected_types - actual_types}"
        )


class TestGetApisForEntity:
    """Tests for TerminologyRouter.get_apis_for_entity()."""

    def test_medication_returns_rxnorm_and_umls(
        self, default_router: TerminologyRouter
    ) -> None:
        """Medication must route to rxnorm and umls."""
        apis = default_router.get_apis_for_entity("Medication")
        assert apis == ["rxnorm", "umls"]

    def test_condition_returns_icd10_snomed_umls(
        self, default_router: TerminologyRouter
    ) -> None:
        """Condition must route to icd10, snomed, and umls."""
        apis = default_router.get_apis_for_entity("Condition")
        assert apis == ["icd10", "snomed", "umls"]

    def test_lab_value_returns_loinc_and_umls(
        self, default_router: TerminologyRouter
    ) -> None:
        """Lab_Value must route to loinc and umls."""
        apis = default_router.get_apis_for_entity("Lab_Value")
        assert apis == ["loinc", "umls"]

    def test_demographic_returns_empty_list(
        self, default_router: TerminologyRouter
    ) -> None:
        """Demographic must return empty list (explicitly skipped)."""
        apis = default_router.get_apis_for_entity("Demographic")
        assert apis == []

    def test_demographic_skip_is_logged_at_info(
        self,
        default_router: TerminologyRouter,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Demographic skip must be logged at INFO level (explicit, not silent)."""
        with caplog.at_level(logging.INFO, logger="protocol_processor"):
            default_router.get_apis_for_entity("Demographic")
        assert any("Demographic" in record.message for record in caplog.records)
        assert any(
            record.levelno == logging.INFO
            for record in caplog.records
            if "Demographic" in record.message
        )

    def test_unknown_entity_type_returns_empty_list(
        self, default_router: TerminologyRouter
    ) -> None:
        """Unknown entity types must return empty list, not raise."""
        apis = default_router.get_apis_for_entity("UnknownType")
        assert apis == []

    def test_unknown_entity_type_logs_warning(
        self,
        default_router: TerminologyRouter,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown entity types must be logged at WARNING level (not silent)."""
        with caplog.at_level(logging.WARNING, logger="protocol_processor"):
            default_router.get_apis_for_entity("UnknownType")
        assert any("UnknownType" in record.message for record in caplog.records)
        assert any(
            record.levelno == logging.WARNING
            for record in caplog.records
            if "UnknownType" in record.message
        )

    def test_custom_config_entity_returns_correct_apis(
        self, custom_config_path: Path
    ) -> None:
        """Custom config entity type must return its configured APIs."""
        router = TerminologyRouter(config_path=custom_config_path)
        apis = router.get_apis_for_entity("TestEntity")
        assert apis == ["api_a", "api_b"]

    def test_custom_config_skip_entity_returns_empty(
        self, custom_config_path: Path
    ) -> None:
        """Custom config skip entity must return empty list."""
        router = TerminologyRouter(config_path=custom_config_path)
        apis = router.get_apis_for_entity("SkipEntity")
        assert apis == []
