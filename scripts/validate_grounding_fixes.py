"""Validation script for grounding fixes.

Checks that grounding-related fixes are properly implemented across:
- Decomposition prompt (anti-decomposition rules)
- Relation validation in FieldMappingItem
- Acronym detection in terminology_router
- Multi-domain OMOP config
- Grounding system prompt (search strategy instructions)
- Grounding reasoning prompt (improved Q3)

Usage:
    uv run python scripts/validate_grounding_fixes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: add the protocol-processor-service source to sys.path so that
# `protocol_processor.*` imports work without an editable install.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PP_SRC = _REPO_ROOT / "services" / "protocol-processor-service" / "src"
if str(_PP_SRC) not in sys.path:
    sys.path.insert(0, str(_PP_SRC))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def _record(name: str, passed: bool, detail: str = "") -> None:
    marker = "[PASS]" if passed else "[FAIL]"
    line = f"{marker} {name}"
    if detail:
        line += f": {detail}"
    print(line)
    _results.append((name, passed, detail))


# ---------------------------------------------------------------------------
# Check 1: Decomposition prompt — anti-decomposition rules
# ---------------------------------------------------------------------------


def check_decomposition_prompt() -> None:
    prompt_path = (
        _REPO_ROOT
        / "services"
        / "protocol-processor-service"
        / "src"
        / "protocol_processor"
        / "prompts"
        / "entity_decompose.jinja2"
    )
    required_phrases = [
        "Do NOT separate anatomical modifiers",
        "tricompartmental knee replacement",
    ]
    try:
        content = prompt_path.read_text(encoding="utf-8")
        missing = [p for p in required_phrases if p not in content]
        if missing:
            _record(
                "decomposition_prompt",
                False,
                f"Missing phrases: {missing}",
            )
        else:
            _record("decomposition_prompt", True)
    except FileNotFoundError:
        _record("decomposition_prompt", False, f"File not found: {prompt_path}")


# ---------------------------------------------------------------------------
# Check 2: Relation validation in FieldMappingItem
# ---------------------------------------------------------------------------


def check_relation_validation() -> None:
    try:
        from pydantic import ValidationError
        from protocol_processor.tools.field_mapper import (
            FieldMappingItem,
            FieldMappingValue,
        )

        def _make_item(relation: str) -> FieldMappingItem:
            return FieldMappingItem(
                entity="TestEntity",
                relation=relation,  # type: ignore[arg-type]
                value=FieldMappingValue(
                    type="standard",
                    value="1",
                    unit="",
                    min=None,
                    max=None,
                    duration=None,
                ),
                unit=None,
                value_concept_id=None,
                value_concept_system=None,
            )

        # Valid relations that must pass directly
        valid_relations = ["=", "!=", ">", "contains"]
        for rel in valid_relations:
            try:
                item = _make_item(rel)
                if item.relation != rel:
                    _record(
                        f"relation_valid_{rel}",
                        False,
                        f"Expected '{rel}', got '{item.relation}'",
                    )
                    return
            except Exception as exc:
                _record(f"relation_valid_{rel}", False, str(exc))
                return

        # Normalized relations: LLM aliases → canonical
        normalized = {"has": "contains", "is": "=", "==": "="}
        for alias, expected in normalized.items():
            try:
                item = _make_item(alias)
                if item.relation != expected:
                    _record(
                        f"relation_normalize_{alias}",
                        False,
                        f"Expected '{expected}', got '{item.relation}'",
                    )
                    return
            except Exception as exc:
                _record(f"relation_normalize_{alias}", False, str(exc))
                return

        # Invalid relation must raise ValidationError
        raised = False
        try:
            _make_item("has_value")
        except ValidationError:
            raised = True
        except Exception as exc:
            _record(
                "relation_invalid_has_value",
                False,
                f"Expected ValidationError, got {type(exc).__name__}: {exc}",
            )
            return

        if not raised:
            _record(
                "relation_invalid_has_value",
                False,
                "Expected ValidationError for 'has_value', but none was raised",
            )
            return

        _record("relation_validation", True)

    except ImportError as exc:
        _record("relation_validation", False, f"Import error: {exc}")


# ---------------------------------------------------------------------------
# Check 3: Acronym detection in terminology_router
# ---------------------------------------------------------------------------


def check_acronym_detection() -> None:
    try:
        from protocol_processor.tools.terminology_router import _is_likely_acronym

        should_detect = ["HTN", "MI", "DM", "CKD", "COPD"]
        for term in should_detect:
            result = _is_likely_acronym(term)
            if not result:
                _record(
                    "acronym_detection",
                    False,
                    f"Expected True for '{term}', got False",
                )
                return

        should_reject = ["age", "metformin", "body mass index", "sex"]
        for term in should_reject:
            result = _is_likely_acronym(term)
            if result:
                _record(
                    "acronym_detection",
                    False,
                    f"Expected False for '{term}', got True",
                )
                return

        _record("acronym_detection", True)

    except ImportError as exc:
        _record("acronym_detection", False, f"Import error: {exc}")


# ---------------------------------------------------------------------------
# Check 4: Multi-domain OMOP config
# ---------------------------------------------------------------------------


def check_multi_domain_omop_config() -> None:
    try:
        from protocol_processor.tools.omop_mapper import ENTITY_TYPE_TO_OMOP_DOMAINS

        expected: dict[str, list[str]] = {
            "Condition": ["Condition", "Observation"],
            "Lab_Value": ["Measurement", "Observation"],
            "Procedure": ["Procedure", "Observation"],
        }
        for entity_type, domains in expected.items():
            actual = ENTITY_TYPE_TO_OMOP_DOMAINS.get(entity_type)
            if actual != domains:
                _record(
                    "omop_multi_domain_config",
                    False,
                    f"'{entity_type}': expected {domains}, got {actual}",
                )
                return

        _record("omop_multi_domain_config", True)

    except ImportError as exc:
        _record("omop_multi_domain_config", False, f"Import error: {exc}")


# ---------------------------------------------------------------------------
# Check 5: Grounding system prompt — search strategy instructions
# ---------------------------------------------------------------------------


def check_grounding_system_prompt() -> None:
    prompt_path = (
        _REPO_ROOT
        / "services"
        / "protocol-processor-service"
        / "src"
        / "protocol_processor"
        / "prompts"
        / "grounding_system.jinja2"
    )
    required_phrases = ["DO NOT retry the exact same phrase"]
    try:
        content = prompt_path.read_text(encoding="utf-8")
        missing = [p for p in required_phrases if p not in content]
        if missing:
            _record(
                "grounding_system_prompt",
                False,
                f"Missing phrases: {missing}",
            )
        else:
            _record("grounding_system_prompt", True)
    except FileNotFoundError:
        _record("grounding_system_prompt", False, f"File not found: {prompt_path}")


# ---------------------------------------------------------------------------
# Check 6: Grounding reasoning prompt — improved Q3
# ---------------------------------------------------------------------------


def check_grounding_reasoning_prompt() -> None:
    prompt_path = (
        _REPO_ROOT
        / "services"
        / "protocol-processor-service"
        / "src"
        / "protocol_processor"
        / "prompts"
        / "grounding_reasoning.jinja2"
    )
    required_phrases = ["SUBSTANTIALLY DIFFERENT, SIMPLER query"]
    try:
        content = prompt_path.read_text(encoding="utf-8")
        missing = [p for p in required_phrases if p not in content]
        if missing:
            _record(
                "grounding_reasoning_prompt",
                False,
                f"Missing phrases: {missing}",
            )
        else:
            _record("grounding_reasoning_prompt", True)
    except FileNotFoundError:
        _record("grounding_reasoning_prompt", False, f"File not found: {prompt_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Grounding Fixes Validation ===\n")

    check_decomposition_prompt()
    check_relation_validation()
    check_acronym_detection()
    check_multi_domain_omop_config()
    check_grounding_system_prompt()
    check_grounding_reasoning_prompt()

    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print(f"\n=== Summary: {passed}/{total} passed, {failed} failed ===")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
