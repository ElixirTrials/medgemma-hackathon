#!/usr/bin/env python3
"""Run FULL grounding pipeline against test_snippets.json golden entities.

Exercises the same code path as the production ground node:
  TerminologyRouter → MedGemma selection → OMOP dual grounding →
  Field mapping generation → Unit normalization

Usage:
    set -a && source .env && set +a && uv run python tests/e2e/run_grounding_snippets.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "services"
        / "protocol-processor-service"
        / "src"
    ),
)
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "services" / "api-service" / "src")
)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "libs" / "shared" / "src"))

from protocol_processor.nodes.ground import _ground_entity_parallel, _get_router
from protocol_processor.tools.unit_normalizer import normalize_unit

SNIPPETS_PATH = Path(__file__).parent / "test_snippets.json"


async def main() -> None:
    data = json.loads(SNIPPETS_PATH.read_text())
    grounding_snippets = data["grounding_test_snippets"]

    router = _get_router()
    semaphore = asyncio.Semaphore(4)

    total_entities = 0
    exact_code_match = 0
    grounded_ok = 0
    unit_ucum_match = 0
    unit_omop_match = 0
    total_units = 0
    field_mapping_count = 0
    results: list[dict] = []

    for snippet_idx, snippet in enumerate(grounding_snippets):
        snippet_text = snippet["snippet_text"]
        print(f"\n{'─' * 70}")
        print(f"Snippet {snippet_idx}: {snippet_text[:80]}...")
        print(f"{'─' * 70}")

        for ent_idx, golden in enumerate(snippet["entities"]):
            total_entities += 1
            entity_name = golden["entity_name"]
            expected_code = golden["code"]
            expected_system = golden["system"]
            expected_unit = golden.get("unit")
            expected_ucum = golden.get("unit_ucum")
            expected_omop_cid = golden.get("unit_omop_concept_id")
            expected_relation = golden.get("relation")
            golden.get("value")

            # Build entity dict matching what parse_node produces
            entity = {
                "text": entity_name,
                "entity_type": "Condition",  # generic — router handles dispatch
                "criterion_text": snippet_text,
                "criteria_type": "inclusion",
            }

            # Run the FULL grounding pipeline
            result, error, elapsed_ms, retries = await _ground_entity_parallel(
                entity,
                router,
                snippet_text,
                entity_num=ent_idx + 1,
                total=len(snippet["entities"]),
                semaphore=semaphore,
            )

            if error:
                print(f"\n  ENTITY: {entity_name}")
                print(f"    ERROR: {error}")
                results.append(
                    {"entity": entity_name, "grounded": False, "code_match": False}
                )
                continue

            if result is None:
                print(f"\n  ENTITY: {entity_name}")
                print("    ERROR: no result and no error (unexpected)")
                results.append(
                    {"entity": entity_name, "grounded": False, "code_match": False}
                )
                continue

            grounded_ok += 1
            code_match = result.selected_code == expected_code
            if code_match:
                exact_code_match += 1

            # Check field mappings (narrow type for mypy)
            field_mappings = result.field_mappings or []
            has_mappings = bool(field_mappings)
            if has_mappings:
                field_mapping_count += 1

            # Print entity result
            status_icon = "OK" if code_match else "MISMATCH"
            print(f"\n  ENTITY: {entity_name}")
            print(
                f"    Code [{status_icon}]: expected={expected_system}:{expected_code}"
                f"  got={result.selected_system}:{result.selected_code}"
            )
            print(f"    Preferred term: {result.preferred_term}")
            print(
                f"    Confidence: {result.confidence:.2f}  |  OMOP: {result.omop_concept_id}"
                f"  |  Retries: {retries}  |  Time: {elapsed_ms:.0f}ms"
            )
            if result.reasoning:
                # Truncate long reasoning
                reasoning_short = result.reasoning[:120] + (
                    "..." if len(result.reasoning) > 120 else ""
                )
                print(f"    Reasoning: {reasoning_short}")

            # Field mappings
            if has_mappings:
                print(f"    Field mappings ({len(field_mappings)}):")
                for fm in field_mappings:
                    rel = fm.get("relation", "?")
                    val = fm.get("value", {})
                    val_str = val.get("value", val.get("min", "?"))
                    unit = val.get("unit", "")
                    print(
                        f"      {fm.get('entity', '?')} {rel} {val_str} {unit}".rstrip()
                    )
            else:
                print("    Field mappings: NONE")

            # Check relation and value if golden has them
            if expected_relation and has_mappings:
                got_relation = (
                    field_mappings[0].get("relation") if field_mappings else None
                )
                rel_match = got_relation == expected_relation
                print(
                    f"    Relation: expected={expected_relation}  got={got_relation}"
                    f"  {'OK' if rel_match else 'MISMATCH'}"
                )

            # Unit normalization
            if expected_unit is not None:
                total_units += 1
                got_ucum, got_omop = normalize_unit(expected_unit)
                ucum_ok = got_ucum == expected_ucum
                omop_ok = got_omop == expected_omop_cid
                if ucum_ok:
                    unit_ucum_match += 1
                if omop_ok:
                    unit_omop_match += 1
                unit_status = "OK" if (ucum_ok and omop_ok) else "MISMATCH"
                print(
                    f"    Unit [{unit_status}]: '{expected_unit}' -> UCUM={got_ucum} OMOP={got_omop}"
                )

            results.append(
                {
                    "entity": entity_name,
                    "grounded": True,
                    "code_match": code_match,
                    "has_mappings": has_mappings,
                }
            )

    # ═══════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'═' * 70}")
    print("FULL PIPELINE RESULTS")
    print(f"{'═' * 70}")
    print(f"  Entities:            {total_entities}")
    print(
        f"  Grounded:            {grounded_ok}/{total_entities}"
        f" ({100 * grounded_ok // max(total_entities, 1)}%)"
    )
    print(
        f"  Exact code match:    {exact_code_match}/{total_entities}"
        f" ({100 * exact_code_match // max(total_entities, 1)}%)"
    )
    print(
        f"  With field mappings: {field_mapping_count}/{total_entities}"
        f" ({100 * field_mapping_count // max(total_entities, 1)}%)"
    )
    print(
        f"  Unit UCUM match:     {unit_ucum_match}/{total_units}"
        f" ({100 * unit_ucum_match // max(total_units, 1)}%)"
    )
    print(
        f"  Unit OMOP match:     {unit_omop_match}/{total_units}"
        f" ({100 * unit_omop_match // max(total_units, 1)}%)"
    )
    print(f"{'═' * 70}")

    # Failures summary
    failures = [r for r in results if not r.get("code_match")]
    if failures:
        print("\nCode match failures:")
        for f in failures:
            status = "ERROR" if not f["grounded"] else "MISMATCH"
            print(f"  [{status}] {f['entity']}")

    no_mappings = [
        r for r in results if r.get("grounded") and not r.get("has_mappings")
    ]
    if no_mappings:
        print("\nMissing field mappings:")
        for f in no_mappings:
            print(f"  {f['entity']}")


if __name__ == "__main__":
    asyncio.run(main())
