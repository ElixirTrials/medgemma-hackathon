#!/usr/bin/env python3
"""Run grounding test snippets through the live pipeline and compare to golden values.

Usage:
    set -a && source .env && set +a
    uv run python scripts/test_grounding_snippets.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load snippets
# ---------------------------------------------------------------------------

SNIPPETS_PATH = Path(__file__).parent.parent / "tests" / "e2e" / "test_snippets.json"
data = json.loads(SNIPPETS_PATH.read_text())
grounding_snippets = data["grounding_test_snippets"]


# Relation normalization (same as pipeline)
_REL_NORM = {"==": "=", "is": "=", "has": "contains", "not": "not_contains"}


def norm_rel(r: str) -> str:
    return _REL_NORM.get(r, r)


# ---------------------------------------------------------------------------
# Core grounding logic (extracted from ground_node)
# ---------------------------------------------------------------------------


async def ground_snippet(snippet: dict) -> dict:
    """Ground a single snippet through TerminologyRouter + MedGemma + OMOP."""
    from protocol_processor.nodes.ground import (
        _ground_categorical_values,
        _ground_entity_with_retry,
        _reconcile_dual_grounding,
    )
    from protocol_processor.tools.field_mapper import generate_field_mappings
    from protocol_processor.tools.omop_mapper import lookup_omop_concept
    from protocol_processor.tools.terminology_router import (
        TerminologyRouter,
        _is_likely_acronym,
    )

    router = TerminologyRouter()
    results = []

    # We don't have pre-extracted entities — we need to extract them first.
    # Use Gemini to decompose the snippet into entities, then ground each one.
    from protocol_processor.tools.entity_decomposer import (
        decompose_entities_from_criterion,
    )

    entities = await decompose_entities_from_criterion(snippet["snippet_text"], None)

    for ent in entities:
        entity_text = ent.get("text", ent.get("entity", ""))
        entity_type = ent.get("entity_type", "Condition")

        entity_dict = {
            "text": entity_text,
            "entity_type": entity_type,
            "criterion_text": snippet["snippet_text"],
        }

        try:
            acronym = _is_likely_acronym(entity_text)

            # Parallel: TerminologyRouter + OMOP
            tu_task = _ground_entity_with_retry(
                entity_dict, router, snippet["snippet_text"]
            )
            omop_task = lookup_omop_concept(
                entity_text, entity_type, is_acronym=acronym
            )
            (result, _attempts), omop_result = await asyncio.gather(tu_task, omop_task)

            result = _reconcile_dual_grounding(result, omop_result)

            # Field mappings
            field_mappings = await generate_field_mappings(
                result, snippet["snippet_text"]
            )
            if field_mappings:
                field_mappings = _ground_categorical_values(field_mappings)
            result.field_mappings = field_mappings or None

            results.append(
                {
                    "entity_name": result.preferred_term or result.entity_text,
                    "entity_text": result.entity_text,
                    "entity_type": entity_type,
                    "system": result.selected_system,
                    "code": result.selected_code,
                    "confidence": result.confidence,
                    "omop_id": result.omop_concept_id,
                    "reconciliation": result.reconciliation_status,
                    "field_mappings": result.field_mappings,
                }
            )
        except Exception as e:
            results.append(
                {
                    "entity_name": entity_text,
                    "entity_text": entity_text,
                    "entity_type": entity_type,
                    "error": str(e),
                }
            )

    return {"snippet_text": snippet["snippet_text"], "grounded_entities": results}


def _value_from_field_mapping(fm: dict) -> str | None:
    """Extract display value from a field_mapping for reporting."""
    val = fm.get("value")
    if isinstance(val, dict):
        return val.get("value") or val.get("raw")
    return str(val) if val is not None else None


async def ground_snippet_with_known_entities(snippet: dict) -> dict:
    """Ground a snippet using its pre-defined golden entities (skip extraction)."""
    from protocol_processor.nodes.ground import (
        _ground_categorical_values,
        _ground_entity_with_retry,
        _reconcile_dual_grounding,
    )
    from protocol_processor.tools.field_mapper import generate_field_mappings
    from protocol_processor.tools.omop_mapper import lookup_omop_concept
    from protocol_processor.tools.terminology_router import (
        TerminologyRouter,
        _is_likely_acronym,
    )

    router = TerminologyRouter()
    results = []

    for expected_entity in snippet["entities"]:
        entity_text = expected_entity["entity_name"]
        # Guess entity_type from context
        entity_type = (
            "Lab_Value"
            if expected_entity["relation"] in ("<", ">", "<=", ">=")
            else "Condition"
        )

        entity_dict = {
            "text": entity_text,
            "entity_type": entity_type,
            "criterion_text": snippet["snippet_text"],
        }

        try:
            acronym = _is_likely_acronym(entity_text)

            tu_task = _ground_entity_with_retry(
                entity_dict, router, snippet["snippet_text"]
            )
            omop_task = lookup_omop_concept(
                entity_text, entity_type, is_acronym=acronym
            )
            (result, _attempts), omop_result = await asyncio.gather(tu_task, omop_task)

            result = _reconcile_dual_grounding(result, omop_result)

            # Generate field_mappings for value/relation manual comparison
            field_mappings = await generate_field_mappings(
                result, snippet["snippet_text"]
            )
            if field_mappings:
                field_mappings = _ground_categorical_values(field_mappings)

            got_rel = got_val = None
            if field_mappings:
                first = field_mappings[0]
                got_rel = first.get("relation")
                got_val = _value_from_field_mapping(first)

            results.append(
                {
                    "entity_name": result.preferred_term or result.entity_text,
                    "entity_text": result.entity_text,
                    "system": result.selected_system,
                    "code": result.selected_code,
                    "confidence": result.confidence,
                    "omop_id": result.omop_concept_id,
                    "reconciliation": result.reconciliation_status,
                    "expected_code": expected_entity["code"],
                    "expected_system": expected_entity["system"],
                    "expected_relation": expected_entity.get("relation"),
                    "expected_value": expected_entity.get("value"),
                    "got_relation": got_rel,
                    "got_value": got_val,
                    "code_match": (
                        result.selected_code == expected_entity["code"]
                        if result.selected_code
                        else False
                    ),
                }
            )
        except Exception as e:
            results.append(
                {
                    "entity_name": entity_text,
                    "error": str(e),
                    "expected_code": expected_entity["code"],
                    "expected_relation": expected_entity.get("relation"),
                    "expected_value": expected_entity.get("value"),
                    "got_relation": None,
                    "got_value": None,
                    "code_match": False,
                }
            )

    return {"snippet_text": snippet["snippet_text"], "grounded_entities": results}


# ---------------------------------------------------------------------------
# Pretty-print results
# ---------------------------------------------------------------------------


def print_results(all_results: list[dict]) -> None:
    total_entities = 0
    matched = 0
    grounded = 0

    for i, res in enumerate(all_results):
        print(f"\n{'=' * 80}")
        snippet = res["snippet_text"]
        print(f"Snippet {i + 1}: {snippet[:100]}{'...' if len(snippet) > 100 else ''}")
        print(f"{'=' * 80}")

        for ent in res["grounded_entities"]:
            total_entities += 1
            code = ent.get("code")
            expected = ent.get("expected_code", "?")
            match = ent.get("code_match", False)
            conf = ent.get("confidence", 0)
            err = ent.get("error")

            if code:
                grounded += 1
            if match:
                matched += 1

            status = "MATCH" if match else ("MISS" if code else "FAIL")
            icon = (
                "\033[32m✓\033[0m"
                if match
                else ("\033[33m≈\033[0m" if code else "\033[31m✗\033[0m")
            )

            if err:
                print(f"  {icon} [{status}] {ent['entity_name']}")
                print(f"      ERROR: {err}")
            else:
                name = ent.get("entity_name", "?")
                system = ent.get("system", "?")
                omop = ent.get("omop_id", "—")
                recon = ent.get("reconciliation", "—")
                print(f"  {icon} [{status}] {name}")
                print(
                    f"      Got:      {system}:{code}  (conf={conf:.2f}, omop={omop}, recon={recon})"
                )
                print(f"      Expected: {ent.get('expected_system', '?')}:{expected}")
                # Value/relation for manual comparison (no rigid pass/fail)
                exp_rel = ent.get("expected_relation")
                exp_val = ent.get("expected_value")
                got_rel = ent.get("got_relation")
                got_val = ent.get("got_value")
                if (
                    exp_rel is not None
                    or exp_val is not None
                    or got_rel is not None
                    or got_val is not None
                ):
                    print(
                        f"      Value:    expected relation={exp_rel!r} value={exp_val!r}  |  got relation={got_rel!r} value={got_val!r}"
                    )

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total entities:  {total_entities}")
    print(f"  Grounded:        {grounded}/{total_entities}")
    print(f"  Exact code match: {matched}/{total_entities}")
    print(
        f"  Accuracy:        {matched / total_entities * 100:.0f}%"
        if total_entities
        else "  Accuracy:        N/A"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    print("Grounding Test Snippets — Live Pipeline Evaluation")
    print(f"Running {len(grounding_snippets)} snippets with known entities...\n")

    results = []
    for i, snippet in enumerate(grounding_snippets):
        entity_count = len(snippet["entities"])
        print(
            f"[{i + 1}/{len(grounding_snippets)}] "
            f"Grounding {entity_count} entities from: "
            f"{snippet['snippet_text'][:70]}..."
        )
        result = await ground_snippet_with_known_entities(snippet)
        results.append(result)

    print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
